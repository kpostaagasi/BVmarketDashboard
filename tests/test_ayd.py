"""AYD AVM Metrekare Verimlilik Endeksi istemcisi testleri."""

from datetime import date
from types import SimpleNamespace

import pytest

from ingest.ayd import (
    _govdeyi_ayikla,
    ay_url,
    cekilecek_donemler,
    puan_cek,
    seri_cek,
)


def _bulten_html(cumle: str) -> str:
    return f'<div class="post_content clearfix"><div class="content_box activityDescription"><div class="text"><p>{cumle}</p></div></div></div>'


# --- puan_cek: iki farklı sayı biçimi ---


def test_puan_cek_binlik_noktali():
    html = _bulten_html("nominal olarak yüzde 25,2 artarak 5.169 puan olarak kaydedildi.")
    assert puan_cek(html) == 5169.0


def test_puan_cek_ayracsiz():
    html = _bulten_html("yüzde 28,5 oranında artarak 5004 puana yükseldi.")
    assert puan_cek(html) == 5004.0


def test_govdeyi_ayikla_sablon_degismisse_hata():
    with pytest.raises(RuntimeError, match="içerik kutusu"):
        _govdeyi_ayikla("<html><body>alakasız içerik</body></html>")


def test_puan_cek_puan_ifadesi_yoksa_hata():
    html = _bulten_html("bu ayda hiçbir sayısal değer geçmiyor.")
    with pytest.raises(RuntimeError, match="puan"):
        puan_cek(html)


# --- ay_url: slug üretimi ---


def test_ay_url_slug():
    assert ay_url(2026, 7) == "https://www.ayd.org.tr/temmuz-2026-ciro-endeksi"
    assert ay_url(2025, 2) == "https://www.ayd.org.tr/subat-2025-ciro-endeksi"


# --- cekilecek_donemler: ILK_YIL'den bugüne, gelecek ay yok ---


def test_cekilecek_donemler_gelecek_ay_uretmez():
    donemler = cekilecek_donemler(date(2025, 3, 15))
    assert donemler[-1] == (2025, 3)
    assert (2025, 4) not in donemler


def test_cekilecek_donemler_ilk_yildan_baslar():
    donemler = cekilecek_donemler(date(2025, 2, 1))
    assert donemler[0] == (2025, 1)


# --- seri_cek: 404 atlanır, CA paketi mock'lanır ---


class _SahteYanit:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        pass


class _SahteOturum:
    def __init__(self, aylik_puanlar: dict[tuple[int, int], float]):
        self.aylik_puanlar = aylik_puanlar
        self.cagrilar = []
        self.headers: dict = {}

    def get(self, url, **kwargs):
        self.cagrilar.append(url)
        for (yil, ay), puan in self.aylik_puanlar.items():
            if ay_url(yil, ay) == url:
                return _SahteYanit(text=_bulten_html(f"yüzde 10 artarak {puan:.0f} puan oldu."))
        return _SahteYanit(status_code=404)


def test_seri_cek_eksik_ay_atlanir(monkeypatch):
    monkeypatch.setattr("ingest.ayd._ca_paketi", lambda session=None: None)
    oturum = _SahteOturum({(2025, 1): 3400, (2025, 3): 3829})  # 2025-02 eksik
    df = seri_cek(SimpleNamespace(), onbellek={}, session=oturum, bugun=date(2025, 3, 15))
    assert list(df["date"]) == ["2025-01-01", "2025-03-01"]
    assert list(df["value"]) == [3400.0, 3829.0]


def test_seri_cek_hic_veri_yoksa_hata(monkeypatch):
    monkeypatch.setattr("ingest.ayd._ca_paketi", lambda session=None: None)
    oturum = _SahteOturum({})
    with pytest.raises(RuntimeError, match="hiçbir aydan"):
        seri_cek(SimpleNamespace(), onbellek={}, session=oturum, bugun=date(2025, 1, 15))


def test_seri_cek_onbellek_tekrar_taramaz(monkeypatch):
    monkeypatch.setattr("ingest.ayd._ca_paketi", lambda session=None: None)
    oturum = _SahteOturum({(2025, 1): 3400})
    onbellek: dict = {}
    seri_cek(SimpleNamespace(), onbellek=onbellek, session=oturum, bugun=date(2025, 1, 15))
    ilk_cagri_sayisi = len(oturum.cagrilar)
    seri_cek(SimpleNamespace(), onbellek=onbellek, session=oturum, bugun=date(2025, 1, 15))
    assert len(oturum.cagrilar) == ilk_cagri_sayisi  # ikinci çağrı önbellekten döndü
