# BV Market Dashboard

Türkiye ekonomisi için veri ve grafikler — BV Portföy iç kullanımı.
Resmi kaynaklardan otomatik veri çekme, normalize etme, hazır
istatistikli grafik sayfaları olarak sunma.

## Mimari

```
app.py                    # st.navigation — sol menü katalogdan üretilir
catalog/series.yaml       # tek doğruluk kaynağı: 111 seri tanımı
catalog/categories.yaml   # menü ağacı: 15 kategori + her birinin KPI panosu
catalog/hisseler.yaml     # 8 BIST tickerı: kendi verisi + bağlam serileri
core/                     # catalog, data, stats, charts, components, page, takvim
ingest/                   # evds.py + yahoo.py + epias.py + osd.py + tim.py + bddk.py + tefas.py + eurocontrol.py + run.py (orchestrator)
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
  kaynak_tipi: evds              # evds | yahoo | epias | osd | tim | bddk | tefas | eurocontrol (zorunlu alan)
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
`osd_firma`; TİM için `tim_sektor` (gerekirse `tim_eski_adlar`); BDDK için
`bddk_kalem` (gerekirse `bddk_taraf`, `bddk_kumulatif`); TEFAS için
`tefas_tip` + `tefas_olcut`; EUROCONTROL için `ec_kaynak` + `ec_varlik`
kullanın.
Hangi kaynak tipinin hangi alanı taşıyabileceği
`core/catalog.py::KAYNAK_ALANLARI` tablosunda; `olcek` ve `gecikme_gunu` her
tip için geçerli ortak alanlardır (`ingest/run.py::olcekle` ölçeği tek
noktadan uygular, `core/takvim.py` gecikmeyi tazelik eşiğine ekler).

Sonra `python -m ingest.run --only <yeni-id>` ile veriyi üretin.

## Yeni hisse sayfası ekleme

`catalog/hisseler.yaml`'a bir kayıt ekleyin; kod değişikliği gerekmez:

```yaml
- kod: FROTO                    # BIST kodu, 4–6 büyük harf
  title: Ford Otosan
  sektor: Otomotiv
  kendi: [otomotiv/ford-otosan]          # şirketin kendi verisi (zorunlu)
  baglam: [ihracat/otomotiv, ekonomi-makro/usd-try]   # sektör/girdi vekilleri
  note: >-
    Sayfada gösterilen açıklama.
```

`kendi` ve `baglam` sayfada ayrı başlıklar altında çizilir: KPI satırı
yalnızca `kendi`den beslenir. Aynı seri iki listede olamaz ve bilinmeyen
seri id'si `KatalogHatasi` verir.

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
| 3 | Veri Takvimi (3a), Elektrik/EPİAŞ (3b), üretim kompozisyonu (3c), OSD otomotiv (3e), EVDS genişletme (3f), TİM sektörel ihracat (3g), BDDK bankacılık (3h), TEFAS fonlar (3i), EUROCONTROL havacılık (3j) | ✅ |
| 4 | Hisse sayfaları (8 ticker: FROTO, TOASO, TTRAK, KARSN, OTKAR, ASUZU, THYAO, PGSUS) | ✅ |
| 5 | Arama, favoriler, AI raporları | Planlandı |

Tasarım detayları: `docs/superpowers/specs/2026-08-27-streamlit-dashboard-design.md`
