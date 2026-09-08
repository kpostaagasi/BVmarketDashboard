"""BDDK Aylık Bülten (Gelişmiş Gösterim) istemcisi testleri.

Yanıtlar jqGrid biçiminde inline üretilir; gerçek uç iki farklı şekil
döndürüyor (kar/zarar: TP+YP+Toplam, rasyo: tek değer sütunu) ve testler
ikisini de kapsar.
"""

from datetime import date
from types import SimpleNamespace

import pytest

from ingest.bddk import (
    VARSAYILAN_TARAF,
    deger_sutunu,
    geriye_aylar,
    kumulatifi_ayliga_cevir,
    noktalari_ayikla,
    seri_cek,
)


def kar_zarar_yaniti(noktalar):
    """noktalar: [(yıl, ay, tp, yp, toplam)]"""
    return {
        "success": True,
        "Json": {
            "colNames": ["Banka", "Yıl", "Ay", "TP", "YP", "Toplam", "Sira"],
            "data": {"rows": [
                {"cell": ["Sektör", y, a, tp, yp, top, i + 1]}
                for i, (y, a, tp, yp, top) in enumerate(noktalar)
            ]},
        },
    }


def rasyo_yaniti(noktalar):
    """noktalar: [(yıl, ay, rasyo)]"""
    return {
        "success": True,
        "Json": {
            "colNames": ["Banka", "Yıl", "Ay", "Rasyo", "Sira"],
            "data": {"rows": [
                {"cell": ["Sektör", y, a, v, i + 1]}
                for i, (y, a, v) in enumerate(noktalar)
            ]},
        },
    }


def bddk_seri(**kwargs):
    varsayilan = dict(
        id="bankacilik/net-donem-kari",
        kaynak_tipi="bddk",
        bddk_kalem="194,148",
        bddk_taraf=None,
        bddk_kumulatif=None,
        start_date=None,
    )
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


class SahteYanit:
    def __init__(self, govde, status_code=200):
        self._govde = govde
        self.status_code = status_code
        self.content = b"-----BEGIN CERTIFICATE-----\nsahte\n-----END CERTIFICATE-----\n"

    def json(self):
        return self._govde


class SahteOturum:
    """POST'lara sırayla yanıt verir; GET'ler sertifika indirmesidir."""

    def __init__(self, yanitlar):
        self.yanitlar = list(yanitlar)
        self.gonderilenler = []

    def get(self, url, timeout=None):
        return SahteYanit({})

    def post(self, url, data=None, headers=None, timeout=None, verify=None):
        self.gonderilenler.append(data)
        return self.yanitlar.pop(0)


@pytest.fixture(autouse=True)
def _ca_paketini_atla(monkeypatch, tmp_path):
    """Gerçek GlobalSign indirmesi testte koşmasın."""
    paket = tmp_path / "ca.pem"
    paket.write_text("sahte", encoding="utf-8")
    monkeypatch.setattr("ingest.bddk._ca_paketi", lambda session=None: str(paket))


# --- Sütun çözümleme ---


def test_deger_sutunu_toplami_secer():
    """Kar/zarar kaleminde TP/YP değil Toplam istenir."""
    assert deger_sutunu(["Banka", "Yıl", "Ay", "TP", "YP", "Toplam", "Sira"]) == 5


def test_deger_sutunu_rasyoda_tek_sutunu_bulur():
    assert deger_sutunu(["Banka", "Yıl", "Ay", "Rasyo", "Sira"]) == 3


def test_deger_sutunu_belirsizse_hata():
    """Toplam yoksa ve birden çok değer sütunu varsa sessizce seçim yapılmaz."""
    with pytest.raises(RuntimeError, match="belirsiz"):
        deger_sutunu(["Banka", "Yıl", "Ay", "TP", "YP", "Sira"])


# --- Nokta çıkarma ---


def test_noktalari_ayikla_ay_tarihine_cevirir():
    noktalar = noktalari_ayikla(kar_zarar_yaniti([(2026, 7, 10.0, 2.0, 12.0)]))
    assert noktalar == {"2026-07-01": 12.0}


def test_noktalari_ayikla_rasyo_seklini_de_okur():
    assert noktalari_ayikla(rasyo_yaniti([(2026, 7, 2.86)])) == {"2026-07-01": 2.86}


def test_noktalari_ayikla_basarisiz_yanitta_hata():
    yanit = {"success": False, "error": "2026 yılının en son 7 ayına ait veri..."}
    with pytest.raises(RuntimeError, match="başarısız"):
        noktalari_ayikla(yanit)


def test_noktalari_ayikla_bos_seride_hata():
    with pytest.raises(RuntimeError, match="hiç nokta"):
        noktalari_ayikla(kar_zarar_yaniti([]))


# --- Kümülatif → aylık ---


def test_kumulatifi_ayliga_cevir_yil_icinde_fark_alir():
    """Gerçek ölçüm: 2026-01=201.706 … 2026-07=1.471.532 (kümülatif)."""
    kumulatif = {
        "2026-01-01": 201706.0,
        "2026-02-01": 390766.0,
        "2026-03-01": 618342.0,
    }
    assert kumulatifi_ayliga_cevir(kumulatif) == {
        "2026-01-01": 201706.0,
        "2026-02-01": 189060.0,
        "2026-03-01": 227576.0,
    }


def test_kumulatifi_ayliga_cevir_yil_baslarinda_sifirlanir():
    """Ocak kümülatifin kendisidir; aralık→ocak farkı ALINMAZ."""
    aylik = kumulatifi_ayliga_cevir({
        "2025-12-01": 1725136.0,
        "2026-01-01": 201706.0,
    })
    assert aylik["2026-01-01"] == 201706.0


def test_kumulatifi_ayliga_cevir_eksik_ayi_atlar():
    """Yayın atlanmışsa iki ayı tek aya yığmak yerine o ay düşer."""
    aylik = kumulatifi_ayliga_cevir({
        "2026-01-01": 100.0,
        "2026-03-01": 300.0,  # Şubat yok
        "2026-04-01": 380.0,
    })
    assert "2026-03-01" not in aylik
    assert aylik == {"2026-01-01": 100.0, "2026-04-01": 80.0}


# --- Bitiş dönemi geri yürümesi ---


def test_geriye_aylar_yil_sinirini_gecer():
    assert geriye_aylar(date(2026, 2, 15), adet=4) == [
        (2026, 2), (2026, 1), (2025, 12), (2025, 11),
    ]


def test_seri_cek_yayimlanmamis_ayi_geriye_dogru_dener():
    """Uç, veri olmayan bitiş ayında HTTP 200 + success:false döndürüyor."""
    oturum = SahteOturum([
        SahteYanit({"success": False, "error": "en son 7 ayına ait veri"}),
        SahteYanit({"success": False, "error": "en son 7 ayına ait veri"}),
        SahteYanit(rasyo_yaniti([(2026, 7, 2.86)])),
    ])
    df = seri_cek(bddk_seri(bddk_kalem="544"), session=oturum, bugun=date(2026, 9, 8))
    assert len(oturum.gonderilenler) == 3
    assert [g["bitisAy"] for g in oturum.gonderilenler] == [9, 8, 7]
    assert df["value"].iloc[0] == pytest.approx(2.86)


def test_seri_cek_bulunan_bitis_donemini_onbellekte_paylasir():
    """İlk seri dönemi bulur; kalan seriler tek istekte çeker."""
    oturum = SahteOturum([
        SahteYanit({"success": False, "error": "yok"}),
        SahteYanit(rasyo_yaniti([(2026, 7, 2.86)])),
        SahteYanit(rasyo_yaniti([(2026, 7, 76.2)])),
    ])
    onbellek: dict = {}
    seri_cek(bddk_seri(bddk_kalem="544"), onbellek=onbellek, session=oturum,
             bugun=date(2026, 8, 20))
    seri_cek(bddk_seri(id="bankacilik/karsilik-orani", bddk_kalem="545"),
             onbellek=onbellek, session=oturum, bugun=date(2026, 8, 20))
    assert onbellek["bitis"] == (2026, 7)
    assert len(oturum.gonderilenler) == 3  # 2 deneme + 1 doğrudan


def test_seri_cek_hicbir_ayda_veri_yoksa_hata():
    oturum = SahteOturum([SahteYanit({"success": False, "error": "yok"})] * 14)
    with pytest.raises(RuntimeError, match="hiçbiri için veri döndürmedi"):
        seri_cek(bddk_seri(bddk_kalem="544"), session=oturum, bugun=date(2026, 9, 8))


def test_seri_cek_http_hatasi_yukselir():
    oturum = SahteOturum([SahteYanit({}, status_code=503)])
    with pytest.raises(RuntimeError, match="HTTP 503"):
        seri_cek(bddk_seri(), session=oturum, bugun=date(2026, 9, 8))


# --- İstek gövdesi ve kümülatif bayrağı ---


def test_seri_cek_varsayilan_taraf_sektor():
    oturum = SahteOturum([SahteYanit(rasyo_yaniti([(2026, 7, 1.0)]))])
    seri_cek(bddk_seri(bddk_kalem="544"), session=oturum, bugun=date(2026, 7, 20))
    gonderilen = oturum.gonderilenler[0]
    assert gonderilen["taraf"] == VARSAYILAN_TARAF
    assert gonderilen["kalemSutun"] == "544"
    assert gonderilen["baslangicYil"] == 2019 and gonderilen["periyot"] == 1


def test_seri_cek_kumulatif_bayragi_farki_uygular():
    veri = kar_zarar_yaniti([
        (2026, 1, 0, 0, 100.0), (2026, 2, 0, 0, 250.0),
    ])
    oturum = SahteOturum([SahteYanit(veri)])
    df = seri_cek(bddk_seri(bddk_kumulatif=True), session=oturum,
                  bugun=date(2026, 2, 20))
    assert list(df["value"]) == [100.0, 150.0]


def test_seri_cek_kumulatif_bayragi_yoksa_deger_bozulmaz():
    """Stok ve rasyo kalemleri kümülatif değildir; fark alınmamalı."""
    veri = kar_zarar_yaniti([
        (2026, 1, 0, 0, 100.0), (2026, 2, 0, 0, 250.0),
    ])
    oturum = SahteOturum([SahteYanit(veri)])
    df = seri_cek(bddk_seri(), session=oturum, bugun=date(2026, 2, 20))
    assert list(df["value"]) == [100.0, 250.0]
