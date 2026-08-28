# Faz 3b — Elektrik Sektörü Tasarım Spec'i

Tarih: 2026-08-28
Durum: Onaylandı (kullanıcı onayı: 2026-08-28, sohbet içi)

## Amaç

İlk sektör sayfasını uçtan uca kurmak: yeni bir kaynak tipi (EPİAŞ Şeffaflık
Platformu 2.0 REST API), üç yeni seri ve kategori sayfasına eklenen bir
**pano** bileşeni. Bu dilim kalan sekiz sektörün şablonudur.

Elektrik seçildi çünkü dokuz sektör içinde birinci sınıf açık API'si olan tek
kaynak odur. Bankacılık (BDDK), Otomotiv (OSD) ve Sigortacılık (TSB) bülten
kazıma gerektirir; sektör sayfası mimarisini kırılgan bir kazıma katmanıyla
aynı anda kurmak ikisini de bulanıklaştırırdı.

## Kapsam

### Giren: üç EPİAŞ serisi

| Seri | Birim | Kaynak frekansı | Aylık toplama |
|---|---|---|---|
| Toplam elektrik üretimi | GWh | günlük | `sum` |
| Piyasa takas fiyatı (PTF) | TL/MWh | günlük | `mean` |
| Baraj doluluk oranı | % | günlük | `mean` |

Üçü de yeni `elektrik` kategorisine girer.

### Çıkan: iki yetenek, gerekçeleriyle

**Kaynak bazlı üretim payları** (doğalgaz, hidroelektrik, rüzgar, güneş,
kömür, jeotermal, biyo/atık) bu dilime alınmıyor. Sayfanın imza grafiği
olmasına rağmen: mevcut `Seri` modeli tek seri–tek değerdir ve yedi kaynağı
tek grafikte legend'lı göstermek **çok serili grafik** yeteneği ister.
`core/charts.py` bugün yalnızca tek seri çizer. Bu, kendi başına bir dilimdir
(Faz 3c); sektör mimarisiyle birlikte kurulursa ikisi de yarım kalır.

**Eurostat Türkiye–Avrupa elektrik fiyatı karşılaştırması** de alınmıyor.
Dördüncü bir kaynak tipi demek; EPİAŞ dilimi otururken araya sıkıştırılmamalı.

## Çerçeve kararı: `sectors.yaml` bu dilimde kurulmuyor

marketvisuals'ta sektör, **kategoriler arası** bir eksendir — Elektrik sayfası
EPİAŞ ve Eurostat'tan birlikte beslenir. Bizim v1'imizde ise üç serinin üçü de
tek kaynaktan gelir, yani `sektör` ile `kategori` birebir örtüşür.

Bu durumda ikinci bir eksen (`catalog/sectors.yaml`) kurmak, bugün hiçbir şeyi
ayırmayan bir soyutlama olurdu. Bunun yerine **`Kategori` isteğe bağlı bir
`pano` alanı kazanır**: hangi serilerin başlık metriği olduğunu ve sırasını
tutar.

Sayfa şekli marketvisuals'ınkiyle aynı kalır; yalnızca altındaki eksen sayısı
bir eksiktir.

### Yükseltme tetiği

Bir sayfanın birden çok kategoriden seri çekmesi gerektiği ilk anda
`sectors.yaml` ekseni açılır. Somut tetikleyiciler:

- Eurostat fiyat serisi eklendiğinde (Elektrik sayfası iki kategoriden beslenir)
- Bankacılık sayfası BDDK ve EVDS serilerini birleştirdiğinde

O ana kadar tek eksen yeterlidir. Bu bir geri adım değil, ertelenmiş bir
karardır: kullanıcıya giden sayfa aynı sayfadır.

## Mimari

```
catalog/
  categories.yaml     # `elektrik` kategorisi + `pano` alanı
  series.yaml         # üç yeni seri, kaynak_tipi: epias
core/
  catalog.py          # Kategori.pano; GECERLI_KAYNAK_TIPLERI += "epias"
  page.py             # pano render'ı; takvim kategoriye filtreli
  takvim.py           # takvim(kategori=None) parametresi
ingest/
  epias.py            # YENİ — TGT auth + endpoint sözlüğü + seri_cek
  run.py              # _cek() üçüncü dal: epias
```

### `ingest/epias.py`

`evds.py`'nin biçimini izler — saf yardımcılar ağdan ayrık, tek I/O kabuğu:

```python
UCLAR: dict[str, str]                                    # endpoint sözlüğü
def tgt_al(kullanici, parola, session) -> str            # ticket, ~2 saat geçerli
def noktalari_ayikla(yanit: dict, alan: str) -> list[tuple[str, float]]
def seri_cek(seri, kimlik, session=None) -> pd.DataFrame # run.py'nin arayüzü
```

Kimlik `EPIAS_USERNAME` ve `EPIAS_PASSWORD` ortam değişkenlerinden okunur.
TGT tek seferde alınıp üç serinin çekiminde paylaşılır; her çağrıda yeniden
ticket almak throttle'a takılır.

### Endpoint yolları implementasyonda doğrulanır

Kesin endpoint yolları bu spec'te sabitlenmiyor: yazarken elimizde EPİAŞ
kimlik bilgisi yoktu ve uydurma bir yol spec'i yanlış yönlendirirdi. Yollar
tek bir `UCLAR` sözlüğünde toplanır ve implementasyon sırasında
[teknik dokümana](https://seffaflik.epias.com.tr/electricity-service/technical/tr/index.html)
karşı doğrulanır. Yanlış çıkarsa tek yerde düzelir.

### Pano

`Kategori.pano: tuple[str, ...] = ()` — seri id'leri, gösterim sırasında.
Boşsa pano hiç render olmaz; mevcut altı kategori değişmeden çalışır.

Her pano kartı: seri başlığı, son değer + birim, son dönem, MoM/YoY değişim.
Bileşenler `core/components.py`'deki `kpi_satiri`'dan türetilir — yeni
istatistik hesabı yazılmaz, `core/stats.py` olduğu gibi kullanılır.

### Takvim filtresi

`takvim(bugun=None, kategori=None)` — `kategori` verilirse yalnızca o
kategorinin serileri döner. Global Veri Takvimi sayfası parametresiz çağırır,
davranışı değişmez.

## Doğrulama stratejisi

1. Saf fonksiyonlar (`noktalari_ayikla`, pano seçimi, takvim filtresi) ağsız
   pytest ile — mevcut `tests/test_evds.py` bu kalıbı kuruyor.
2. Ağa çıkan tek test `@pytest.mark.network` işaretli smoke test; CI'da atlanır.
3. Tarayıcıda: Elektrik kategorisi sayfası panosuyla render olur, üç grafik
   gerçek veriyle çizilir, konsol ve sunucu logu temiz.
4. `python -m ingest.run --only elektrik/...` üç seri için de gerçek EPİAŞ'a
   karşı bir kez koşturulmuş olmalı.

## Riskler

1. **Bloke edici ön koşul: EPİAŞ kaydı.** API'nin açık uçlu endpoint'i yok;
   kullanıcı adı/parola ile TGT alınır.
   [kayit.epias.com.tr](https://kayit.epias.com.tr/epias-transparency-platform-registration-form)
   üzerinden kayıt ve `EPIAS_USERNAME`/`EPIAS_PASSWORD` repo secret'ları
   gerekir. Kayıt olmadan kod ve testler yazılabilir, ancak dilim
   "tamamlandı" sayılamaz.
2. **Endpoint yolları doğrulanmamış** — yukarıda gerekçesiyle açıklandı;
   `UCLAR` sözlüğünde izole.
3. **TGT süresi.** Ticket ~2 saat geçerli; ingest koşusu dakikalar sürdüğü
   için tazeleme mantığı gerekmez. Gerekirse ileride eklenir.
4. **Baraj doluluk serisinin EPİAŞ'ta bulunması doğrulanmadı.** Şeffaflık
   Platformu'nda mevcut olduğu biliniyor ancak endpoint teyit edilmedi;
   çıkmazsa seri bu dilimden düşer ve dilim iki seriyle tamamlanır.

## Stack

Python 3.12 · Streamlit · pandas · Plotly · PyYAML · requests · pytest ·
GitHub Actions (cron) · Streamlit Community Cloud

Yeni çalışma zamanı bağımlılığı yok: `eptr2` yerine ince kendi istemcimiz
yazılıyor. Gerekçe — dört endpoint için 175 servislik bir kütüphane taşımak,
`requirements.txt` ingest ve uygulama tarafından paylaşıldığı için Streamlit
Cloud'a da kurulurdu.
