import re

from core.theme import RENKLER

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def test_kategorik_palet_sekiz_renk():
    assert len(RENKLER["kategorik"]) == 8


def test_kategorik_renkler_gecerli_hex():
    assert all(HEX.match(r) for r in RENKLER["kategorik"])


def test_kategorik_renkler_tekil():
    assert len(set(RENKLER["kategorik"])) == 8


def test_kategorik_palet_durum_renkleriyle_karismaz():
    """artis/dusus durum rengidir; grafiğin içinde asla kullanılmaz."""
    assert RENKLER["artis"] not in RENKLER["kategorik"]
    assert RENKLER["dusus"] not in RENKLER["kategorik"]
