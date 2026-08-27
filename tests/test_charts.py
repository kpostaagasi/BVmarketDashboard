import pandas as pd
import pytest

from core.charts import aylige_cevir, mevsimsellik_figuru, seviye_figuru
from core.theme import RENKLER, TR_AYLAR


def gunluk_df(baslangic, periyot, deger=1.0):
    idx = pd.date_range(baslangic, periods=periyot, freq="D", name="date")
    return pd.DataFrame({"value": [deger] * periyot}, index=idx)


def aylik_df(baslangic, periyot):
    idx = pd.date_range(baslangic, periods=periyot, freq="MS", name="date")
    return pd.DataFrame({"value": [float(i) for i in range(periyot)]}, index=idx)


def test_aylige_cevir_ortalama_alir():
    idx = pd.date_range("2026-01-01", periods=31, freq="D", name="date")
    df = pd.DataFrame({"value": [10.0] * 30 + [41.0]}, index=idx)
    sonuc = aylige_cevir(df, "mean")
    assert len(sonuc) == 1
    assert sonuc.iloc[0]["value"] == pytest.approx(11.0)


def test_aylige_cevir_son_degeri_alir():
    idx = pd.date_range("2026-01-01", periods=3, freq="D", name="date")
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0]}, index=idx)
    assert aylige_cevir(df, "last").iloc[0]["value"] == 3.0


def test_aylige_cevir_toplar():
    idx = pd.date_range("2026-01-01", periods=3, freq="D", name="date")
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0]}, index=idx)
    assert aylige_cevir(df, "sum").iloc[0]["value"] == 6.0


def test_mevsimsellik_uc_yil_icin_uc_iz_uretir():
    df = aylik_df("2022-01-01", 60)  # 2022-01 .. 2026-12
    fig = mevsimsellik_figuru(df, "Adet")
    assert len(fig.data) == 3


def test_mevsimsellik_ilk_iz_cari_yil_ve_kalin():
    df = aylik_df("2022-01-01", 60)
    fig = mevsimsellik_figuru(df, "Adet")
    ilk = fig.data[0]
    assert ilk.name == "2026"
    assert ilk.line.color == RENKLER["seri"][0]
    assert ilk.line.width == 3
    assert fig.data[1].line.width == 2


def test_mevsimsellik_x_ekseni_ay_numaralari():
    df = aylik_df("2022-01-01", 60)
    fig = mevsimsellik_figuru(df, "Adet")
    assert list(fig.data[0].x) == list(range(1, 13))
    assert list(fig.layout.xaxis.ticktext) == TR_AYLAR


def test_mevsimsellik_kisa_seride_mevcut_yillari_verir():
    df = aylik_df("2026-01-01", 6)
    fig = mevsimsellik_figuru(df, "Adet")
    assert len(fig.data) == 1
    assert fig.data[0].name == "2026"


def test_seviye_tek_iz_ve_legendsiz():
    df = aylik_df("2024-01-01", 24)
    fig = seviye_figuru(df, "TL")
    assert len(fig.data) == 1
    assert fig.layout.showlegend is False
    assert fig.data[0].line.color == RENKLER["seri"][0]


def test_seviye_y_ekseni_birimi_gosterir():
    df = aylik_df("2024-01-01", 24)
    fig = seviye_figuru(df, "TL")
    assert fig.layout.yaxis.title.text == "TL"


def test_mevsimsellik_tek_yilda_legend_kapali():
    df = aylik_df("2026-01-01", 6)
    assert mevsimsellik_figuru(df, "Adet").layout.showlegend is False


def test_mevsimsellik_cok_yilda_legend_acik():
    df = aylik_df("2022-01-01", 60)
    assert mevsimsellik_figuru(df, "Adet").layout.showlegend is True


def test_mevsimsellik_paletten_fazla_yil_istenirse_hata():
    df = aylik_df("2016-01-01", 120)
    with pytest.raises(ValueError, match="yil_sayisi"):
        mevsimsellik_figuru(df, "Adet", yil_sayisi=4)
