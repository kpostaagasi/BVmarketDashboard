# Faz 3c — Üretim Kompozisyonu Tasarım Spec'i

Tarih: 2026-08-28
Durum: Onaylandı (kullanıcı onayı: 2026-08-28, sohbet içi, iki bölüm ayrı ayrı)

## Amaç

Elektrik üretiminin kaynak bazlı dağılımını göstermek: doğalgaz, kömür,
hidroelektrik, rüzgar, güneş ve diğerlerinin zaman içindeki payları. Referans
sitenin Elektrik sayfasındaki imza grafiği budur ve "enerji dönüşümü nereye
gidiyor?" sorusunun tek görselle cevabıdır.

Veri Faz 3b'de zaten çekiliyor: EPİAŞ `realtime-generation` ucu 16 kaynak
alanını saat saat döndürüyor, biz yalnızca `total` alanını okuyoruz.

## Bulgu: `total` saf üretim değildir

Canlı veriye karşı doğrulandı (2026-08-20, 12:00 saati):

```
16 alanın toplamı = 36.125,4 MWh
`total` alanı     = 36.125,4 MWh     fark 0,00
```

Toplam **birebir tutuyor**, ancak toplama `importExport` de dahil ve o negatif
olabiliyor (ölçülen saatte −833,9 MWh, net ihracat). Yani:

```
total = yurtiçi üretim + net ithalat
```

İki sonucu var:

1. **Yayındaki `elektrik/uretim` serisi bu tanımı taşıyor.** Değeri yanlış
   değil, adı eksik. Başlık "Toplam Elektrik Üretimi" → **"Toplam Elektrik
   Arzı (net ithalat dahil)"** olarak düzeltilir. Veri değişmez.

2. **Pay paydası `total` OLAMAZ.** Negatif bileşen yüzünden paylar %100'ü
   aşar. Ölçülen saatte güneş `total`'a göre %11,1, gerçek üretime göre %10,9.

**Karar:** Paylar yalnızca üretim kaynaklarının toplamına bölünür;
`importExport` paydadan ve gruplardan dışlanır. `importExport` bir üretim
kaynağı değil, ticaret kalemidir. Bu, payların %100'e tam toplanmasını da
garanti eder.

## Gruplama: 16 alan → 8 grup

Referans site ve TEİAŞ/EPİAŞ raporlama pratiği:

| Grup | EPİAŞ alanları |
|---|---|
| Kömür | `importCoal`, `lignite`, `blackCoal`, `asphaltiteCoal` |
| Hidroelektrik | `dammedHydro`, `river` |
| Doğalgaz | `naturalGas`, `lng` |
| Güneş | `sun` |
| Rüzgar | `wind` |
| Jeotermal | `geothermal` |
| Biyo/Atık | `biomass`, `wasteheat` |
| Diğer | `fueloil`, `naphta` |

`importExport` hiçbir gruba girmez. Bu dışlama koda yorumla gerekçelendirilir.

"Diğer" grubu küçüktür (ölçülen saatte %0,2) ama korunur: payların %100'e
toplanması, grafiğin doğru okunması için kaybedilemez bir özelliktir.

## Veri modeli

Yeni bir üst kavram (`SeriGrubu`) **icat edilmez.** Mevcut `Seri` yapısı
korunur; tek fark CSV'nin geniş olmasıdır:

```
date,Kömür,Hidroelektrik,Doğalgaz,Güneş,Rüzgar,Jeotermal,Biyo/Atık,Diğer
2021-08-28,412.3,198.4,...
```

Katalog tarafı:

- `Seri.epias_bilesenler: dict[str, tuple[str, ...]] | None` — grup adı →
  EPİAŞ alanları. Yalnızca `kaynak_tipi: epias` taşıyabilir; alan sahipliği
  tablosuna (`KAYNAK_ALANLARI`) eklenir.
- Yeni grafik türü: `GECERLI_GRAFIKLER`'e `"composition"` eklenir.
- `epias_bilesenler` taşıyan bir seri `charts: [composition]` almalıdır ve
  tersi de doğrudur; `_dogrula` bu bağı zorlar.

Okuma tarafı:

- **`load_series`'in sözleşmesi bozulmaz** — 24 seri ona bağlı. Geniş CSV
  için ayrı bir okuyucu eklenir: `load_wide_series(seri_id) -> pd.DataFrame`
  (tarih indeksli, her grup bir sütun).

Ingest tarafı:

- `ingest/epias.py`, `epias_bilesenler` tanımlıysa `epias_alani` yerine
  bileşen alanlarını okur, gruplar, günlük toplama indirger (`monthly_agg`
  bu seri için `sum`) ve geniş CSV yazar.
- Eksik saatli gün düşürme kuralı (Faz 3b, C1) aynen geçerlidir.

## Görselleştirme

**Biçim:** 8 çizgili zaman serisi. Günlük veri beş yılda 1826 nokta × 8 çizgi
eder — okunamaz. Çizim öncesi **aylığa indirilir** (`aylige_cevir`, `sum`).

**Toggle:** Kart kendi `Pay % / GWh` seçicisini taşır ve sayfa düzeyindeki
Varsayılan/YoY/MoM seçicisine **bağlanmaz.** Gerekçe: kompozisyon grafiğinde
YoY'un anlamı yoktur; iki toggle'ı bağlamak anlamsız kombinasyonlar üretir.

**Yerleşim:** Yeni sayfa makinesi kurulmaz. Bu, `elektrik` kategorisinde
`charts: [composition]` taşıyan bir seridir ve mevcut ızgarada kart olarak
render olur. Katalog güdümlü model bunu zaten karşılıyor.

## Palet

`RENKLER["seri"]` **kullanılamaz.** O üç renk kategorik değil, *güncellik
yuvasıdır* (0 = cari yıl, 1 = geçen yıl, 2 = iki yıl önce) ve mevsimsellik
grafiğine aittir. Ayrı bir `RENKLER["kategorik"]` gerekir, 8 giriş.

Bu spec **hex değeri sabitlemez.** Koyu zeminde (#0F1E33 sayfa, #16273F kart)
sekiz rengin birbirinden ayrılması gerçek bir kısıttır ve mevcut palet
docstring'i ΔE 15 tabanından söz etmektedir. Palet, implementasyon sırasında
`dataviz` skill'i yüklenip onun doğrulayıcısıyla üretilir ve doğrulama çıktısı
implementasyon raporuna eklenir.

Hedef, mümkün olduğunca semantik çapadır (güneş sarı, kömür koyu gri, hidro
mavi). **Kısıt erişilebilirliktir:** semantik çapa ile ayırt edilebilirlik
çakışırsa semantik feda edilir.

## Doğrulama stratejisi

1. Saf fonksiyonlar ağsız pytest ile: gruplama (16 alan → 8 grup),
   `importExport` dışlaması, pay hesabının %100'e toplanması, geniş CSV
   okuma, aylık indirgeme.
2. Palet doğrulayıcısı çıktısı raporda; sekiz rengin ikili ayrımı belgelenir.
3. Gerçek veri bir kez çekilir; grupların toplamı `total − importExport`
   değerine eşit olmalıdır (tolerans: kayan nokta).
4. Tarayıcıda: `/elektrik` sayfasında kompozisyon kartı render olur, toggle
   iki görünüm arasında geçer, konsol ve sunucu logu temiz.

## Riskler

1. **Sekiz kategorik renk koyu temada ayrılamayabilir.** Doğrulayıcı sekizi
   birden geçiremezse grup sayısı düşürülür ("Diğer"e katlama) — payların
   %100'e toplanması korunur. Karar implementasyonda, doğrulayıcı çıktısıyla
   verilir.
2. **Geniş CSV, `load_series` varsayımlarını bozabilir.** Ayrı okuyucu bu
   yüzden var; `core/takvim.py` ve `core/stats.py` gibi tüketicilerin geniş
   seriyi hiç görmediği testle doğrulanır. Veri Takvimi'nin bu seriyi nasıl
   ele alacağı (tek `value` sütunu yok) implementasyonda çözülür.
3. **EPİAŞ alan adları değişebilir.** Faz 3b'de eklenen ağ smoke testi
   `epias_alani`'nı kontrol ediyor; bileşen alanları da aynı teste eklenir.

## Kapsam dışı

Eurostat fiyat karşılaştırması, `sectors.yaml` ekseni, baraj doluluk serisi.
Üçü de Faz 3b'de gerekçeleriyle ertelendi ve bu dilim onları değiştirmez.

## Stack

Python 3.12 · Streamlit · pandas · Plotly · PyYAML · requests · pytest.
Yeni çalışma zamanı bağımlılığı yok.
