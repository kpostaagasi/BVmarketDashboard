import pandas as pd
import pytest

from core.stats import (
    aralik_12a,
    gorunum_uygula,
    mom,
    seri_mom,
    seri_yoy,
    son_deger,
    son_tarih,
    yoy,
)


def aylik_df(degerler, baslangic="2024-01-01"):
    idx = pd.date_range(baslangic, periods=len(degerler), freq="MS", name="date")
    return pd.DataFrame({"value": degerler}, index=idx)


def test_son_tarih_ve_son_deger():
    df = aylik_df([10.0, 20.0, 30.0])
    assert son_tarih(df) == pd.Timestamp("2024-03-01")
    assert son_deger(df) == 30.0


def test_mom_bir_onceki_aya_gore_yuzde():
    df = aylik_df([100.0, 110.0])
    assert mom(df) == pytest.approx(10.0)


def test_yoy_on_iki_ay_oncesine_gore_yuzde():
    df = aylik_df([100.0] + [0.0] * 11 + [125.0])
    assert yoy(df) == pytest.approx(25.0)


def test_yoy_yeterli_gecmis_yoksa_none():
    df = aylik_df([100.0, 110.0, 120.0])
    assert yoy(df) is None


def test_mom_tek_nokta_varsa_none():
    df = aylik_df([100.0])
    assert mom(df) is None


def test_sifir_taban_none_dondurur():
    df = aylik_df([0.0, 50.0])
    assert mom(df) is None


def test_negatif_taban_none_dondurur():
    df = aylik_df([-10.0, 50.0])
    assert mom(df) is None


def test_seri_degisim_negatif_tabanda_nan_verir():
    # -20 -> 40 arasında yüzde değişim tanımsız; sayı uydurmak yerine boşluk
    df = aylik_df([-20.0] + [0.0] * 11 + [40.0])
    sonuc = seri_yoy(df)
    assert pd.isna(sonuc.loc[pd.Timestamp("2025-01-01"), "value"])


def test_aralik_12a_son_on_iki_ayin_min_maksi():
    # 24 ay: ilk 12 ay 1..12, sonraki 12 ay 100..111
    df = aylik_df([float(v) for v in range(1, 13)] + [float(v) for v in range(100, 112)])
    assert aralik_12a(df) == (100.0, 111.0)


def test_gunluk_seride_mom_bir_ay_oncesine_bakar():
    idx = pd.date_range("2026-01-01", periods=60, freq="D", name="date")
    df = pd.DataFrame({"value": [float(i) for i in range(60)]}, index=idx)
    # son gün 2026-03-01 (değer 59); bir ay öncesi 2026-02-01 (değer 31)
    assert mom(df) == pytest.approx((59 / 31 - 1) * 100)


def test_seri_yoy_her_nokta_icin_yuzde_uretir():
    df = aylik_df([100.0] * 12 + [110.0] * 12)
    sonuc = seri_yoy(df)
    assert sonuc.loc[pd.Timestamp("2025-01-01"), "value"] == pytest.approx(10.0)
    assert pd.isna(sonuc.loc[pd.Timestamp("2024-01-01"), "value"])


def test_seri_mom_her_nokta_icin_yuzde_uretir():
    df = aylik_df([100.0, 110.0, 121.0])
    sonuc = seri_mom(df)
    assert sonuc.loc[pd.Timestamp("2024-02-01"), "value"] == pytest.approx(10.0)
    assert sonuc.loc[pd.Timestamp("2024-03-01"), "value"] == pytest.approx(10.0)


def test_gorunum_uygula_varsayilan_ayni_dfyi_dondurur():
    df = aylik_df([1.0, 2.0])
    pd.testing.assert_frame_equal(gorunum_uygula(df, "Varsayılan"), df)


def test_gorunum_uygula_bilinmeyen_gorunumde_hata_verir():
    df = aylik_df([1.0, 2.0])
    with pytest.raises(ValueError):
        gorunum_uygula(df, "Haftalık %")
