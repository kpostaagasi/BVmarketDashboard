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
