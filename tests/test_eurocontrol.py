"""EUROCONTROL Daily Traffic Variation istemcisi testleri.

Yanıtlar Google Charts DataTable biçiminde inline üretilir: ilk iki eleman
sütun adları ve tipleridir, veri üçüncüden başlar.
"""

import json
from datetime import date
from types import SimpleNamespace

import pytest

from ingest.eurocontrol import (
    DOSYALAR,
    dosya_url,
    noktalari_ayikla,
    referans_sutunu,
    sayi_parse,
    seri_cek,
)

BASLIKLAR = [
    "Entity", "Week", "Day", "Flights 2019 (Reference)", "Flights",
    "% vs 2019 (Daily)", "Flights (7-day moving average)",
    "% vs 2019 (7-day Moving Average)", "Day 2019", "Day Previous Year",
    "Flights 2025 (Reference)", "% vs 2025 (Daily)",
    "% vs 2025 (7-day Moving Average)",
]
TIPLER = ["string", "number", "date"] + ["number"] * 10


def satir(varlik, gun, ucus, onceki_gun=None, onceki=None, ucus2019=" 2000"):
    return [
        varlik, " 1", gun, ucus2019, ucus, " 0.1", "2.8e+03", " 0.28",
        "2019-01-03", onceki_gun, onceki, " 0.05", " 0.06",
    ]


def govde(satirlar):
    return [BASLIKLAR, TIPLER, *satirlar]


class SahteYanit:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


class SahteOturum:
    def __init__(self, dosyaya_gore):
        self.dosyaya_gore = dosyaya_gore
        self.istekler = []

    def get(self, url, timeout=None):
        self.istekler.append(url)
        for ad, yanit in self.dosyaya_gore.items():
            if url.endswith(ad):
                return yanit
        return SahteYanit("<html>404</html>", 404)


def ec_seri(**kwargs):
    varsayilan = dict(
        id="havacilik/thy",
        kaynak_tipi="eurocontrol",
        ec_kaynak="havayolu",
        ec_varlik="Turkish Airlines Group",
        start_date=None,
    )
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


# --- URL ve sayı ayrıştırma ---


def test_dosya_url_kaynaga_gore_secer():
    assert dosya_url("ulke").endswith("/tfc_ct_data.json")
    assert dosya_url("havayolu").endswith("/tfc_ao_data.json")
    assert dosya_url("havalimani").endswith("/tfc_apt_100_data.json")


def test_dosyalar_uc_kaynagi_kapsar():
    assert set(DOSYALAR) == {"ulke", "havayolu", "havalimani"}


def test_sayi_parse_bastaki_bosluklu_dizeyi_okur():
    """Kaynak sayıları `" 2441"` biçiminde dize olarak veriyor."""
    assert sayi_parse(" 2441") == 2441.0
    assert sayi_parse("2.8e+03") == 2800.0


def test_sayi_parse_bos_ve_gecersizde_none():
    assert sayi_parse(None) is None
    assert sayi_parse("  ") is None
    assert sayi_parse("-") is None
    assert sayi_parse("yok") is None


# --- Referans sütunu ---


def test_referans_sutunu_onceki_yili_secer():
    assert referans_sutunu(BASLIKLAR, date(2026, 5, 1)) == "Flights 2025 (Reference)"


def test_referans_sutunu_2019u_secmez():
    """2019 ile cari yıl arasında beş yıllık boşluk var; bilinçle atlanır."""
    assert referans_sutunu(BASLIKLAR, date(2021, 5, 1)) is None


# --- Nokta çıkarma ---


def test_noktalari_ayikla_cari_ve_onceki_yili_birlestirir():
    veri = govde([
        satir("Turkish Airlines Group", "2026-01-01", " 1500", "2025-01-02", " 1395"),
        satir("Turkish Airlines Group", "2026-01-02", " 1600", "2025-01-03", " 1425"),
    ])
    noktalar = noktalari_ayikla(veri, "Turkish Airlines Group", date(2026, 9, 8))
    assert noktalar == {
        "2025-01-02": 1395.0, "2025-01-03": 1425.0,
        "2026-01-01": 1500.0, "2026-01-02": 1600.0,
    }


def test_noktalari_ayikla_diger_varliklari_disliyor():
    veri = govde([
        satir("Pegasus", "2026-01-01", " 400"),
        satir("Turkish Airlines Group", "2026-01-01", " 1500"),
    ])
    assert noktalari_ayikla(veri, "Pegasus", date(2026, 9, 8)) == {"2026-01-01": 400.0}


def test_noktalari_ayikla_cari_yil_degeri_referansi_ezmez_ama_kazanir():
    """Aynı gün iki kaynaktan gelirse taze (cari yıl) değer kalır."""
    veri = govde([
        satir("X", "2025-06-01", " 999"),
        satir("X", "2026-06-01", " 1200", "2025-06-01", " 111"),
    ])
    noktalar = noktalari_ayikla(veri, "X", date(2026, 9, 8))
    assert noktalar["2025-06-01"] == 999.0


def test_noktalari_ayikla_varlik_yoksa_hata():
    """Kaynak adlandırmayı değiştirirse boş seri yazılmaz."""
    veri = govde([satir("Pegasus", "2026-01-01", " 400")])
    with pytest.raises(RuntimeError, match="varlık bulunamadı"):
        noktalari_ayikla(veri, "Turkish Airlines Group", date(2026, 9, 8))


def test_noktalari_ayikla_sutun_eksikse_hata():
    bozuk = [["Entity", "Week", "Day"], ["string", "number", "date"],
             ["X", " 1", "2026-01-01"]]
    with pytest.raises(RuntimeError, match="Flights"):
        noktalari_ayikla(bozuk, "X", date(2026, 9, 8))


def test_noktalari_ayikla_bos_dosyada_hata():
    with pytest.raises(RuntimeError, match="beklenen biçimde"):
        noktalari_ayikla([BASLIKLAR], "X", date(2026, 9, 8))


def test_noktalari_ayikla_bos_ucus_degerini_atlar():
    """Yayınlanmamış gün boş gelebilir; sıfır yazmak yanlış olurdu."""
    veri = govde([
        satir("X", "2026-01-01", " 1500"),
        satir("X", "2026-01-02", None),
    ])
    noktalar = noktalari_ayikla(veri, "X", date(2026, 9, 8))
    assert "2026-01-02" not in noktalar


# --- seri_cek ---


def test_seri_cek_siralanmis_df_dondurur():
    oturum = SahteOturum({"tfc_ao_data.json": SahteYanit(json.dumps(govde([
        satir("Turkish Airlines Group", "2026-01-02", " 1600", "2025-01-03", " 1425"),
        satir("Turkish Airlines Group", "2026-01-01", " 1500", "2025-01-02", " 1395"),
    ])))})
    df = seri_cek(ec_seri(), session=oturum, bugun=date(2026, 9, 8))
    assert list(df.columns) == ["date", "value"]
    assert list(df["date"]) == [
        "2025-01-02", "2025-01-03", "2026-01-01", "2026-01-02",
    ]


def test_seri_cek_dosyayi_onbellekten_paylasir():
    """Yedi seri üç dosyayı okuyor; dosyalar 2–5 MB, tekrar indirilmemeli."""
    oturum = SahteOturum({"tfc_ao_data.json": SahteYanit(json.dumps(govde([
        satir("Turkish Airlines Group", "2026-01-01", " 1500"),
        satir("Pegasus", "2026-01-01", " 400"),
    ])))})
    onbellek: dict = {}
    seri_cek(ec_seri(), onbellek=onbellek, session=oturum, bugun=date(2026, 9, 8))
    seri_cek(ec_seri(id="havacilik/pegasus", ec_varlik="Pegasus"),
             onbellek=onbellek, session=oturum, bugun=date(2026, 9, 8))
    assert len(oturum.istekler) == 1


def test_seri_cek_http_hatasi_yukselir():
    oturum = SahteOturum({})
    with pytest.raises(RuntimeError, match="HTTP 404"):
        seri_cek(ec_seri(), session=oturum, bugun=date(2026, 9, 8))


def test_seri_cek_start_date_oncesini_kirpar():
    oturum = SahteOturum({"tfc_ao_data.json": SahteYanit(json.dumps(govde([
        satir("Turkish Airlines Group", "2026-01-01", " 1500", "2025-01-02", " 1395"),
    ])))})
    df = seri_cek(ec_seri(start_date="2026-01-01"), session=oturum,
                  bugun=date(2026, 9, 8))
    assert list(df["date"]) == ["2026-01-01"]
