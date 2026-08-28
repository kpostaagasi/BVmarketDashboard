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


def test_aylige_cevir_sum_bos_ayi_sifir_yapmaz():
    # Şubat'ta hiç veri yok — 0.0 değil, boşluk olmalı
    idx = pd.DatetimeIndex(
        ["2026-01-05", "2026-01-19", "2026-03-02", "2026-03-16"], name="date"
    )
    df = pd.DataFrame({"value": [10.0, 10.0, 20.0, 20.0]}, index=idx)
    sonuc = aylige_cevir(df, "sum")
    assert list(sonuc.index.month) == [1, 3]


def test_aylige_cevir_sum_tamamlanmamis_son_ayi_atar():
    idx = pd.date_range("2026-01-05", "2026-04-10", freq="W-MON", name="date")
    df = pd.DataFrame({"value": [100.0] * len(idx)}, index=idx)
    sonuc = aylige_cevir(df, "sum", freq="weekly")
    assert sonuc.index.max() == pd.Timestamp("2026-03-01")


def test_aylige_cevir_aylik_seride_son_ay_korunur():
    idx = pd.date_range("2026-01-01", periods=4, freq="MS", name="date")
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0, 4.0]}, index=idx)
    sonuc = aylige_cevir(df, "sum", freq="monthly")
    assert sonuc.index.max() == pd.Timestamp("2026-04-01")


def test_aylige_cevir_mean_tamamlanmamis_son_ayi_korur():
    idx = pd.date_range("2026-01-05", "2026-04-10", freq="W-MON", name="date")
    df = pd.DataFrame({"value": [100.0] * len(idx)}, index=idx)
    sonuc = aylige_cevir(df, "mean", freq="weekly")
    assert sonuc.index.max() == pd.Timestamp("2026-04-01")


def test_paylara_cevir_yuzdeye_normalize_eder():
    from core.charts import paylara_cevir

    df = pd.DataFrame(
        {"Kömür": [60.0, 30.0], "Rüzgar": [40.0, 10.0]},
        index=pd.to_datetime(["2026-07-01", "2026-08-01"]),
    )
    paylar = paylara_cevir(df)
    assert list(paylar["Kömür"]) == [60.0, 75.0]
    assert list(paylar["Rüzgar"]) == [40.0, 25.0]


def test_paylara_cevir_her_satir_yuze_toplanir():
    from core.charts import paylara_cevir

    df = pd.DataFrame(
        {"A": [1.0, 2.0], "B": [3.0, 5.0], "C": [6.0, 3.0]},
        index=pd.to_datetime(["2026-07-01", "2026-08-01"]),
    )
    toplamlar = paylara_cevir(df).sum(axis=1)
    assert all(abs(t - 100.0) < 1e-9 for t in toplamlar)


def test_paylara_cevir_sifir_toplamli_satirda_nan_uretir():
    """Sıfıra bölme sessizce 0 pay üretmemeli — veri yokluğu görünür kalsın."""
    from core.charts import paylara_cevir

    df = pd.DataFrame(
        {"A": [0.0, 2.0], "B": [0.0, 2.0]},
        index=pd.to_datetime(["2026-07-01", "2026-08-01"]),
    )
    paylar = paylara_cevir(df)
    assert paylar.iloc[0].isna().all()
    assert list(paylar.iloc[1]) == [50.0, 50.0]


def test_kompozisyon_figuru_her_gruba_bir_iz_ekler():
    from core.charts import kompozisyon_figuru

    df = pd.DataFrame(
        {"Kömür": [60.0, 30.0], "Rüzgar": [40.0, 10.0]},
        index=pd.to_datetime(["2026-07-01", "2026-08-01"]),
    )
    fig = kompozisyon_figuru(df, "GWh")
    assert len(fig.data) == 2
    assert {iz.name for iz in fig.data} == {"Kömür", "Rüzgar"}


def test_kompozisyon_figuru_kategorik_paleti_sutun_adina_gore_kullanir():
    """Renk sütun ADINA göre seçilmeli — pozisyona göre `zip` semantiği bozar.

    RENKLER["kategorik"] artık grup adıyla anahtarlanmış bir dict (liste
    değil); df'teki sütun sırası paletin doğrulayıcıya verilen sırasından
    farklı olsa da her iz kendi grubunun rengini almalı.
    """
    from core.charts import kompozisyon_figuru

    df = pd.DataFrame(
        {"Rüzgar": [1.0], "Kömür": [2.0], "Güneş": [3.0]},
        index=pd.to_datetime(["2026-07-01"]),
    )
    fig = kompozisyon_figuru(df, "GWh")
    renkler = {iz.name: iz.line.color for iz in fig.data}
    assert renkler == {
        "Rüzgar": RENKLER["kategorik"]["Rüzgar"],
        "Kömür": RENKLER["kategorik"]["Kömür"],
        "Güneş": RENKLER["kategorik"]["Güneş"],
    }


def test_kompozisyon_figuru_bilinmeyen_sutun_key_error_firlatir():
    """Katalogla palet ayrışırsa sessiz varsayılana düşmek yerine patlamalı."""
    from core.charts import kompozisyon_figuru

    df = pd.DataFrame(
        {"Bilinmeyen-Grup": [1.0]},
        index=pd.to_datetime(["2026-07-01"]),
    )
    with pytest.raises(KeyError):
        kompozisyon_figuru(df, "GWh")


def test_kompozisyon_figuru_desen_sutun_adina_gore_uygular():
    """Çizgi deseni de CIZGI_DESENLERI'nden sütun adına göre gelmeli."""
    from core.charts import kompozisyon_figuru
    from core.theme import CIZGI_DESENLERI

    df = pd.DataFrame(
        {"Rüzgar": [1.0], "Kömür": [2.0], "Doğalgaz": [3.0]},
        index=pd.to_datetime(["2026-07-01"]),
    )
    fig = kompozisyon_figuru(df, "GWh")
    desenler = {iz.name: iz.line.dash for iz in fig.data}
    assert desenler == {
        "Rüzgar": CIZGI_DESENLERI["Rüzgar"],
        "Kömür": CIZGI_DESENLERI["Kömür"],
        "Doğalgaz": CIZGI_DESENLERI["Doğalgaz"],
    }
