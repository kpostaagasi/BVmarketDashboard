# BV Market Dashboard — Faz 1 Makro Paketi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** TCMB EVDS'ten ~15 makro göstergeyi (TÜFE, resmi kur, faiz, konut, tüketici güveni, kredi kartı, yabancı akımlar) çekip normalize edip mevcut jenerik `/kategori/[slug]` sayfalarında yayınlamak.

**Architecture:** Tek bir `scripts/ingest/sources/evds.ts` modülü, EVDS3'ün yeni `POST /igmevdsms-dis/fe` endpoint'ini saran genel bir istemci (`fetchEvdsSeries`) içerir; 15 seri, kod+başlık+birim+kategori içeren bir konfigürasyon listesinden üretilir. Sayfa katmanı zaten jenerik (`getSeries`/`listSeries`/`ChartClient`) — yeni JSON dosyaları oluşunca otomatik render olur, yeni route kodu gerekmez.

**Tech Stack:** Faz 0 ile aynı (Next.js 16, TypeScript, tsx). Yeni: `EVDS_API_KEY` ortam değişkeni.

**Spec:** `docs/superpowers/specs/2026-08-26-bvmarketdashboard-design.md` (Faz 1 satırı) + bu planın API sözleşmesi bölümü (spec yazıldığından beri TCMB API'sini değiştirdiği için burada güncel sözleşme yer alıyor, spec'in yerini alır).

## Global Constraints

- `EVDS_API_KEY` ortam değişkeninden okunur (`process.env.EVDS_API_KEY`); yoksa modül `[fail] evds: EVDS_API_KEY tanımlı değil` ile hata verir, diğer kaynakları etkilemez (run.ts zaten hata izole ediyor).
- **EVDS3 API sözleşmesi** (2026-08 itibariyle doğrulanmış, eski dokümantasyon geçersiz):
  ```
  POST https://evds3.tcmb.gov.tr/igmevdsms-dis/fe
  Header: key: <EVDS_API_KEY>
  Content-Type: application/json
  Body: {
    type: "json",
    series: `-${kod}`,              // tek seri için tek kod, dash-prefixed
    aggregationTypes: "-avg",
    formulas: "-0",
    startDate: "DD-MM-YYYY",        // 2 yıl geriden bugüne
    endDate: "DD-MM-YYYY",
    frequency: "1" | "5",           // 1=günlük, 5=aylık (seriye göre)
    decimalSeperator: ".",
    decimal: "5",
    dateFormat: "0",
    lang: "TR",
    yon: "1",
    sira: "1",
    ozelFormuller: [],
    groupSeperator: true,
    isRaporSayfasi: false
  }
  Yanıt: { totalCount, items: [{ Tarih: "DD-MM-YYYY", <KOD_ALT_CIZGILI>: "değer" | null, UNIXTIME: {...} }] }
  ```
  Seri kodundaki `.` karakterleri yanıt alan adında `_`'a çevrilir (`TP.DK.USD.A` → `TP_DK_USD_A`).
- `Series` tipi Faz 0'daki gibi sabit (`src/lib/types.ts`); `null` değerli noktalar atlanır; tarihler `DD-MM-YYYY` → ISO `YYYY-MM-DD`'ye çevrilir (gün/ay/yıl sırasına dikkat — Türkçe format).
- Kategori adları (dizin adı = `data/<kategori>/`): `tufe`, `kur`, `faiz`, `konut`, `tuketici`, `portfoy`.
- Kaynak: her seri için `source: { name: "TCMB EVDS", url: "https://evds3.tcmb.gov.tr" }`.

## Seri Listesi (15 seri, 6 kategori)

| Kategori | Dosya adı | EVDS Kodu | Başlık | Birim | Frekans |
|---|---|---|---|---|---|
| tufe | genel | TP.FE.OKTG01 | TÜFE Genel Endeks | Endeks (2003=100) | 5 (aylık) |
| tufe | yillik-degisim | TP.FG.J0 | TÜFE Yıllık Değişim | % | 5 |
| tufe | gida | TP.FE.OKTG05 | TÜFE Gıda ve Alkolsüz İçecekler | Endeks | 5 |
| kur | usd-resmi | TP.DK.USD.A | USD/TRY (TCMB Alış) | TL | 1 (günlük) |
| kur | eur-resmi | TP.DK.EUR.A | EUR/TRY (TCMB Alış) | TL | 1 |
| faiz | politika | TP.APIFON4 | TCMB Politika Faizi (1 Hafta Repo) | % | 1 |
| faiz | mevduat-tl | TP.TRY.MT02 | TL Mevduat Faizi (3 Ay) | % | 5 |
| konut | fiyat-endeksi | TP.KFE.TR | Konut Fiyat Endeksi (Türkiye) | Endeks (2010=100) | 5 |
| konut | satis-toplam | TP.HKSAT01 | Toplam Konut Satışları | Adet | 5 |
| konut | satis-ipotekli | TP.HKSAT02 | İpotekli Konut Satışları | Adet | 5 |
| tuketici | guven-endeksi | TP.TUKGUVENENDEKSI | Tüketici Güven Endeksi | Endeks | 5 |
| tuketici | kredikarti-harcama | TP.KKHARCAMA.TOPLAM | Kredi Kartı Harcamaları (Toplam) | Milyon TL | 5 |
| portfoy | yabanci-hisse | TP.YAT01.HS | Yabancı Yatırımcı Hisse Net Alım-Satım | Milyon USD | 2 (haftalık) |
| portfoy | yabanci-dibs | TP.YAT01.DIBS | Yabancı Yatırımcı DİBS Net Alım-Satım | Milyon USD | 2 |

**Not implementer'a:** Yukarıdaki kodlar spec'teki EVDS veri kategorilerinden (TÜFE COICOP, konut fiyat endeksi, tüketici güveni, kredi kartı, yabancı menkul kıymet akımları) türetilmiş en olası kod adlarıdır ancak TCMB kod sözlüğü zaman zaman değişir. Task 1'in ilk adımı `GET /igmevdsms-dis/categories/withDatagroups/type=json` ile kod listesini gerçek veriden doğrulamak/düzeltmektir — bu adım olmadan devam ETME.

## Task 1: EVDS istemcisi + kod doğrulama + tüm seriler

**Files:**
- Create: `scripts/ingest/sources/evds.ts`
- Modify: `scripts/ingest/run.ts` (sources listesine evds ekle)

**Interfaces:**
- Consumes: `Series`/`SourceMeta` tipleri (`../types`).
- Produces: `export async function ingest(): Promise<Series[]>` — yukarıdaki 15 seriyi üretir (bulunamayan/kod hatalı seriler için o seri atlanır, hata loglanır, tüm modül çökmez).

- [ ] **Step 1: Kod doğrulama**

`GET https://evds3.tcmb.gov.tr/igmevdsms-dis/categories/withDatagroups/type=json` header `key: $EVDS_API_KEY` ile çek (curl veya geçici script). Yanıttaki `DATAGROUPS[].DATAGROUP_CODE` ve ilgili seri kodlarını yukarıdaki tablo ile karşılaştır. TÜFE, kur, faiz gibi genel kategoriler için doğru `DATAGROUP_CODE`'u bulup, o veri grubunun seri listesini (varsa `getSeriler`/`serieList` benzeri bir GET ile, ya da TCMB EVDS web arayüzünden `https://evds3.tcmb.gov.tr` üzerinden kategori arayarak) doğrula. Yanlış kod bulunan satırları düzelt; hâlâ bulunamayan seri varsa o satırı listeden çıkar ve raporda belirt (tüm 15'i zorlama).

- [ ] **Step 2: fetchEvdsSeries genel fonksiyonu**

```ts
async function fetchEvdsSeries(
  code: string,
  frequency: "1" | "5" | "2",
  startDate: string,
  endDate: string,
): Promise<{ date: string; value: number }[]> {
  const res = await fetch("https://evds3.tcmb.gov.tr/igmevdsms-dis/fe", {
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
    .map((item) => {
      const raw = item[field];
      const [gun, ay, yil] = String(item.Tarih).split("-");
      return { date: `${yil}-${ay}-${gun}`, value: raw === null || raw === undefined ? null : Number(raw) };
    })
    .filter((p): p is { date: string; value: number } => p.value !== null && !Number.isNaN(p.value));
  return points;
}
```

- [ ] **Step 3: 15 serilik konfigürasyon + ingest()**

Yukarıdaki tablodaki (Step 1'de doğrulanmış) her satır için `{ id: "<kategori>/<dosya-adı>", title, unit, freq, evdsCode, frequency }` içeren bir dizi tanımla; `ingest()` bu diziyi dolaşıp her biri için `fetchEvdsSeries` çağırır, hata alanı `Promise.allSettled` ile izole eder (bir serinin hatası diğerlerini etkilemez), başarılı olanları `Series[]` olarak döner, başarısızları `console.error` ile logla.

`startDate`/`endDate`: bugünden 2 yıl geriye (Faz 0'daki Yahoo modülüyle tutarlı pencere).

- [ ] **Step 4: run.ts'e ekle**

`scripts/ingest/run.ts`'teki `sources` dizisine `{ name: "evds", module: evds }` ekle (mevcut `yahoo` girdisinin yanına).

- [ ] **Step 5: Koştur ve doğrula**

`EVDS_API_KEY=<key> npm run ingest` — en az 10/15 serinin başarıyla üretilmesini bekle (bazı kodlar Step 1'de düzeltilmiş olsa da üretimde başarısız olabilir; %100 şart değil ama %60'ın altı düzeltme gerektirir). Her üretilen JSON'un şemasını (id/title/source/unit/freq/updated/points, artan ISO tarih) doğrula.

- [ ] **Step 6: Build doğrula ve commit**

`npm run build` temiz (yeni route yok, sadece veri — ama `/kategori/tufe` gibi path'ler artık dinamik render için veri buluyor olmalı, hızlı bir `curl localhost:3000/kategori/kur` kontrolü ile teyit et). Commit: `feat: TCMB EVDS ingest module with 15 macro series` (data/ dahil, gerçek anahtar dosyaya YAZILMAZ — sadece env'den okunur).

## Task 2: GitHub secret + workflow güncellemesi

**Files:**
- Modify: `.github/workflows/update.yml`

**Interfaces:**
- Consumes: Task 1'in `EVDS_API_KEY` env okuması.

- [ ] **Step 1: workflow'a env ekle**

`update-data` job'ının `npm run ingest` step'ine `env: { EVDS_API_KEY: ${{ secrets.EVDS_API_KEY }} }` ekle.

- [ ] **Step 2: README'ye not**

`README.md`'deki "Ön koşullar" bölümüne GitHub repo secret'ının adının `EVDS_API_KEY` olduğunu ve `Settings → Secrets and variables → Actions`'tan ekleneceğini belirt (zaten Faz 0'da genel not vardı, secret adını netleştir).

- [ ] **Step 3: Commit**

`ci: wire EVDS_API_KEY into daily ingest workflow`
