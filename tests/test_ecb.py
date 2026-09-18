"""ECB Data Portal istemcisinin kabul testleri (stub oturum, canlı istek yok)."""

from __future__ import annotations

import pandas as pd
import pytest

from core.catalog import Kaynak, Seri
from ingest import ecb


def _ornek_seri(**override) -> Seri:
    taban = dict(
        id="otomotiv/test",
        title="Test Serisi",
        category="otomotiv",
        kaynak=Kaynak(name="ECB", url="https://data.ecb.europa.eu"),
        kaynak_tipi="ecb",
        unit="adet",
        freq="monthly",
        charts=("level",),
        ecb_akis="CAR",
        ecb_anahtar="M.I10.N.CREG.PC0000.4Z1.N.PN",
    )
    taban.update(override)
    return Seri(**taban)


class SahteYanit:
    def __init__(self, metin: str, durum: int = 200):
        self.text = metin
        self.status_code = durum


class SahteOturum:
    def __init__(self, yanit: SahteYanit):
        self.yanit = yanit
        self.cagrilar: list[tuple[str, dict]] = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.cagrilar.append((url, params))
        return self.yanit


CSV_ORNEK = (
    "KEY,FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE\n"
    "CAR.M.I10.N.CREG.PC0000.4Z1.N.PN,M,I10,2026-05,816314\n"
    "CAR.M.I10.N.CREG.PC0000.4Z1.N.PN,M,I10,2026-06,979505\n"
)


def test_ecb_dogru_akis_ve_anahtar_ile_cagrilir():
    oturum = SahteOturum(SahteYanit(CSV_ORNEK))
    ecb.seri_cek(_ornek_seri(), session=oturum)
    (url, params), = oturum.cagrilar
    assert url == "https://data-api.ecb.europa.eu/service/data/CAR/M.I10.N.CREG.PC0000.4Z1.N.PN"
    assert params == {"format": "csvdata"}


def test_ecb_csv_ayristirir_ve_tarihe_gore_sirali_dondurur():
    oturum = SahteOturum(SahteYanit(CSV_ORNEK))
    df = ecb.seri_cek(_ornek_seri(), session=oturum)
    assert df["date"].dtype.kind == "M"
    assert df["date"].tolist() == [pd.Timestamp("2026-05-01"), pd.Timestamp("2026-06-01")]
    assert df["value"].tolist() == [816314.0, 979505.0]


def test_ecb_start_date_onceki_gunleri_atar():
    oturum = SahteOturum(SahteYanit(CSV_ORNEK))
    df = ecb.seri_cek(_ornek_seri(start_date="2026-06-01"), session=oturum)
    assert df["date"].tolist() == [pd.Timestamp("2026-06-01")]


def test_ecb_404_yanlis_akis_anahtar_mesaji_verir():
    oturum = SahteOturum(SahteYanit("not found", durum=404))
    with pytest.raises(RuntimeError, match="CAR/M.I10"):
        ecb.seri_cek(_ornek_seri(), session=oturum)


def test_ecb_diger_http_hatasinda_runtime_error_verir():
    oturum = SahteOturum(SahteYanit("error", durum=500))
    with pytest.raises(RuntimeError, match="HTTP 500"):
        ecb.seri_cek(_ornek_seri(), session=oturum)


def test_ecb_beklenmeyen_sutunlarda_yukselir():
    oturum = SahteOturum(SahteYanit("KEY,FREQ\nX,M\n"))
    with pytest.raises(RuntimeError, match="beklenen sütunları taşımıyor"):
        ecb.seri_cek(_ornek_seri(), session=oturum)
