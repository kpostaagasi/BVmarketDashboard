from datetime import date
from types import SimpleNamespace

import pytest

from ingest.epias import (
    _kapasite_agirlikli_doluluk,
    baraj_doluluk_cek,
    havza_listesi_cek,
)


class SahteYanit:
    def __init__(self, status_code, govde=None):
        self.status_code = status_code
        self._govde = govde or {}

    def json(self):
        return self._govde


class SahteCokluOturum:
    """URL'e göre farklı yanıt dönen sahte oturum (baraj iki uç kullanıyor)."""

    def __init__(self, yanitlar_by_url):
        self._yanitlar = yanitlar_by_url
        self.istekler: list[dict] = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.istekler.append({"url": url, "headers": headers, "govde": json})
        for parca, yanit in self._yanitlar.items():
            if parca in url:
                return yanit
        raise AssertionError(f"beklenmeyen url: {url}")

    def get(self, url, headers=None, timeout=None):
        self.istekler.append({"url": url, "headers": headers})
        for parca, yanit in self._yanitlar.items():
            if parca in url:
                return yanit
        raise AssertionError(f"beklenmeyen url: {url}")


def _hacim_govdesi(kayitlar):
    return SahteYanit(200, {"items": [
        {"date": "2026-09-18T00:00:00+03:00", "basinName": basin, "damName": ad,
         "activeVolume": hacim, "id": 900, "damId": did}
        for did, basin, ad, hacim in kayitlar
    ]})


def _kapasite_govdesi(kayitlar):
    return SahteYanit(200, {"items": [
        {"date": "2026-09-18T13:00:00+03:00", "basinName": basin, "damName": ad,
         "maxVolume": maxv, "minVolume": minv, "id": did}
        for did, basin, ad, maxv, minv in kayitlar
    ]})


def _seri(**kwargs):
    varsayilan = dict(
        id="elektrik/baraj-doluluk-turkiye", title="t", category="elektrik",
        kaynak=SimpleNamespace(name="x", url="y"), kaynak_tipi="epias",
        unit="%", freq="daily", charts=("level",), epias_ucu="baraj-doluluk",
        epias_havza=None, monthly_agg="mean",
    )
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


# --- _kapasite_agirlikli_doluluk (saf) ---


def test_kapasite_agirlikli_doluluk_turkiye_geneli_agirlikli_ortalama_alir():
    # Baraj A: 50/100 hacim (%50), Baraj B: 180/200 hacim (%90).
    # Basit ortalama %70 olurdu; kapasite ağırlıklı = (50+180)/(100+200)*100.
    hacimler = {1: 50.0, 2: 180.0}
    kapasiteler = {1: 100.0, 2: 200.0}
    havza_by_id = {1: "Sakarya", 2: "Sakarya"}
    deger = _kapasite_agirlikli_doluluk(hacimler, kapasiteler, havza_by_id, None)
    assert deger == pytest.approx(230.0 / 300.0 * 100)


def test_kapasite_agirlikli_doluluk_havza_filtresi_uygular():
    hacimler = {1: 50.0, 2: 180.0}
    kapasiteler = {1: 100.0, 2: 200.0}
    havza_by_id = {1: "Sakarya", 2: "Ceyhan"}
    assert _kapasite_agirlikli_doluluk(hacimler, kapasiteler, havza_by_id, "Sakarya") == 50.0
    assert _kapasite_agirlikli_doluluk(hacimler, kapasiteler, havza_by_id, "Ceyhan") == 90.0


def test_kapasite_agirlikli_doluluk_kapasitesi_olmayan_baraji_atlar():
    # id=3'ün kapasitesi yok (dam-volume'da hiç yok) — payı da dışarıda kalmalı.
    hacimler = {1: 50.0, 3: 999.0}
    kapasiteler = {1: 100.0}
    havza_by_id = {1: "Sakarya", 3: "Sakarya"}
    assert _kapasite_agirlikli_doluluk(hacimler, kapasiteler, havza_by_id, None) == 50.0


def test_kapasite_agirlikli_doluluk_kapasite_sifirsa_yukselir():
    with pytest.raises(RuntimeError, match="Sakarya"):
        _kapasite_agirlikli_doluluk({}, {}, {}, "Sakarya")


# --- baraj_doluluk_cek ---


def test_baraj_doluluk_cek_turkiye_genelini_hesaplar():
    oturum = SahteCokluOturum({
        "active-volume": _hacim_govdesi([
            (1, "Sakarya", "A", 50.0), (2, "Ceyhan", "B", 180.0),
        ]),
        "dam-volume": _kapasite_govdesi([
            (1, "Sakarya", "A", 100.0, 0.0), (2, "Ceyhan", "B", 200.0, 0.0),
        ]),
    })
    df = baraj_doluluk_cek(_seri(), "TGT-abc", session=oturum, bugun=date(2026, 9, 18))
    assert list(df.columns) == ["date", "value"]
    assert df.iloc[0]["date"] == "2026-09-18"
    assert df.iloc[0]["value"] == pytest.approx(230.0 / 300.0 * 100)


def test_baraj_doluluk_cek_havza_filtreli_seri_yalnizca_o_havzayi_toplar():
    oturum = SahteCokluOturum({
        "active-volume": _hacim_govdesi([
            (1, "Sakarya", "A", 50.0), (2, "Ceyhan", "B", 180.0),
        ]),
        "dam-volume": _kapasite_govdesi([
            (1, "Sakarya", "A", 100.0, 0.0), (2, "Ceyhan", "B", 200.0, 0.0),
        ]),
    })
    df = baraj_doluluk_cek(
        _seri(epias_havza="Ceyhan"), "TGT-abc", session=oturum, bugun=date(2026, 9, 18)
    )
    assert df.iloc[0]["value"] == pytest.approx(90.0)


def test_baraj_doluluk_cek_tgt_basligini_gonderir():
    oturum = SahteCokluOturum({
        "active-volume": _hacim_govdesi([(1, "Sakarya", "A", 50.0)]),
        "dam-volume": _kapasite_govdesi([(1, "Sakarya", "A", 100.0, 0.0)]),
    })
    baraj_doluluk_cek(_seri(), "TGT-xyz", session=oturum, bugun=date(2026, 9, 18))
    assert all(istek["headers"]["TGT"] == "TGT-xyz" for istek in oturum.istekler)


def test_baraj_doluluk_cek_http_hatasinda_yukselir():
    oturum = SahteCokluOturum({
        "active-volume": SahteYanit(500),
        "dam-volume": _kapasite_govdesi([]),
    })
    with pytest.raises(RuntimeError, match="500"):
        baraj_doluluk_cek(_seri(), "TGT-abc", session=oturum, bugun=date(2026, 9, 18))


def test_baraj_doluluk_cek_bos_hacim_listesinde_yukselir():
    oturum = SahteCokluOturum({
        "active-volume": _hacim_govdesi([]),
        "dam-volume": _kapasite_govdesi([]),
    })
    with pytest.raises(RuntimeError, match="boş"):
        baraj_doluluk_cek(_seri(), "TGT-abc", session=oturum, bugun=date(2026, 9, 18))


def test_baraj_doluluk_cek_onbellek_iki_seride_iki_istege_dusurur():
    # 18 seri (17 havza + ülke) aynı iki uçtan aynı yanıtı paylaşır.
    oturum = SahteCokluOturum({
        "active-volume": _hacim_govdesi([
            (1, "Sakarya", "A", 50.0), (2, "Ceyhan", "B", 180.0),
        ]),
        "dam-volume": _kapasite_govdesi([
            (1, "Sakarya", "A", 100.0, 0.0), (2, "Ceyhan", "B", 200.0, 0.0),
        ]),
    })
    onbellek: dict = {}
    baraj_doluluk_cek(_seri(), "TGT-abc", session=oturum, bugun=date(2026, 9, 18), onbellek=onbellek)
    baraj_doluluk_cek(
        _seri(epias_havza="Ceyhan"), "TGT-abc", session=oturum,
        bugun=date(2026, 9, 18), onbellek=onbellek,
    )
    assert len(oturum.istekler) == 2  # 4 değil


# --- havza_listesi_cek ---


def test_havza_listesi_cek_listeyi_doner():
    oturum = SahteCokluOturum({"basin-list": SahteYanit(200, ["Sakarya", "Ceyhan"])})
    assert havza_listesi_cek("TGT-abc", session=oturum) == ["Sakarya", "Ceyhan"]


def test_havza_listesi_cek_http_hatasinda_yukselir():
    oturum = SahteCokluOturum({"basin-list": SahteYanit(404)})
    with pytest.raises(RuntimeError, match="404"):
        havza_listesi_cek("TGT-abc", session=oturum)
