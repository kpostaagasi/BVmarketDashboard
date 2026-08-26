import type { Series } from "../types";

const ENDPOINT =
  "https://query1.finance.yahoo.com/v8/finance/chart/USDTRY=X?range=2y&interval=1d";

const STOOQ_URL = "https://stooq.com/q/d/l/?s=usdtry&i=d";

// Yahoo, tarayıcı UA'larını 429 ile reddediyor; Googlebot UA kabul ediliyor.
const USER_AGENT =
  "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)";

function isoDate(timestampSeconds: number): string {
  return new Date(timestampSeconds * 1000).toISOString().slice(0, 10);
}

async function fetchYahoo(): Promise<Series> {
  const res = await fetch(ENDPOINT, {
    headers: { "User-Agent": USER_AGENT, Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`Yahoo HTTP ${res.status}`);
  }
  const json = (await res.json()) as {
    chart?: {
      result?: Array<{
        timestamp?: number[];
        indicators?: {
          quote?: Array<{ close?: (number | null)[] }>;
        };
      }>;
      error?: unknown;
    };
  };
  const result = json.chart?.result?.[0];
  const timestamps = result?.timestamp;
  const closes = result?.indicators?.quote?.[0]?.close;
  if (!timestamps || !closes) throw new Error("Yahoo yanıtı beklenen formatta değil");

  const points = timestamps
    // Unix timestamp (saniye) -> ISO takvim tarihi (UTC).
    .map((ts, i) => ({ date: new Date(ts * 1000).toISOString().slice(0, 10), value: closes[i] }))
    .filter((p): p is { date: string; value: number } => p.value !== null)
    .filter((p, i, arr) => i === 0 || p.date !== arr[i - 1].date);

  if (points.length === 0) {
    throw new Error("Yahoo yanıtı hiç geçerli nokta içermedi");
  }

  return {
    id: "yahoo/usdtry",
    title: "ABD Doları / Türk Lirası",
    source: { name: "Yahoo Finance", url: "https://finance.yahoo.com/quote/USDTRY=X" },
    unit: "TL",
    freq: "daily",
    updated: points[points.length - 1].date,
    points,
  };
}

async function fetchStooq(): Promise<Series> {
  const res = await fetch(STOOQ_URL, { headers: { "User-Agent": USER_AGENT } });
  if (!res.ok) {
    throw new Error(`Stooq HTTP ${res.status}`);
  }
  const csv = await res.text();
  const lines = csv.trim().split("\n");
  if (lines.length < 2 || !lines[0].startsWith("Date,Close")) {
    throw new Error("Stooq CSV beklenen formatta değil");
  }

  const points = lines
    .slice(1)
    .map((line) => {
      const [date, close] = line.split(",");
      return { date, value: Number(close) };
    })
    .filter((p) => p.date && Number.isFinite(p.value));

  if (points.length === 0) {
    throw new Error("Stooq CSV hiç geçerli nokta içermedi");
  }

  return {
    id: "yahoo/usdtry",
    title: "ABD Doları / Türk Lirası",
    source: { name: "Yahoo Finance", url: "https://finance.yahoo.com/quote/USDTRY=X" },
    unit: "TL",
    freq: "daily",
    updated: points[points.length - 1].date,
    points,
  };
}

export async function ingest(): Promise<Series[]> {
  try {
    return [await fetchYahoo()];
  } catch (yahooError) {
    try {
      const series = await fetchStooq();
      console.error("[warn] yahoo başarısız, stooq fallback kullanıldı:", (yahooError as Error).message);
      return [series];
    } catch (stooqError) {
      throw new Error(
        `Yahoo: ${(yahooError as Error).message} | Stooq fallback: ${(stooqError as Error).message}`,
      );
    }
  }
}
