# BV Market Dashboard — Streamlit Tasarım Spec'i

Tarih: 2026-08-27
Durum: Onaylandı (kullanıcı onayı: 2026-08-27, sohbet içi)
Önceki spec: `2026-08-26-bvmarketdashboard-design.md` (Next.js) — bu belge onun yerine geçer.

## Amaç

[marketvisuals.net](https://marketvisuals.net) tarzı bir Türkiye ekonomisi veri platformunu BV Portföy'de **şirket içi kullanım için** Streamlit ile kurmak: resmi kaynaklardan otomatik veri çekme, normalize etme, hazır istatistikli grafik sayfaları olarak sunma.

### Neden Streamlit (stack değişikliği)

Önceki spec Next.js statik site öngörüyordu ve Faz 0–1 tamamlanmıştı. Streamlit'e geçiş kullanıcı kararıdır. Kazanç: Python ekosistemi (pandas), katalog-sürümlü sayfa üretimi, Community Cloud üzerinden sıfır-altyapı dağıtım.

## Kaynak sitenin anatomisi (2026-08-27 incelemesi)

`marketvisuals.net` bir **analiz sandbox'ı değil, lookup ürünüdür**. Yapı:

| Katman | İçerik |
|---|---|
| Sol menü | ~19 kategori + sayfa sayısı rozeti (İhracat 8, Sanayi 9, Bankacılık 12, Emtia 11, Havacılık 6, İnşaat 6, Sigortacılık 5, Perakende 5, Elektrik 4, Gemi/Liman 4, Otomotiv 4, Enflasyon 3, Ekonomi & Makro 6, Sağlık 3, Telekom 2, Faktöring 2, Aracı Kurum 2, Varlık Yönetimi 2, Kredi Kartı) + Hisseler, Yatırım Fonları, AI Raporları, Trend Sayfalar, Favorilerim |
| Sektör sayfası | 4'lü KPI paneli → **Veri Takvimi** (sıradaki veri, yayın tarihi, sıklık, kaynak, bildirim) → sektörel grafik ızgarası |
| Veri sayfası | Başlık + kaynak + son veri tarihi → 4 KPI kartı → arama + **Varsayılan / YoY% / MoM%** toggle → ilgili veri çipleri → grafik kartı ızgarası |
| Grafik kartı | Başlık, kaynak rozeti, "Son Dönem" + sıklık etiketi, hazır istatistik satırı (değer, MoM, YoY, 12A aralık), legend, grafik |
| Baskın grafik formu | **Mevsimsellik overlay'i** — yıl başına bir çizgi, x ekseni Oca→Ara |

Ölçek: 180+ veri sayfası, 3.500+ grafik, 30+ kaynak.

**Çıkarım:** değer UI'da değil ingest katmanında. Streamlit tarafı günler, veri tarafı aylar sürer. Mimari buna göre kurulur.

## Kapsam kararları (kullanıcı onaylı)

- **v1 dikey dilimi:** Makro & Enflasyon (TCMB EVDS). Uçtan uca (ingest → sayfa) bitirilir ve tüm mimarinin şablonu olur. Not: EVDS'in 13 serisi menü ağacında dört kategoriye dağılır — `enflasyon`, `ekonomi-makro`, `insaat`, `kredi-karti`. v1'de bu dördü açılır; diğer 15 kategori Faz 2+ ile gelir.
- **Veri yaklaşımı:** A — *repo-as-database*. GitHub Actions cron çeker ve commit'ler; app yalnızca repodan okur.
- **Dağıtım:** Streamlit Community Cloud, private repo, viewer allowlist ile BV Portföy'e kısıtlı.
- **Repo:** Mevcut `BVmarketDashboard` repo'sunun kökü Streamlit'e çevrilir; Next.js uygulaması silinir (git history'de kalır).
- **Görsel kimlik:** Birebir kopya değil. Tanıdık koyu tema, kendi kimliğimiz. Şirket içi kullanım + kopya olmaması trade dress riskini ortadan kaldırır.

### Değerlendirilip elenen yaklaşımlar

| | Yaklaşım | Neden elendi |
|---|---|---|
| B | Runtime fetch + `@st.cache_data(ttl)` | Uyanan app'te ilk kullanıcı 13 API çağrısı bekler; EVDS düşerse dashboard düşer; revizyon geçmişi kaybolur; API key runtime'da yaşar |
| C | Harici veritabanı (Supabase/Postgres) | Doğru cevap ama ~3.500 seri ölçeğinde. v1'de ilk sayfadan önce kurulacak fazladan katman. |

C'ye kapı açık bırakılır: **tüm okuma tek bir `load_series(id) -> pd.DataFrame` fonksiyonundan geçer.** Seri sayısı repoyu zorladığında bu fonksiyonun içi değişir, sayfalar değişmez.

## Mimari

```
bv-market-dashboard/                 (repo kökü)
  app.py                    # st.navigation — sol menü ağacını katalogdan üretir
  catalog/
    series.yaml             # ★ tek doğruluk kaynağı: seri tanımları
    categories.yaml         # menü ağacı + sayfa başlıkları
  core/
    data.py                 # load_series(id) -> DataFrame   ← tek okuma kapısı
    stats.py                # yoy(), mom(), son_donem(), aralik_12a()
    charts.py               # seasonality(), level(), chart_card()
    theme.py                # koyu tema, renk paleti
  ingest/
    evds.py                 # EVDS3 istemcisi
    run.py                  # orchestrator, modül bazlı hata izolasyonu
  data/
    enflasyon/tufe-genel.csv
    ekonomi-makro/politika-faizi.csv
  tests/
  .streamlit/config.toml
  .github/workflows/ingest.yml
  requirements.txt
```

### Katalog-merkezli tasarım

180 sayfayı taşımanın yolu her seriyi Python'da elle yazmak değil, katalogda bir kez tanımlamaktır:

```yaml
# catalog/series.yaml
- id: enflasyon/tufe-genel
  title: TÜFE Genel Endeks
  category: enflasyon
  source: { name: TCMB EVDS, url: "https://evds3.tcmb.gov.tr" }
  unit: "Endeks (2025=100)"
  freq: monthly
  evds_code: TP.TUKFIY2025.GENEL
  evds_frequency: "5"
  charts: [seasonality, level]
```

Sayfalar bildirimsel olur: `render_category("enflasyon")` katalogdan serileri okur, her biri için `chart_card()` çağırır. Yeni seri = YAML'a ~8 satır.

### Veri formatı: CSV (parquet değil)

Veri dosyasında yalnızca `date,value`. Metadata katalogda yaşar.

**Gerekçe:** Aylık makro serisi ~300 satır, CSV'de birkaç KB. Karşılığında git diff okunabilir kalır — TÜİK/TCMB geçmiş bir dönemi revize ettiğinde commit diff'i hangi ayın hangi değerden hangi değere döndüğünü gösterir. Parquet binary olduğu için bu denetim izi kaybolur. Metadata'yı veri dosyasından ayırmak, cron'un ürettiği diff'in yalnızca gerçek veri değişimini göstermesini sağlar.

Faz 2'de günlük/yüksek hacimli emtia serilerine geçildiğinde o kategori parquet'e çevrilir; `load_series()` içeride halleder.

## Sayfa anatomisi

| MarketVisuals | Streamlit karşılığı |
|---|---|
| Sol menü, kategori + sayı | `st.navigation` — `categories.yaml`'dan gruplu sayfa listesi |
| Başlık + kaynak + son veri tarihi | sayfa header'ı, katalogdan |
| 4'lü KPI kartı satırı | `st.columns(4)` + `st.container(border=True)` |
| Varsayılan / YoY% / MoM% | `st.segmented_control` → `stats.py` dönüşümü |
| İlgili veri çipleri | `st.page_link` satırı, katalogdaki `related:` alanı |
| Grafik ızgarası | `st.columns(2)` içinde `chart_card()` |

`chart_card()` tek fonksiyondur; sitedeki tüm kartlar onun bir örneğidir:

```
┌─────────────────────────────────────────┐
│ Toplam Üretim (GWh)             EPİAŞ   │  başlık + kaynak rozeti
│ Son Dönem: 2026-08  [AYLIK]             │  katalogdan freq etiketi
│ Miktar    26.295    MoM  ▼ -12.7%       │  stats.py
│ YoY ▼ -15.9%   12A Aralık 23.179–30.229 │
│ ──────────── grafik ──────────────────  │
└─────────────────────────────────────────┘
```

### Grafik kütüphanesi: Plotly

`st.line_chart` mevsimsellik overlay'ini (yıl başına bir seri, x ekseni Oca→Ara) kontrol etmeye yetmiyor. Altair alternatifti; Plotly iki somut avantajla seçildi: hover'da tam değer okunuyor (makro veride kritik) ve modebar'daki PNG indirme, yatırım komitesi sunumu için grafik çıkarma ihtiyacını ek iş olmadan karşılıyor.

v1'de iki grafik formu yeterli:

- **`seasonality`** — son 3 yıl, yıl başına bir çizgi, x ekseni Oca→Ara, içinde bulunulan yıl vurgulu
- **`level`** — tüm geçmiş, tek çizgi

Katalogdaki `charts:` alanı hangi serinin hangisini alacağını belirler.

### Görsel kimlik

Streamlit sürümü marketvisuals.net'in birebir kopyası **olmayacak**. Streamlit'i o noktaya zorlamak kırılgan CSS hack'leri gerektirir ve her Streamlit sürümünde bozulur. `.streamlit/config.toml` ile koyu tema (lacivert zemin, sarı vurgu) + `st.container(border=True)` ile kart görünümü. Sonuç tanıdık, kimlik bizim.

## Ingest

### Devralınan EVDS3 kontratı

Mevcut `scripts/ingest/sources/evds.ts` çalışan bir kontrat içeriyor; Python'a birebir taşınır. Sıfırdan keşfi yarım gün alacak, dokümante edilmemiş detaylar:

- Endpoint dokümante edilen evds2 REST'i **değil**: `POST https://evds3.tcmb.gov.tr/igmevdsms-dis/fe`, key HTTP header'ında (`key: <API_KEY>`)
- **Tarih formatı tutarsız:** aylık seriler `YYYY-MM`, günlük/haftalık `DD-MM-YYYY` döner (dokümantasyona aykırı). Aylıkta gün bilgisi yok → ayın ilk günü kullanılır.
- Yanıt alan adı = seri kodunun noktaları alt çizgiye çevrilmiş hali (`TP.TUKFIY2025.GENEL` → `TP_TUKFIY2025_GENEL`)
- `groupSeperator: true` yüzünden değerler `139,411.00000` biçiminde gelir — parse öncesi binlik ayraç temizlenmeli
- Frekans kodları: `1`=günlük, `2`=haftalık, `5`=aylık
- **13 doğrulanmış seri kodu** (`categories/withDatagroups` + `serieList` taramasıyla teyit edilmiş, tahmin değil)

### Devralınan 13 seri

| id | Başlık | Birim | Sıklık | EVDS kodu |
|---|---|---|---|---|
| `enflasyon/tufe-genel` | TÜFE Genel Endeks | Endeks (2025=100) | aylık | `TP.TUKFIY2025.GENEL` |
| `enflasyon/tufe-gida` | TÜFE Gıda ve Alkolsüz İçecekler | Endeks (2025=100) | aylık | `TP.TUKFIY2025.01` |
| `ekonomi-makro/usd-try` | USD/TRY (TCMB Alış) | TL | günlük | `TP.DK.USD.A.YTL` |
| `ekonomi-makro/eur-try` | EUR/TRY (TCMB Alış) | TL | günlük | `TP.DK.EUR.A.YTL` |
| `ekonomi-makro/politika-faizi` | TCMB Ağırlıklı Ort. Fonlama Maliyeti | % | günlük | `TP.APIFON4` |
| `ekonomi-makro/mevduat-faizi-tl` | TL Mevduat Faizi (3 aya kadar, stok) | % | aylık | `TP.MT210AGS.TRY.MT02` |
| `insaat/konut-fiyat-endeksi` | Konut Fiyat Endeksi (Türkiye) | Endeks (2010=100) | aylık | `TP.KFE.TR` |
| `insaat/konut-satis-toplam` | Toplam Konut Satışları | Adet | aylık | `TP.AKONUTSAT1.KTRTOPLAM` |
| `insaat/konut-satis-ipotekli` | İpotekli Konut Satışları | Adet | aylık | `TP.AKONUTSAT2.KTRTOPLAM` |
| `ekonomi-makro/tuketici-guven` | Tüketici Güven Endeksi | Endeks | aylık | `TP.TG2.Y01` |
| `kredi-karti/harcama-toplam` | Kredi Kartı Harcamaları (Toplam) | Bin TL | haftalık | `TP.KKHARTUT.KT1` |
| `ekonomi-makro/yabanci-hisse` | Yabancı Yatırımcı Hisse Net Alım-Satım | Milyon USD | haftalık | `TP.MKNETHAR.M7` |
| `ekonomi-makro/yabanci-dibs` | Yabancı Yatırımcı DİBS Net Alım-Satım | Milyon USD | haftalık | `TP.MKNETHAR.M8` |

Kategori yolları Streamlit menü ağacına göre yeniden düzenlenmiştir (eski `tufe/`, `kur/`, `faiz/`, `konut/`, `tuketici/`, `portfoy/` yerine).

### Kontrata yapılan iki değişiklik

1. **Tarih penceresi 2 yıldan 15 yıla çıkar.** Mevcut modül son 2 yılı çekiyor; mevsimsellik grafiği 3 yıl, `level` grafiği daha fazlasını gerektiriyor. Katalogdaki opsiyonel `start_date` alanı seri bazında geçersiz kılar; tanımlı değilse bugünden 15 yıl geriye gidilir.
2. **Her koşuda tam pencere yeniden çekilir**, artımlı ekleme yapılmaz. TCMB/TÜİK geçmiş dönemleri revize ediyor; tam çekim revizyonu yakalar ve CSV diff'inde görünür kılar. Aylık veride maliyeti sıfır.

### Hata izolasyonu

Bir serinin başarısızlığı diğerlerini düşürmez. `run.py` özet rapor basar, başarılı serileri yine de yazar, en az bir başarısızlık varsa non-zero exit ile Actions'ı kırmızıya çevirir.

## Tazelik ve dağıtım

```
GitHub Actions (cron, 06:00 UTC / 09:00 TR)
   └─ python -m ingest.run          # EVDS_API_KEY repo secret'ından
        └─ data/**/*.csv güncellenir
   └─ git diff --quiet || commit + push
        └─ Streamlit Cloud push'u görür → otomatik redeploy
```

Community Cloud kısıtları (doküman teyitli, 2026-08-27):

- **Cron yok, kalıcı disk yok.** App içinde zamanlanmış veri çekme kurulamaz; yazdığı dosya oturumlar arasında kalıcı değil. Ingest'in Actions'ta olması bir tercih değil, zorunluluk.
- **Kaynak limitleri:** 0.078–2 CPU, 690MB–2.7GB RAM, 50GB disk. Makro seriler için fazlasıyla yeterli.
- **Private repo destekleniyor** (read-only deploy key ile).
- **Runtime'da hiç secret yok.** App yalnızca repodaki CSV'leri okur; EVDS key sadece Actions'ta yaşar. A yaklaşımının B'ye karşı sessiz güvenlik avantajı.
- **Uyku gecikmesi:** App hareketsizlik sonrası uykuya dalar; günün ilk kullanıcısı ~30 sn soğuk başlangıç bekler. Şirket içi araç için kabul edildi. Uptime ping'i v1 kapsamı dışında (YAGNI).

## Doğrulama stratejisi

1. `pytest` yeşil:
   - `stats.py` — YoY/MoM/12A aralık, bilinen fixture'lar üzerinde
   - katalog validasyonu — id'ler tekil, her seride `evds_code`, geçerli `freq`, kategori `categories.yaml`'da mevcut
   - EVDS parse — aylık `YYYY-MM` ve günlük `DD-MM-YYYY` formatları, binlik ayraçlı değerler
2. Ingest en az bir kez gerçek EVDS'e karşı koşturulur; üretilen CSV şemaya ve beklenen satır sayısına uyar
3. `streamlit run` + tarayıcıda her sayfa gezilir; konsol hatasız, her grafik gerçek veriyle render olur — ekran görüntüsü kanıtıyla
4. Actions workflow'u `workflow_dispatch` ile elle tetiklenir ve yeşil görülür

## Riskler

1. **EVDS3 endpoint'i dokümante değil.** `igmevdsms-dis/fe` resmi API dokümanında yok; TCMB uyarısız değiştirebilir. Tek modülde izole, kolay değiştirilebilir; resmi evds2 REST'e düşüş yolu açık.
2. **Community Cloud viewer allowlist davranışı** ücretsiz katmanda deploy anında yerinde doğrulanacak. Dokümantasyon private repo desteğini teyit ediyor, allowlist'in güncel kısıtları teyit edilmedi. Yetersiz çıkarsa çare: bulut VM + reverse proxy auth (daha önce elenen seçenek).
3. **Repo şişmesi.** Her cron koşusu değişen CSV'leri commit'ler. Aylık makro veride yıllarca sorun değil; günlük serilerle Faz 2'de yeniden değerlendirilir.
4. **Streamlit sürüm kırılganlığı.** Özel CSS'e dayanan görünüm Streamlit güncellemelerinde bozulabilir — bu yüzden özel CSS minimumda, yerleşik bileşenler tercih ediliyor.

## Faz planı

| Faz | Kapsam | Kaynaklar | Durum |
|---|---|---|---|
| **1** | Streamlit iskeleti + katalog + `chart_card()` + EVDS dilimi (13 seri, 4 kategori sayfası) uçtan uca; Actions cron; Community Cloud deploy | TCMB EVDS | **v1 — sıradaki** |
| **2** | Emtia (~11 sayfa): Brent, altın, HRC çelik, bakır, rafineri marjları + günlük seriler için parquet geçişi | Yahoo Finance, Dünya Bankası | Planlandı |
| **3** | Sektör sayfaları + Veri Takvimi bileşeni | BDDK, OSD, TSB, EPİAŞ, TÜİK | Planlandı |
| **4** | Hisse sayfaları | Yahoo Finance `.IS`, KAP | Planlandı |
| **5** | Arama, favoriler, AI raporları | — | Planlandı |

## Stack

Python 3.12 · Streamlit · pandas · Plotly · PyYAML · requests · pytest · GitHub Actions (cron) · Streamlit Community Cloud (private repo)
