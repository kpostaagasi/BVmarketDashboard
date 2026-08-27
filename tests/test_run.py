import dataclasses

import pandas as pd
import pytest

from core.catalog import seri_getir
from ingest.run import _cek


def sahte_df():
    return pd.DataFrame({"date": ["2026-01-01"], "value": [1.0]})


def test_cek_yahoo_serisini_yahoo_moduline_yonlendirir(monkeypatch):
    gorulen = {}

    def sahte(seri, session=None):
        gorulen["id"] = seri.id
        return sahte_df()

    monkeypatch.setattr("ingest.run.yahoo.seri_cek", sahte)
    _cek(seri_getir("emtia-enerji/brent"), None, None)
    assert gorulen["id"] == "emtia-enerji/brent"


def test_cek_evds_serisini_evds_moduline_yonlendirir(monkeypatch):
    gorulen = {}

    def sahte(seri, api_key, session=None, bugun=None):
        gorulen["id"] = seri.id
        gorulen["key"] = api_key
        return sahte_df()

    monkeypatch.setattr("ingest.run.evds.seri_cek", sahte)
    _cek(seri_getir("enflasyon/tufe-genel"), "gizli", None)
    assert gorulen["id"] == "enflasyon/tufe-genel"
    assert gorulen["key"] == "gizli"


def test_cek_bilinmeyen_kaynak_tipinde_hata():
    seri = dataclasses.replace(seri_getir("enflasyon/tufe-genel"), kaynak_tipi="bloomberg")
    with pytest.raises(ValueError, match="Bilinmeyen kaynak tipi"):
        _cek(seri, "gizli", None)
