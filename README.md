# BV Market Dashboard

Türkiye ekonomisi için veri ve grafikler — BV Portföy iç kullanımı.
Resmi kaynaklardan otomatik veri çekme, normalize etme, hazır
istatistikli grafik sayfaları olarak sunma.

## Mimari

```
app.py                    # st.navigation — sol menü katalogdan üretilir
catalog/series.yaml       # tek doğruluk kaynağı: 69 seri tanımı
catalog/categories.yaml   # menü ağacı: 11 kategori + her birinin KPI panosu
core/                     # catalog, data, stats, charts, components, page, takvim
ingest/                   # evds.py + yahoo.py + epias.py + osd.py + run.py (orchestrator)
data/<kategori>/<seri>.csv
.github/workflows/ingest.yml    # günlük cron: ingest → commit → push
.github/workflows/test.yml      # her push/PR: pytest
```

Veri repoda yaşar; uygulama yalnızca okur ve **runtime'da hiç secret
kullanmaz**. `EVDS_API_KEY` sadece GitHub Actions ortamında geçer.

## Komutlar

```bash
pip install -r requirements-dev.txt
streamlit run app.py                       # geliştirme sunucusu
EVDS_API_KEY=<key> python -m ingest.run    # veriyi tazele
pytest                                     # test paketi
```

Tek bir seriyi hata ayıklamak için: `python -m ingest.run --only enflasyon/tufe-genel`

## Yeni seri ekleme

`catalog/series.yaml`'a bir kayıt ekleyin; kod değişikliği gerekmez:

```yaml
- id: <kategori>/<ad>
  title: Görünen Ad
  category: <kategori>          # categories.yaml'da tanımlı olmalı
  kaynak: { name: TCMB EVDS, url: "https://evds3.tcmb.gov.tr" }
  kaynak_tipi: evds              # evds | yahoo | epias | osd (zorunlu alan)
  unit: "Birim"
  freq: monthly                 # daily | weekly | monthly
  evds_code: TP.XXX.YYY
  evds_frequency: "5"           # 1=günlük, 2=haftalık, 5=aylık
  monthly_agg: mean             # mean | last | sum (günlük/haftalık için)
  olcek: 0.001                  # isteğe bağlı: ham değeri çarpar (Bin TL → Milyon TL)
  charts: [seasonality, level]
```

Yahoo Finance serisi için `kaynak_tipi: yahoo` ve `evds_code`/`evds_frequency`
yerine `yahoo_symbol: "BZ=F"`; EPİAŞ için `epias_ucu`/`epias_alani`; OSD için
`osd_firma` kullanın. Hangi kaynak tipinin hangi alanı taşıyabileceği
`core/catalog.py::KAYNAK_ALANLARI` tablosunda; `olcek` her tip için geçerli
ortak alandır ve `ingest/run.py::olcekle` tarafından tek noktadan uygulanır.

Sonra `python -m ingest.run --only <yeni-id>` ile veriyi üretin.

## Deploy

Streamlit Community Cloud, private repo. Erişim viewer allowlist'i ile
BV Portföy e-postalarına kısıtlıdır.

Uygulama hareketsizlik sonrası uykuya dalar; günün ilk kullanıcısı
~30 saniye soğuk başlangıç bekler.

## Ön koşul

[TCMB EVDS](https://evds2.tcmb.gov.tr)'ten ücretsiz API key alıp GitHub
repo secret'ına `EVDS_API_KEY` olarak ekleyin.

## Yol haritası

| Faz | İçerik | Durum |
|---|---|---|
| 1 | Streamlit iskeleti + EVDS dilimi (13 seri, 4 kategori) | ✅ |
| 2 | Emtia (10 seri, 2 kategori): Brent, WTI, doğalgaz, altın, gümüş, bakır, HRC çelik, platin, paladyum, alüminyum | ✅ |
| 3 | Veri Takvimi (3a), Elektrik/EPİAŞ (3b), üretim kompozisyonu (3c), OSD otomotiv (3e), EVDS genişletme (3f) | ✅ |
| 4 | Hisse sayfaları | Planlandı |
| 5 | Arama, favoriler, AI raporları | Planlandı |

Tasarım detayları: `docs/superpowers/specs/2026-08-27-streamlit-dashboard-design.md`
