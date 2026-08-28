"""Görsel kimlik sabitleri.

RENKLER["seri"] dataviz doğrulayıcısından geçmiş bir settir; slotlar
yıla değil *güncelliğe* atanır (0 = cari yıl, 1 = geçen yıl, 2 = iki yıl
önce). Böylece takvim yılı döndüğünde renkler yeniden dağılmaz.

Cari yıl vurgusu renkle değil çizgi kalınlığıyla verilir: aynı hue'nun
iki tonu koyu tema açıklık bandına sıkıştığında normal görüşte bile
ayırt edilemiyor (ΔE 14.4 < 15 tabanı).

RENKLER["artis"]/["dusus"] durum renkleridir; yalnızca ▲/▼ işaretiyle
birlikte istatistik satırlarında kullanılır, grafiğin içinde asla.

RENKLER["kategorik"] — elektrik üretiminin sekiz kaynak grubu için
*kategorik* (kimlik) palettir, "seri"nin güncellik yuvasıyla karıştırılmaz;
sekizi de aynı çizgi grafikte birlikte görünür. `dataviz` skill'inin
`scripts/validate_palette.js` doğrulayıcısından geçti — koyu mod, kart
zemini (#16273F) yüzeyine karşı, çizgi grafikler için öngörülen *adjacent*
(komşu çift) kuralıyla: OKLCH açıklık bandı ve krom tabanı hepsi PASS, en
zayıf komşu çift kahverengi↔kırmızı ΔE 8.7 (protan, ≥8 hedefi) ve normal
görüşte ΔE 15.3 (≥15 tabanı, sınırda ama PASS). Liste sırası, komşu
çiftlerin bu eşikleri geçmesi için erişilebilirlik doğrulayıcısına göre
optimize edilmiştir — brief'teki semantik sıralama (Kömür, Hidroelektrik,
Doğalgaz, Güneş, Rüzgar, Jeotermal, Biyo/Atık, Diğer) o sırayla FAIL verdiği
için (Doğalgaz↔Güneş normal-görüş ΔE 12.8; Biyo/Atık↔Diğer ΔE 2.8) terk
edildi. Gerçek eşleme (indeks → grup):
    0 Hidroelektrik (mavi)     4 Diğer (mor-gri)
    1 Doğalgaz (turuncu)       5 Biyo/Atık (yeşil-turkuaz)
    2 Rüzgar (turkuaz)         6 Kömür (kahverengi)
    3 Güneş (sarı)             7 Jeotermal (kırmızı)
Kömür ve Diğer için hedeflenen "koyu/nötr" ve "gri" çağrışımı feda edildi:
krom tabanı (C ≥ 0.10) gerçek griyi/füme tonu doğrudan reddediyor, o yüzden
Kömür sıcak bir kahverengiye, Diğer mor-gri bir tona kaydırıldı. Doğrulayıcı
yalnızca *komşu* çiftleri (çizgi grafik kuralı) zorunlu tutar; bilgi amaçlı
`--pairs all` koşusunda Kömür↔Doğalgaz (ΔE 1.8) ve Biyo/Atık↔Rüzgar (ΔE 4.7)
gibi komşu olmayan çiftler zayıf kalıyor — çizgiler grafikte kesişirse bu
ayrımı zayıflatabilir; bu kısıt tam raporda ayrıca not edildi.
"""

RENKLER = {
    "sayfa_zemini": "#0F1E33",
    "kart_zemini": "#16273F",
    "metin": "#E6EDF5",
    "metin_soluk": "#9FB3CC",
    "izgara": "#22354F",
    "vurgu": "#E8B54D",
    "artis": "#199e70",
    "dusus": "#e66767",
    "seri": ["#3987e5", "#d95926", "#199e70"],
    "kategorik": [
        "#3a80dc",  # Hidroelektrik — mavi
        "#d15c24",  # Doğalgaz — turuncu
        "#0e9d90",  # Rüzgar — turkuaz
        "#b58900",  # Güneş — sarı
        "#9678c0",  # Diğer — mor-gri (semantik feda: gerçek gri krom tabanını geçemiyor)
        "#279d70",  # Biyo/Atık — yeşil-turkuaz
        "#9c6620",  # Kömür — kahverengi (semantik feda: koyu/nötr krom tabanını geçemiyor)
        "#e5685e",  # Jeotermal — kırmızı
    ],
}

TR_AYLAR = [
    "Oca", "Şub", "Mar", "Nis", "May", "Haz",
    "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara",
]
