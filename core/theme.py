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
sekizi de aynı çizgi grafikte birlikte görünür. Grup adıyla anahtarlanmış
bir dict'tir (`catalog/series.yaml`daki `elektrik/uretim-kompozisyon`
serisinin `epias_bilesenler` anahtarlarıyla birebir aynı sekiz ad) — grafik
katmanı sütun adına göre renk seçmeli, pozisyona göre `zip` YAPMAMALI:
doğrulayıcı paleti kendi sırasında (aşağıda) ölçtü, bu sıra katalogdaki
sırayla (Kömür, Hidroelektrik, Doğalgaz, Güneş, Rüzgar, Jeotermal,
Biyo/Atık, Diğer) aynı değil; pozisyonel eşleme yanlış rengi yanlış gruba
bağlar.

`dataviz` skill'inin `scripts/validate_palette.js` doğrulayıcısından geçti
— koyu mod, kart zemini (#16273F) yüzeyine karşı, çizgi grafikler için
öngörülen *adjacent* (komşu çift, doğrulayıcıya verilen sıraya göre) kuralıyla:
OKLCH açıklık bandı ve krom tabanı hepsi PASS. Doğrulayıcıya verilen sıra —
Hidroelektrik, Doğalgaz, Rüzgar, Güneş, Diğer, Biyo/Atık, Kömür, Jeotermal —
brief'teki semantik sıralama (Kömür, Hidroelektrik, Doğalgaz, Güneş, Rüzgar,
Jeotermal, Biyo/Atık, Diğer) o sırayla FAIL verdiği için (Doğalgaz↔Güneş
normal-görüş ΔE 12.8 < 15 tabanı; Biyo/Atık↔Diğer CVD ΔE 2.8 < 6.0 floor'u)
terk edilip erişilebilirlik doğrulayıcısına göre yeniden sıralandı. En zayıf
komşu çift **Kömür↔Jeotermal**: CVD ΔE 8.7 (protan, ≥8 hedefine karşı — dar
ama net PASS) ve normal görüşte ΔE 15.3 (≥15 tabanına karşı — dar ama net
PASS). Marj küçük: bu ikisinden biri ileride değiştirilirse doğrulayıcıyı
aynı komut ve sırayla yeniden çalıştırmadan renk değiştirilmemeli. Diğer
altı komşu çiftin hepsi belirgin şekilde daha rahat (en düşüğü Biyo/Atık↔
Kömür, CVD ΔE 9.3).

Kömür ve Diğer için hedeflenen "koyu/nötr" ve "gri" çağrışımı feda edildi:
krom tabanı (C ≥ 0.10) gerçek griyi/füme tonu doğrudan reddediyor, o yüzden
Kömür sıcak bir kahverengiye, Diğer mor-gri bir tona kaydırıldı. Doğrulayıcı
yalnızca *komşu* çiftleri (çizgi grafik kuralı) zorunlu tutar; bilgi amaçlı
`--pairs all` koşusunda Kömür↔Doğalgaz (ΔE 1.8) ve Biyo/Atık↔Rüzgar (ΔE 4.7)
gibi komşu olmayan çiftler zayıf kalıyor — çizgiler grafikte kesişirse bu
ayrımı zayıflatabilir; sekiz grup korunuyor, ikincil kodlama (çizgi deseni)
Task 5'te eklenecek.
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
    "kategorik": {
        "Hidroelektrik": "#3a80dc",  # mavi
        "Doğalgaz": "#d15c24",  # turuncu
        "Rüzgar": "#0e9d90",  # turkuaz
        "Güneş": "#b58900",  # sarı
        "Diğer": "#9678c0",  # mor-gri (semantik feda: gerçek gri krom tabanını geçemiyor)
        "Biyo/Atık": "#279d70",  # yeşil-turkuaz
        "Kömür": "#9c6620",  # kahverengi (semantik feda: koyu/nötr krom tabanını geçemiyor)
        "Jeotermal": "#e5685e",  # kırmızı
    },
}

TR_AYLAR = [
    "Oca", "Şub", "Mar", "Nis", "May", "Haz",
    "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara",
]
