import re

from core.catalog import seri_getir
from core.theme import RENKLER

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


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
