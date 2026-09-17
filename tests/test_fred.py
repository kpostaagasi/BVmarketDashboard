"""FRED istemcisinin kabul testleri (stub oturum, canlı istek yok)."""

from __future__ import annotations

import pandas as pd
import pytest

from core.catalog import Kaynak, Seri
from ingest import fred


def _ornek_seri() -> Seri:
    """FRED tipinde örnek Seri döndürür; doğrudan test değil, yardımcıdır."""
    return Seri(
        id="ekonomi-makro/test",
        title="Test Serisi",
        category="ekonomi-makro",
        kaynak=Kaynak(name="FRED", url="https://fred.stlouisfed.org"),
        kaynak_tipi="fred",
        unit="%",
        freq="monthly",
        charts=("level",),
        fred_code="TESTKOD",
    )

class SahteYanit:
    def __init__(self, metin: str, durum: int = 200):
        self.text = metin
        self.status_code = durum


class SahteOturum:
    def __init__(self, yanit: SahteYanit):
        self.yanit = yanit
        self.cagrilar: list[str] = []

    def get(self, url: str, timeout=None):
        self.cagrilar.append(url)
        if self.yanit.status_code != 200:
            return self.yanit
        return self.yanit


CSV_ORNEK = """observation_date,TESTKOD
2026-01-01,10.5
2026-02-01,.
2026-03-01,11.0
"""


def test_fred_bos_gozlemi_dusurup_iki_satir_uretir():
    oturum = SahteOturum(SahteYanit(CSV_ORNEK))
    df = fred.seri_cek(_ornek_seri(), session=oturum)
    assert oturum.cagrilar == [
        "https://fred.stlouisfed.org/graph/fredgraph.csv?id=TESTKOD"
    ]
    assert len(df) == 2  # "." boş gözlemi düşer
    assert df["date"].dtype.kind == "M"
    assert df["date"].tolist() == [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-03-01")]
    assert df["value"].tolist() == [10.5, 11.0]


def test_fred_start_date_onceki_gunleri_atar():
    oturum = SahteOturum(SahteYanit(CSV_ORNEK))
    seri = _ornek_seri()
    filtrelenen = Seri(
        **{
            **{f.name: getattr(seri, f.name) for f in seri.__dataclass_fields__.values()},
            "start_date": "2026-03-01",
        }
    )
    df = fred.seri_cek(filtrelenen, session=oturum)
    assert df["date"].tolist() == [pd.Timestamp("2026-03-01")]


def test_fred_http_hatasinda_runtime_error_verir():
    oturum = SahteOturum(SahteYanit("<!DOCTYPE html>", durum=404))
    with pytest.raises(RuntimeError, match="TESTKOD"):
        fred.seri_cek(_ornek_seri(), session=oturum)
