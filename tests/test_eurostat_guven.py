"""Eurostat euro bölgesi güven endeksleri istemcisi testleri."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ingest.eurostat_guven import TABAN, seri_cek


class SahteYanit:
    def __init__(self, govde: dict):
        self.govde = govde

    def raise_for_status(self):
        pass

    def json(self):
        return self.govde


class SahteOturum:
    def __init__(self, govde: dict):
        self.govde = govde
        self.cagrilar: list[tuple[str, dict]] = []

    def get(self, url, params=None, timeout=None):
        self.cagrilar.append((url, params))
        return SahteYanit(self.govde)


def _govde(zamanlar: list[str], degerler: dict[int, float]) -> dict:
    return {
        "dimension": {"time": {"category": {"index": {t: i for i, t in enumerate(zamanlar)}}}},
        "value": {str(i): v for i, v in degerler.items()},
    }


def test_tuketici_dogru_kume_ve_gostergeyi_ea21_icin_ister():
    oturum = SahteOturum(_govde(["2026-08", "2026-09"], {0: -15.5, 1: -16.5}))
    df = seri_cek(SimpleNamespace(eurostat_guven_gosterge="tuketici"), session=oturum)
    url, params = oturum.cagrilar[0]
    assert url == TABAN + "ei_bsco_m"
    assert params["indic"] == "BS-CSMCI"
    assert params["geo"] == "EA21"
    assert params["s_adj"] == "SA"
    assert list(df.columns) == ["date", "value"]
    assert df["date"].tolist() == ["2026-08-01", "2026-09-01"]
    assert df["value"].tolist() == pytest.approx([-15.5, -16.5])


def test_imalat_ayri_kume_kullanir_ve_bos_degeri_atlar():
    oturum = SahteOturum(_govde(["2026-07", "2026-08", "2026-09"], {0: -5.9, 2: -3.8}))
    df = seri_cek(SimpleNamespace(eurostat_guven_gosterge="imalat"), session=oturum)
    assert oturum.cagrilar[0][0] == TABAN + "ei_bssi_m_r2"
    assert oturum.cagrilar[0][1]["indic"] == "BS-ICI-BAL"
    assert df["date"].tolist() == ["2026-07-01", "2026-09-01"]


def test_gecersiz_gosterge_patlar():
    with pytest.raises(RuntimeError, match="Geçersiz eurostat_guven_gosterge"):
        seri_cek(SimpleNamespace(eurostat_guven_gosterge="hizmet"), session=SahteOturum({}))


def test_ea21_icin_hic_deger_yoksa_sessiz_bos_donmez():
    oturum = SahteOturum(_govde(["2026-09"], {}))
    with pytest.raises(RuntimeError, match="EA21 için değer dönmedi"):
        seri_cek(SimpleNamespace(eurostat_guven_gosterge="tuketici"), session=oturum)
