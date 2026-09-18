"""Fon kartı hesapları: karşılaştırma endeksi ve dönem grafiği sözleşmesi."""

from __future__ import annotations

import pandas as pd
import pytest

from core.charts import fon_donem_figuru, karsilastirma_figuru
from core.components import ONS_GRAM, _fon_karsilastirma
from core.theme import RENKLER


def test_karsilastirma_ilk_gunu_yuze_endeksler(monkeypatch):
    gunler = pd.bdate_range("2025-01-02", periods=5)
    fiyat = pd.Series([0.5, 0.55, 0.6, 0.6, 0.66], index=gunler)
    olcutler = {
        "ekonomi-makro/bist100": pd.Series([100.0, 110, 120, 120, 130], index=gunler),
        "ekonomi-makro/usd-try": pd.Series([35.0, 35, 35, 35, 35], index=gunler),
        "emtia-metaller/altin": pd.Series([2600.0] * 5, index=gunler),
    }
    monkeypatch.setattr(
        "core.components.load_series",
        lambda seri_id: olcutler[seri_id].to_frame("value"),
    )
    df = _fon_karsilastirma(fiyat)
    assert list(df.columns) == ["Fon", "BIST 100", "Dolar/TL", "Gram Altın"]
    assert df.iloc[0].tolist() == [100.0, 100.0, 100.0, 100.0]
    # Fon %32 arttı, BIST %30; Dolar ve gram altın sabit kaldı.
    assert df["Fon"].iloc[-1] == pytest.approx(132.0)
    assert df["BIST 100"].iloc[-1] == pytest.approx(130.0)
    assert df["Gram Altın"].iloc[-1] == pytest.approx(100.0)


def test_karsilastirma_olcut_tatilinde_fon_gunu_dusmez(monkeypatch):
    gunler = pd.bdate_range("2025-01-02", periods=3)
    fiyat = pd.Series([1.0, 1.1, 1.2], index=gunler)
    # Ölçütün orta günü yayınlanmamış: ileri doldurma ile hizalanmalı.
    eksik = pd.Series([10.0, 12.0], index=[gunler[0], gunler[2]])
    monkeypatch.setattr(
        "core.components.load_series",
        lambda seri_id: eksik.to_frame("value"),
    )
    df = _fon_karsilastirma(fiyat)
    assert len(df) == 3
    assert df["BIST 100"].tolist() == pytest.approx([100.0, 100.0, 120.0])


def test_gram_altin_ons_donusumu_kullanir(monkeypatch):
    gunler = pd.bdate_range("2025-01-02", periods=2)
    fiyat = pd.Series([1.0, 1.0], index=gunler)
    seriler = {
        "ekonomi-makro/bist100": pd.Series([1.0, 1.0], index=gunler),
        "ekonomi-makro/usd-try": pd.Series([40.0, 40.0], index=gunler),
        "emtia-metaller/altin": pd.Series([3000.0, 6000.0], index=gunler),
    }
    monkeypatch.setattr(
        "core.components.load_series",
        lambda seri_id: seriler[seri_id].to_frame("value"),
    )
    df = _fon_karsilastirma(fiyat)
    # Ons iki katına çıktı → gram altın endeksi de iki katı; ölçek sabiti bozulmamalı.
    assert df["Gram Altın"].tolist() == pytest.approx([100.0, 200.0])
    assert ONS_GRAM == pytest.approx(31.1034768)


def test_donem_figuru_sifir_tabanli_cubuk():
    degerler = pd.Series([-2.0, 3.0], index=pd.to_datetime(["2026-08-31", "2026-09-30"]))
    fig = fon_donem_figuru(degerler, "%")
    assert fig.data[0].type == "bar"
    assert fig.layout.yaxis.rangemode == "tozero"


def test_karsilastirma_figuru_fonu_vurgu_rengiyle_cizer():
    gunler = pd.to_datetime(["2026-09-16", "2026-09-17"])
    df = pd.DataFrame({"Fon": [100.0, 110.0], "BIST 100": [100.0, 105.0]}, index=gunler)
    fig = karsilastirma_figuru(df, "Endeks")
    assert [iz.name for iz in fig.data] == ["Fon", "BIST 100"]
    assert fig.data[0].line.color == RENKLER["vurgu"]
    assert fig.data[0].line.width > fig.data[1].line.width
