from datetime import date

import pytest

from ingest.evds import (
    alan_adi,
    deger_parse,
    istek_govdesi,
    noktalari_ayikla,
    tarih_formatla,
    tarih_parse,
)


def test_alan_adi_noktalari_alt_cizgiye_cevirir():
    assert alan_adi("TP.TUKFIY2025.GENEL") == "TP_TUKFIY2025_GENEL"


def test_aylik_tarih_ayin_ilk_gunune_cevrilir():
    # EVDS aylık serilerde dokümantasyona aykırı olarak "YYYY-MM" döndürüyor
    assert tarih_parse("2026-07") == "2026-07-01"


def test_gunluk_tarih_gun_ay_yil_sirasindan_isoya_cevrilir():
    assert tarih_parse("05-08-2026") == "2026-08-05"


def test_taninmayan_tarih_none_dondurur():
    assert tarih_parse("2026/08/05") is None
    assert tarih_parse("") is None


def test_deger_binlik_ayraci_temizlenir():
    # groupSeperator:true yüzünden değerler "139,411.00000" gibi geliyor
    assert deger_parse("139,411.00000") == pytest.approx(139411.0)


def test_deger_bos_ve_gecersizler_none():
    assert deger_parse(None) is None
    assert deger_parse("") is None
    assert deger_parse("   ") is None
    assert deger_parse("yok") is None


def test_tarih_formatla_evds_bicimini_verir():
    assert tarih_formatla(date(2026, 8, 5)) == "05-08-2026"


def test_istek_govdesi_seri_kodunu_tire_ile_gonderir():
    govde = istek_govdesi("TP.APIFON4", "1", "01-01-2011", "27-08-2026")
    assert govde["series"] == "-TP.APIFON4"
    assert govde["frequency"] == "1"
    assert govde["startDate"] == "01-01-2011"
    assert govde["endDate"] == "27-08-2026"
    assert govde["decimalSeperator"] == "."
    assert govde["groupSeperator"] is True


def test_noktalari_ayikla_siralar_ve_gecersizleri_atar():
    yanit = {
        "items": [
            {"Tarih": "2026-03", "TP_TUKFIY2025_GENEL": "102,50000"},
            {"Tarih": "2026-01", "TP_TUKFIY2025_GENEL": "100.00000"},
            {"Tarih": "2026-02", "TP_TUKFIY2025_GENEL": None},
            {"Tarih": "bozuk", "TP_TUKFIY2025_GENEL": "999"},
        ]
    }
    assert noktalari_ayikla(yanit, "TP.TUKFIY2025.GENEL") == [
        ("2026-01-01", 100.0),
        ("2026-03-01", 102.5),
    ]


def test_noktalari_ayikla_bos_yanitta_bos_liste():
    assert noktalari_ayikla({}, "TP.APIFON4") == []
