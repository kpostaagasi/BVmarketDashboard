# Faz 2 — Emtia Tasarım Spec'i

Tarih: 2026-08-27
Durum: Onaylandı (kullanıcı onayı: 2026-08-27, sohbet içi)
Önceki spec: `2026-08-27-streamlit-dashboard-design.md` — bu belge onun Faz 2 satırını detaylandırır ve **iki kararını tersine çevirir** (aşağıda gerekçeleriyle).

## Amaç

Panoya küresel emtia fiyatlarını eklemek: Yahoo Finance'ten günlük vadeli
kontrat verisi, iki yeni kategori sayfası, on seri.

## Kapsam kararı

Sitedeki **Emtia** kategorisi 11 sayfa ve üç ayrı kaynak ailesine yayılıyor:

| Grup | Sayfalar | Kaynak |
|---|---|---|
| Küresel emtia fiyatları | Enerji, Metaller, Tarım, Diğer | Yahoo Finance / Dünya Bankası |
| Türkiye regülasyon verisi | EPDK Marjları, EPDK Satış Verileri, BOTAŞ Doğal Gaz Tarifesi, EPDK Doğal Gaz Verileri | EPDK/BOTAŞ doküman kazıma |
| Türkiye tarım/hayvancılık | Tavukçuluk, Balıkçılık, Hayvancılık | TÜİK |

**Faz 2 yalnızca birinci gruptan Enerji + Metaller'i kapsar.** Kalan yedi sayfa
doküman kazıma işidir ve zorluk olarak Faz 3'e (sektör kazıma) aittir.

Tarım (buğday `ZW=F`, mısır `ZC=F`) da kapsam dışıdır. Sembolleri çalışıyor
ancak **`USX` (sent) cinsinden kote** — birim yanlış yazılırsa 100 kat sapma
olur. İstenirse sonradan katalog satırı olarak eklenir.

### Değerlendirilip elenen yaklaşımlar

| | Yaklaşım | Neden elendi |
|---|---|---|
| B | Yahoo + Dünya Bankası Pink Sheet | İkinci bir keşif turu; Pink Sheet bir Excel dosyası ve şekli yıllar içinde değişiyor. Kanıtlanmamış bir kazıma işini kanıtlanmış bir işle aynı fazda paketlemek olurdu. Ayrıca Yahoo'nun alüminyum (`ALI=F`) ve HRC çeliği (`HRC=F`) de kapsadığı doğrulandı — Pink Sheet'in ana gerekçesi zayıfladı. |
| C | Yalnızca Dünya Bankası | Resmî ve kararlı ama aylık frekans ve ~1 ay gecikme. "Brent sabah nerede?" sorusuna cevap vermiyor — panonun ana kullanım amacını karşılamıyor. |

## Tersine çevrilen iki karar

### 1. Parquet geçişi yapılmayacak

Faz 1 spec'i günlük/yüksek hacimli seriler için parquet öngörüyordu. **Ölçüm bunu
çürüttü.** `usd-try` serisi (3.771 nokta) üzerinde, 31 günlük cron koşusu
simüle edilerek:

| Format | Tek dosya | 31 sürüm, paketlenmiş git deposu |
|---|---|---|
| CSV | 72.842 bayt | **176 KB** |
| Parquet | 60.872 bayt (%16 küçük) | **232 KB (%32 büyük)** |

Parquet tek dosyada marjinal kazanıyor — tarih + float sütununda sıkıştırma
avantajı neredeyse yok. Ama binary olduğu için git delta üretemiyor: her günlük
yeniden yazım neredeyse tam bir kopya olarak saklanıyor. CSV'de bir satırlık
ekleme minik bir delta. Üstüne okunabilir diff denetim izi de korunuyor.

**CSV kalır.** Bu karar ölçüme dayanıyor; Faz 3'te seri sayısı 10 katına
çıkarsa yeniden ölçülür.

### 2. Stooq fallback'i kaldırıldı

Faz 0'da `yahoo.ts` içinde çalışan bir Stooq yedeği vardı. Stooq artık **her
isteğe** — Faz 0'da çalışan `usdtry` sembolü dahil — JavaScript tabanlı bir
proof-of-work bot doğrulaması döndürüyor. Bunu programatik olarak geçmek bot
korumasını atlatmak olur; yapılmayacak.

**Yedek kaynak eklenmiyor** (kullanıcı onaylı). Gerekçe: Yahoo düşerse ingest
non-zero exit verir, Actions kırmızıya döner, kısmi veri yayınlanmaz ve panodaki
"Son Dönem" etiketi bayatlığı gösterir — bu mekanizmaların hepsi Faz 1'de
kuruldu ve çalışıyor. Egzersiz edilmeyen bir yedek zaten güvenilmez. Yahoo
kalıcı olarak kırılırsa FRED (St. Louis Fed, resmî ve ücretsiz API) ilk
alternatiftir.

## Mimari

### Katalog şemasının çok-kaynaklı hale getirilmesi

Faz 2'nin asıl işi budur. Mevcut şema EVDS'e özeldir: `Seri` dataclass'ında
`evds_code` ve `evds_frequency` zorunludur ve `_dogrula` ikisini de arar. Bir
Yahoo serisinin EVDS kodu yoktur.

`Seri` bir `kaynak_tipi` alanı kazanır; kaynağa özel alanlar opsiyonel olur:

```yaml
# mevcut seriler — kaynak_tipi eklenir, gerisi aynı
- id: enflasyon/tufe-genel
  kaynak_tipi: evds
  evds_code: TP.TUKFIY2025.GENEL
  evds_frequency: "5"

# yeni
- id: emtia-enerji/brent
  title: Brent Petrol
  category: emtia-enerji
  kaynak: { name: Yahoo Finance, url: "https://finance.yahoo.com/quote/BZ=F" }
  kaynak_tipi: yahoo
  yahoo_symbol: "BZ=F"
  unit: "USD/varil"
  freq: daily
  monthly_agg: mean
  charts: [level, seasonality]
```

`_dogrula` kaynak tipine göre doğrular:

- `kaynak_tipi` ∈ {`evds`, `yahoo`}
- `evds` ise: `evds_code` dolu, `evds_frequency` ∈ {`1`, `2`, `5`}
- `yahoo` ise: `yahoo_symbol` dolu

Bu değişiklik 13 mevcut seriye tek satır ekler, `core/catalog.py` ve
`ingest/run.py`'yi etkiler, **sayfa katmanını hiç etkilemez**.

### Seriler

Hepsi 2026-08-27'de canlı doğrulandı; Brent için 15 yıllık geçmiş teyit edildi
(2011-08-29 → 2026-08-27, 3.777 nokta).

| Kategori | Seri | Sembol | Birim |
|---|---|---|---|
| `emtia-enerji` | Brent Petrol | `BZ=F` | USD/varil |
| | WTI Ham Petrol | `CL=F` | USD/varil |
| | Doğal Gaz | `NG=F` | USD/MMBtu |
| `emtia-metaller` | Altın | `GC=F` | USD/ons |
| | Gümüş | `SI=F` | USD/ons |
| | Bakır | `HG=F` | USD/libre |
| | HRC Çelik | `HRC=F` | USD/ton |
| | Platin | `PL=F` | USD/ons |
| | Paladyum | `PA=F` | USD/ons |
| | Alüminyum | `ALI=F` | USD/ton |

**Katalog sırası bilinçlidir.** KPI satırı bir kategorinin ilk dört serisini
gösterir (konumsal seçim — Faz 1'in ertelenen 3 numaralı işi). Metaller'de
Altın/Gümüş/Bakır/HRC Çelik önde tutulur ki KPI satırında sanayi açısından
anlamlı dördü çıksın.

`monthly_agg: mean` seçildi: emtiada aylık ortalama fiyat standart istatistiktir
ve tek günün kapanışından daha az gürültülüdür. (`last` kur serileri için
doğruydu, fiyat serisi için değil.)

### Yahoo ingest modülü

`ingest/yahoo.py`, `ingest/evds.py`'nin şeklini izler: saf parse fonksiyonları +
`seri_cek()`. API key gerektirmez.

Kontrat — yarısı `yahoo.ts`'ten devralındı (`git show bcd8033:scripts/ingest/sources/yahoo.ts`),
yarısı 2026-08-27'de doğrulandı:

- **Endpoint:** `GET https://query1.finance.yahoo.com/v8/finance/chart/{SEMBOL}?range=15y&interval=1d`
- **Sembol URL-kodlanmalı:** `BZ=F` → `BZ%3DF`
- **User-Agent tuzağı:** Yahoo tarayıcı UA'larını 429 ile reddeder; Googlebot
  UA'sı kabul edilir.
- **Yanıt yolu:** `chart.result[0].timestamp[]` ve
  `chart.result[0].indicators.quote[0].close[]`
- **Tarih tuzağı:** Yahoo günlük barları borsa yerel gece yarısına damgalar.
  `round(ts / 86400) * 86400` ile en yakın UTC gece yarısına yuvarlamak DST'nin
  her iki yönünde de borsa yerel takvim gününü verir. `meta.gmtoffset`'e
  bağlanmak mevsimsel kayma üretir.
- **`close[]` null içerebilir** (tatil, işlem durması) — atılır. Ardışık aynı
  tarihli noktalar tekilleştirilir.

**Hız sınırlama eklenmez.** 2026-08-27'de arka arkaya 12 istek atıldı, hiçbiri
429 almadı — sınırlandığımıza dair kanıt yok. 429 görülürse eklenecek ilk şey
istekler arası gecikmedir.

### Orchestrator

`ingest/run.py` kaynak tipine göre açık dallanır — kayıt defteri (registry)
soyutlaması kurulmaz; iki kaynak için açık `if` hem okunaklı hem dürüsttür:

```python
def _cek(seri, api_key, oturum, bugun):
    if seri.kaynak_tipi == "evds":
        return evds.seri_cek(seri, api_key, session=oturum, bugun=bugun)
    if seri.kaynak_tipi == "yahoo":
        return yahoo.seri_cek(seri, session=oturum, bugun=bugun)
    raise ValueError(f"Bilinmeyen kaynak tipi: {seri.kaynak_tipi}")
```

Ayrıca **`EVDS_API_KEY` kontrolü koşullu hale gelir**: yalnızca koşuya gerçekten
bir EVDS serisi giriyorsa aranır. Şu an key yoksa koşu her hâlükârda exit 2
veriyor; `--only emtia-enerji/brent` key gerektirmediği hâlde düşerdi.

### Sayfa katmanı

**Değişmez.** `core/page.py` kategoriyi katalogdan okur, `app.py` kategorileri
katalogdan üretir, `core/components.py` serinin alanlarını kullanır,
`_SIKLIK_ETIKETLERI` zaten `daily → GÜNLÜK` içerir. İki yeni kategori sayfası =
`catalog/categories.yaml`'a iki satır.

Bu, planın doğrulayacağı bir iddiadır: Faz 2 diff'i `core/page.py`,
`core/components.py`, `core/charts.py`, `core/theme.py` ve `app.py`'ye
dokunmamalıdır.

## Veri kalitesi uyarısı

`BZ=F` gibi semboller **sürekli ön vade** (front-month continuous) serileridir.
Vade değişimlerinde fiyat sıçraması içerirler; grafikteki bir sıçrama piyasa
hareketi değil kontrat roll'ü olabilir. Standart ve yaygın kullanılan bir seri
türüdür, ancak panoya bakan bunu bilmelidir.

Kategori sayfasının açıklama satırına bu uyarı konur.

## Doğrulama stratejisi

1. `pytest` yeşil:
   - Katalog şema testleri — her iki kaynak tipi için ayrı doğrulama kuralları,
     eksik `yahoo_symbol` ve eksik `evds_code` vakaları
   - Yahoo parse testleri — null filtreleme, tekilleştirme, ve özellikle
     **DST sınırında tarih yuvarlama**
   - Mevcut 66 test kırılmadan geçmeli
2. Gerçek koşu: önce `python -m ingest.run --only emtia-enerji/brent`
   (key gerektirmemeli), sonra tam koşu — 23/23 seri
3. Tarayıcı: iki yeni kategori sayfası gerçek veriyle; mevsimsellik ve seviye
   grafikleri, KPI satırı, YoY/MoM toggle'ı
4. Actions: workflow değişmez ama koşu 13'ten 23 seriye çıkar — yeşil kaldığı
   `workflow_dispatch` ile doğrulanır
5. Faz 2 diff'i sayfa katmanına dokunmamış olmalı (yukarıdaki iddia)

## Riskler

1. **Yahoo resmî API değildir ve yedeği yoktur** (bilinçli karar). Kırılırsa o
   serilerin çekimi başarısız olur, Actions kırmızıya döner ve panodaki "Son
   Dönem" etiketi bayatlığı gösterir. Commit adımı `if: always()` taşıdığı için
   başarılı seriler yine yazılır — tek bir Yahoo tökezlemesi resmî EVDS
   dilimini dondurmaz. Kalıcı kırılmada FRED ilk alternatiftir.
2. **Sembol semantiği sessizce değişebilir.** Yahoo bir sembolün kontrat
   tanımını değiştirirse veri sessizce başka bir şeyi ölçmeye başlar. Katalogdaki
   `unit` alanı ve ilk gerçek çekimdeki değer aralığı gözle kontrol edilerek
   azaltılır.
3. **Katalog şema değişikliği 13 mevcut seriye dokunur.** Yanlış giderse Faz 1'in
   çalışan ingest'i kırılır. Şema testleri bu yüzden her iki kaynak tipini de
   kapsar.
4. **Front-month roll sıçramaları** veri kalitesi uyarısıyla ele alınır.

## Stack

Değişiklik yok: Python 3.12 · Streamlit ≥1.49 · pandas · Plotly · PyYAML ·
requests · pytest · GitHub Actions · Streamlit Community Cloud
