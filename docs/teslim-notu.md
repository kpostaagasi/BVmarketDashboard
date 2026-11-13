# BV Market Dashboard — Teslim Notu

Tarih: 2026-11-13 · Durum: **teslim koşulu bekleniyor** (aşağıda)

## Ne teslim ediliyor

Türkiye makro, sektör ve emtia verilerini her gün kaynağından çekip grafik
sayfaları olarak sunan, BV Portföy iç kullanımına yönelik bir pano.

| | |
|---|---|
| Veri serisi | 4.226 |
| Kategori sayfası | 51 (6 grup) |
| Hisse sayfası | 8 |
| Sabit sayfa | 6 (Genel Bakış, Ara, Favoriler, Raporlar, Fonlar, Veri Takvimi) |
| Kaynak adaptörü | 57 |
| Otomatik test | 1.416 |

Kapsam donduruldu. Referans siteye (`marketvisuals.net`) göre karşılama
%92,1; kalan boşlukların dökümü `docs/kapsam-bosluklari.md` dosyasında.

## Teslim koşulu

Teslim, **2026-11-16 Pazartesi tam veri koşusunun yeşil dönmesiyle**
tamamlanır. 13 Kasım'da yapılan adaptör düzeltmeleri yerelde canlı kaynaklara
karşı doğrulandı, ancak GitHub koşusunda ilk kez o gün çalışacak.

Koşu kırmızı dönerse: Actions özetindeki "✗" satırlarına bakın. Kırmızı,
tanım gereği bizim kodumuzdaki bir hatadır; kaynağa erişilememesi koşuyu
kırmızı yapmaz.

## 13 Kasım 2026 kabul kontrolü

| Kontrol | Sonuç |
|---|---|
| Test paketi | 1.416 geçti |
| Sayfa taraması (65 sayfa, başsız) | İstisna, hata ve uyarı yok |
| Bayat seri raporu | 20 seri gecikmiş, tamamı açıklama notlu; notsuz 0 |
| Gözle (tarayıcıda) kontrol | **Yapılmadı** |

## Bilinen sınırlar

- **74 seri açıklama notu taşıyor** (`yayin_notu`): kaynağı geride, seyrek ya
  da erişime kapalı. Not, serinin kartında görünür. En büyük gruplar: EVDS
  turizm ve benzeri (20), Fintables THYAO finansalları (17, kaynak 403
  dönüyor, son veri 2026 2. çeyrek).
- **Aylık, çeyreklik ve yıllık seriler haftada iki kez güncellenir**
  (Pazartesi, Perşembe); günlük ve haftalık seriler her gün.
- **Kaynak şablonu değişince adaptör kırılır.** Bu beklenen bir bakım
  yüküdür: 13 Kasım'da beş kaynakta (UAB, OSD, THY trafik, THY sunum, AYD)
  şablon kayması düzeltildi.
- **Kısmi veri dönüşü henüz genel olarak engellenmiyor.** Bir kaynak geçici
  olarak kısa geçmiş döndürürse CSV o gün kısalır, ertesi koşuda düzelir
  (Yahoo TTF doğal gazda Kasım 2026'da üç kez görüldü). Tamamen boş dönüş
  engelleniyor.
- **Uygulama uykuya dalar**; günün ilk kullanıcısı ~30 saniye bekler.

## Bakım

| İş | Nasıl |
|---|---|
| Günlük sağlık | GitHub Actions → "Veri güncelle" koşusu ve özetindeki bayat seri raporu |
| Yeni seri | `catalog/series.yaml`'a kayıt + `python -m ingest.run --only <id>` |
| Yeni hisse sayfası | `catalog/hisseler.yaml`'a kayıt |
| Bayat seri | Düzelt, katalogdan çıkar ya da `yayin_notu` ekle; notsuz bayat seri bırakma |
| Zamanlama | cron-job.org her gün 09:00 TSİ'de workflow'u tetikler |
| Kimlik bilgileri | GitHub repo secret'ları: `EVDS_API_KEY`, `EPIAS_USERNAME`, `EPIAS_PASSWORD` |

Geliştirici rehberi: `AGENTS.md`. Kullanıcıya dönük özet: `README.md`.

## Açık kararlar

- GitHub deposu herkese açık (public). İç kullanım için bilinçli bir tercih
  olup olmadığı teyit edilmeli; private yapılırsa Actions dakikaları
  ücretlenir.
- Kısalan veriyi reddeden genel koruma önerildi, henüz uygulanmadı.
