import re

from core.catalog import seri_getir
from core.theme import CIZGI_DESENLERI, RENKLER

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# Doğrulayıcının renkte ayıramadığı, ikincil (çizgi deseni) kodlama zorunlu
# olan dört çift. Bkz. core/theme.py CIZGI_DESENLERI docstring'i.
DESEN_ZORUNLU_CIFTLER = [
    ("Kömür", "Doğalgaz"),
    ("Biyo/Atık", "Rüzgar"),
    ("Doğalgaz", "Güneş"),
    ("Biyo/Atık", "Diğer"),
]


def test_kategorik_palet_sekiz_renk():
    assert len(RENKLER["kategorik"]) == 8


def test_kategorik_renkler_gecerli_hex():
    assert all(HEX.match(r) for r in RENKLER["kategorik"].values())


def test_kategorik_renkler_tekil():
    assert len(set(RENKLER["kategorik"].values())) == 8


def test_kategorik_palet_durum_renkleriyle_karismaz():
    """artis/dusus durum rengidir; grafiğin içinde asla kullanılmaz."""
    assert RENKLER["artis"] not in RENKLER["kategorik"].values()
    assert RENKLER["dusus"] not in RENKLER["kategorik"].values()


def test_kategorik_palet_seri_renkleriyle_karismaz():
    """seri güncellik yuvasıdır (cari/geçen/iki yıl önce), kategorik değildir."""
    assert not set(RENKLER["kategorik"].values()) & set(RENKLER["seri"])


def test_kategorik_palet_anahtarlari_katalogla_birebir_eslesir():
    """Grafik, sütun adına göre renk seçer; anahtar kümesi katalogdaki
    `epias_bilesenler` grup adlarıyla birebir aynı olmalı — aksi halde
    katalogda grup adı değişince grafik sessizce renksiz kalır."""
    seri = seri_getir("elektrik/uretim-kompozisyon")
    assert set(RENKLER["kategorik"]) == set(seri.epias_bilesenler)


def test_cizgi_desenleri_sekiz_grubun_tamami_icin_tanimli():
    seri = seri_getir("elektrik/uretim-kompozisyon")
    assert set(CIZGI_DESENLERI) == set(seri.epias_bilesenler)


def test_cizgi_desenleri_gecerli_plotly_degerleri():
    gecerli = {"solid", "dash", "dot", "dashdot"}
    assert set(CIZGI_DESENLERI.values()) <= gecerli


def test_cizgi_desenleri_zorunlu_ciftleri_ayirir():
    """Renkte ayrışmayan dört çift, çizgi deseninde ayrışmalı."""
    for a, b in DESEN_ZORUNLU_CIFTLER:
        assert CIZGI_DESENLERI[a] != CIZGI_DESENLERI[b], f"{a} ↔ {b} ayrışmıyor"


def test_cizgi_desenleri_hepsi_kesikli_degil():
    """Görsel gürültü sınırlı kalmalı: en az bir grup solid kalmalı."""
    assert "solid" in CIZGI_DESENLERI.values()
