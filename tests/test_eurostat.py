"""Eurostat elektrik fiyatı istemcisi (nrg_pc_204/nrg_pc_205) testleri.

Gerçek kaynaktan canlı ölçülen JSON-stat 2.0 zarf yapısı pinlenir: `value`
sözlüğünün SATIR-ESAS düz indeksten çözülmesi, `geo`/`currency` eksenlerinin
tek istekte birden çok değer taşıması, ve "YYYY-S1"/"YYYY-S2" yarıyıl
etiketinin yarıyılın İLK ayına damgalanması. TR/EUR ve TR/NAC değerleri
2025-S2 için CANLI ölçülen gerçek rakamlarla (6,79 cent EUR/kWh hane, 3,2857
TL/kWh hane, 9,17 cent EUR/kWh sanayi, 4,4411 TL/kWh sanayi) BİREBİR eşleşti
— MarketVisuals'ın eurostat_electricity_prices.html kartlarına bkz. modül
docstring'i.
"""

from types import SimpleNamespace

import pytest

from ingest.eurostat import _donem_tarihi, _noktalari_coz, _veri_getir, seri_cek


def eurostat_seri(**kwargs):
    varsayilan = dict(
        id="elektrik-avrupa/hane-tr-cent",
        kaynak_tipi="eurostat",
        eurostat_dataset="nrg_pc_204",
        eurostat_geo="TR",
        eurostat_currency="EUR",
        start_date=None,
    )
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


def _json_stat_govdesi():
    """2 geo × 2 currency × 2 time = 8 nokta taşıyan küçük bir JSON-stat
    2.0 zarfı — gerçek Eurostat yanıtının aynı geometri kuralına uyar
    (bkz. modül docstring'i, `id`/`size` sırası SATIR-ESAS)."""
    return {
        "id": ["geo", "currency", "time"],
        "size": [2, 2, 2],
        "dimension": {
            "geo": {"category": {"index": {"TR": 0, "EU27_2020": 1}}},
            "currency": {"category": {"index": {"EUR": 0, "NAC": 1}}},
            "time": {"category": {"index": {"2025-S1": 0, "2025-S2": 1}}},
        },
        # flat index = geo*4 + currency*2 + time (son boyut en hızlı değişen)
        "value": {
            "0": 0.0657,  # TR, EUR, 2025-S1
            "1": 0.0679,  # TR, EUR, 2025-S2
            "2": 2.7028,  # TR, NAC, 2025-S1
            "3": 3.2857,  # TR, NAC, 2025-S2
            "5": 0.2942,  # EU27_2020, EUR, 2025-S2 (2025-S1 EKSİK — sparse)
        },
    }


# --- _noktalari_coz: JSON-stat 2.0 düz indeks çözümü ---


def test_noktalari_coz_dogru_koordinatlara_esler():
    noktalar = _noktalari_coz(_json_stat_govdesi())
    assert len(noktalar) == 5
    by_key = {(n["geo"], n["currency"], n["time"]): n["value"] for n in noktalar}
    assert by_key[("TR", "EUR", "2025-S1")] == pytest.approx(0.0657)
    assert by_key[("TR", "EUR", "2025-S2")] == pytest.approx(0.0679)
    assert by_key[("TR", "NAC", "2025-S2")] == pytest.approx(3.2857)
    assert by_key[("EU27_2020", "EUR", "2025-S2")] == pytest.approx(0.2942)


def test_noktalari_coz_seyrek_eksik_kombinasyonu_atlar():
    """Eurostat yalnızca VERİSİ OLAN kombinasyonları `value`de taşır —
    EU27_2020/EUR/2025-S1 hiç anahtar olarak yok (canlı davranış)."""
    noktalar = _noktalari_coz(_json_stat_govdesi())
    assert not any(
        n["geo"] == "EU27_2020" and n["currency"] == "EUR" and n["time"] == "2025-S1"
        for n in noktalar
    )


# --- _donem_tarihi: yarıyıl -> yarıyılın ilk ayı ---


def test_donem_tarihi_s1_ocaka_damgalanir():
    assert _donem_tarihi("2025-S1") == "2025-01-01"


def test_donem_tarihi_s2_temmuza_damgalanir():
    assert _donem_tarihi("2025-S2") == "2025-07-01"


# --- _veri_getir: onbellek dataset başına tek istek paylaşır ---


class SahteYanit:
    def __init__(self, status_code, govde=None):
        self.status_code = status_code
        self._govde = govde or {}

    def json(self):
        return self._govde


class SahteOturum:
    def __init__(self, yanit):
        self._yanit = yanit
        self.istek_sayisi = 0

    def get(self, url, params=None, timeout=None):
        self.istek_sayisi += 1
        return self._yanit


def test_veri_getir_http_hatasinda_yukselir():
    oturum = SahteOturum(SahteYanit(500))
    with pytest.raises(RuntimeError, match="500"):
        _veri_getir("nrg_pc_204", {}, session=oturum)


def test_veri_getir_onbellek_paylasilirsa_tekrar_istek_atilmaz():
    oturum = SahteOturum(SahteYanit(200, _json_stat_govdesi()))
    onbellek = {}
    _veri_getir("nrg_pc_204", onbellek, session=oturum)
    _veri_getir("nrg_pc_204", onbellek, session=oturum)
    assert oturum.istek_sayisi == 1


def test_veri_getir_farkli_dataset_ayri_istek_atar():
    oturum = SahteOturum(SahteYanit(200, _json_stat_govdesi()))
    onbellek = {}
    _veri_getir("nrg_pc_204", onbellek, session=oturum)
    _veri_getir("nrg_pc_205", onbellek, session=oturum)
    assert oturum.istek_sayisi == 2


# --- seri_cek: uçtan uca ---


def test_seri_cek_geo_ve_currencye_gore_filtreler_tarihe_gore_siralar():
    oturum = SahteOturum(SahteYanit(200, _json_stat_govdesi()))
    df = seri_cek(eurostat_seri(), onbellek={}, session=oturum)
    assert list(df["date"]) == ["2025-01-01", "2025-07-01"]
    assert list(df["value"]) == pytest.approx([0.0657, 0.0679])


def test_seri_cek_nac_para_birimi_ayri_seri_doner():
    oturum = SahteOturum(SahteYanit(200, _json_stat_govdesi()))
    df = seri_cek(eurostat_seri(eurostat_currency="NAC"), onbellek={}, session=oturum)
    assert list(df["value"]) == pytest.approx([2.7028, 3.2857])


def test_seri_cek_eu27_seyrek_veride_yalnizca_mevcut_donemi_doner():
    oturum = SahteOturum(SahteYanit(200, _json_stat_govdesi()))
    df = seri_cek(
        eurostat_seri(eurostat_geo="EU27_2020"), onbellek={}, session=oturum
    )
    assert list(df["date"]) == ["2025-07-01"]


def test_seri_cek_eslesme_yoksa_hata():
    oturum = SahteOturum(SahteYanit(200, _json_stat_govdesi()))
    with pytest.raises(RuntimeError, match="veri yok"):
        seri_cek(eurostat_seri(eurostat_geo="DE"), onbellek={}, session=oturum)


def test_seri_cek_start_date_filtreler():
    oturum = SahteOturum(SahteYanit(200, _json_stat_govdesi()))
    df = seri_cek(
        eurostat_seri(start_date="2025-06-01"), onbellek={}, session=oturum
    )
    assert list(df["date"]) == ["2025-07-01"]


def test_seri_cek_onbellek_paylasilirsa_ayni_dataset_tekrar_cekilmez():
    """6 seri (2 dataset × 3 geo/currency) aynı 2 GET isteğini paylaşır."""
    oturum = SahteOturum(SahteYanit(200, _json_stat_govdesi()))
    onbellek = {}
    seri_cek(eurostat_seri(eurostat_currency="EUR"), onbellek=onbellek, session=oturum)
    seri_cek(eurostat_seri(eurostat_currency="NAC"), onbellek=onbellek, session=oturum)
    seri_cek(
        eurostat_seri(eurostat_geo="EU27_2020", eurostat_currency="EUR"),
        onbellek=onbellek,
        session=oturum,
    )
    assert oturum.istek_sayisi == 1
