# BV Market Dashboard — Faz 0 İskelet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Statik, veri-odaklı Türkiye ekonomi/BIST dashboard'unun çalışan iskeletini kurmak: Next.js + Tailwind + Recharts uygulaması, ingest çerçevesi ve uçtan uca gerçek veriyle bir örnek seri (USD/TRY).

**Architecture:** `scripts/ingest/` altında kaynak-başına TS modülleri normalize serileri `data/**/*.json`'a yazar (repoda tutulur). Next.js App Router sunucu bileşenleri bu JSON'ları `fs` ile okuyup statik render eder; grafikler Recharts client bileşenidir. GitHub Actions günlük ingest koşturup değişen JSON'ları commit'ler.

**Tech Stack:** Next.js 16 (App Router) · TypeScript · Tailwind CSS 4 · Recharts · tsx (script runner) · Node 22

**Spec:** `docs/superpowers/specs/2026-08-26-bvmarketdashboard-design.md`

## Global Constraints

- Marka adı: **"BV Market Dashboard"** — kodda hiçbir yerde "marketvisuals" referansı geçmez.
- Tema: koyu; ana arka plan `#0F1E33`. Görsel düzen marketvisuals.net'in bilgi mimarisini izler (bölümler, kart ızgaraları, kaynak notları) ama tüm metin/marka bizimdir.
- Veri sözleşmesi (`src/lib/types.ts`, tüm fazlarda sabit):

```ts
export type Frequency = "daily" | "weekly" | "monthly" | "quarterly" | "yearly";

export interface SourceMeta {
  name: string;   // örn "Yahoo Finance"
  url: string;    // kaynağın sayfası
}

export interface SeriesPoint {
  date: string;   // ISO tarih "YYYY-MM-DD"
  value: number;
}

export interface Series {
  id: string;         // "<kaynak>/<seri-adı>" örn "yahoo/usdtry"
  title: string;
  source: SourceMeta;
  unit: string;
  freq: Frequency;
  updated: string;    // ISO tarih
  points: SeriesPoint[]; // artan tarih sırası
}
```

- JSON dosya konumu: `data/<kategori>/<seri-id-son-parçası>.json`
- Ingest modül sözleşmesi: `export async function ingest(): Promise<Series[]>`; hata modülü bazında izole edilir, orchestrator exit code'u hatalarla yönetir.
- Paket yöneticisi: npm. Script koşturucu: tsx.
- Her task sonunda `npm run build` temiz geçmeli.

---

### Task 1: Proje iskeleti

**Files:**
- Create: `package.json`, `tsconfig.json`, `next.config.ts`, `src/app/layout.tsx`, `src/app/globals.css`, `src/app/page.tsx` (create-next-app üretimi + temizlik)

**Interfaces:**
- Produces: çalışan `npm run dev`/`npm run build`; Task 2+ bu iskeletin üstüne yazar.

- [ ] **Step 1: create-next-app ile scaffold**

```bash
cd /Users/kpostaagasi/Documents/GitHub/BVmarketDashboard
npx create-next-app@latest . --ts --tailwind --eslint --app --src-dir --no-turbopack --import-alias "@/*" --use-npm --yes
npm install recharts tsx
```

Notlar: dizin boş değil (.gitignore, docs/) — create-next-app bunu kabul ediyorsa devam, etmezse geçici alt dizinde oluştur ve dosyaları taşı. Varsayılan `page.tsx` içeriğini tamamen sil (placeholder içerik kalmasın); `layout.tsx` metadata'sı:

```tsx
export const metadata: Metadata = {
  title: "BV Market Dashboard",
  description: "Türkiye ekonomisi ve BIST için veri ve grafikler",
};
```

- [ ] **Step 2: Build doğrula**

Run: `npm run build` → hatasız.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "chore: scaffold Next.js app with Tailwind and Recharts"
```

### Task 2: Tema, layout, Header/Footer

**Files:**
- Modify: `src/app/globals.css`, `src/app/layout.tsx`
- Create: `src/components/Header.tsx`, `src/components/Footer.tsx`

**Interfaces:**
- Consumes: Task 1 iskeleti.
- Produces: `<Header />` (props: yok; nav linkleri: Ana Sayfa `/`, Sektörler `#sektorler`, Hisse `#hisseler`, AI Raporları `/ai-raporlari`) ve `<Footer />`; tüm sayfalar bunları layout'tan alır. CSS custom property'ler: `--bg:#0F1E33`, `--card:#16283f`, `--border:#233a57`, `--text:#e7eef7`, `--muted:#93a7c0`, `--accent:#4ade80`.

- [ ] **Step 1: globals.css tema değişkenleri**

Tailwind 4 `@theme` bloğu ile yukarıdaki renkleri token olarak tanımla; body arka planı `var(--bg)`, metin `var(--text)`.

- [ ] **Step 2: Header/Footer bileşenleri**

Header: sol logo ("BV Market Dashboard", accent renk vurgulu), sağda nav linkleri, sticky, `bg-[#0F1E33]/90 backdrop-blur`. Footer: telif satırı "© BV Market Dashboard", linkler: Hakkında, Veri Kaynakları, Metodoloji (şimdilik `/` veya placeholder route'a bağlanabilir; Task 5'te `/ai-raporlari` geliyor — footer linklerini o zaman tamamla).

- [ ] **Step 3: layout.tsx'e uygula**

`<html lang="tr">`, body içinde `<Header />{children}<Footer />`.

- [ ] **Step 4: Doğrula**

`npm run build` temiz; dev server'da boş ana sayfa header/footer ile görünüyor (browser kontrolü, ekran görüntüsü).

- [ ] **Step 5: Commit** — `feat: dark theme, header and footer`

### Task 3: Veri katmanı — tipler, okuyucu, SourceNote

**Files:**
- Create: `src/lib/types.ts` (Global Constraints'taki sözleşme, kelimesi kelimesine), `src/lib/data.ts`, `src/components/SourceNote.tsx`, `src/components/ChartClient.tsx`

**Interfaces:**
- Produces:
  - `getSeries(seriesPath: string): Promise<Series>` — `data/${seriesPath}.json` dosyasını okur (`fs/promises`), parse eder, `points` artan tarih sırasına göre doğrular; bozuksa açıklayıcı Error fırlatır. Sunucu bileşenlerinde kullanılır.
  - `listSeries(kategori: string): Promise<string[]>` — `data/<kategori>/` altındaki json id'lerini listeler (dizin yoksa `[]`).
  - `<SourceNote source={series.source} updated={series.updated} />` — "Kaynak: <ad ↗> · Son güncelleme: <GG.AA.YYYY>" satırı.
  - `<ChartClient series={Series} />` — `"use client"`; Recharts `ResponsiveContainer > LineChart` (veya tek nokta tipine göre AreaChart), tarih→`toLocaleDateString("tr-TR")` ekseni, tooltip Türkçe; yükseklik ~320px.

- [ ] **Step 1: types.ts** — Global Constraints'teki tipleri birebir yaz.

- [ ] **Step 2: data.ts** — yukarıdaki iki fonksiyon; `process.cwd()` bazlı yol; JSON şema doğrulaması minimal (alan varlığı + points sıralı).

- [ ] **Step 3: SourceNote.tsx + ChartClient.tsx** — yukarıdaki davranış.

- [ ] **Step 4: Derleme doğrula** — `npm run build` (henüz tüketici yok; sadece derlenir).

- [ ] **Step 5: Commit** — `feat: series data layer, source note and chart client`

### Task 4: Ingest çerçevesi + ilk gerçek seri (Yahoo Finance USD/TRY)

**Files:**
- Create: `scripts/ingest/types.ts` (src/lib/types.ts'den re-export), `scripts/ingest/sources/yahoo.ts`, `scripts/ingest/run.ts`
- Create (üretim): `data/doviz/usdtry.json`
- Modify: `package.json` (script: `"ingest": "tsx scripts/ingest/run.ts"`)

**Interfaces:**
- Consumes: Task 3 tipleri.
- Produces:
  - Modül sözleşmesi: `export async function ingest(): Promise<Series[]>`
  - `run.ts`: `sources/index` listesindeki modülleri sırayla koşturur; her modülün hatasını yakalar, stdout'a `[ok] yahoo: N seri` / `[fail] <modül>: <mesaj>` yazar; en az bir fail varsa exit 1, hepsi ok ise 0; üretilen serileri `data/<kategori>/<id>.json`'a yazar (kategori = id'nin ilk segmenti).
  - `yahoo.ts` şu seriyi üretir: id `yahoo/usdtry`, başlık "ABD Doları / Türk Lirası", unit "TL", freq "daily", kaynak { name: "Yahoo Finance", url: "https://finance.yahoo.com/quote/USDTRY=X" }. Endpoint: `https://query1.finance.yahoo.com/v8/finance/chart/USDTRY=X?range=2y&interval=1d`; yanıt `chart.result[0].timestamp[]` + `indicators.quote[0].close[]`; null close'lar atılır; timestamp sn→ISO tarih (UTC).

- [ ] **Step 1: yahoo.ts** — yukarıdaki dönüşümü yaz; fetch'e tarayıcı benzeri User-Agent header'ı ekle (Yahoo bot isteklerini reddedebiliyor).
- [ ] **Step 2: run.ts** — orchestrator + JSON yazımı (klasör yoksa oluştur, 2-space pretty JSON).
- [ ] **Step 3: Koştur** — `npm run ingest` → `data/doviz/usdtry.json` oluşmalı, ~500 nokta, exit 0. Başarısızsa endpoint/UA ayarla; Yahoo erişilemezse `stooq.com` CSV fallback'i aynı modüle ekle (`https://stooq.com/q/d/l/?s=usdtry&i=d`, Date,Close kolonları).
- [ ] **Step 4: Şema doğrula** — üretilen JSON alanları Global Constraints'teki `Series` ile birebir eşleşiyor (jq ile alan listesi kontrolü).
- [ ] **Step 5: Commit** — `feat: ingest framework with Yahoo Finance USDTRY source` (data/*.json dahil)

### Task 5: Ana sayfa + örnek kategori sayfası (uçtan uca)

**Files:**
- Create: `src/app/page.tsx` (Task 1'deki stub'u gerçek içerikle değiştir), `src/app/kategori/[slug]/page.tsx`, `src/app/ai-raporlari/page.tsx`
- Modify: `src/components/Footer.tsx` (AI Raporları linki artık gerçek)

**Interfaces:**
- Consumes: Task 3 (`getSeries`, `ChartClient`, `SourceNote`), Task 4 verisi (`doviz/usdtry`).

Ana sayfa bölümleri (marketvisuals.net ana sayfasının bölüm yapısıyla aynı sıra):
1. Hero: "Türkiye Ekonomisi ve BIST için Veri ve Grafikler"
2. İstatistik bandı: Toplam Grafik / Veri Kaynağı sayaçları (`listSeries` sonuçlarından hesaplanır; statik sayılar hardcode edilmez)
3. "Sık Takip Edilen Hisseler" rozetleri (TUPRS, THYAO, FROTO, KARSN, TTRAK, MGROS, TOASO, EBEBK — şimdilik `/hisse/<sym>` linki; route Faz 4'te gelecek, linkler `href="#"` DEĞİL gerçek route path'i yazılır, sayfa 404 verirse de kabul: Faz 4 dolduracak)
4. "Sık Aranan" rozetleri (İhracat, Enflasyon, Altın, Brent Petrol, Bankacılık, Sigorta…)
5. "Sektör Sayfaları" kartları (9 sektör, `/sektor/[slug]` — Faz 3)
6. "Dikkat Çekenler": `doviz/usdtry` grafiği gerçek veriyle burada render olur (uçtan uca kanıt)

`/kategori/[slug]`: `listSeries(slug)` ile o kategorideki tüm seriler, her biri başlık+grafik+SourceNote; generateStaticParams yerine dinamik + notFound. `/ai-raporlari`: iki placeholder kart ("Piyasa Özeti & Öne Çıkanlar — günlük otomatik", "Sektörel Trend Raporu — haftalık trend"), her ikisinde "Yakında aktif olacak".

- [ ] **Step 1: Ana sayfa** — yukarıdaki 6 bölüm; sayaçlar `listSeries` üzerinden.
- [ ] **Step 2: kategori route'u** — `/kategori/doviz` USD/TRY grafiğini gösterir.
- [ ] **Step 3: ai-raporlari placeholder'ı**.
- [ ] **Step 4: Doğrula** — `npm run build` temiz (statik export'ta `/kategori/doviz` üretilmiş olmalı); dev server + browser ile `/`, `/kategori/doviz`, `/ai-raporlari` gezilir; grafik gerçek veriyle render; ekran görüntüleri alınır.
- [ ] **Step 5: Commit** — `feat: homepage, category page and AI reports placeholder`

### Task 6: GitHub Actions günlük güncelleme

**Files:**
- Create: `.github/workflows/update.yml`, `README.md`

**Interfaces:**
- Consumes: Task 4 `npm run ingest`.

Workflow mantığı:
```yaml
on:
  schedule: [{cron: "0 5 * * *"}]   # her gün 05:00 UTC
  workflow_dispatch:
permissions: {contents: write}
jobs:
  update-data:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: {node-version: 22, cache: npm}
      - run: npm ci
      - run: npm run ingest
      - run: |
          git config user.name "data-bot"
          git config user.email "actions@users.noreply.github.com"
          git add data/
          git diff --cached --quiet || git commit -m "data: daily update $(date -u +%F)"
          git push
```

README: proje amacı (3-4 cümle), mimari şeması (spec'teki ASCII), `EVDS_API_KEY` secret'ının Faz 1'de gerekeceği notu, yerel geliştirme komutları (`npm run dev`, `npm run ingest`).

- [ ] **Step 1: update.yml** — yukarıdaki içerikle.
- [ ] **Step 2: README.md**.
- [ ] **Step 3: Doğrula** — `act` yoksa yerelde workflow YAML sözdizimini gözden geçir; `npm run build` son kez temiz; commit.

- [ ] **Step 4: Commit** — `ci: daily data update workflow and README`
