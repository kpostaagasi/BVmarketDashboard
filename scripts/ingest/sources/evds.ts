import type { Frequency, Series, SeriesPoint, SourceMeta } from "../types";

const ENDPOINT = "https://evds3.tcmb.gov.tr/igmevdsms-dis/fe";

const SOURCE: SourceMeta = { name: "TCMB EVDS", url: "https://evds3.tcmb.gov.tr" };

// EVDS3 /fe frekans kodları: 1=günlük, 5=aylık, 2=haftalık.
type EvdsFrequency = "1" | "5" | "2";

interface SeriesConfig {
  id: string; // "<kategori>/<dosya-adı>"
  title: string;
  unit: string;
  freq: Frequency;
  evdsCode: string;
  evdsFrequency: EvdsFrequency;
}

// Kodlar 2026-08-26'da `categories/withDatagroups` + `serieList` taramasıyla
// doğrulanmış gerçek EVDS3 seri kodlarıdır (task-1-context.md'deki tablo tahminidir,
// bir kısmı hatalıydı — bkz. task-1-report.md "Step 1" bölümü).
const SERIES_CONFIG: SeriesConfig[] = [
  {
    id: "tufe/genel",
    title: "TÜFE Genel Endeks",
    unit: "Endeks (2025=100)",
    freq: "monthly",
    evdsCode: "TP.TUKFIY2025.GENEL",
    evdsFrequency: "5",
  },
  {
    id: "tufe/gida",
    title: "TÜFE Gıda ve Alkolsüz İçecekler",
    unit: "Endeks (2025=100)",
    freq: "monthly",
    evdsCode: "TP.TUKFIY2025.01",
    evdsFrequency: "5",
  },
  {
    id: "kur/usd-resmi",
    title: "USD/TRY (TCMB Alış)",
    unit: "TL",
    freq: "daily",
    evdsCode: "TP.DK.USD.A.YTL",
    evdsFrequency: "1",
  },
  {
    id: "kur/eur-resmi",
    title: "EUR/TRY (TCMB Alış)",
    unit: "TL",
    freq: "daily",
    evdsCode: "TP.DK.EUR.A.YTL",
    evdsFrequency: "1",
  },
  {
    id: "faiz/politika",
    title: "TCMB Ağırlıklı Ortalama Fonlama Maliyeti",
    unit: "%",
    freq: "daily",
    evdsCode: "TP.APIFON4",
    evdsFrequency: "1",
  },
  {
    id: "faiz/mevduat-tl",
    title: "TL Mevduat Faizi (3 Aya Kadar, Stok)",
    unit: "%",
    freq: "monthly",
    evdsCode: "TP.MT210AGS.TRY.MT02",
    evdsFrequency: "5",
  },
  {
    id: "konut/fiyat-endeksi",
    title: "Konut Fiyat Endeksi (Türkiye)",
    unit: "Endeks (2010=100)",
    freq: "monthly",
    evdsCode: "TP.KFE.TR",
    evdsFrequency: "5",
  },
  {
    id: "konut/satis-toplam",
    title: "Toplam Konut Satışları",
    unit: "Adet",
    freq: "monthly",
    evdsCode: "TP.AKONUTSAT1.KTRTOPLAM",
    evdsFrequency: "5",
  },
  {
    id: "konut/satis-ipotekli",
    title: "İpotekli Konut Satışları",
    unit: "Adet",
    freq: "monthly",
    evdsCode: "TP.AKONUTSAT2.KTRTOPLAM",
    evdsFrequency: "5",
  },
  {
    id: "tuketici/guven-endeksi",
    title: "Tüketici Güven Endeksi",
    unit: "Endeks",
    freq: "monthly",
    evdsCode: "TP.TG2.Y01",
    evdsFrequency: "5",
  },
  {
    id: "tuketici/kredikarti-harcama",
    title: "Kredi Kartı Harcamaları (Toplam)",
    unit: "Bin TL",
    freq: "weekly",
    evdsCode: "TP.KKHARTUT.KT1",
    evdsFrequency: "2",
  },
  {
    id: "portfoy/yabanci-hisse",
    title: "Yabancı Yatırımcı Hisse Senedi Net Alım-Satım",
    unit: "Milyon USD",
    freq: "weekly",
    evdsCode: "TP.MKNETHAR.M7",
    evdsFrequency: "2",
  },
  {
    id: "portfoy/yabanci-dibs",
    title: "Yabancı Yatırımcı DİBS Net Alım-Satım",
    unit: "Milyon USD",
    freq: "weekly",
    evdsCode: "TP.MKNETHAR.M8",
    evdsFrequency: "2",
  },
];

const TWO_YEARS_MS = 2 * 365 * 24 * 60 * 60 * 1000;

function formatEvdsDate(d: Date): string {
  const dd = String(d.getUTCDate()).padStart(2, "0");
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  const yyyy = d.getUTCFullYear();
  return `${dd}-${mm}-${yyyy}`;
}

// EVDS "Tarih" alanı frekansa göre iki farklı biçimde döner: günlük/haftalık
// "DD-MM-YYYY" (Türkçe gün/ay/yıl sırası, dokümante edilmiş sözleşmeye uygun),
// aylık ise dokümantasyonun aksine "YYYY-MM" (gün bilgisi yok — ayın ilk günü
// ISO tarihi olarak kullanılır). İkisi de desteklenmezse null döner.
function parseEvdsDate(tarih: string): string | null {
  const monthly = /^(\d{4})-(\d{2})$/.exec(tarih);
  if (monthly) {
    const [, yil, ay] = monthly;
    return `${yil}-${ay}-01`;
  }
  const daily = /^(\d{2})-(\d{2})-(\d{4})$/.exec(tarih);
  if (daily) {
    const [, gun, ay, yil] = daily;
    return `${yil}-${ay}-${gun}`;
  }
  return null;
}

async function fetchEvdsSeries(
  code: string,
  frequency: EvdsFrequency,
  startDate: string,
  endDate: string,
): Promise<SeriesPoint[]> {
  const res = await fetch(ENDPOINT, {
    method: "POST",
    headers: {
      key: process.env.EVDS_API_KEY ?? "",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      type: "json",
      series: `-${code}`,
      aggregationTypes: "-avg",
      formulas: "-0",
      startDate,
      endDate,
      frequency,
      decimalSeperator: ".",
      decimal: "5",
      dateFormat: "0",
      lang: "TR",
      yon: "1",
      sira: "1",
      ozelFormuller: [],
      groupSeperator: true,
      isRaporSayfasi: false,
    }),
  });
  if (!res.ok) throw new Error(`EVDS HTTP ${res.status} (${code})`);

  const json = (await res.json()) as { items?: Record<string, string | null>[] };
  const field = code.replace(/\./g, "_");

  const points = (json.items ?? [])
    .map((item): SeriesPoint | null => {
      const date = parseEvdsDate(String(item.Tarih));
      const raw = item[field];
      if (date === null || raw === null || raw === undefined) return null;
      // groupSeperator:true isteniyor -> değerler "139,411.00000" gibi binlik
      // ayraçlı virgül içerebilir; Number() öncesi temizlenmesi gerekir.
      const value = Number(String(raw).replace(/,/g, ""));
      if (!Number.isFinite(value)) return null;
      return { date, value };
    })
    .filter((p): p is SeriesPoint => p !== null)
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));

  return points;
}

export async function ingest(): Promise<Series[]> {
  if (!process.env.EVDS_API_KEY) {
    throw new Error("EVDS_API_KEY tanımlı değil");
  }

  const now = new Date();
  const start = new Date(now.getTime() - TWO_YEARS_MS);
  const startDate = formatEvdsDate(start);
  const endDate = formatEvdsDate(now);

  const results = await Promise.allSettled(
    SERIES_CONFIG.map(async (cfg): Promise<Series> => {
      const points = await fetchEvdsSeries(cfg.evdsCode, cfg.evdsFrequency, startDate, endDate);
      if (points.length === 0) {
        throw new Error(`${cfg.evdsCode} hiç geçerli nokta içermedi`);
      }
      return {
        id: cfg.id,
        title: cfg.title,
        source: SOURCE,
        unit: cfg.unit,
        freq: cfg.freq,
        updated: points[points.length - 1].date,
        points,
      };
    }),
  );

  const series: Series[] = [];
  results.forEach((result, i) => {
    const cfg = SERIES_CONFIG[i];
    if (result.status === "fulfilled") {
      series.push(result.value);
    } else {
      console.error(`[warn] evds ${cfg.id} (${cfg.evdsCode}) atlandı:`, (result.reason as Error).message);
    }
  });

  if (series.length === 0) {
    throw new Error("hiçbir seri üretilemedi");
  }

  return series;
}
