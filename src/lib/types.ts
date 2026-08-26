export type Frequency = "daily" | "weekly" | "monthly" | "quarterly" | "yearly";

export interface SourceMeta {
  name: string; // örn "Yahoo Finance"
  url: string; // kaynağın sayfası
}

export interface SeriesPoint {
  date: string; // ISO tarih "YYYY-MM-DD"
  value: number;
}

export interface Series {
  id: string; // "<kaynak>/<seri-adı>" örn "yahoo/usdtry"
  title: string;
  source: SourceMeta;
  unit: string;
  freq: Frequency;
  updated: string; // ISO tarih
  points: SeriesPoint[]; // artan tarih sırası
}
