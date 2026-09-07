# Faz 3f: EVDS Genişletme — Tasarım Spec'i

Tarih: 2026-09-07
Durum: Onaylandı
Önceki fazlar: `2026-08-27-streamlit-dashboard-design.md` (ana spec),
`2026-08-27-faz3a-veri-takvimi-design.md`, `2026-08-28-faz3b-elektrik-sektoru-design.md`,
`2026-08-28-faz3c-uretim-kompozisyonu-design.md`, `2026-09-04-faz3e-osd-otomotiv-design.md`

## Amaç

Mevcut EVDS adaptörünü **hiç yeni ingest kodu yazmadan** 29 yeni seriyle
kullanıp katalogdaki seri sayısını 40'tan 69'a çıkarmak: üç yeni kategori
sayfası (`sanayi`, `dis-ticaret`, `para-banka`) açmak ve dört mevcut ince
sayfayı (`enflasyon`, `insaat`, `kredi-karti`, `ekonomi-makro`)
zenginleştirmek.

Ana spec'in çıkarımı yön verdi: *"değer UI'da değil ingest katmanında."*
Bu dilim o değeri en düşük riskle alır — `kaynak_tipi: evds` yolu 14 seride
kanıtlı, dolayısıyla iş büyük ölçüde katalog düzenlemesi. Faz 4 (hisse
sayfaları) ve Faz 5 (arama/favoriler) veri genişliği olmadan ince kalacağı
için önce genişlik alınır.

## Kapsam kararları (kullanıcı onaylı)

1. **29 seri, üç yeni kategori.** Liste aşağıda; her kod bu spec yazılmadan
   önce canlı doğrulandı (bkz. "Doğrulanmış kodlar").
2. **`olcek` kaynak-tipinden bağımsız ortak alana yükseltilir.** EVDS bu
   serilerin bir kısmını "Bin TL"/"Bin USD" cinsinden döner; ölçeklenmeden
   KPI kartında okunamazlar. Uygulama noktası orchestrator'a taşınır.
3. **`pano` her kategoriye yazılır.** Devredilen iş #3 (KPI'ların konumsal
   `seriler[:4]` seçimi) bu dilimde kapanır.
4. **Turizm, KKM, COICOP alt kırılımı ve yapı ruhsatı kapsam dışı** —
   gerekçeler "Kapsam dışı" bölümünde.

## EVDS metadata uçları (bu dilimde keşfedildi)

Seri kodları tahminle değil, EVDS3 SPA'sının kendi metadata uçlarından
alındı. `evds2.tcmb.gov.tr/service/evds/...` REST'i **ölü** (SPA HTML'i
döner); çalışan uçlar `https://evds3.tcmb.gov.tr/igmevdsms-dis` altında,
`key` HTTP header'ı ile:

| Uç | İçerik |
|---|---|
| `GET /categories/withDatagroups/type=json` | 154 konu, 676 veri grubu (`DATAGROUP_CODE`, `DATAGROUP_TYPE`) |
| `GET /serieList/fe/type=json&code=<grup>` | Grubun serileri: `SERIE_CODE`, `SERIE_NAME`, `FREQUENCY_STR`, `DEFAULT_AGG_METHOD_STR` |
| `GET /searchResults?searchVal=<metin>` | Alt dize aramasıyla veri grubu arama (semantik değil) |

Bu uçlar **ingest'e girmez** — koşu başına gereksiz istek olur ve kod zaten
katalogdaki sabit kodlarla çalışır. Belgeye geçme amacı: bir sonraki EVDS
dilimi kod aramak için sıfırdan keşif yapmasın.

## Doğrulanmış kodlar

Hepsi 2026-09-07'de `ingest.evds.seri_cek` ile `start_date: 2013-01-01`
penceresinde çekildi; satır sayısı, son tarih ve son değer teyit edildi.

### Yeni kategori: `sanayi` — Sanayi & Reel Kesim

| id | evds_code | frek | birim | son nokta |
|---|---|---|---|---|
| `sanayi/uretim-endeksi` | `TP.TSANAYMT2021.Y1` | 5 | Endeks (2021=100) | 2026-06 · 110,67 |
| `sanayi/kapasite-kullanim` | `TP.KKO2.IS.TOP` | 5 | % | 2026-08 · 73,5 |
| `sanayi/reel-kesim-guven` | `TP.GY1.N2.MA` | 5 | Endeks | 2026-08 · 102,4 |
| `sanayi/oncu-gostergeler` | `TP.CLI2.A01` | 5 | Endeks | 2026-07 · 405,88 |
| `sanayi/kurulan-sirket` | `TP.AC2.TOP.A` | 5 | Adet | 2026-07 · 9.642 |
| `sanayi/kapanan-sirket` | `TP.KAP2.TOP.A` | 5 | Adet | 2026-07 · 2.794 |

### Yeni kategori: `dis-ticaret` — Dış Ticaret & Ödemeler Dengesi

| id | evds_code | frek | birim | olcek | son nokta |
|---|---|---|---|---|---|
| `dis-ticaret/ihracat` | `TP.IHRACATBEC.9999` | 5 | Milyon USD | 0.001 | 2026-07 · 25.623 |
| `dis-ticaret/ithalat` | `TP.ITHALATBEC.9999` | 5 | Milyon USD | 0.001 | 2026-07 · 32.966 |
| `dis-ticaret/cari-denge` | `TP.ODANA6.Q01` | 5 | Milyon USD | — | 2026-06 · −4.194 |

İhracat/ithalat EVDS'te **Bin USD**; `olcek: 0.001` ile Milyon USD'ye
çevrilir ki cari denge ile aynı eksende karşılaştırılabilsin.

### Yeni kategori: `para-banka` — Para & Banka

| id | evds_code | frek | birim | olcek | son nokta |
|---|---|---|---|---|---|
| `para-banka/kredi-hacmi` | `TP.KREHACBS.A1` | 5 | Milyar TL | 0.000001 | 2026-07 · 26.352 |
| `para-banka/mevduat` | `TP.KM.F35` | 5 | Milyar TL | 0.000001 | 2026-07 · 28.269 |
| `para-banka/m3` | `TP.PBD.H17` | 5 | Milyar TL | 0.000001 | 2026-07 · 31.271 |
| `para-banka/rezervler` | `TP.AB.TOPLAM` | 2 | Milyon USD | — | 2026-08-28 · 188.198 |

Rezervler haftalık (Cuma) yayımlanır — `freq: weekly`, `evds_frequency: "2"`,
`monthly_agg: last` (stok büyüklüğü; haftaları toplamak ya da ortalamak
stoku yanlış gösterir).

### Mevcut kategorilere eklenenler

`ekonomi-makro` (+3):

| id | evds_code | frek | birim | olcek | son nokta |
|---|---|---|---|---|---|
| `ekonomi-makro/issizlik-orani` | `TP.TIG08` | 5 | % | — | 2026-07 · 8,1 |
| `ekonomi-makro/istihdam-orani` | `TP.TIG07` | 5 | % | — | 2026-07 · 48,3 |
| `ekonomi-makro/butce-dengesi` | `TP.KB.GEN35` | 5 | Milyar TL | 0.000001 | 2026-07 · −318,5 |

`enflasyon` (+4):

| id | evds_code | frek | birim | son nokta |
|---|---|---|---|---|
| `enflasyon/cekirdek-c` | `TP.FE25.OKTG04` | 5 | Endeks (2025=100) | 2026-08 · 133,34 |
| `enflasyon/ufe` | `TP.TUFE1YI.T1` | 5 | Endeks | 2026-08 · 5.781,74 |
| `enflasyon/tufe-enerji` | `TP.FE25.OKTG09` | 5 | Endeks (2025=100) | 2026-08 · 147,13 |
| `enflasyon/beklenti-12a` | `TP.PKAUO.S01.E.U` | 5 | % | 2026-08 · 23,69 |

`insaat` (+4):

| id | evds_code | frek | birim | son nokta |
|---|---|---|---|---|
| `insaat/konut-satis-ilk-el` | `TP.AKONUTSAT3.KTRTOPLAM` | 5 | Adet | 2026-07 · 42.529 |
| `insaat/konut-satis-ikinci-el` | `TP.AKONUTSAT4.KTRTOPLAM` | 5 | Adet | 2026-07 · 81.074 |
| `insaat/konut-fiyat-istanbul` | `TP.KFE.TR10` | 5 | Endeks | 2026-07 · 222,50 |
| `insaat/kira-endeksi` | `TP.YKKE.TR` | 5 | Endeks | 2026-07 · 328,50 (seri 2018-01'de başlar) |

`kredi-karti` (+5, sektör bazlı harcama tutarı, hepsi haftalık/Cuma,
`monthly_agg: sum`, birim Bin TL — mevcut `harcama-toplam` ile aynı birim,
bilinçli olarak ölçeklenmez ki toplamla aynı eksende dursun; hepsi
2014-03-07'den 2026-08-28'e 652 nokta):

| id | evds_code | son nokta (Bin TL) |
|---|---|---|
| `kredi-karti/market` | `TP.KKHARTUT.KT16` | 133.105.984 |
| `kredi-karti/akaryakit` | `TP.KKHARTUT.KT4` | 45.729.527 |
| `kredi-karti/giyim` | `TP.KKHARTUT.KT9` | 33.845.220 |
| `kredi-karti/yemek` | `TP.KKHARTUT.KT24` | 44.068.312 |
| `kredi-karti/havayollari` | `TP.KKHARTUT.KT10` | 8.347.690 |

Toplam: 6 + 3 + 4 + 3 + 4 + 4 + 5 = **29 seri**, katalog 40 → 69.

## Tek kod değişikliği: `olcek`'in ortak alana yükseltilmesi

### Bugünkü durum

`olcek` yalnızca `KAYNAK_ALANLARI["epias"]["istege_bagli"]` içinde; uygulama
noktası `ingest/epias.py::_olcekle`, çağrısı `epias.seri_cek`'in son
satırında. `core/catalog.py`'nin tablo yorumu kuralı açıkça yazıyor: *"bir
alan burada listelenmemişse o kaynak için YASAKTIR"* — çünkü onurlandırılmayan
bir alan grafiği fark edilmeden yanlış ölçekte çizdirir. İki test bu yasağı
EVDS için çiviliyor (`test_evds_serisi_olcek_tasiyamaz`,
`test_evds_serisi_acik_yazilmis_olcek_1_de_tasiyamaz`).

### Değişiklik

`olcek` artık **her kaynak tipi için onurlandırılır**, dolayısıyla tip
tablosundan çıkıp ortak alan setine girer:

```python
# Tipe değil, kataloğa ait alanlar: her kaynak için onurlandırılır,
# dolayısıyla hiçbir tip için yasak değildir.
ORTAK_ALANLAR = frozenset({"olcek"})
```

`TIPE_OZGU_ALANLAR` yalnızca tip tablosundaki alanların birleşimi kalır;
`_alan_sahipligini_dogrula`'nın red döngüsü `TIPE_OZGU_ALANLAR - izinli`
üzerinden yürüdüğü için `olcek` hiçbir tipte reddedilmez. Değer kontrolü
(`olcek > 0`) yerinde kalır.

Uygulama noktası orchestrator'a taşınır: `ingest/run.py::olcekle(df, olcek)`,
`_cek` adaptörden döndükten hemen sonra çağrılır ve `date` dışındaki **tüm**
sütunları ölçekler (geniş/kompozisyon serileri de tek çağrıda kapsanır).
`ingest/epias.py::_olcekle` ve içindeki çağrı silinir.

### Neden orchestrator

Değerlendirilen üç yol:

| | Yaklaşım | Karar |
|---|---|---|
| **A** | `olcekle`'yi `run.py`'ye taşı, `_cek` sonrası uygula | **Seçildi** |
| B | `evds.seri_cek` içine ikinci bir ölçekleme çağrısı ekle | Elendi: uygulama noktası kaynak sayısı kadar çoğalır; bir sonraki kaynak tipi aynı satırı üçüncü kez yazar |
| C | Kod değiştirme, birimi "Bin TL" yaz | Elendi: `26.351.644.811 Bin TL` KPI kartında okunamaz |

A, EPİAŞ'ın invariantını bozmaz: *"ölçekleme günlüğe indirgemeden SONRA
uygulanır"* — indirgeme adaptörün içinde bitiyor, `_cek` zaten indirgenmiş
çerçeve döndürüyor, dolayısıyla orchestrator'da uygulanan ölçek aynı sırayı
korur. Kazanç: tek uygulama noktası ve `olcek`'in kaynak-tipinden bağımsız
hale gelmesi.

### Etkilenen testler

Kontrat değiştiği için üçü güncellenir, ikisi silinir:

- **Silinir:** `test_evds_serisi_olcek_tasiyamaz`,
  `test_evds_serisi_acik_yazilmis_olcek_1_de_tasiyamaz` — artık geçersiz bir
  kuralı çiviliyorlar. Yerine `olcek`'in EVDS'te kabul edildiğini gösteren
  bir test gelir.
- **Güncellenir:** `test_olcek_verilmemisse_ingest_olceklemez`,
  `test_olcekle_sutun_listesiyle_coklu_sutunu_olcekler` (import yolu ve
  imza), `test_seri_cek_olceklendirmeyi_indirgemeden_sonra_uygular` ile iki
  kompozisyon ölçek testi (`epias.seri_cek` artık ölçeklemez → adaptör ham
  değer döndürür, ölçek `run` seviyesinde doğrulanır).
- **Eklenir:** `_cek`'in EVDS serisinde `olcek`i uyguladığını ve geniş
  serinin tüm sütunlarının ölçeklendiğini gösteren `run` testleri.

## `pano` ve devredilen iş #3

`Kategori.pano` faz3b'de eklendi ama yalnızca `elektrik` ve `otomotiv`
kullanıyor; kalan kategoriler `components.kpi_satiri`'nın `seriler[:4]`
konumsal seçimine düşüyor. Bu dilim her kategoriye seri sayısı 4'ü aştığı
için o borcu görünür kılıyor, dolayısıyla **sekiz eski + üç yeni kategorinin
tamamına `pano` yazılır**. `pano_serileri` bilinmeyen id'de `KatalogHatasi`
yükselttiği için yazım hatası sessiz kalmaz.

Seçilen panolar sektör ilgisine göre: örneğin `sanayi` →
üretim endeksi, KKO, reel kesim güven, öncü göstergeler; `dis-ticaret` →
ihracat, ithalat, cari denge; `para-banka` → kredi hacmi, mevduat, M3,
rezervler.

## İkinci kod değişikliği: seri bazında yayın gecikmesi

Uygulama sırasında ortaya çıktı, tasarımda yoktu. Tam ingest sonrası Veri
Takvimi iki yeni seriyi kalıcı olarak "dikkat gerektiriyor" bandına düşürdü:
`sanayi/uretim-endeksi` ve `dis-ticaret/cari-denge` — ikisinin kaynağı da
dönem sonundan ~42 gün sonra yayımlıyor, dolayısıyla bir sonraki dönem
gelene kadar 69 gün geçiyor ve aylık eşiğin (50 gün) altına hiç inmiyorlar.

Kalıcı alarm, takvimin tek sözleşmesini yok eder: *"bir seri geciktiğinde ya
kaynak geç kalmıştır ya da bizim ingest'imiz sessizce kırılmıştır."* Kırmızı
satır her gün kırmızıysa kimse bakmaz. `core/takvim.py`'nin docstring'i bu
durumu öngörmüştü: *"Seri bazında geçersiz kılma bilinçli olarak eklenmedi —
hangi serinin gürültü çıkaracağı henüz bilinmiyor."* Artık biliniyor.

Eklenen alan: `Seri.gecikme_gunu: int | None` (ortak alan, `ORTAK_ALANLAR`).
`durum_hesapla(freq, bekleme_gunu, gecikme_gunu=0)` eşiği o kadar genişletir;
`ESIKLER` sabiti ve tüm diğer seriler değişmez. Katalogda yalnızca bu iki
seri `gecikme_gunu: 25` taşır ve bir test alanın diğer serilere yayılmasını
fark ettirir (yayılırsa eşik anlamsızlaşır). Değer kontrolü: pozitif olmalı —
`0` alanı gereksiz yazmaktır, negatif eşiği daraltıp sahte "gecikmiş" üretir.

Alternatif olarak eşiği (`ESIKLER["monthly"] = 50 → 75`) topluca gevşetmek
de mümkündü; elendi, çünkü zamanında yayımlanan 30+ aylık serinin gerçek
gecikmesini 25 gün boyunca gizlerdi.

## Sayfa yükü (devredilen iş #17)

Yeni serilerin 24'ü aylık, 6'sı haftalık; EVDS'in varsayılan 15 yıllık
penceresi aylık seride ~180, haftalık seride ~650 nokta veriyor
(`start_date` yazılmadı — katalogdaki hiçbir seri yazmıyor). Üç yeni
sayfanın en büyüğü 6 aylık seri; `kredi-karti` haftalık altı seriyle en ağır
yeni sayfa. `emtia-metaller`'in ~1,4 MB'lık yükü bu dilimde büyümüyor;
#17 açık kalır ve bu dilimde ele alınmaz.

## Doğrulama (uygulama sonrası ölçüldü)

1. **Testler:** `pytest` 285 geçti, 4 ağ testi hariç tutuldu. Kapsam:
   `olcek`'in EVDS'te kabul edildiği, ortak alan setinin tip yasaklarını
   (`yahoo` + `evds_code`) gevşetmediği, her kategorinin `pano`sunun geçerli
   ve tek değerli id'lere işaret ettiği, `run.olcekle`'nin `None`'da
   dokunmadığı / tarih dışı tüm sütunları çarptığı / girdiyi mutasyona
   uğratmadığı, `_cek`'in ölçeği uyguladığı, `epias.seri_cek`'in artık ham
   değer döndürdüğü, `durum_hesapla`'nın `gecikme_gunu` ile gerçek gecikmeyi
   gizlemediği.
2. **Tam ingest:** `python -m ingest.run` → **69/69 seri başarılı** (236 sn).
   29 yeni CSV'de tekrar eden tarih, sıra bozukluğu ve NaN yok; son değerler
   yukarıdaki tablolarla tutarlı.
3. **Ölçekleme regresyonu:** `data/elektrik/*.csv` diff'i yalnızca revizyon
   ve yeni gün içeriyor; GWh büyüklükleri (~900) korunmuş — ölçekleme
   adaptörden orchestrator'a taşınırken EPİAŞ serileri bozulmadı.
4. **Tarayıcıda:** 11 kategori menüde; `sanayi`, `dis-ticaret`, `para-banka`
   panolarıyla render oldu; ölçekli KPI'lar okunur ("26.351,64 Milyar TL",
   "25.622,85 Milyon USD"); Genel Bakış 11 kartta 69 seri sayıyor; Veri
   Takvimi **69 seri · 69 güncel · 0 dikkat gerektiriyor**.

## Riskler

1. **EVDS rebasing.** `TP.FE25.*` serileri 2025=100 bazlı; TÜİK baz yılını
   değiştirdiğinde kod ölür ve seri boş döner. `noktalari_ayikla` alan adı
   bulunamazsa hata verir — sessiz sıfır yazmaz; Veri Takvimi de seriyi
   "bekleniyor" bandına düşürür.
2. **Yayın gecikmesi farkı.** Sanayi üretim endeksi ve cari denge bir dönem
   geriden gelir; bu iki seri `gecikme_gunu: 25` ile takvimde normal
   karşılanır (bkz. "İkinci kod değişikliği"). Kaynak takvimini kalıcı
   olarak değiştirirse alan güncellenmeli.
3. **`olcek` ortak alana çıkınca yeni bir sessiz yanlışlık kapısı.** Bir
   sonraki adaptör `_cek`'in dışında kendi ölçeğini uygularsa çift ölçekleme
   olur. `run.olcekle`'nin tek uygulama noktası olduğu docstring'e yazılır ve
   `run` testiyle korunur.
4. **`pano` yazım hatası.** `pano_serileri` hata yükselttiği için sayfa
   sessizce KPI'sız kalmaz; kırılırsa açıkça kırılır.

## Kapsam dışı

- **Turizm.** EVDS'in `TP.TURIZMYZS.GK178629` serisi 2026-03'te duruyor
  (5 ay gecikme); Takvim'i sahte alarmla doldurur. Zamanlı veri YİGM'de,
  ayrı dilim.
- **KKM.** `TP.KKM.K4` son değeri `0` — program söndü, ölü seri.
- **TÜFE COICOP alt kırılımı (349 seri) ve kredi kartı sektör
  kompozisyonu.** İkisi de çok-kodlu geniş seri altyapısı ister;
  `epias_bilesenler` tek uçtan gelen bileşenler için tasarlandı. Ayrı dilim.
- **Yapı ruhsatı.** `bie_inyprh2` 176 seri; hangi kırılımın (daire sayısı /
  yüzölçüm / değer, devlet-özel-kooperatif) gösterileceği ayrı bir karar.
- **Seri bazında ondalık basamak (devredilen iş #5)** ve
  **`emtia-metaller` sayfa yükü (#17)**: bu dilimin serileri iki basamakla
  doğru görünüyor ve yükü büyütmüyor.

## Stack

Python 3.12 · Streamlit · pandas · Plotly · PyYAML · requests ·
pdfplumber (yalnızca ingest) · pytest · GitHub Actions ·
Streamlit Community Cloud. **Yeni bağımlılık yok.**
