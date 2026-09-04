# Faz 3e — Otomotiv Sektörü (OSD) Tasarım Spec'i

Tarih: 2026-09-04
Durum: Onaylandı (kullanıcı onayı: 2026-09-04, sohbet içi, üç bölüm ayrı ayrı)

## Amaç

Otomotiv kategorisini açmak: OSD (Otomotiv Sanayii Derneği) aylık üretim
bültenlerinden 13 firmanın aylık toplam üretimini çekmek. Bu, dashboard'un ilk
**PDF kaynaklı** dilimi ve Faz 4'teki hisse sayfalarının (FROTO, TOASO, KARSN,
TTRAK, OTKAR, ASUZU) üretim tarafının temeli.

## Keşif bulguları

Canlı bültene karşı ölçüldü (Temmuz 2026 bülteni, 15 sayfa) — uydurma değil.

### Bülten yapısı

| Sayfa | İçerik |
|---|---|
| 2 | Firma × araç tipi, **bültenin ayı**, `TOPLAM` sütunu dahil (19 sütun) |
| 3 | Aynı tablo, yıl kümülatif |
| 4 | Araç tipi × yıl karşılaştırma |
| 5 | Araç tipi × ay, iki yıl |
| **6–9** | **Firma × ay**, araç tipi bölümlerinde (14 sütun: tip + 12 ay + toplam) |
| 10–14 | Model bazında üretim |
| 15 | Kapasite kullanımı |

### Doğrulanan gerçekler

1. **Tablolar makine-okunur.** PDF taranmış görüntü değil; `pdfplumber` 15
   sayfanın tamamında tablo çıkarıyor.
2. **6–9. sayfa toplamı = 2. sayfa TOPLAM sütunu.** 13 firmanın 13'ünde de
   fark 0. Bu, aşağıdaki tarihsel doldurma kararının doğruluk kanıtıdır ve
   ayrıştırıcıya gömülü bir öz-doğrulama olarak kalır.
3. **Format kararlı.** Aralık 2024 bülteni ile Temmuz 2026 bülteni aynı
   sayfada, aynı 26×14 tablo şeklinde, aynı başlık düzeninde.
4. **URL'ler türetilemez.** İndirme yolu yükleme tarihini gömüyor
   (`/saved-files/PDF/2026/08/17/Otomotiv_Sanayii_Uretim_Bulteni-2026.07.pdf`),
   dolayısıyla indeks sayfası kazınmak zorunda. HTML'de yollar ters bölü
   içeriyor (`/saved-files\PDF\2026\08\17\...`) ve düz bölüye çevrilmeli.
5. **Eski PDF'lerde font kodlaması bozuk.** Aralık 2024 bülteninde başlıklar
   Türkçe karakterlerde `\x00` sızdırıyor (`"T\x00pler"`). Sayısal hücreler
   temiz. Firma adı normalizasyonu zorunlu.
6. **Dosya adı tutarsız.** 2022 alt çizgi (`Bulteni_2022.12.pdf`), 2023 ve
   sonrası tire (`Bulteni-2023.12.pdf`) kullanıyor. Desen ikisini de kabul
   etmeli.

### 13 firma (bültendeki ham adlarıyla)

`A.I.O.S.` · `FORD OTOSAN` · `HATTAT TRAKTÖR` · `HYUNDAI MOTOR TÜRKİYE` ·
`KARSAN` · `M. BENZ TÜRK` · `MAN TÜRKİYE` · `OTOKAR` · `OYAK RENAULT` ·
`TEMSA` · `TOFAŞ` · `TOYOTA` · `TÜRK TRAKTÖR`

`TOPLAM / TOTAL` bir firma değil, alt toplam satırıdır ve dışlanır.

## Karar: hangi sayfa okunur ve kaç PDF çekilir

İki yol vardı:

| Yol | Kaynak | 2022-01→bugün için PDF sayısı |
|---|---|---|
| 2. sayfa (tek ay, TOPLAM hazır) | her ay bir bülten | **~56** |
| **6–9. sayfa (firma × ay)** | bir bülten o yılın tamamı | **5** |

İkincisi seçildi. Kural: **her yılın Aralık bülteni** o yılın 12 ayını taşır;
**en güncel bülten** cari yılı taşır.

İndeks sayfası yıl başına tam olarak bir dosya sunuyor ve doğrulandı:
`2022.12` (alt çizgili adlandırma), `2023.12`, `2024.12`, `2025.12` (tireli)
ve `2026.07` (güncel) — **beş PDF, 2022-01'den cari aya**. 2022 bülteni de
modern formatta (15 sayfa, s2 15×19, s6 26×14, `TOPLAM Total` sütunu yerinde).

**2021 ve öncesi kapsam dışı:** o yıllar `Üretim Bülteni _YYYY.pdf` biçiminde
farklı adlandırmayla ve doğrulanmamış iç formatla duruyor. Dahil etmek ayrı
bir doğrulama ve ikinci bir ayrıştırma yolu gerektirirdi.

Bu, deponun mevcut **"her koşuda tam pencereyi yeniden çek"** ilkesini korur:
revizyonlar yakalanır, CSV deterministik olarak yeniden üretilir. Artımlı
biriktirme (yalnızca son bülteni okuyup CSV'ye eklemek) bu ilkeyi kırardı ve
kaçırılan tek bir koşu kalıcı bir delik bırakırdı.

**Ocak kenar durumu:** Ocak ayında en güncel bülten, önceki yılın Aralık
bültenidir (ayın ortasında yayımlanır) ve Aralık bültenleri listesiyle
çakışır. Noktalar `(firma, tarih)` üzerinden tekilleştirilir.

## Öz-doğrulama

Ayrıştırıcı, bültenin kendi ayı için 6–9. sayfa firma toplamlarını 2.
sayfanın `TOPLAM` sütunuyla karşılaştırır. Tutmazsa `RuntimeError` yükselir.

Gerekçe: OSD şablonu değiştirirse (sütun eklenir, bölüm kaldırılır, firma adı
değişir) sessizce eksik veri üretmek yerine ingest kırılır ve Veri Takvimi
gecikmeyi gösterir. Bu, Faz 3c'de `bilesen_noktalari_ayikla`'nın bilinmeyen
alanda `KeyError` fırlatmasıyla aynı felsefedir: sessiz yanlış veri, gürültülü
hatadan kötüdür.

## Mimari

```
catalog/
  categories.yaml     # `otomotiv` kategorisi + pano
  series.yaml         # 13 seri, kaynak_tipi: osd
core/
  catalog.py          # GECERLI_KAYNAK_TIPLERI += "osd"; Seri.osd_firma;
                      # KAYNAK_ALANLARI'na osd satırı
ingest/
  osd.py              # YENİ — indeks kazıma + PDF ayrıştırma + öz-doğrulama
  run.py              # _cek() dördüncü dal: osd; koşu başına PDF önbelleği
requirements.txt          # uygulama — DEĞİŞMEZ
requirements-ingest.txt   # YENİ — `-r requirements.txt` + pdfplumber
.github/workflows/ingest.yml  # requirements-ingest.txt kurar
```

### `ingest/osd.py`

Üç saf katman ağdan ayrık ve fixture'la test edilir; ağ yalnızca `seri_cek`
kabuğundadır:

```python
INDEKS_URL: str
def bulten_baglantilari(html: str) -> dict[str, str]   # "2026.07" -> tam URL
def cekilecek_bultenler(baglantilar: dict, bugun: date, gecmis_yil: int) -> list[str]
def firma_adini_normalize(ham: str) -> str             # \x00 ve boşluk temizliği
def firma_aylik_noktalari(pdf) -> list[tuple[str, str, float]]  # (firma, YYYY-MM-01, adet)
def dogrula(pdf, noktalar) -> None                     # s2 TOPLAM ile karşılaştır
def seri_cek(seri, onbellek=None, session=None, bugun=None) -> pd.DataFrame
```

**PDF önbelleği:** 13 seri aynı beş PDF'i paylaşır. Koşu başına tek `dict`
paylaşılır (Faz 3c'deki EPİAŞ dilim önbelleği kalıbı birebir); yoksa 78
indirme olurdu (13×5). Önbellek isteğe bağlıdır; verilmezse davranış değişmez.

### Katalog

`Seri.osd_firma: str | None` — bültendeki ham firma adı. `KAYNAK_ALANLARI`'na:

```python
"osd": {"zorunlu": ("osd_firma",), "istege_bagli": ("start_date",)},
```

Seriler `otomotiv` kategorisinde, birim `adet`, `freq: monthly`,
`monthly_agg: sum`, `charts: [level, seasonality]`.

Kategori panosu: portföy ilgisi olan dört firma —
`otomotiv/ford-otosan`, `otomotiv/tofas`, `otomotiv/turk-traktor`,
`otomotiv/karsan`.

## Doğrulama stratejisi

1. Saf fonksiyonlar ağsız pytest ile: bağlantı çıkarma, bülten seçimi
   (Ocak kenar durumu dahil), ad normalizasyonu (`\x00` içeren gerçek örnekle),
   nokta çıkarma, öz-doğrulamanın hem geçen hem kırılan hâli.
2. Ağ smoke testi (`@pytest.mark.network`): indeks sayfası çekilir, en az bir
   bülten bağlantısı bulunduğu ve URL'in `.pdf` ile bittiği doğrulanır.
3. Gerçek veri bir kez çekilir. Kabul ölçütleri:
   - 13 seri de nokta üretir
   - Tarih aralığı 2022-01 → cari ay
   - Tarihler tekil ve artan
   - Ford Otosan aylık üretimi ~20.000–45.000 adet bandında
   - Türk Traktör ~1.000–5.000 bandında
   - Tüm firmaların bir aydaki toplamı, o ayın sektör toplamıyla tutarlı
4. Tarayıcıda: `/otomotiv` sayfası panosuyla render olur, 13 kart çizilir,
   konsol ve sunucu logu temiz.

## Riskler

1. **OSD şablon değişikliği ayrıştırıcıyı kırar.** Öz-doğrulama bunu sessiz
   olmaktan çıkarır; modül bazlı hata izolasyonu diğer 27 seriyi korur.
2. **İndeks sayfası yapısı değişirse** bağlantı bulunamaz. `bulten_baglantilari`
   hiç bağlantı bulamazsa `RuntimeError` yükseltir — boş liste döndürüp sessizce
   devam etmez.
3. **Eski PDF font kodlaması.** Normalizasyon fonksiyonu ve testi zorunlu;
   normalizasyon başarısız olursa firma katalogla eşleşmez ve o seri boş kalır
   — öz-doğrulama bunu yakalar.
4. **`pdfplumber` Streamlit Cloud'a sızarsa** uygulama gereksiz büyür.
   `requirements.txt` bu dilimde değişmez; ayrım testle değil, workflow ve
   dosya içeriğiyle güvenceye alınır.
5. **Bülten yayın gecikmesi.** OSD ayın 12–18'i arası yayımlıyor; cari ayın
   verisi bir sonraki bültene kadar görünmez. Veri Takvimi'nin aylık eşiği
   (dönem sonundan 50 gün) bunu normal karşılar.

## Kapsam dışı

Araç tipi kırılımı (kompozisyon kalıbına uygun ama ayrı dilim), model bazında
üretim, kapasite kullanımı (15. sayfa), ihracat (ayrı OSD bülteni),
ODMD / ACEA / Indicata kaynakları, firmaların kendi aylık duyuruları
(FROTO ve TTRAK için OSD'den bir hafta önce yayımlanıyor — hız avantajı ayrı
bir dilimin konusu).

## Stack

Python 3.12 · Streamlit · pandas · Plotly · PyYAML · requests · **pdfplumber
(yalnızca ingest)** · pytest · GitHub Actions · Streamlit Community Cloud.
