from core.components import sayi_bicimle, yuzde_rozeti


def test_sayi_binlik_nokta_ondalik_virgul():
    assert sayi_bicimle(9422.21) == "9.422,21"


def test_sayi_birimle_birlikte():
    assert sayi_bicimle(26295.0, "GWh") == "26.295,00 GWh"


def test_sayi_milyonlarda_gruplanir():
    assert sayi_bicimle(1234567.5) == "1.234.567,50"


def test_sayi_none_tire_dondurur():
    assert sayi_bicimle(None) == "—"


def test_yuzde_rozeti_artis_ve_dusus():
    assert "▲" in yuzde_rozeti(12.7)
    assert "▼" in yuzde_rozeti(-12.7)


def test_yuzde_rozeti_turkce_bicimde():
    assert "%2.204,4" in yuzde_rozeti(2204.4)
