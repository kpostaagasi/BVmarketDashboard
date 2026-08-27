"""Görsel kimlik sabitleri.

RENKLER["seri"] dataviz doğrulayıcısından geçmiş bir settir; slotlar
yıla değil *güncelliğe* atanır (0 = cari yıl, 1 = geçen yıl, 2 = iki yıl
önce). Böylece takvim yılı döndüğünde renkler yeniden dağılmaz.

Cari yıl vurgusu renkle değil çizgi kalınlığıyla verilir: aynı hue'nun
iki tonu koyu tema açıklık bandına sıkıştığında normal görüşte bile
ayırt edilemiyor (ΔE 14.4 < 15 tabanı).

RENKLER["artis"]/["dusus"] durum renkleridir; yalnızca ▲/▼ işaretiyle
birlikte istatistik satırlarında kullanılır, grafiğin içinde asla.
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
}

TR_AYLAR = [
    "Oca", "Şub", "Mar", "Nis", "May", "Haz",
    "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara",
]
