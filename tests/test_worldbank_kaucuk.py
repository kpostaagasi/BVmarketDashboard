"""Dünya Bankası Pink Sheet "Rubber, TSR20" ekleme testi
(`ingest/worldbank.py::SERI_TANIMLARI["kaucuk-tsr20"]`).

Ayrı dosyada: `tests/test_worldbank.py` gübre-endeksi/urea/dap serilerinin
sahibi (bkz. proje geçmişi); bu dosya yalnızca "Doğal Kauçuk - ABD" ailesi
için eklenen dördüncü seriyi kapsar, mevcut dosyaya dokunmaz.
"""

from __future__ import annotations

import io
from types import SimpleNamespace

import openpyxl
import pytest

from ingest.worldbank import SERI_TANIMLARI, seri_cek


def wb_seri(**kwargs):
    varsayilan = dict(id="emtia-diger/kaucuk-tsr20-test", wb_seri="kaucuk-tsr20", start_date=None)
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


def test_seri_tanimlari_kaucuk_tsr20_dogru_sayfa_ve_etikete_isaret_eder():
    assert SERI_TANIMLARI["kaucuk-tsr20"] == ("Monthly Prices", "Rubber, TSR20")


class SahteYanit:
    def __init__(self, content=b"", text=None, status_code=200):
        self.content = content
        self.text = text
        self.status_code = status_code


class SahteOturum:
    def __init__(self, yanit_haritasi):
        self.yanit_haritasi = yanit_haritasi

    def get(self, url, timeout=None, headers=None):
        return self.yanit_haritasi[url]


DOSYA_URL = "https://thedocs.worldbank.org/x/related/CMO-Historical-Data-Monthly.xlsx"
LANDING_SAYFASI = "https://www.worldbank.org/en/research/commodity-markets"


def _pink_sheet_baytlari() -> bytes:
    """Ölçülen gerçek başlık/veri deseniyle sahte "Monthly Prices" sayfası:
    5. satıra kadar başlık, sonra `YYYYMmm` etiketli veri satırları — gerçek
    dosyada "Rubber, TSR20" 56. sütun, burada test için 2. sütun."""
    kitap = openpyxl.Workbook()
    ws = kitap.active
    ws.title = "Monthly Prices"
    for _ in range(4):
        ws.append([None])
    ws.append([None, "Rubber, TSR20", "Rubber, RSS3"])
    ws.append([None, "($/kg)", "($/kg)"])
    ws.append(["2026M07", 2.14, 2.78])
    ws.append(["2026M08", 2.24, 2.73])
    tampon = io.BytesIO()
    kitap.save(tampon)
    return tampon.getvalue()


def _pink_sheet_oturumu() -> SahteOturum:
    html = f'<a href="{DOSYA_URL}">CMO-Historical-Data-Monthly.xlsx</a>'
    return SahteOturum({
        LANDING_SAYFASI: SahteYanit(text=html),
        DOSYA_URL: SahteYanit(content=_pink_sheet_baytlari()),
    })


def test_seri_cek_kaucuk_tsr20_dogru_deger_dondurur():
    """Ölçülen gerçek (Ağustos 2026): WB Rubber TSR20 = 2,24 $/kg —
    marketvisuals'ın "Doğal Kauçuk - ABD (Gerçekleşen)" kartıyla (2,32) 13
    aylık pencerede oran 0,98–1,05 bandında, aynı küresel benchmark."""
    df = seri_cek(wb_seri(), onbellek={}, session=_pink_sheet_oturumu())
    assert list(df["date"]) == ["2026-07-01", "2026-08-01"]
    assert df["value"].iloc[-1] == pytest.approx(2.24)


def test_seri_cek_kaucuk_tsr20_rss3_sutunuyla_karismaz():
    """Aynı sayfada bitişik "Rubber, RSS3" sütunu yanlışlıkla okunmamalı —
    ölçüldü: bu iki seri 2026'da sürekli açılan bir oranla farklılaşıyor,
    biri diğerinin yerine geçemez."""
    df = seri_cek(wb_seri(), onbellek={}, session=_pink_sheet_oturumu())
    assert df["value"].iloc[-1] != pytest.approx(2.73)
