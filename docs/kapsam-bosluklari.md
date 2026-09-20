# Kapsam Boşlukları (marketvisuals.net referansı)

Ölçüm: 2026-09-20. Referans sitenin 65 veri sayfasındaki **800 grafik kartı**
sayıldı (her sayfanın `var SECTIONS` bloğu, divider satırları hariç).

| Durum | Kart | Pay |
|---|---:|---:|
| Katalog serisiyle karşılanan | 736 | %92,0 |
| Görünüm/türetme ile karşılanan | 36 | %4,5 |
| **Toplam karşılanan** | **772** | **%96,5** |
| Kanıtlı boşluk (aşağıda) | 28 | %3,5 |

"Görünüm ile karşılanan" 36 kart, referansın ayrı kart olarak çizdiği ama
bizde aynı seri üzerinde bir görünümle üretilen kartlardır: 20 "Çeyreksel —
X" (`core/stats.py::ceyreklige_cevir`), 6 karşılaştırma/kümülatif/mevsimsellik
(`mevsimsellik_figuru`, `hareketli_ortalama_uygula`), 10 pay/oran/fark
(`paylara_cevir`, `seri_yoy`/`seri_mom`). Aynı veriyi ikinci kez seri olarak
saklamak yerine hesaplanıyor.

## Kanıtlı boşluklar — 28 kart

Bu kartlar için **veri üretilmedi**. Vekil/muadil seri ikamesi bilinçli olarak
reddedildi: farklı benchmark'ı aynıymış gibi göstermek sessiz yanlış temsildir.
Kullanıcı kararı (2026-09-20): lisans alınmayacak, boşluk belgelenecek.

### Ücretli lisans arkasında (19)

| Kaynak | Kart | Ölçüm |
|---|---|---|
| Business Analytiq | LPG ABD/Avrupa (gerçekleşen+tahmin, 4), Kok kömürü ABD/Avrupa (gerçekleşen+tahmin, 4), Jet/kerosen Avrupa + Orta Doğu (3), Nafta (1) | Veri Looker Studio gömülüsünde; kamuya açık eşdeğeri yok. EIA'nın ABD Gulf Coast jet yakıtı serisi FARKLI benchmark (USD/gal vs BA'nın USD/kg aylık ortalaması) — ikame sayılmadı. |
| Baltic Exchange | BDI, Capesize BCI, Supramax BSI, Clean Tanker BCTI, Dirty Tanker BDTI (5) | Resmi site yalnızca metodoloji/lisans sayfası yayımlıyor; aynalayan ücretsiz uçlar (stockq vb.) HTTP 403. |
| Neste / LSEG | Dizel Marjı (NWE), Avrupa Dizel Fiyatı (NWE) (2) | Ücretli veri terminali + özel metodoloji. |

### Kaynak tarafında ölü / erişilemez (9)

| Kart | Ölçüm |
|---|---|
| Patates | EEX European Processing Potato Future 2026-06-04'te delist edildi; referans kartın verisi de aynı gün donmuş. TÜİK Tarım-ÜFE'de kalem bazlı patates kırılımı yok. |
| Etanol | Yahoo `EH=F` son gerçek gözlem 2025-04-03 (16+ ay donmuş). |
| Uranyum | Yahoo `UX=F` 15 yıllık sorguda tek gözlem — günlük seri değil. |
| Kömür (Newcastle) | Yahoo'da yalnızca `MTF=F` var; o da API2 CIF ARA (Avrupa), Newcastle/API4 değil; ayrıca 2025-12-26'da kesilmiş. |
| Lityum Karbonat | GFEX'in ücretsiz API'si çalışıyor ancak hiçbir vade referans değere denk gelmiyor — referans farklı bir spot endeks kullanıyor. |
| Soda Külü | CZCE HTTP 412 (bot koruması). |
| 2. El Araç İlan Hacmi, İlanda Kalma Süresi | BETAM/sahibindex PDF'i Cloudflare Turnstile arkasında; Indicata 2024 sonrası kamusal dağıtımı kesti. |
| VYŞ NPL ihale kartları (ayrı sayfa) | BDDK VYŞ bülteni yalnızca sektör bilançosu veriyor; şirket/ihale kırılımı yok. Referans site KAP serbest metin duyurularından elle derlemiş. |

### Kısmi boşluklar (seri var, tarihçe sınırlı)

- **TÜRKBESD**: yıllık ürün kırılımı (24 seri) tam; ürün kırılımsız aylık/çeyreksel
  toplamlar yok — dernek bunları düzenli ve mutlak olarak yayımlamıyor
  (haber arşivi ~3 ayda bir, bazı duyurular yalnızca % değişim, ithalat hiç yok).
- **İTHİB tekstil**: liste sayfasının varsayılan penceresi ~22 ay veriyor; daha
  eski bülten sayfalaması çözülemedi. "Toplam ihracat" ve dokuma kumaş alt
  kırılımları salt görsel PDF sayfasında.
- **BOTAŞ tarife**: yalnızca güncel tarife yayımlanıyor, tarihsel arşiv yok.
