from datetime import date
from types import SimpleNamespace

import pytest

from ingest.epias import noktalari_ayikla, seri_cek, tgt_al


def yanit(kayitlar):
    return {"items": kayitlar}


def test_noktalari_ayikla_tarih_ve_degeri_cikarir():
    ham = yanit([
        {"date": "2026-08-01T00:00:00+03:00", "price": 2500.0},
        {"date": "2026-08-01T01:00:00+03:00", "price": 2450.5},
    ])
    assert noktalari_ayikla(ham, "price") == [
        ("2026-08-01", 2500.0),
        ("2026-08-01", 2450.5),
    ]


def test_noktalari_ayikla_bos_degeri_atlar():
    ham = yanit([
        {"date": "2026-08-01T00:00:00+03:00", "price": None},
        {"date": "2026-08-02T00:00:00+03:00", "price": 2450.5},
    ])
    assert noktalari_ayikla(ham, "price") == [("2026-08-02", 2450.5)]


def test_noktalari_ayikla_bos_listede_bos_doner():
    assert noktalari_ayikla(yanit([]), "price") == []


def test_noktalari_ayikla_eksik_alanda_hata_verir():
    ham = yanit([{"date": "2026-08-01T00:00:00+03:00"}])
    with pytest.raises(KeyError):
        noktalari_ayikla(ham, "price")


def test_noktalari_ayikla_uretim_alaninda_total_okur():
    # Gerçek üretim gövdesi: date + hour + total + kaynak bazlı alanlar
    ham = yanit([
        {"date": "2026-08-01T00:00:00+03:00", "hour": "00:00",
         "total": 45231.61, "naturalGas": 2575.4, "dammedHydro": 12419.11,
         "wind": 10148.79},
    ])
    assert noktalari_ayikla(ham, "total") == [("2026-08-01", 45231.61)]


class SahteYanit:
    def __init__(self, status_code, govde=None, metin=""):
        self.status_code = status_code
        self._govde = govde or {}
        self.text = metin

    def json(self):
        return self._govde


class SahteOturum:
    def __init__(self, yanit):
        self._yanit = yanit
        self.cagrilan_url = None
        self.gonderilen_govde = None
        self.gonderilen_basliklar = None

    def post(self, url, headers=None, data=None, json=None, timeout=None):
        self.cagrilan_url = url
        self.gonderilen_basliklar = headers
        self.gonderilen_govde = json if json is not None else data
        return self._yanit


# --- tgt_al ---


def test_tgt_al_basarili_ticketi_doner():
    oturum = SahteOturum(SahteYanit(200, metin="TGT-123-abc-cas"))
    assert tgt_al("kullanici", "parola", session=oturum) == "TGT-123-abc-cas"


def test_tgt_al_kullanici_ve_parolayi_form_ile_gonderir():
    oturum = SahteOturum(SahteYanit(200, metin="TGT-xyz"))
    tgt_al("kullanici@example.com", "gizli-parola", session=oturum)
    assert oturum.gonderilen_govde == {
        "username": "kullanici@example.com",
        "password": "gizli-parola",
    }


def test_tgt_al_http_hatasinda_yukselir():
    oturum = SahteOturum(SahteYanit(401, metin="Unauthorized"))
    with pytest.raises(RuntimeError, match="401"):
        tgt_al("kullanici", "parola", session=oturum)


def test_tgt_al_beklenmeyen_govdede_yukselir():
    oturum = SahteOturum(SahteYanit(200, metin="<html>hata</html>"))
    with pytest.raises(RuntimeError, match="TGT"):
        tgt_al("kullanici", "parola", session=oturum)


# --- seri_cek ---


def _epias_seri(**kwargs):
    varsayilan = dict(
        id="elektrik/ptf",
        epias_ucu="ptf",
        epias_alani="price",
        monthly_agg="mean",
        start_date=None,
        olcek=1.0,
    )
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


def test_seri_cek_http_hatasinda_yukselir():
    oturum = SahteOturum(SahteYanit(500))
    with pytest.raises(RuntimeError, match="500"):
        seri_cek(_epias_seri(), "TGT-abc", session=oturum)


def test_seri_cek_bos_seride_yukselir():
    oturum = SahteOturum(SahteYanit(200, yanit([])))
    with pytest.raises(RuntimeError, match="boş seri"):
        seri_cek(_epias_seri(), "TGT-abc", session=oturum)


def test_seri_cek_tgt_basligini_gonderir():
    oturum = SahteOturum(SahteYanit(200, yanit([
        {"date": "2026-08-01T00:00:00+03:00", "price": 2500.0},
    ])))
    seri_cek(_epias_seri(), "TGT-abc", session=oturum)
    assert oturum.gonderilen_basliklar["TGT"] == "TGT-abc"


def test_seri_cek_mean_serisi_gunluk_ortalama_alir():
    # PTF gibi monthly_agg="mean" seriler: aynı günün saatlik değerleri
    # ORTALAMASI alınmalı, toplamı değil.
    oturum = SahteOturum(SahteYanit(200, yanit([
        {"date": "2026-08-01T00:00:00+03:00", "price": 100.0},
        {"date": "2026-08-01T01:00:00+03:00", "price": 300.0},
    ])))
    df = seri_cek(_epias_seri(monthly_agg="mean"), "TGT-abc", session=oturum)
    assert list(df.columns) == ["date", "value"]
    assert len(df) == 1
    assert df.iloc[0]["value"] == pytest.approx(200.0)


def test_seri_cek_sum_serisi_gunluk_toplam_alir():
    # Üretim gibi monthly_agg="sum" seriler: saatlik MWh'lerin günlük
    # TOPLAMI alınmalı — ortalaması alınırsa değer 1/24'üne düşer.
    oturum = SahteOturum(SahteYanit(200, yanit([
        {"date": "2026-08-01T00:00:00+03:00", "total": 45000.0},
        {"date": "2026-08-01T01:00:00+03:00", "total": 46000.0},
    ])))
    seri = _epias_seri(id="elektrik/uretim", epias_ucu="uretim",
                        epias_alani="total", monthly_agg="sum")
    df = seri_cek(seri, "TGT-abc", session=oturum)
    assert df.iloc[0]["value"] == pytest.approx(91000.0)


def test_seri_cek_olceklendirmeyi_indirgemeden_sonra_uygular():
    # Üretim MWh döner, GWh olarak gösterilecek: olcek=0.001.
    # Ölçekleme günlük TOPLAMDAN sonra uygulanmalı (91000 * 0.001 = 91.0),
    # tek tek saatlik değerlere değil.
    oturum = SahteOturum(SahteYanit(200, yanit([
        {"date": "2026-08-01T00:00:00+03:00", "total": 45000.0},
        {"date": "2026-08-01T01:00:00+03:00", "total": 46000.0},
    ])))
    seri = _epias_seri(id="elektrik/uretim", epias_ucu="uretim",
                        epias_alani="total", monthly_agg="sum", olcek=0.001)
    df = seri_cek(seri, "TGT-abc", session=oturum)
    assert df.iloc[0]["value"] == pytest.approx(91.0)


def test_seri_cek_ptf_ucunu_dogru_yola_ister():
    oturum = SahteOturum(SahteYanit(200, yanit([
        {"date": "2026-08-01T00:00:00+03:00", "price": 2500.0},
    ])))
    seri_cek(_epias_seri(), "TGT-abc", session=oturum)
    assert oturum.cagrilan_url.endswith(
        "/electricity-service/v1/markets/dam/data/mcp"
    )


def test_seri_cek_uretim_ucunu_dogru_yola_ister():
    oturum = SahteOturum(SahteYanit(200, yanit([
        {"date": "2026-08-01T00:00:00+03:00", "total": 45000.0},
    ])))
    seri = _epias_seri(id="elektrik/uretim", epias_ucu="uretim",
                        epias_alani="total")
    seri_cek(seri, "TGT-abc", session=oturum)
    assert oturum.cagrilan_url.endswith(
        "/electricity-service/v1/generation/data/realtime-generation"
    )


def test_seri_cek_baslangic_gunu_start_date_varsa_ondan_alinir():
    oturum = SahteOturum(SahteYanit(200, yanit([
        {"date": "2026-08-01T00:00:00+03:00", "price": 2500.0},
    ])))
    seri = _epias_seri(start_date="2020-01-01")
    seri_cek(seri, "TGT-abc", session=oturum, bugun=date(2026, 8, 27))
    assert oturum.gonderilen_govde["startDate"] == "2020-01-01T00:00:00+03:00"
    assert oturum.gonderilen_govde["endDate"] == "2026-08-27T00:00:00+03:00"
