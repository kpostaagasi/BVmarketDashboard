"""TÜİK kümes hayvancılığı üretim istatistiği (Eurostat apro_mt_pwgtm aynası)
istemcisi testleri."""

from types import SimpleNamespace

import pytest

from ingest.tuik import OLCUT_KODLARI, noktalari_ayikla, seri_cek


def tuik_seri(**kwargs):
    varsayilan = dict(id="kanatli/toplam-uretim", kaynak_tipi="tuik_kanatli", tuik_kanatli_olcut="toplam-uretim")
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


def _json_stat(meat_kodlari, unit_kodlari, zaman_etiketleri, degerler_matrisi):
    """`degerler_matrisi[meat_idx][unit_idx][t]` -> değer ya da None (eksik)."""
    zaman_boyutu = len(zaman_etiketleri)
    unit_boyutu = len(unit_kodlari)
    value = {}
    for mi, satir in enumerate(degerler_matrisi):
        for ui, seri in enumerate(satir):
            for t, deger in enumerate(seri):
                if deger is not None:
                    taban = (mi * unit_boyutu + ui) * zaman_boyutu
                    value[str(taban + t)] = deger
    return {
        "dimension": {
            "meat": {"category": {"index": {k: i for i, k in enumerate(meat_kodlari)}}},
            "unit": {"category": {"index": {k: i for i, k in enumerate(unit_kodlari)}}},
            "time": {"category": {"index": {k: i for i, k in enumerate(zaman_etiketleri)}}},
        },
        "value": value,
    }


# --- noktalari_ayikla ---


def test_noktalari_ayikla_dogru_hucreyi_okur():
    veri = _json_stat(
        ["B7000", "B7100"], ["THS_T", "THS_HD"], ["2026-06", "2026-07"],
        [[[206.27, 237.18], [None, None]], [[None, None], [108064.56, 133407.03]]],
    )
    assert noktalari_ayikla(veri, "B7000", "THS_T") == [("2026-06-01", 206.27), ("2026-07-01", 237.18)]
    assert noktalari_ayikla(veri, "B7100", "THS_HD") == [("2026-06-01", 108064.56), ("2026-07-01", 133407.03)]


def test_noktalari_ayikla_eksik_ayi_atlar():
    veri = _json_stat(["B7000"], ["THS_T"], ["2026-06", "2026-07"], [[[206.27, None]]])
    assert noktalari_ayikla(veri, "B7000", "THS_T") == [("2026-06-01", 206.27)]


def test_noktalari_ayikla_bilinmeyen_meat_kodunda_hata():
    veri = _json_stat(["B7000"], ["THS_T"], ["2026-06"], [[[1.0]]])
    with pytest.raises(RuntimeError, match="meat kodu"):
        noktalari_ayikla(veri, "B9999", "THS_T")


def test_olcut_kodlari_uc_olcutu_kapsar():
    assert set(OLCUT_KODLARI) == {"toplam-uretim", "tavuk-uretim", "kesilen-tavuk"}
    assert OLCUT_KODLARI["kesilen-tavuk"] == ("B7100", "THS_HD")


# --- seri_cek: ağ kabuğu ---


class SahteOturum:
    def __init__(self, json_veri):
        self.json_veri = json_veri
        self.cagri_sayisi = 0

    def get(self, url, params=None, timeout=None):
        self.cagri_sayisi += 1
        return SimpleNamespace(status_code=200, json=lambda: self.json_veri)


def test_seri_cek_dogru_seriyi_secer_ve_olceklenmemis_deger_doner():
    veri = _json_stat(
        ["B7000", "B7100"], ["THS_T", "THS_HD"], ["2026-07"],
        [[[257.0], [None]], [[251.86], [133407.03]]],
    )
    oturum = SahteOturum(veri)
    df = seri_cek(tuik_seri(), onbellek={}, session=oturum)
    assert list(df["date"]) == ["2026-07-01"]
    assert df["value"].iloc[0] == pytest.approx(257.0)  # olcek katalogda uygulanır, adaptörde değil


def test_seri_cek_onbellegi_paylasir():
    veri = _json_stat(["B7000", "B7100"], ["THS_T", "THS_HD"], ["2026-07"], [[[1.0], [1.0]], [[1.0], [1.0]]])
    oturum = SahteOturum(veri)
    onbellek = {}
    seri_cek(tuik_seri(), onbellek=onbellek, session=oturum)
    seri_cek(tuik_seri(tuik_kanatli_olcut="tavuk-uretim"), onbellek=onbellek, session=oturum)
    assert oturum.cagri_sayisi == 1


def test_seri_cek_veri_yoksa_hata():
    veri = _json_stat(["B7000", "B7100"], ["THS_T", "THS_HD"], ["2026-07"], [[[None], [None]], [[None], [None]]])
    oturum = SahteOturum(veri)
    with pytest.raises(RuntimeError, match="hiç veri yok"):
        seri_cek(tuik_seri(), onbellek={}, session=oturum)


def test_seri_cek_http_hatasi_yukselir():
    class HataliOturum:
        def get(self, url, params=None, timeout=None):
            return SimpleNamespace(status_code=500, json=lambda: {})

    with pytest.raises(RuntimeError, match="HTTP 500"):
        seri_cek(tuik_seri(), onbellek={}, session=HataliOturum())
