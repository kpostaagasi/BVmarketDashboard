from core.catalog import seri_getir
from core.components import donem_etiketi, grafik_agg, sayi_bicimle, yuzde_rozeti
from core.stats import MOM, VARSAYILAN, YOY
import pandas as pd


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


def test_yuzde_rozeti_negatifte_cift_isaret_yok():
    rozet = yuzde_rozeti(-12.74)
    assert "▼" in rozet
    assert "-" not in rozet


def test_grafik_agg_varsayilanda_katalogdaki_aggi_kullanir():
    seri = seri_getir("kredi-karti/harcama-toplam")
    assert grafik_agg(seri, VARSAYILAN) == "sum"


def test_grafik_agg_yuzde_gorunumunde_ortalamaya_duser():
    seri = seri_getir("kredi-karti/harcama-toplam")
    assert grafik_agg(seri, YOY) == "mean"
    assert grafik_agg(seri, MOM) == "mean"


def test_donem_etiketi_aylik_seride_gun_gostermez():
    assert donem_etiketi(pd.Timestamp("2026-08-01"), "monthly") == "2026-08"


def test_donem_etiketi_gunluk_ve_haftalik_seride_gun_gosterir():
    assert donem_etiketi(pd.Timestamp("2026-08-27"), "daily") == "2026-08-27"
    assert donem_etiketi(pd.Timestamp("2026-08-24"), "weekly") == "2026-08-24"


def test_kpi_uygun_seriler_genis_seriyi_atlar():
    """KPI kartı tek sayı gösterir; çok bileşenli serinin tek sayısı yoktur (I3).

    Bu, `pano`da AÇIKÇA listelenmemiş (örtük "ilk dördü göster") durum
    için sessiz atlama davranışıdır — açık listelemede `pano_serileri`
    KatalogHatasi fırlatır (bkz. tests/test_page.py).
    """
    from core.components import _kpi_uygun_seriler

    genis = seri_getir("elektrik/uretim-kompozisyon")
    tekil = seri_getir("elektrik/uretim")
    assert [s.id for s in _kpi_uygun_seriler([genis, tekil])] == [tekil.id]


def test_kpi_uygun_seriler_tekil_serileri_korur():
    from core.components import _kpi_uygun_seriler

    seriler = [seri_getir("enflasyon/tufe-genel"), seri_getir("elektrik/uretim")]
    assert _kpi_uygun_seriler(seriler) == seriler
