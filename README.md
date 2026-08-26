# BV Market Dashboard

Türkiye ekonomisi ve BIST için veri ve grafikler: resmi/açık kaynaklardan otomatik veri çekme, normalize etme ve statik grafik sayfaları olarak sunma.

## Mimari

```
scripts/ingest/            # kaynak başına bir TS modülü
  sources/yahoo.ts         #   Yahoo Finance (emtia + döviz)
  run.ts                   #   orchestrator: modülleri koşturur, hataları izole eder
data/
  <kategori>/<seri>.json   # normalize edilmiş seriler (repoda tutulur)
src/app/                   # Next.js App Router (build'de data/*.json'dan render)
.github/workflows/update.yml  # günlük cron: ingest → commit → push
```

Site tamamen statiktir; veri tazeliği GitHub Actions'ın günlük commit'iyle gelir. Her grafiğin altında kaynağı ve son güncelleme tarihi gösterilir.

Tasarım detayları: `docs/superpowers/specs/2026-08-26-bvmarketdashboard-design.md`

## Komutlar

```bash
npm run dev      # geliştirme sunucusu
npm run build    # prod build (statik)
npm run ingest   # veri çekme: data/ altına yazar
```

## Veri sözleşmesi

Her ingest modülü `ingest(): Promise<Series[]>` döner; seriler `data/<kategori>/<ad>.json` olarak yazılır (kategori = id'nin ilk segmenti). Şema `src/lib/types.ts`'te tanımlı.

## Yol haritası

| Faz | İçerik | Durum |
|---|---|---|
| 0 | İskelet + ilk gerçek seri (USD/TRY) | ✅ |
| 1 | Makro paketi (~15 seri): TÜFE, kur, faiz, konut, tüketici güveni… (TCMB EVDS) | Sırada |
| 2 | Emtia (~12 seri): Brent, altın, bakır… | Planlandı |
| 3 | 9 sektör sayfası (BDDK, OSD, TSB, TEİAŞ…) | Planlandı |
| 4 | Hisse sayfaları (~23) | Planlandı |
| 5 | AI Raporları + arama/indeks | Planlandı |

## Ön koşullar

**Faz 1 için:** [TCMB EVDS](https://evds2.tcmb.gov.tr)'ten ücretsiz API key alıp GitHub repo secret'ına `EVDS_API_KEY` olarak ekleyin.
