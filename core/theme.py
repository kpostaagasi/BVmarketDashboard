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
aşağıdaki `CIZGI_DESENLERI` ile eklendi.

CIZGI_DESENLERI — renk tek başına yetmediği dört çift için ikincil (çizgi
deseni) kodlama. Doğrulayıcının `--pairs all` raporunda ayrışmayan dört çift
zorunlu kısıt: Kömür↔Doğalgaz, Biyo/Atık↔Rüzgar, Doğalgaz↔Güneş, Biyo/Atık↔
Diğer. Yalnızca "solid"/"dash" iki desen kullanılır (görsel gürültüyü
sınırlamak için) ve dörder dörde dengeli dağıtılır:
  - dash: Doğalgaz, Biyo/Atık, Hidroelektrik, Jeotermal
  - solid: Kömür, Güneş, Rüzgar, Diğer
Bu atama dört zorunlu çiftin hepsini ayırır (her kenarın iki ucu farklı
gruptadır) ve grafikte çizgilerin yarısından fazlası kesikli olmaz. Atama
sütun ADINA bağlıdır, pozisyona değil — `RENKLER["kategorik"]` ile aynı
gerekçe: katalogla sözleşme ayrışırsa `KeyError` doğal olarak fırlamalı.
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

CIZGI_DESENLERI = {
    "Kömür": "solid",
    "Hidroelektrik": "dash",
    "Doğalgaz": "dash",
    "Güneş": "solid",
    "Rüzgar": "solid",
    "Jeotermal": "dash",
    "Biyo/Atık": "dash",
    "Diğer": "solid",
}

TR_AYLAR = [
    "Oca", "Şub", "Mar", "Nis", "May", "Haz",
    "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara",
]

# Uygulama geneli CSS. Streamlit'in kendi teması (.streamlit/config.toml)
# renkleri verir; bu blok yalnızca tipografi, kart ve boşluk ritmini ekler.
# Hedefleme Streamlit'in iç sınıf adlarına değil, `data-testid` ve
# `st.container(key=...)`in ürettiği `st-key-*` sınıflarına yapılır — iç
# sınıf adları sürüm başına değişiyor, bu ikisi kararlı API.
# Sayılar `tabular-nums`: KPI ve tabloda basamaklar alt alta hizalanır.
STIL_CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [data-testid="stApp"], [data-testid="stMarkdownContainer"],
[data-testid="stCaptionContainer"], button, input {{
  font-family: 'Inter', system-ui, sans-serif;
  font-feature-settings: 'tnum' 1, 'cv11' 1;
}}
[data-testid="stMainBlockContainer"] {{
  max-width: 1440px;
  padding-top: 4.5rem;
  padding-bottom: 4rem;
}}
h1 {{ font-size: 1.9rem !important; font-weight: 700 !important;
     letter-spacing: -0.02em; padding-bottom: 0.1rem !important; }}
h2, h3 {{ letter-spacing: -0.01em; }}
[data-testid="stCaptionContainer"] {{ color: {RENKLER["metin_soluk"]}; }}

/* Kart yüzeyi: grafik kartı ve kategori kutuları aynı dili konuşur. */
[class*="st-key-kart-"] {{
  background: {RENKLER["kart_zemini"]};
  border: 1px solid {RENKLER["izgara"]};
  border-radius: 14px;
  padding: 1rem 1.1rem 0.6rem 1.1rem;
}}
[class*="st-key-kutu-"] {{
  background: {RENKLER["kart_zemini"]};
  border: 1px solid {RENKLER["izgara"]};
  border-radius: 12px;
  padding: 0.55rem 0.8rem;
  transition: border-color .15s ease;
}}
[class*="st-key-kutu-"]:hover {{ border-color: {RENKLER["vurgu"]}; }}

/* KPI kartı (saf HTML, bkz. core/components.py::kpi_karti_html) */
.bv-kpi {{
  background: {RENKLER["kart_zemini"]};
  border: 1px solid {RENKLER["izgara"]};
  border-radius: 14px;
  padding: 0.85rem 1rem 0.75rem 1rem;
  height: 100%;
  display: flex; flex-direction: column; gap: 0.3rem;
  color: {RENKLER["metin"]};
}}
.bv-kpi-etiket {{
  font-size: 0.78rem; color: {RENKLER["metin_soluk"]};
  line-height: 1.25; min-height: 2.5em;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden;
}}
.bv-kpi-govde {{ display: flex; align-items: flex-end;
  justify-content: space-between; gap: 0.5rem; }}
.bv-kpi-deger {{ font-size: 1.65rem; font-weight: 650; line-height: 1.1;
  letter-spacing: -0.02em; white-space: nowrap; }}
.bv-kpi-birim {{ font-size: 0.72rem; color: {RENKLER["metin_soluk"]};
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.bv-kpi-alt {{ display: flex; flex-wrap: wrap; align-items: center;
  gap: 0.35rem; font-size: 0.74rem; color: {RENKLER["metin_soluk"]}; }}
.bv-kivilcim {{ flex-shrink: 0; }}

.bv-rozet {{ display: inline-flex; align-items: center; gap: 0.2rem;
  padding: 0.08rem 0.45rem; border-radius: 999px; font-size: 0.72rem;
  font-weight: 600; white-space: nowrap; }}
.bv-rozet-artis {{ color: {RENKLER["artis"]}; background: {RENKLER["artis"]}22; }}
.bv-rozet-dusus {{ color: {RENKLER["dusus"]}; background: {RENKLER["dusus"]}22; }}
.bv-rozet-notr {{ color: {RENKLER["metin_soluk"]}; background: {RENKLER["izgara"]}; }}
.bv-rozet small {{ font-weight: 500; opacity: .8; }}

/* Grafik kartı başlığı */
.bv-kart-bas {{ display: flex; justify-content: space-between;
  align-items: baseline; gap: 0.75rem; }}
.bv-kart-baslik {{ font-weight: 600; font-size: 0.98rem; color: {RENKLER["metin"]}; }}
.bv-kart-kaynak a {{ font-size: 0.72rem; color: {RENKLER["metin_soluk"]};
  text-decoration: none; white-space: nowrap; }}
.bv-kart-kaynak a:hover {{ color: {RENKLER["vurgu"]}; }}
.bv-kart-ist {{ display: flex; flex-wrap: wrap; align-items: baseline;
  gap: 0.4rem 0.9rem; margin: 0.35rem 0 0.1rem 0; }}
.bv-kart-deger {{ font-size: 1.35rem; font-weight: 650; letter-spacing: -0.01em; }}
.bv-kart-deger small {{ font-size: 0.72rem; font-weight: 500;
  color: {RENKLER["metin_soluk"]}; margin-left: 0.25rem; }}
.bv-kart-meta {{ font-size: 0.74rem; color: {RENKLER["metin_soluk"]}; }}

/* Ana sayfa */
.bv-hero-alt {{ color: {RENKLER["metin_soluk"]}; font-size: 0.95rem;
  margin-top: -0.4rem; }}
.bv-sayac {{ display: flex; gap: 2rem; flex-wrap: wrap; margin: 0.6rem 0 0.4rem 0; }}
.bv-sayac div {{ display: flex; flex-direction: column; }}
.bv-sayac b {{ font-size: 1.4rem; font-weight: 700; color: {RENKLER["vurgu"]}; }}
.bv-sayac span {{ font-size: 0.75rem; color: {RENKLER["metin_soluk"]};
  text-transform: uppercase; letter-spacing: 0.06em; }}
.bv-bolum {{ font-size: 0.78rem; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.08em; color: {RENKLER["vurgu"]}; margin: 1.4rem 0 0.2rem 0; }}
.bv-liste {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
.bv-liste td {{ padding: 0.45rem 0.4rem; border-bottom: 1px solid {RENKLER["izgara"]};
  color: {RENKLER["metin"]}; }}
.bv-liste td.soluk {{ color: {RENKLER["metin_soluk"]}; font-size: 0.75rem; }}
.bv-liste td.sag {{ text-align: right; white-space: nowrap; }}
.bv-liste tr:last-child td {{ border-bottom: none; }}
"""
