import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import type { Frequency, Series } from "./types";

const FREQS: Frequency[] = ["daily", "weekly", "monthly", "quarterly", "yearly"];

const DATA_DIR = path.join(process.cwd(), "data");

function fail(seriesPath: string, reason: string): never {
  throw new Error(`Seri okunamadı: data/${seriesPath}.json — ${reason}`);
}

function validateSeries(seriesPath: string, parsed: unknown): Series {
  if (typeof parsed !== "object" || parsed === null) {
    fail(seriesPath, "JSON içeriği bir nesne değil");
  }
  const s = parsed as Record<string, unknown>;

  for (const field of ["id", "title", "source", "unit", "freq", "updated", "points"]) {
    if (!(field in s)) fail(seriesPath, `"${field}" alanı eksik`);
  }
  if (typeof s.source !== "object" || s.source === null) {
    fail(seriesPath, '"source" bir nesne olmalı');
  }
  const source = s.source as Record<string, unknown>;
  if (typeof source.name !== "string" || typeof source.url !== "string") {
    fail(seriesPath, '"source.name" ve "source.url" string olmalı');
  }
  for (const field of ["id", "title", "unit", "updated"] as const) {
    if (typeof s[field] !== "string") fail(seriesPath, `"${field}" string olmalı`);
  }
  if (!FREQS.includes(s.freq as Frequency)) {
    fail(seriesPath, `"freq" geçersiz: ${String(s.freq)}`);
  }
  if (!Array.isArray(s.points) || s.points.length === 0) {
    fail(seriesPath, '"points" boş olmayan bir dizi olmalı');
  }
  const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
  for (const p of s.points as unknown[]) {
    const point = p as Record<string, unknown>;
    if (
      typeof p !== "object" ||
      p === null ||
      typeof point.date !== "string" ||
      !ISO_DATE.test(point.date) ||
      typeof point.value !== "number"
    ) {
      fail(
        seriesPath,
        'points öğeleri "{ date: "YYYY-MM-DD", value: number }" olmalı',
      );
    }
  }

  const points = s.points as { date: string; value: number }[];
  for (let i = 1; i < points.length; i++) {
    if (points[i].date <= points[i - 1].date) {
      fail(
        seriesPath,
        `points artan tarih sırasında değil (index ${i - 1}→${i}: ${points[i - 1].date} → ${points[i].date})`,
      );
    }
  }

  return {
    id: s.id as string,
    title: s.title as string,
    source: { name: source.name, url: source.url },
    unit: s.unit as string,
    freq: s.freq as Frequency,
    updated: s.updated as string,
    points,
  };
}

export async function getSeries(seriesPath: string): Promise<Series> {
  let raw: string;
  try {
    raw = await readFile(path.join(DATA_DIR, `${seriesPath}.json`), "utf8");
  } catch {
    fail(seriesPath, "dosya bulunamadı veya okunamadı");
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch (e) {
    fail(seriesPath, `JSON parse hatası: ${(e as Error).message}`);
  }
  return validateSeries(seriesPath, parsed);
}

export async function listSeries(kategori: string): Promise<string[]> {
  let entries: string[];
  try {
    entries = await readdir(path.join(DATA_DIR, kategori));
  } catch {
    return [];
  }
  return entries
    .filter((f) => f.endsWith(".json"))
    .map((f) => `${kategori}/${f.replace(/\.json$/, "")}`);
}
