# Faz 3a — Veri Takvimi Tasarım Spec'i

Tarih: 2026-08-27
Durum: Onaylandı (kullanıcı onayı: 2026-08-27, sohbet içi)
Önceki spec'ler: `2026-08-27-streamlit-dashboard-design.md` (Faz 1),
`2026-08-27-faz2-emtia-design.md` (Faz 2)

## Amaç

Panoya bir **Veri Takvimi** sayfası eklemek: her serinin son ne zaman
güncellendiğini, ne kadar süredir yeni veri gelmediğini ve bunun o serinin
frekansı için normal olup olmadığını tek ekranda göstermek.

## Faz 3'ün ayrıştırılması

Faz 3 yol haritasında "9 sektör sayfası" olarak duruyor. İnceleme gösterdi ki
tek bir sektör sayfası (Otomotiv) şu kaynakları istiyor: TÜİK, TCMB, ACEA,
ODMD, OSD, Indicata/BETAM, artı altı şirketin yatırımcı sunumu. Dokuz sektör
50+ kaynak eder — tek bir spec'e sığmaz.

**Faz 3 dört dilime ayrıldı** (kullanıcı onaylı), kaynak zorluğuna göre
sıralanmış:

| Dilim | İçerik | Durum |
|---|---|---|
| **3a** | Veri Takvimi — mevcut serilerin tazelik monitörü | **bu spec** |
| 3b | EVDS'ten ulaşılabilen sektörel göstergeler | planlandı |
| 3c | Tek sektörün tam dikey dilimi (kazıma dahil), şablon olarak | planlandı |
| 3d+ | Kalan sektörler, 3c'nin şablonuyla | planlandı |

Bu sıra riski sona yığar: ilk iki dilim kanıtlanmış altyapıyla çalışır, kazıma
ancak üçüncü dilimde girer.

### Sektör sayfası kabuğu bu dilimde kurulmuyor

3a'nın ilk taslağı sektör sayfası kabuğunu da içeriyordu. Elendi: sektör
verisi 3b ve 3c'den önce gelmiyor, dolayısıyla şimdi kurulan dokuz sayfa
neredeyse boş kalır ve panoyu açan için değer üretmez. Kabuk 3c'de, doldurulacak
gerçek veri görüldükten sonra tasarlanacak.

## Çerçeve kararı: takvim değil, tazelik monitörü

marketvisuals.net'in Veri Takvimi'i **ileriye** bakar: "TÜFE 22 Eylül'de
açıklanacak." Sitenin kendi notu bunun elle küratörlendiğini söylüyor:
*"Tarihler ilgili kurumların yayınladığı resmi takvimlerden elle alınmıştır."*

Bizde sitede olmayan bir girdi var: **her serinin son gözlem tarihi ve frekansı
katalogda.** Aynı tablo geriye bakacak şekilde kurulabilir — *"bu serinin verisi
bayat mı?"*

Şirket içi bir araç için bu daha keskin bir soru. Bir seri beklenenden geç
kalıyorsa iki ihtimal vardır: kaynak gecikmiştir ya da **bizim ingest'imiz
sessizce kırılmıştır.** İkincisi bugün ancak tesadüfen fark edilir — Actions
kırmızıya dönerse görülür, ama Yahoo bir sembol için sessizce boş dönerse ya da
bir EVDS kodu geçersizleşirse koşu yeşil kalıp veri donabilir. Bu sayfa o sessiz
kırılmanın tek görünür yeri olur.

### Değerlendirilip elenen yaklaşımlar

| | Yaklaşım | Neden elendi |
|---|---|---|
| B | Yayın takvimi (siteye sadık) | Sayfa değer üretmeden önce 23 kuralın küratörlenmesini ve sonra bakımını gerektirir. Bayatlayan bakım yükü. |
| C | İkisi birden | En zengin, ama B'nin bakım yükünü ilk günden üstlenir. A'nın opsiyonel alanı C'ye giden yolu zaten açık bırakıyor. |

## Hesaplama modeli

Tablonun tamamı katalogdan ve veriden türetilir. Hiçbir satır elle girilmiş
tarihe bağımlı değildir.

Her seri için:

| Alan | Kaynak |
|---|---|
| Son dönem | CSV'nin son satırının tarihi |
| Bekleme süresi | bugün − son dönem (gün) |
| Durum | frekansa göre eşikle karşılaştırma |
| Sıklık, kategori, kaynak, başlık | katalog |

Durum üç değer alır:

```
güncel      — son gözlem eşiğin içinde
bekleniyor  — eşik aşıldı, veri henüz gelmedi
gecikmiş    — eşiğin belirgin ötesinde (eşiğin 2 katı)
```

### Eşikler

`core/takvim.py`'de tek yerde sabit:

| Frekans | Eşik | Gerekçe |
|---|---|---|
| `daily` | 5 gün | uzun hafta sonu + resmî tatil |
| `weekly` | 14 gün | iki periyot |
| `monthly` | 50 gün | bir periyot + tipik yayın gecikmesi |

**Bu eşikler sezgiseldir ve öyle olduğu açıkça belirtilir.** Az sayıda,
görünür ve tek yerdeler. Seri bazında geçersiz kılma bu dilimde eklenmiyor —
hangi serinin gürültü çıkaracağı bilinmiyor. Gürültü görülürse eklenir.

Mevcut dağılım: 13 günlük, 7 aylık, 3 haftalık seri.

### Yayın kuralı motoru kurulmuyor

Onaylanan yaklaşımda editoryal kural "opsiyonel zenginleştirme"dir. Bu dilimde
**serbest metin** olarak alınır, hesaplanan tarih olarak değil:

```yaml
  yayin_notu: "TÜİK, takip eden ayın 3'ünde açıklar"
```

Tabloda olduğu gibi gösterilir. Tarih ayrıştıran ve sonraki oluşumu hesaplayan
bir motor gerçek bir iştir ve bugün hiçbir serinin böyle bir kuralı girilmiş
değildir. Serbest metin editoryal değerin neredeyse tamamını sıfır kodla verir
ve bayatlamaz — çünkü bir tarih değil, bir örüntü tarifidir.

**Alan kurulur ama hiçbir seriye doldurulmaz.** Yayın ritimleri doğrulanmadan
yazılırsa yanlış bir not hiç not olmamasından kötüdür: tabloya bakan kişi ona
güvenip veriyi boşuna bekler. Doldurmak kullanıcının işidir ve bir YAML
satırıdır.

## Mimari

Mevcut dikiş birebir izlenir: saf hesaplama Streamlit'ten ayrı.

```
core/takvim.py       # saf: durum hesabı, eşikler, sıralama. Streamlit importu YOK.
core/page.py         # + veri_takvimi_sayfasi()
app.py               # "Genel" grubuna ikinci sayfa
catalog/series.yaml  # + opsiyonel yayin_notu (boş)
core/catalog.py      # Seri.yayin_notu alanı
tests/test_takvim.py
```

`core/takvim.py`, `core/stats.py` ve `core/charts.py` ile aynı sınıfa aittir:
saf, test edilebilir, Streamlit'e bağımsız. Render `core/page.py`'ye gider.

### Sayfa yapısı

İki bölüm.

**Üstte, yalnızca sorun varsa görünen uyarı bloğu:**

```
⚠ 2 seri bekleniyor
   Konut Fiyat Endeksi — 58 gündür yeni veri yok (aylık)
   Yabancı Yatırımcı DİBS — 21 gündür yeni veri yok (haftalık)
```

Sorun yoksa bu blok hiç render edilmez.

**Altta tam tablo**, `st.dataframe` ile. Sütunlar:

`Veri · Kategori · Son Dönem · Durum · Sıklık · Kaynak · Yayın notu`

Sıralama sabit: önce durum ciddiyeti (gecikmiş → bekleniyor → güncel), sonra
bekleme süresi azalan. Sorunlar en üstte. Katalog sırası burada anlam taşımaz,
dolayısıyla KPI satırındaki konumsal tuzak yoktur.

23 satır için tablo doğru görsel dildir ve 100 satıra ölçeklenir.

### Navigasyon

"Genel" grubuna, Genel Bakış'ın yanına. Bir veri kategorisi değil, panonun
kendisi hakkında bir sayfadır — kategori sayfalarıyla aynı grupta olmaz.

## Doğrulama stratejisi

1. `pytest` yeşil:
   - Durum hesabı sentetik tarihlerle: her üç frekans, eşik sınırının iki yanı,
     `güncel`/`bekleniyor`/`gecikmiş` ayrımı
   - Sıralama: gecikmiş satırlar bekleniyor'un, o da güncel'in üstünde
   - Katalog: `yayin_notu` opsiyonel, yokluğunda `None`
   - Mevcut 94 test kırılmadan geçmeli
2. Tarayıcı: sayfa gerçek veriyle; uyarı bloğunun sorun yokken görünmemesi ve
   sentetik bir bayat seriyle görünmesi
3. Actions ve ingest bu dilimde hiç değişmez — diff `ingest/` altına dokunmamalı

## Riskler

1. **Eşikler sezgiseldir.** Yanlış ayarlanırsa ya sürekli yanlış alarm verir ya
   da gerçek bir donmayı kaçırır. Azaltma: eşikler tek yerde, açıkça sezgisel
   olarak belgeli, ilk gerçek kullanımda gözden geçirilecek.
2. **Sayfa yalnızca bizim çektiğimiz veriyi bilir.** Kaynak yayınladığı hâlde
   bizim ingest'imiz almadıysa "bekleniyor" der ama nedenini söyleyemez. Bu
   kabul edilen bir sınırdır; sayfanın işi soruyu ortaya çıkarmak, cevaplamak
   değil.
3. **Bugün tarihi test edilebilirliği.** Durum hesabı "bugün"e bağlıdır;
   fonksiyonlar `bugun` parametresi alır ki testler sabit tarihlerle koşsun —
   `ingest/evds.py`'deki kalıbın aynısı.

## Stack

Değişiklik yok: Python 3.12 · Streamlit ≥1.49 · pandas · PyYAML · pytest
