"""EIA `dnav` istemcisinin kabul testleri (stub oturum, canlı istek yok)."""

from __future__ import annotations

from io import BytesIO

import openpyxl
import pytest

from core.catalog import Kaynak, Seri
from ingest import eia


def _ornek_seri(**kwargs) -> Seri:
    varsayilan = dict(
        id="emtia-enerji/test",
        title="Test Serisi",
        category="emtia-enerji",
        kaynak=Kaynak(name="EIA", url="https://www.eia.gov"),
        kaynak_tipi="eia",
        unit="USD/gal",
        freq="daily",
        charts=("level",),
        eia_series_id="EER_EPJK_PF4_RGC_DPG",
    )
    varsayilan.update(kwargs)
    return Seri(**varsayilan)


def _dnav_xls(satirlar: list[tuple[str, float]]) -> bytes:
    """EIA `dnav` `.xls`'inin "Data 1" sayfasını taklit eden gerçek bir
    workbook üretir (3 metadata satırı + tarih/değer çiftleri, gerçek
    dosyayla birebir — bkz. ingest/eia.py docstring'i)."""
    kitap = openpyxl.Workbook()
    sayfa = kitap.active
    sayfa.title = "Data 1"
    sayfa.append(["Back to Contents", "Data 1: U.S. Gulf Coast Kerosene-Type Jet Fuel Spot Price FOB (Dollars per Gallon)"])
    sayfa.append(["Sourcekey", "EER_EPJK_PF4_RGC_DPG"])
    sayfa.append(["Date", "U.S. Gulf Coast Kerosene-Type Jet Fuel Spot Price FOB (Dollars per Gallon)"])
    for tarih, deger in satirlar:
        sayfa.append([tarih, deger])
    tampon = BytesIO()
    kitap.save(tampon)
    return tampon.getvalue()


class SahteYanit:
    def __init__(self, durum: int, icerik: bytes = b""):
        self.status_code = durum
        self.content = icerik


class SahteOturum:
    def __init__(self, yanit: SahteYanit):
        self.yanit = yanit
        self.cagrilar: list[str] = []

    def get(self, url: str, timeout=None):
        self.cagrilar.append(url)
        return self.yanit


def test_seri_cek_dogru_url_ve_degerleri_dondurur():
    icerik = _dnav_xls([("2026-09-14", 4.488), ("2026-09-15", 4.705)])
    oturum = SahteOturum(SahteYanit(200, icerik))
    df = eia.seri_cek(_ornek_seri(), session=oturum)
    assert oturum.cagrilar == [
        "https://www.eia.gov/dnav/pet/hist_xls/EER_EPJK_PF4_RGC_DPGd.xls"
    ]
    assert df["date"].tolist() == ["2026-09-14", "2026-09-15"]
    assert df["value"].tolist() == [4.488, 4.705]


def test_seri_cek_start_date_onceki_gunleri_atar():
    icerik = _dnav_xls([("2026-09-14", 4.488), ("2026-09-15", 4.705)])
    oturum = SahteOturum(SahteYanit(200, icerik))
    df = eia.seri_cek(_ornek_seri(start_date="2026-09-15"), session=oturum)
    assert df["date"].tolist() == ["2026-09-15"]


def test_seri_cek_http_hatasinda_yukselir():
    oturum = SahteOturum(SahteYanit(404))
    with pytest.raises(RuntimeError, match="EER_EPJK_PF4_RGC_DPG"):
        eia.seri_cek(_ornek_seri(), session=oturum)


def test_seri_cek_bos_seride_yukselir():
    icerik = _dnav_xls([])
    oturum = SahteOturum(SahteYanit(200, icerik))
    with pytest.raises(RuntimeError, match="boş seri"):
        eia.seri_cek(_ornek_seri(), session=oturum)
