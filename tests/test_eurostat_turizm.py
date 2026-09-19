"""Eurostat tour_occ_nim (konaklama geceleme) istemcisi testleri.

Yanıt gövdesi gerçek JSON-stat yapısını taklit eder: boyut sırası
[freq, c_resid, unit, nace_r2, geo, time]; sorguda freq/unit/nace_r2/geo
tek kategori (boyut-1), yalnızca c_resid (3 kategori) ve time gerçekten
değişkendir — düz değer dizisi indeksi c_resid_i * zaman_uzunluğu + zaman_i.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ingest.eurostat_turizm import PARAMETRELER, UC, seri_cek


def _json_stat_govdesi(zaman_etiketleri: list[str], resid_degerleri: dict[str, list[float | None]]) -> dict:
    zaman_index = {t: i for i, t in enumerate(zaman_etiketleri)}
    resid_index = {r: i for i, r in enumerate(resid_degerleri)}
    n = len(zaman_etiketleri)
    degerler = {}
    for resid, degerler_listesi in resid_degerleri.items():
        r_i = resid_index[resid]
        for t_i, deger in enumerate(degerler_listesi):
            if deger is not None:
                degerler[str(r_i * n + t_i)] = deger
    return {
        "dimension": {
            "time": {"category": {"index": zaman_index}},
            "c_resid": {"category": {"index": resid_index}},
        },
        "size": [1, len(resid_index), 1, 1, 1, n],
        "value": degerler,
    }


class SahteYanit:
    def __init__(self, govde: dict, status_code: int = 200):
        self.govde = govde
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.govde


class SahteOturum:
    def __init__(self, govde: dict):
        self.govde = govde
        self.calls: list[tuple] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        assert url == UC
        assert params == PARAMETRELER
        return SahteYanit(self.govde)


def _seri(resid: str):
    return SimpleNamespace(eurostat_turizm_resid=resid)


def test_seri_cek_duz_indeksi_dogru_cozer_total():
    govde = _json_stat_govdesi(
        ["2025-11", "2025-12"],
        {"TOTAL": [15321457.0, 12272844.0], "DOM": [7742940.0, 6903812.0], "FOR": [7578517.0, 5369032.0]},
    )
    oturum = SahteOturum(govde)
    df = seri_cek(_seri("TOTAL"), onbellek={}, session=oturum)
    satirlar = dict(zip(df["date"], df["value"]))
    assert satirlar["2025-12-01"] == 12272844.0
    assert satirlar["2025-11-01"] == 15321457.0


def test_seri_cek_dom_ve_for_farkli_dilimi_okur():
    govde = _json_stat_govdesi(
        ["2025-12"],
        {"TOTAL": [12272844.0], "DOM": [6903812.0], "FOR": [5369032.0]},
    )
    oturum = SahteOturum(govde)
    df_dom = seri_cek(_seri("DOM"), onbellek={}, session=oturum)
    df_for = seri_cek(_seri("FOR"), onbellek={}, session=oturum)
    assert df_dom["value"].iloc[0] == 6903812.0
    assert df_for["value"].iloc[0] == 5369032.0


def test_seri_cek_eksik_deger_satir_uretmez():
    govde = _json_stat_govdesi(["2025-11", "2025-12"], {"TOTAL": [None, 12272844.0]})
    oturum = SahteOturum(govde)
    df = seri_cek(_seri("TOTAL"), onbellek={}, session=oturum)
    assert list(df["date"]) == ["2025-12-01"]


def test_seri_cek_gecersiz_resid_hata():
    govde = _json_stat_govdesi(["2025-12"], {"TOTAL": [12272844.0]})
    oturum = SahteOturum(govde)
    with pytest.raises(RuntimeError, match="Geçersiz eurostat_turizm_resid"):
        seri_cek(_seri("YABANCI"), onbellek={}, session=oturum)


def test_seri_cek_onbellegi_api_yanitini_paylasir():
    govde = _json_stat_govdesi(
        ["2025-12"], {"TOTAL": [12272844.0], "DOM": [6903812.0], "FOR": [5369032.0]},
    )
    oturum = SahteOturum(govde)
    onbellek: dict = {}
    seri_cek(_seri("TOTAL"), onbellek=onbellek, session=oturum)
    ilk_cagri = len(oturum.calls)
    seri_cek(_seri("DOM"), onbellek=onbellek, session=oturum)
    seri_cek(_seri("FOR"), onbellek=onbellek, session=oturum)
    assert len(oturum.calls) == ilk_cagri, "sonraki seriler API'ye tekrar istek atmamalı"
