# BV Market Dashboard — Tasarım Spec'i

Tarih: 2026-08-26
Durum: Onaylandı (kullanıcı onayı: 2026-08-26, sohbet içi)

## Amaç

[marketvisuals.net](https://marketvisuals.net) benzeri, kendi kullandığımız bir Türkiye ekonomisi ve BIST veri platformu kurmak: resmi/açık kaynaklardan otomatik veri çekme, normalize etme ve grafikli sayfalar olarak sunma.

Kapsam kararları (kullanıcı onaylı):

- **MVP sırası:** Tüm katmanlar sırayla (makro → emtia → sektör → hisse → AI raporları)
- **Güncelleme:** GitHub Actions cron — ingest commit'ler, statik deploy takip eder
- **Görsel kimlik:** marketvisuals.net ile aynı layout/renk/typografi; marka adı ve logo bizim ("BV Market Dashboard", #0F1E33 koyu tema). *Bilinen trade dress riski kullanıcı tarafından kabul edildi.*

## Mimari

```
scripts/ingest/            # kaynak başına bir TS modülü
  evds.ts                  #   TCMB EVDS API (tek key, ~15 seri)
  yahoo.ts                 #   Yahoo Finance (emtia + .IS hisse fiyatları)
  worldbank.ts             #   Dünya Bankası Pink Sheet CSV (gübre vb.)
  bddk.ts, osd.ts, tsb.ts… #   doküman kazıma modülleri (Faz 3)
  run.ts                   #   orchestrator: modülleri koşturur, hataları izole eder
data/
  <kategori>/<seri>.json   # { source, unit, freq, updated, points: [{date, value}] }
src/app/                   # Next.js App Router (build'de data/*.json'dan render)
.github/workflows/update.yml  # günlük cron: pnpm ingest → git diff → commit+push
```

Site tamamen statiktir; canlı sunucu yok. Veri tazeliği Actions'ın commit'iyle gelir.

### Veri sözleşmesi

Her ingest modülü `ingest(): Promise<Series[]>` imzasına uyar:

```ts
type Series = {
  id: string;              // "evds/tufe-genel"
  title: string;
  source: SourceMeta;      // { name, url, note? } — her grafik altında gösterilir
  unit: string;            // "%", "TL", "adet", "endeks (2010=100)"…
  freq: "daily" | "weekly" | "monthly" | "quarterly" | "yearly";
  updated: string;         // ISO tarih
  points: { date: string; value: number }[];  // artan tarih sırası
};
```

- Bir modülün hatası diğerlerini çökertmez; `run.ts` başarısızlıkları raporlar ve exit code'u yönetir.
- JSON dosyaları repoda tutulur → her commit veri geçmişi, her deploy deterministik.

### Sayfa yapısı

| Route | İçerik |
|---|---|
| `/` | Sık takip edilenler, arama, sektör listesi, öne çıkan seriler (marketvisuals ana sayfa düzeniyle aynı bölümler) |
| `/kategori/[slug]` | ~90 kategori sayfası (Faz 1–2'den itibaren doldurulur) |
| `/sektor/[slug]` | 9 sektör sayfası, her biri 2+ grafik + kaynak notu |
| `/hisse/[symbol]` | ~23 hisse: fiyat grafiği + temel göstergeler |
| `/ai-raporlari` | Placeholder kartlar ("yakında aktif olacak") |

Sunucu bileşenleri `fs` ile JSON okur; grafikler Recharts client bileşeni (`ChartClient`). Her grafiğin altında `SourceNote` (kaynak adı + bağlantı + son güncelleme).

## Faz planı

| Faz | Kapsam | Kaynaklar | Ön koşul |
|---|---|---|---|
| **0** | İskelet: Next.js 16 + TypeScript + Tailwind 4 + Recharts; koyu tema (#0F1E33), Header/Footer/Homepage iskeleti; Actions workflow; ilk örnek seri uçtan uca | — | — |
| **1** | Makro paketi (~15 kategori): TÜFE, kur, faiz, konut satış/fiyat endeksi, tüketici güveni, kredi kartı harcamaları, yabancı menkul kıymet akımları | TCMB EVDS API | `EVDS_API_KEY` secret |
| **2** | Emtia (~12 seri): Brent, WTI, doğalgaz, altın, gümüş, bakır, alüminyum… | Yahoo Finance, Dünya Bankası Pink Sheet CSV | — |
| **3** | 9 sektör sayfası: Otomotiv, Havacılık/Turizm, Bankacılık, Elektrik, Finansal Kiralama, Gemi/Liman, İnşaat, Perakende, Sigortacılık | BDDK bültenleri, OSD üretim bültenleri, TSB prim verileri, TEİAŞ, YİGM, Eurocontrol, TÜİK, Indicata | Faz 0 altyapısı |
| **4** | Hisse sayfaları (~23): TUPRS, THYAO, FROTO, TOASO, KARSN, TTRAK, EBEBK, MGROS vb. — fiyat + hacim + mevcut temel veriler | Yahoo Finance `.IS` sembolleri; finansallarda KAP/Fintables kazıması (mümkün değilse sadece fiyat/hacim) | Faz 0 |
| **5** | AI Raporları placeholder + site geneli arama/kategori indeksi + About/Metodoloji/Veri Kaynakları sayfaları | — | — |

## Doğrulama stratejisi (her faz)

1. `npm run build` hatasız.
2. Dev server + tarayıcı ile her yeni sayfa gezilir; konsol hatasız, her grafik gerçek veriyle render olur; ekran görüntüsü kanıtı alınır.
3. Ingest için: her modül en az bir kez gerçek kaynakta koşturulmuş, üretilen JSON şemaya uyumlu olmalı.

## Riskler

1. **EVDS API key** ücretsiz ama kayıt gerektirir — kullanıcı Faz 1 öncesi [evds2.tcmb.gov.tr](https://evds2.tcmb.gov.tr)'den alıp GitHub secret'a (`EVDS_API_KEY`) ekleyecek.
2. **Trade dress riski**: birebir görsel kopya telif/trade dress ihtilali doğurabilir. Kullanıcı bilinçli kabul etti (2026-08-20 ve 2026-08-26 onayları).
3. **Doküman kazıma kırılganlığı**: BDDK/OSD/TSB format değişiklikleri modül kırar → modül bazlı hata izolasyonu + Actions'ta görünür hata raporu.
4. **Yahoo Finance resmi API değildir**; endpoint değişebilir → tek modülde izole, kolay değiştirilebilir.

## Stack

Next.js 16 (App Router) · TypeScript · Tailwind CSS 4 · Recharts · Node 22 (ingest script'leri) · GitHub Actions (cron) · Statik export deploy (Vercel/Netlify/GH Pages)
