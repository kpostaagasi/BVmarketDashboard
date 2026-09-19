"""Eurostat sts_copr_m (İnşaat Üretim Endeksi) istemcisi testleri.

`ingest.eurostat_turizm` testleriyle aynı JSON-stat düz-indeks deseni;
buradaki serbest eksen `nace_r2` (F/F41/F42/F43).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ingest.eurostat_insaat import PARAMETRELER, UC, seri_cek


def _json_stat_govdesi(
    zaman_etiketleri: list[str], nace_degerleri: dict[str, list[float | None]]
) -> dict:
    zaman_index = {t: i for i, t in enumerate(zaman_etiketleri)}
    nace_kodlari = list(nace_degerleri)
    nace_index = {kod: i for i, kod in enumerate(nace_kodlari)}
    zaman_uzunlugu = len(zaman_etiketleri)
    value = {}
    for kod, degerler in nace_degerleri.items():
        for t, deger in zip(zaman_etiketleri, degerler):
            if deger is None:
                continue
            duz = nace_index[kod] * zaman_uzunlugu + zaman_index[t]
            value[str(duz)] = deger
    return {
        "dimension": {
            "nace_r2": {"category": {"index": nace_index}},
            "time": {"category": {"index": zaman_index}},
        },
        "size": [1, 1, len(nace_kodlari), 1, 1, 1, zaman_uzunlugu],
        "value": value,
    }


class SahteYanit:
    def __init__(self, govde: dict, status_code: int = 200):
        self.status_code = status_code
        self._govde = govde

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._govde


class SahteOturum:
    def __init__(self, govde: dict):
        self.govde = govde
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        assert url == UC
        assert params == PARAMETRELER
        return SahteYanit(self.govde)


def _seri(nace: str):
    return SimpleNamespace(eurostat_insaat_nace=nace)


def test_seri_cek_duz_indeksi_dogru_cozer_f():
    govde = _json_stat_govdesi(
        ["2026-06", "2026-07"],
        {"F": [115.3, 119.6], "F41": [130.2, 134.3]},
    )
    oturum = SahteOturum(govde)
    df = seri_cek(_seri("F"), onbellek={}, session=oturum)
    satirlar = dict(zip(df["date"], df["value"]))
    assert satirlar == {"2026-06-01": 115.3, "2026-07-01": 119.6}


def test_seri_cek_farkli_nace_farkli_dilimi_okur():
    govde = _json_stat_govdesi(
        ["2026-07"], {"F": [119.6], "F41": [134.3], "F42": [88.8], "F43": [107.3]}
    )
    oturum = SahteOturum(govde)
    for nace, beklenen in [("F", 119.6), ("F41", 134.3), ("F42", 88.8), ("F43", 107.3)]:
        df = seri_cek(_seri(nace), onbellek={}, session=oturum)
        assert df["value"].iloc[0] == beklenen


def test_seri_cek_eksik_deger_satir_uretmez():
    govde = _json_stat_govdesi(["2026-06", "2026-07"], {"F": [None, 119.6]})
    oturum = SahteOturum(govde)
    df = seri_cek(_seri("F"), onbellek={}, session=oturum)
    assert list(df["date"]) == ["2026-07-01"]


def test_seri_cek_gecersiz_nace_hata():
    govde = _json_stat_govdesi(["2026-07"], {"F": [119.6]})
    oturum = SahteOturum(govde)
    with pytest.raises(RuntimeError, match="eurostat_insaat_nace"):
        seri_cek(_seri("F99"), onbellek={}, session=oturum)


def test_seri_cek_onbellegi_api_yanitini_paylasir():
    govde = _json_stat_govdesi(["2026-07"], {"F": [119.6], "F41": [134.3]})
    oturum = SahteOturum(govde)
    onbellek: dict = {}
    seri_cek(_seri("F"), onbellek=onbellek, session=oturum)
    ilk_cagri = oturum.calls
    seri_cek(_seri("F41"), onbellek=onbellek, session=oturum)
    assert oturum.calls == ilk_cagri, "ikinci seri aynı API yanıtını paylaşmalı"
