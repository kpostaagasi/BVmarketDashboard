import pandas as pd
import pytest

from core.data import VeriYokHatasi, seri_csv_oku


def csv_yaz(tmp_path, icerik):
    yol = tmp_path / "seri.csv"
    yol.write_text(icerik, encoding="utf-8")
    return yol


def test_csv_datetimeindexli_df_verir(tmp_path):
    yol = csv_yaz(tmp_path, "date,value\n2024-01-01,10.5\n2024-02-01,11.25\n")
    df = seri_csv_oku(yol)
    assert list(df.columns) == ["value"]
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.name == "date"
    assert df.loc[pd.Timestamp("2024-02-01"), "value"] == 11.25


def test_satirlar_tarihe_gore_siralanir(tmp_path):
    yol = csv_yaz(tmp_path, "date,value\n2024-03-01,3\n2024-01-01,1\n2024-02-01,2\n")
    df = seri_csv_oku(yol)
    assert list(df["value"]) == [1.0, 2.0, 3.0]


def test_bos_degerler_atilir(tmp_path):
    yol = csv_yaz(tmp_path, "date,value\n2024-01-01,1\n2024-02-01,\n2024-03-01,3\n")
    df = seri_csv_oku(yol)
    assert len(df) == 2


def test_dosya_yoksa_turkce_hata(tmp_path):
    with pytest.raises(VeriYokHatasi, match="ingest.run"):
        seri_csv_oku(tmp_path / "olmayan.csv")


def test_genis_csv_oku_tum_sutunlari_dondurur(tmp_path):
    from core.data import genis_csv_oku

    yol = tmp_path / "k.csv"
    yol.write_text(
        "date,Kömür,Rüzgar\n2026-08-01,10.0,5.0\n2026-08-02,12.0,6.0\n",
        encoding="utf-8",
    )
    df = genis_csv_oku(yol)
    assert list(df.columns) == ["Kömür", "Rüzgar"]
    assert df.index.name == "date"
    assert len(df) == 2
    assert df["Kömür"].dtype == "float64"


def test_genis_csv_oku_tarihe_gore_siralar(tmp_path):
    from core.data import genis_csv_oku

    yol = tmp_path / "k.csv"
    yol.write_text(
        "date,Kömür\n2026-08-02,12.0\n2026-08-01,10.0\n", encoding="utf-8"
    )
    df = genis_csv_oku(yol)
    assert list(df["Kömür"]) == [10.0, 12.0]


def test_genis_csv_oku_dosya_yoksa_veri_yok_hatasi(tmp_path):
    import pytest

    from core.data import VeriYokHatasi, genis_csv_oku

    with pytest.raises(VeriYokHatasi):
        genis_csv_oku(tmp_path / "yok.csv")
