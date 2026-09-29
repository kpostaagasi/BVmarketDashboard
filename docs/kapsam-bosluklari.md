# Kapsam Boşlukları (marketvisuals.net referansı)

Ölçüm: 2026-09-29.

## Yöntem

Referans sitenin **kendi arama indeksi** kullanıldı —
`https://marketvisuals.net/assets/search-chart-titles.js` içindeki
`window.SEARCH_CHART_TITLES` nesnesi. Bu, sitenin `_build_chart_titles.js`
betiğiyle **118 sayfadaki 4.585 başlıktan** üretilmiş (üretim damgası
2026-09-17). Sitenin ana sayfada iddia ettiği "3.500+ grafik" yerine bu indeks
daha kesin bir paydadır.

Bu başlıkların hepsi seri değildir: tablo sütun başlıkları, eksen etiketleri ve
UI başlıkları da indekse girmiş. **4.585 → 3.812 seri-benzeri kalem** (rakam
içermeyen tek-iki kelimelik etiketler ve "En Çok Artan" gibi UI başlıkları
ayıklandıktan sonra).

Eşleştirme: başlıklar Türkçe karakter katlaması + noktalama/parantez temizliği
sonrası tam-normalize eşleşme, token kesişimi (Jaccard-benzeri) ve eşiklerle
yapıldı — `TAM` (normalize birebir), `ESAN` (token örtüşmesi ≥ 0,8), `YAKIN`
(≥ 0,5), `YOK`.

| Durum | Kalem | Pay |
|---|---:|---:|
| TAM (birebir) | 322 | %8,4 |
| ESAN (token eşleşmesi) | 2.676 | %70,2 |
| YAKIN (kısmi token örtüşmesi) | 505 | %13,2 |
| **Toplam karşılanan** | **3.503** | **%91,9** |
| Eşleşmeyen (aşağıda incelendi) | 309 | %8,1 |

**Kendi ölçüğümüz:** 3.772 seri, 64 `kaynak_tipi`, 50 kategori, 61+ `kaynak.name`.

> Önceki ölçüm (2026-09-20, 65 sayfa / 800 kart) **%96,5** diyordu. Fark
> yöntemden: 800 kart "divider satırları hariç gerçek kart" sayımıydı, buradaki
> 3.812 ise başlık indeksinin tamamı. İkisi farklı paydayı ölçer; %91,9 daha
> muhafazakâkârdır ve dipnotlar aşağıda.

## Eşleşmeyen 309 kalemin dağılımı

Bunlar "eksik veri" değil — çoğu sitenin kendi türetilmiş görünümü:

| Kategori | Adet | Durum |
|---|---:|---|
| Sitenin render-time türettiği görünüm (YoY/MoM, mevsimsellik arındırma, pay, karşılaştırma) | ~150 | Bizde `core/stats.py` ile hesaplanıyor; ayrı seri değil |
| Aynı serinin farklı adlandırılmış hâli | ~90 | Ör. `tcmb_swap.html` — scout canlı doğruladı: **tam kapsamlıyız**, eşleştirici yanılmış |
| Ücretli lisans / erişilemeyen kaynak | ~28 | Aşağıda |
| Yeni kaynak ailesi (2026-09-20'den sonra) | ~40 | Aşağıda |

## Kapatılan boşluklar (2026-09-20 → 2026-09-29)

| Boşluk | Durum |
|---|---|
| `tepav_tege.html` / `tepav_tepe.html` (11 kart) | **Kapatıldı** — `ingest/tepav.py` zaten yazılıydı, katalog satırları yoktu. 3 TEGE serisi eklendi (aylık, yıllık, KKTC). |
| `otel_doluluk.html` (3 kart) | **Kapatıldı** — KTB Bakanlık Belgeli Konaklama İstatistikleri bülteni, 31 ay. |
| `sermaye-piyasalari` MKK | **Kapatıldı** — `ingest/mkk.py` yeni, 31 ay (2024-02 → 2026-08). |
| `hisse-finansal` (Fintables) | **Kapatıldı** — `ingest/fintables.py` yeni, 41 çeyrek, THYAO için 17 kalem. |
| TÜFE 13. ana grup (Sigorta ve Finansal Hizmetler) | **Kapatıldı** — `TP.TUKFIY2025.13` canlı doğrulandı (son 126,42). |
| Kredi kartı `KT27`–`KT48` | **Kapatıldı olarak işaretlendi** — 22 kodun **hiçbiri yok** (HTTP 500). Gerçek boşluk `KT50`/`KT51` idi (e-ticaret / mektup-telefon), eklendi. |
| KFE konut fiyat endeksi bölgeleri | **Kapatıldı** — 16 bölgenin 16'sı katalogda. |
| Konut satışı ilk el / ikinci el | **Kapatıldı** — 5 il × 2 el tipi = 10 seri (`AKONUTSAT3`/`AKONUTSAT4`). |
| Elektrik üretimi Doğalgaz | **Kapatıldı** — `elektrik/uretim-dogalgaz`, `naturalGas + lng`. |
| BDDK taraf 10002 / 10005 | **Kapatıldı** — Mevduat bankaları ve Yerli Özel, 4'er kalem. |
| TİM "Avrupa Birliği Ülkeleri" ülke grubu | **Kapatıldı** — ihracatın %39,5'i, en büyük grup. |
| TİM Pazar Monitörü 10 aylık boşluk | **Kapatıldı** — 47 CSV'nin 47'si de 12 satır (2024-12 → 2026-08). |
| THY / Pegasus / ebebek tek satırlık serileri | **Kapatıldı** — arşiv sunumlar/PDF'ler taranmıyordu. |
| `otomotiv/asuzu-kamyonet-ihracat` | **Kaldırıldı** — A.I.O.S. 6 bültenin 12'sinde de "-" bildirmiş; sahte 0 yazmak yerine seri silindi. |

## Ücretli lisans arkasında (19 kart)

Kullanıcı kararı (2026-09-20): **lisans alınmayacak, boşluk belgelenecek.**
2026-09-29'da yeniden doğrulandı:

| Kaynak | Kart | Ölçüm |
|---|---|---|
| Business Analytiq | LPG ABD/Avrupa (gerçekleşen+tahmin, 4), Kok kömürü (4), Jet/kerosen (3), Nafta (1) | Veri Looker Studio gömülüsünde; kamuya açık eşdeğeri yok. EIA'nın ABD Gulf Coast jet yakıtı FARKLI benchmark — ikame sayılmadı. |
| Baltic Exchange | BDI, Capesize BCI, Supramax BSI, Clean Tanker BCTI, Dirty Tanker BDTI (5) | `en.stockq.org/index/BDI.php` **HTTP 403** (http ve https, kök sayfa dahil). Doğrulandı. |
| Neste / LSEG | Dizel Marjı (NWE), Avrupa Dizel Fiyatı (NWE) (2) | Ücretli veri terminali + özel metodoloji. |

## Kaynak tarafında ölü / erişilemez (doğrulandı)

| Kart | Ölçüm |
|---|---|
| Patates | EEX European Processing Potato Future 2026-06-04'te delist edildi. TÜİK Tarım-ÜFE'de kalem bazlı patates kırılımı yok. |
| Etanol | Yahoo `EH=F` son gerçek gözlem 2025-04-03. |
| Uranyum | Yahoo `UX=F` 15 yıllık sorguda tek gözlem. |
| Kömür (Newcastle) | Yahoo'da yalnız `MTF=F` (CIF ARA), Newcastle değil; 2025-12-26'da kesilmiş. |
| Lityum Karbonat | GFEX ücretsiz API çalışıyor ama hiçbir vade referans değere denk gelmiyor. |
| Soda Külü | CZCE HTTP 412. |
| 2. El Araç (Indicata) | `indicata.com.tr/market-watch/` herkese açık ama **yalnızca tanıtım metni ve abonelik formu**; sayısal tablo yok. BETAM/sahibindex Cloudflare Turnstile arkasında. |
| VYŞ NPL ihale kartları | BDDK VYŞ bülteni yalnız **sektör** bilançosu veriyor; şirket/ihale kırılımı yok. |
| Panelder PMI | **YAPILAMAZ** — sayı yalnızca sayı basılı bir JPEG'de; metin katmanı yok. |
| TÜİK J61 hizmet üretim/ciro endeksleri | EVDS'de yayımlanmıyor (daha önce ölçüldü, yeniden doğrulanmadı). |
| `ecb_car_registrations` mevsimsellik/iş günü düzeltmeli | ECB CAR akışında **yalnız `PN`** (düzeltmesiz) varyantı var (`N.K`, `N.S` → HTTP 404). Sitenin "Tescil (mevsimsellik arındırılmış)" kartı kendi render-time türetimi; bizde `mevsimsellik_figuru` var. |
| `tcmb_menkul_kiymet` haftalık toplam | EVDS ana sayfa "Yurt Dışı Yerleşikler MK Portföyü (Net Değişim) (Haftalık)" = −316,01 mn USD yayımlıyor; bizde yok. **EVDS'in diğer uçları (`/GroupList`, `/tumSeriler`, `/md`) bu ağdan 400/403/404**, ama çalışan grup sözlüğü ucu var: `/categories/withDatagroups` + `/serieList/fe` (bkz. `tools/evds_kesif.py`). Bu uçlar taranmalı — aşağıdaki TÜFE boşluğu tam olarak bu yüzden kaçmıştı. |

## TÜİK Veri Portalı — GEREKMEDİĞİ DOĞRULANDI

Bu dosyanın önceki sürümünde TÜFE COICOP alt sınıfları için "TÜİK Veri Portalı API
anahtarı alınmalı" deniyordu. **Bu yanlıştı; anahtar gerekmiyor.**

`https://veriportali.tuik.gov.tr/api/*` uçları gerçekten 403 "Erişim engellendi"
dönüyor (sahte anahtar da aynı yanıtı veriyor → anahtar değil, eşik/IP engeli;
GitHub Actions'tan erişilebilir olabilir, bu ağdan ölçülemedi). Ama gereke de
gelmiyor: **TÜFE'nin tamamı zaten EVDS'te.**

EVDS grup sözlüğü (`python -m tools.evds_kesif seriler bie_tukfiy2025`):

| Derinlik | Seri | Örnek |
|---|---:|---|
| `TP.TUKFIY2025.GENEL` + 2 haneli | 13 | `.01` gıda, `.13` sigorta ve finansal hizmetler |
| 3 haneli (alt grup) | 45 | `.011` gıda, `.012` alkollü içecekler ve tütün |
| 4 haneli | 102 | `.0111` tahıllar ve tahıl ürünleri |
| 5 haneli (alt sınıf) | 189 | `.01111` tahıllar, `.01115` makarna, `.13909` başka yerde sınıflandırılmamış diğer hizmetler |
| **Toplam** | **349** | |

**349 — sitenin "349 COICOP seri" iddiasıyla birebir.** Katalogda 14 vardı, 335 eklendi
ve 335'in tamamı canlı `--only` koşusuyla doğrulandı (her biri 180 aylık nokta).

> **Ders:** Alt grupların EVDS kodu yoktu sanıldı çünkü **kod deseni yanlış
> varsayılmıştı** — `.01.01` denendi, doğru desen `.0111`. EVDS'te bir seri
> bulunamayınca önce `tools/evds_kesif.py gruplar <arama>` ile grup sözlüğü taranmalı;
> kod tahmin edilmemeli.

## Kısmen boşluk (seri var, tarihçe/derinlik sınırlı)

- **TÜRKBESD**: yıllık ürün kırılımı (24 seri) tam; ürün kırılımsız aylık/çeyreksel
  toplamlar yok.
- **İTHİB tekstil**: liste sayfasının varsayılan penceresi ~22 ay; "Toplam ihracat"
  ve dokuma kumaş alt kırılımları salt görsel PDF sayfasında.
- **TAB Gıda (2 seri)**: kablolama tam ve doğrulandı, ancak
  `www.tabgida.com.tr` bu ağdan **ConnectionResetError(54)** veriyor (WAF).
  GitHub Actions farklı bir kaynaktan erişebilir; erişilemezse bu iki seri
  günlük koşuyu 2 hatayla geçer (tür başına eşik 5).
- **BOTAŞ tarife**: **DÜZELTİLDİ.** Önceki not "tarihsel arşiv yok" diyordu;
  bu **yanlıştı**. BOTAŞ'ın HTML tarafında arşiv olmadığı doğru, ancak her
  tarifenin PDF'i dosya deposunda kalıcı duruyor. 21 PDF bulundu
  (2020-05 → 2026-04) ve `ingest/botas.py` bunları okuyor.
- **TİM Pazar Monitörü**: 24 aylık PDF arşivinin **12'sinde metin katmanı yok**
  (tablo vektör/görsel gömülü; `pdftotext -layout` 81 bayt). Bu aylar OCR ister
  (`pdftoppm` + `tesseract`, ~50 MB ek bağımlılık, sayısal hata riski).
  Ayrıca **2024-10 ve 2025-06 bültenleri TİM arşivinde hiç yok** — kalıcı boşluk.
- **MKK**: 20 bülten PDF'i (2024-01 → 2026-08); öncesi MKK sitesinde yok.

## Sitenin hatası (kopyalanmadı)

`otel_doluluk.html` üç kartında YoY sütunu **+2,9 / −0,8 / +8,6 puan** gösteriyor.
Aynı KTB bültenine göre gerçek Temmuz 2026 − Temmuz 2025 farkı **+1,9 / −0,3 /
+2,2**. Seviyeler birebir tutuyor (68,0 / 39,8 / 28,1). **Verimiz doğru, sitenin
YoY sütunu değil.** `catalog/categories.yaml::turizm` notuna yazıldı.
