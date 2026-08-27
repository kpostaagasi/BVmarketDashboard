# Faz 1 — devredilen işler

Tarih: 2026-08-27
Kaynak: Faz 1 uygulama oturumu (plan `2026-08-27-faz1-streamlit-evds.md`, 14 commit, 66 test)

Bu belge, Faz 1'de bilinçli olarak yapılmayan işleri kayda geçirir. Hiçbiri
mevcut davranışı bozmuyor; her biri bir review'da bulunup ertelendi.

## Kullanıcı aksiyonu bekleyenler

1. ~~**EVDS API key.**~~ ✅ **Tamamlandı 2026-08-27** — 13/13 seri çekildi,
   EVDS3 endpoint'i canlı doğrulandı, veri commit'lendi (`7e5a1c4`).
   Uygulama gerçek veriyle tarayıcıda gezildi; mevsimsellik, YoY/MoM
   toggle'ı ve kısmi-ay atma davranışı yerinde teyit edildi.

2. ~~**GitHub remote + secret.**~~ ✅ **Tamamlandı 2026-08-27**
   - Repo: https://github.com/kpostaagasi/BVmarketDashboard (**private**, kişisel hesap)
   - `EVDS_API_KEY` secret'ı kuruldu ve doğrulandı
   - `test.yml` push'ta koştu ve geçti (66 test)
   - `ingest.yml` elle tetiklendi: Actions ortamından 13/13 seri başarılı,
     "değişiklik yok" dalı da doğru çalıştı. Günlük cron 06:00 UTC'de aktif.

   **Not — sahiplik borcu:** repo kişisel hesapta duruyor. BV Portföy org'u
   kurulduğunda transfer edilmeli; Streamlit Cloud deploy'unun yeniden
   bağlanması gerekecek.

3. ~~**Streamlit Community Cloud deploy.**~~ ✅ **Tamamlandı 2026-08-27**
   - URL: https://bvmarketdashboard.streamlit.app/
   - Canlıda doğrulandı: dört kategori sayfası, `/enflasyon` derin bağlantısı,
     Türkçe sayı biçimi, mevsimsellik grafikleri, doğrulanmış palet.
   - **Erişim: private.** "Make this app public" kapalı, davetli listesi boş.
     Şu an yalnızca hesap sahibi erişebiliyor.

   **Spec'teki risk 2 kapandı:** Community Cloud ücretsiz katmanı private
   uygulamayı ve e-posta bazlı davet listesini destekliyor. Bulut VM +
   reverse proxy B planına gerek yok.

## Kalan tek iş

**Ekip davetleri.** Uygulamada sağ üstteki **Share** → **Invite** alanına
BV Portföy çalışanlarının e-postalarını virgülle ayırarak girin. O ana
kadar panoya yalnızca hesap sahibi erişebilir.

## Faz 2'ye devredilen teknik işler

Whole-branch review'da bulundu, ertelendi.

| # | İş | Neden ertelendi |
|---|---|---|
| 1 | `ingest/evds.py`'ye retry/backoff | Tek 5xx, all-or-nothing commit politikası yüzünden günün tamamını götürüyor. `requests.adapters.Retry` ile ucuz. |
| 2 | `seriyi_yaz`'ı `core/data.py`'ye taşımak | Okuma tek kapıdan geçiyor ama yazma `ingest/run.py`'de; parquet geçişinde iki dosya değişecek. |
| 3 | KPI seçimini katalog bayrağına bağlamak | Şu an `seriler[:4]` — `series.yaml` sırası değişirse sayfanın KPI'ları sessizce değişir. `kpi: true` alanı açık hale getirir. |
| 4 | Kaynak URL şema kontrolü | `seri.kaynak.url` `unsafe_allow_html` içinde `href`'e giriyor. Bugün güven sınırı sağlam (girdi repo'ya commit'lenmiş YAML), ama `_dogrula`'ya şema kontrolü kalıcı kapatır. |
| 5 | Seri bazında ondalık basamak | `_tr_sayi` 2 basamağa sabit; USD/TRY `42,12` görünüyor, TCMB 4 basamak yayımlıyor. Katalogda `decimals` alanı. |
| 6 | `ingest.yml`'ye `concurrency` grubu | Elle tetikleme cron ile çakışırsa push yarışı olabilir; `git push`'un pull/rebase geri dönüşü yok. |
| 7 | `noktalari_ayikla`'da atlanan satır sayısını raporlamak | Kısmi seri tam görünüyor. Felaket senaryosu gürültülü (alan adı değişirse tüm satırlar düşer, `seri_cek` hata verir), yalnızca kısmi düşüşler sessiz. |
| 8 | `aylige_cevir` haftalık yolu için test | Elle izlendi ve doğru; test yok. |
| 9 | `seri_mom`/`seri_yoy` haftalık ve günlük vektörel yol testleri | Aynı — elle doğrulandı, test yok. Katalog üç frekansı da karıştırıyor. |
| 10 | `core/stats.py`'de ölü guard temizliği | `_degisim`'deki `df.index.min() > hedef` `_asof` tarafından zaten kapsanıyor; yorum yanıltıcı. Aynı kalıp `_onceki_degerler`'de tekrar ediyor. |
| 11 | `son_tarih`/`son_deger` boş DataFrame guard'ı | `mom`/`yoy`/`aralik_12a`'da var, bu ikisinde yok. Ingest üzerinden ulaşılamaz (`seri_cek` boş seride hata veriyor). |
| 12 | `_temayi_uygula` dönüş değeri tutarlılığı | Bir dalda kullanılıyor, diğerinde atılıyor. Ayrıca boş DataFrame yolu x ekseni etiketlerinden önce dönüyor — bir yıldan kısa geçmişi olan seri YoY görünümünde Oca→Ara yerine 1–12 sayısal eksen alıyor. |
| 13 | `serileri_yukle()` ham `KeyError` | Eksik YAML anahtarı `KatalogHatasi` yerine ham `KeyError` veriyor. Yalnızca elle YAML düzenleyen geliştirici görür. |
| 15 | `run.py`'nin secret hata mesajı boş değeri ayırt etmiyor | "EVDS_API_KEY tanımlı değil" diyor ama secret var ve boş olduğunda da aynı mesaj çıkıyor. İlk Actions koşusunda bu bir hata ayıklama turuna mal oldu (`gh secret set` etkileşimsiz kabukta boş stdin okuyup boş secret yazmıştı). "tanımlı değil veya boş" demek yeterli. |
| 14 | `ingest` tarafı Streamlit'i import ediyor | `ingest/run.py` → `core.data.seri_yolu` → `import streamlit`. İlk gerçek çekimde görüldü: `python -m ingest.run` çıktısına "No runtime found, using MemoryCacheStorageManager" uyarısı düşüyor. Zararsız ama ingest'in Streamlit'e bağımlı olmaması gerekir — `seri_yolu`'nu Streamlit import etmeyen bir modüle taşımak (2 numaralı işle birlikte) çözer. |

## Faz 2'de ele alınacak kapsam (spec'ten)

Faz 1 dışında bırakılanlar: ilgili veri çipleri (`related:` alanı), arama kutusu,
favoriler, Veri Takvimi bileşeni, sektör sayfaları, AI raporları.

`scripts/ingest/sources/yahoo.ts` Task 1'de silindi ama Faz 2 (emtia) için
değerli bir referans — `git show bcd8033:scripts/ingest/sources/yahoo.ts` ile
geri alınabilir.
