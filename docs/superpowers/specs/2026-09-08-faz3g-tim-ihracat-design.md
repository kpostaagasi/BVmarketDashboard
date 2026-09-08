# Faz 3g: TİM İhracat — Tasarım Spec'i

Tarih: 2026-09-08
Durum: Onaylandı
Önceki dilim: `2026-09-07-faz3f-evds-genisletme-design.md`

## Amaç

TİM'in (Türkiye İhracatçılar Meclisi) aylık sektörel ihracat bültenlerinden
13 seri üretmek: toplam ihracat ve 12 sektör kırılımı. Katalog 69 → 82 seri,
11 → 12 kategori.

Neden TİM: sektör kırılımı hiçbir mevcut kaynağımızda yok ve TİM verisi
**takip eden ayın 1–2'sinde** yayımlanıyor — panodaki en hızlı makro sinyal
olur. TÜİK/EVDS ihracat verisi (`dis-ticaret/ihracat`) aynı ayı ~30 gün
sonra veriyor.

## Ölçülen kaynak gerçekleri

Hepsi 2026-09-08'de canlı doğrulandı; tahmin değil.

### URL deseni deterministik

```
https://tim.org.tr/files/downloads/rakamlar/<yıl>/<ay>/<yıl>-<aa>-sektorel-bazda-rakamlar.xlsx
```

`<ay>` dizinde sıfırsız (`/8/`), dosya adında sıfırlı (`2026-08`). Sayfadaki
`?v=1` sorgusu gereksiz. OSD'nin tersine **indeks kazımaya gerek yok**.

| Dosya | HTTP |
|---|---|
| 2026/8, 2025/12, 2024/12, 2022/12, 2020/12, 2020/1, 2019/12 | 200 |
| 2019/1, 2019/6, 2018/12, 2015/12, 2013/12, 2011/12 | 404 |

Pratik geçmiş sınırı: **2019-01**. 2018 ve öncesi farklı adlandırmada ve
`.xls` (ör. `/rakamlar/2011/4/sektorelulke_04_2011.xls`) — kapsam dışı.

### Her dosya o yılın tamamını taşır

Tek sayfa: `SEKTOR`. Satır 4 başlık (`S E K T Ö R`, OCAK…ARALIK, TOPLAM),
satır 5'ten itibaren sektör satırları, `TOPLAM` etiketli satır tabloyu
kapatır. Sütun 1 sektör adı, sütun 2–13 aylar, sütun 14 yıl toplamı.

Sonuç: tam geçmiş için ayda bir değil **yılda bir** dosya gerekir —
`2019/12` artı 2020…cari yıl için en güncel yayımlanmış ay. Bugün 8 istek.
2019 ve 2020 dosyalarında `TOPLAM` satırından SONRA alt mal grubu tabloları
da var (Nisan 2025'te yayımı durdurulmuş); ayrıştırma `TOPLAM` satırında
durduğu için bunlar görülmez.

### Aritmetik öz-doğrulama tam tutuyor

2026-08 dosyasının sekiz ayının hepsinde `I. TARIM + II. SANAYİ +
III. MADENCİLİK == TOPLAM` (fark 0,0). Bu, şablon kaymasını yakalayacak
ucuz ve kesin bir kontrol.

### Yayımlanmamış ay `0` yazıyor

Cari yıl dosyasında Eylül–Aralık 2026 sütunları `0`. Sıfır "ihracat yok"
değil, "henüz yayımlanmadı" demek. `TOPLAM == 0` olan ay **atılır**; aksi
halde grafik dibe düşer, KPI ve YoY yönü yanlış çıkar. (Faz 3b'nin "eksik
saatli günü at" kuralının aynısı, aylık ölçekte.)

### Sektör etiketleri zaman içinde değişiyor

2019 ↔ 2026 farkları: `Elektrik Elektronik` → `Elektrik ve Elektronik`,
`Gemi ve Yat` → `Gemi, Yat ve Hizmetleri`, `Süs Bitkileri ve Mam.` →
`Süs Bitkileri ve Mamulleri`, `Mobilya,Kağıt...` → `Mobilya, Kağıt...`;
`Diğer Sanayi Ürünleri` satırı 2026'da yok. OSD dilimindeki
`osd_eski_adlar` kalıbının aynısı gerekiyor: `tim_eski_adlar`.

Etiketler normalize edilir: baştaki `.`, çoklu boşluk ve satır sonları
temizlenir (`" Yaş Meyve ve Sebze  "` → `"Yaş Meyve ve Sebze"`).

### TİM ≠ TÜİK

Temmuz 2026: TİM toplamı **22.028,9** milyon USD, mevcut TÜİK/EVDS serimiz
(`dis-ticaret/ihracat`) **25.622,9** milyon USD. TİM ihracatçı birlikleri
kayıtlarını sayar, TÜİK gümrük beyanlarının tamamını. Fark gizlenmez;
kategori notuna yazılır. TİM'in değeri seviye karşılaştırması değil, **hız**
ve **sektör kırılımı**.

## Mimari

### `ingest/tim.py` — saf katmanlar + tek ağ kabuğu

| Fonksiyon | Sözleşme |
|---|---|
| `bulten_url(yil, ay)` | Deterministik URL üretir |
| `cekilecek_bultenler(bugun)` | `(yıl, ay)` listesi: 2019/12 + her yıl için en güncel ay |
| `sektor_adini_normalize(ham)` | Baştaki `.`, fazla boşluk, satır sonu temizliği |
| `sayfayi_ayikla(baytlar)` | `{sektör: {"YYYY-MM-01": değer}}`; `TOPLAM` satırında durur |
| `sifir_aylari_at(noktalar, toplamlar)` | `TOPLAM == 0` olan ayı tüm sektörlerden düşer |
| `dogrula(noktalar, anahtar)` | I+II+III == TOPLAM (tolerans 0,5) ve ≥30 sektör satırı |
| `seri_cek(seri, onbellek, session, bugun)` | Ağ + önbellek kabuğu, `date,value` döndürür |

Ağ yalnızca `seri_cek` içinde. XLSX baytları değil **ayrıştırılmış noktalar**
koşu başına önbelleklenir (OSD kalıbı): 13 seri aynı 8 dosyayı paylaşır, 8
indirme olur, 104 değil.

`ingest/run.py::_cek`'e bir dal, `ingest/run.py::main`'e `tim_onbellek`
eklenir. Ölçekleme faz 3f'ten beri orchestrator'da: `olcek: 0.001` ile
Bin USD → Milyon USD.

### Yeni bağımlılık: `openpyxl`

`requirements-ingest.txt`'e girer, `requirements.txt`'e **girmez** —
Streamlit Cloud yalnızca ikincisini kurar ve uygulama XLSX okumaz.
`pdfplumber` için var olan ayrımın aynısı; `tests/test_requirements.py`'ye
simetrik iki test eklenir.

Değerlendirilen alternatif: XLSX'i stdlib `zipfile` + `ElementTree` ile
ayrıştırmak. Elendi — sharedStrings çözümü, inline string, hücre referansı
aritmetiği ve stil-bağımlı sayı okuma kendi elimizde bir hesap tablosu
ayrıştırıcısı demek. Şablon kayması riskini artırır, kod azaltmaz.

### Katalog

`kaynak_tipi: tim`; `KAYNAK_ALANLARI`'na bir satır:

```python
"tim": {"zorunlu": ("tim_sektor",), "istege_bagli": ("start_date", "tim_eski_adlar")},
```

Yeni kategori `ihracat`, 13 seri — hepsi `freq: monthly`, `unit: "Milyon USD"`,
`olcek: 0.001`, `charts: [seasonality, level]`:

| id | tim_sektor | not |
|---|---|---|
| `ihracat/toplam` | `TOPLAM` | TİM genel toplamı |
| `ihracat/otomotiv` | `Otomotiv Endüstrisi` | |
| `ihracat/hazir-giyim` | `Hazırgiyim ve Konfeksiyon` | |
| `ihracat/kimyevi` | `Kimyevi Maddeler ve Mamulleri` | |
| `ihracat/celik` | `Çelik` | |
| `ihracat/elektrik-elektronik` | `Elektrik ve Elektronik` | eski ad: `Elektrik Elektronik` |
| `ihracat/makine` | `Makine ve Aksamları` | |
| `ihracat/demir-disi-metaller` | `Demir ve Demir Dışı Metaller` | |
| `ihracat/savunma-havacilik` | `Savunma ve Havacılık Sanayii` | |
| `ihracat/tekstil` | `Tekstil ve Hammaddeleri` | |
| `ihracat/mucevher` | `Mücevher` | |
| `ihracat/tarim` | `I. TARIM` | ana grup toplamı |
| `ihracat/madencilik` | `Madencilik Ürünleri` | |

Pano: `toplam`, `otomotiv`, `hazir-giyim`, `celik`. Kategori notu TİM–TÜİK
farkını ve yayın hızını açıklar.

## Kompozisyon grafiği kapsam dışı — gerekçe

Sektör paylarını `composition` olarak çizmek iki iş gerektirir: (1)
`epias_bilesenler`'i kaynak-agnostik hale getirmek, (2) 13 sektör için
**yeni bir erişilebilirlik doğrulamalı kategorik palet**. `core/theme.py`'nin
sekiz renkli paleti `dataviz` doğrulayıcısından geçmiş; docstring'i en zayıf
komşu çiftin marjını (Kömür↔Jeotermal, CVD ΔE 8,7) kaydediyor ve
"doğrulayıcı aynı komut ve sırayla yeniden koşturulmadan renk
değiştirilmemeli" diyor. `test_theme.py` de palet anahtarlarını
`elektrik/uretim-kompozisyon` gruplarıyla birebir çiviliyor. 13 sektörlük
ikinci bir palet kendi dilimidir. Bu dilim tek-değerli seri yolunu kullanır;
asıl sinyal (sektör seviyesi + mevsimsellik + YoY) orada.

## Doğrulama stratejisi

1. **Saf fonksiyon testleri (ağsız):** URL üretimi (ay sıfırı: dizinde yok,
   dosya adında var), bülten seçimi (yıl başına en güncel; 2019 sabiti),
   ad normalizasyonu (gerçek 2019 ve 2026 etiketleriyle), `TOPLAM` satırında
   durma (2019 dosyasının alt tabloları sızmamalı), sıfır-ay atma,
   öz-doğrulamanın hem geçen hem kırılan hâli, eski ad eşleşmesi.
2. **Ağ smoke testi** (`@pytest.mark.network`): cari yıl için bir URL 200
   döner ve içerik XLSX'tir.
3. **requirements ayrımı:** `openpyxl` ingest'te var, uygulamada yok.
4. **Gerçek çekim:** tam koşu 82/82; 13 CSV'de tekrar eden tarih / sıra
   bozukluğu / NaN yok; `ihracat/toplam` Temmuz 2026 ≈ 22.029 milyon USD;
   sektör serilerinin toplamı toplam serisiyle tutarlı.
5. **Tarayıcıda:** `ihracat` sayfası panosuyla render olur; Veri Takvimi 82
   seri listeler ve TİM serileri "güncel" bandındadır (yayın ayın 1–2'si,
   aylık eşik 50 gün).

## Ölçülen doğrulama (uygulama sonrası)

1. **Testler:** `pytest` 314 geçti, 5 ağ testi hariç tutuldu. `tests/test_tim.py`
   23 test: URL ay sıfırı, yıl başına tek dosya seçimi, gerçek etiketlerle ad
   normalizasyonu, `TOPLAM` satırında durma (alt tablo sızmıyor), sıfır-ay
   atma (ve sektörün gerçek sıfırını koruma), öz-doğrulamanın geçen +
   üç kırılan hâli, eski ad toplama, önbelleğin yeniden indirmemesi,
   yayımlanmamış cari ayı geriye doğru deneme, HTTP 500'ün yükselmesi.
2. **Plan dışı bulgu:** `tests/test_run.py`'nin iki `main()` testi `osd` ve
   `tim` adaptörlerini stub'lamıyordu — `-m 'not network'` koşusu gerçek OSD
   PDF'lerini ve TİM XLSX'lerini indiriyordu. Stub'landı; paket süresi
   **9,6 sn → 1,6 sn**.
3. **Tam ingest:** **82/82 seri başarılı** (204 sn). 13 TİM serisi
   2019-01 → 2026-08, her biri **92 nokta**; tekrar eden tarih, sıra
   bozukluğu, NaN ve sıfır değer yok (yayımlanmamış Eylül–Aralık 2026
   düşürüldü).
4. **Değer kontrolü:** `ihracat/toplam` Temmuz 2026 = **22.028,92** milyon
   USD (spec'in ölçtüğü değer), `ihracat/otomotiv` = 3.584,63,
   `ihracat/tarim` = 3.160,37. 11 sektör serisi toplamın %78,1'ini kaplıyor
   (kalanı katalogda ayrı seri açılmayan alt kalemler — beklenen).
   `ihracat/elektrik-elektronik` 2019-01'de nokta üretti: `tim_eski_adlar`
   ile `Elektrik Elektronik` etiketi eşleşti.
5. **Tarayıcıda:** `ihracat` sayfası panosuyla (toplam, otomotiv, hazır
   giyim, çelik) ve TİM≠TÜİK notuyla render oldu; Veri Takvimi
   **82 seri · 82 güncel · 0 dikkat gerektiriyor**.

## Riskler

1. **Şablon kayması.** TİM sütun ekler/satır kaydırırsa öz-doğrulama
   (I+II+III == TOPLAM) ve asgari satır sayısı kontrolü hata yükseltir;
   sessiz yanlış veri yazılmaz. Modül bazlı hata izolasyonu diğer 69 seriyi
   korur.
2. **Sektör adı değişimi.** `tim_eski_adlar` kaçış yolu var; bir seri hiçbir
   bültende bulunamazsa `RuntimeError` — boş seri yazılmaz.
3. **Yeni yıl dosyası gecikmesi.** Ocak ayında cari yıl dosyası henüz yokken
   `cekilecek_bultenler` o yıl için hiçbir ay bulamaz; geçen yılın dosyası
   listede kaldığı için seri kesilmez, yalnızca yeni ay gelmez. 404 sessizce
   yutulmaz — cari yıl için en güncel ayı bulmak üzere aylar geriye doğru
   denenir ve hiçbiri bulunamazsa o yıl atlanır (diğer yıllar zarar görmez).
4. **`openpyxl`'in Streamlit Cloud'a sızması.** `requirements.txt` bu
   dilimde değişmez; test ve workflow ile güvenceye alınır.

## Kapsam dışı

Kompozisyon grafiği (yukarıda) · il bazında ve ülke bazında rakamlar (ayrı
XLSX'ler, ayrı dilim) · alt mal grubu kırılımı (TİM Nisan 2025'te yayımı
durdurdu) · 2018 ve öncesi geçmiş (`.xls`, düzensiz adlandırma) ·
hizmet ihracatı (HİB, ayrı kaynak).

## Stack

Python 3.12 · Streamlit · pandas · Plotly · PyYAML · requests · pdfplumber
**+ openpyxl** (ikisi de yalnızca ingest) · pytest · GitHub Actions ·
Streamlit Community Cloud.
