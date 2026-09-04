from datetime import date

import pytest

from ingest.osd import (
    ay_toplamlari,
    bulten_baglantilari,
    cekilecek_bultenler,
    dogrula,
    firma_adini_normalize,
    firma_aylik_noktalari,
    sayi_parse,
)

# --- İndeks kazıma ---

INDEKS_HTML = """
<a href="/saved-files\\PDF\\2023\\01\\16\\Otomotiv_Sanayii_Uretim_Bulteni_2022.12.pdf">2022</a>
<a href="/saved-files\\PDF\\2024\\01\\14\\Otomotiv_Sanayii_Uretim_Bulteni-2023.12.pdf">2023</a>
<a href="/saved-files\\PDF\\2026\\08\\17\\Otomotiv_Sanayii_Uretim_Bulteni-2026.07.pdf">2026</a>
<a href="/saved-files\\PDF\\2010\\01\\01\\Üretim Bülteni _2009.pdf">2009</a>
"""


def test_bulten_baglantilari_tire_ve_alt_cizgiyi_kabul_eder():
    """2022 alt çizgi, 2023+ tire kullanıyor — ikisi de bulunmalı."""
    b = bulten_baglantilari(INDEKS_HTML)
    assert set(b) == {"2022.12", "2023.12", "2026.07"}


def test_bulten_baglantilari_ters_boluyu_duzeltir():
    b = bulten_baglantilari(INDEKS_HTML)
    assert b["2026.07"] == (
        "https://www.osd.org.tr/saved-files/PDF/2026/08/17/"
        "Otomotiv_Sanayii_Uretim_Bulteni-2026.07.pdf"
    )


def test_bulten_baglantilari_eski_bicimi_yok_sayar():
    """`Üretim Bülteni _2009.pdf` farklı format; kapsam dışı."""
    assert "2009" not in bulten_baglantilari(INDEKS_HTML)


def test_bulten_baglantilari_hicbiri_yoksa_yukselir():
    """Site yapısı değişirse sessizce boş dönmemeli."""
    with pytest.raises(RuntimeError, match="bülten bağlantısı"):
        bulten_baglantilari("<html><body>hiçbir şey</body></html>")


# --- Bülten seçimi ---

BAGLANTILAR = {
    "2022.12": "u1", "2023.12": "u2", "2024.12": "u3",
    "2025.12": "u4", "2026.07": "u5",
}


def test_cekilecek_bultenler_aralik_ve_guncel_secer():
    secilen = cekilecek_bultenler(BAGLANTILAR, date(2026, 9, 4))
    assert secilen == ["2022.12", "2023.12", "2024.12", "2025.12", "2026.07"]


def test_cekilecek_bultenler_gecmis_yil_siniri_uygular():
    """VARSAYILAN_GECMIS_YIL=5 ise 2021 ve öncesi alınmaz."""
    genis = dict(BAGLANTILAR, **{"2019.12": "u0", "2020.12": "u0b"})
    secilen = cekilecek_bultenler(genis, date(2026, 9, 4))
    assert "2019.12" not in secilen and "2020.12" not in secilen


def test_cekilecek_bultenler_ocakta_tekrar_secmez():
    """Ocak'ta güncel bülten önceki yılın Aralık'ıdır; iki kez seçilmemeli."""
    ocak = {"2024.12": "u3", "2025.12": "u4"}
    secilen = cekilecek_bultenler(ocak, date(2026, 1, 10))
    assert secilen == sorted(set(secilen))
    assert len(secilen) == len(set(secilen))


# --- Ad ve sayı ayrıştırma ---

def test_firma_adini_normalize_null_bayti_temizler():
    """Eski PDF'lerde font kodlaması Türkçe karakterlerde \\x00 sızdırıyor."""
    assert firma_adini_normalize("T\x00pler") == "Tpler"


def test_firma_adini_normalize_satir_sonu_ve_bosluk_temizler():
    assert firma_adini_normalize("  FORD\nOTOSAN  ") == "FORD OTOSAN"


def test_sayi_parse_turkce_binlik_ayraci():
    assert sayi_parse("36.548") == 36548.0


def test_sayi_parse_bos_ve_tire_none_doner():
    assert sayi_parse("-") is None
    assert sayi_parse("") is None
    assert sayi_parse(None) is None


# --- Nokta çıkarma ---

def _tablo(*satirlar):
    """s6 biçimi: 14 sütun (tip/firma + 12 ay + toplam)."""
    basliklar = ["Tipler\nTypes"] + [f"AY{i}" for i in range(1, 13)] + ["TOPLAM"]
    return [basliklar, *satirlar]


def _firma_satiri(ad, *aylar):
    hucreler = list(aylar) + ["-"] * (12 - len(aylar))
    return [ad, *hucreler, "-"]


def test_firma_aylik_noktalari_firma_satirlarini_okur():
    tablo = _tablo(
        _firma_satiri("FORD OTOSAN", "100", "200"),
        ["Pay / Share %", *["1"] * 13],
        _firma_satiri("TOFAŞ", "10", "20"),
        ["Pay / Share %", *["1"] * 13],
        ["OTOMOBİL Toplam / Pass.Car Total", *["110"] * 13],
        ["Toplam Pay / Total Share", *["100"] * 13],
    )
    noktalar = firma_aylik_noktalari([tablo], 2026)
    assert ("FORD OTOSAN", "2026-01-01", 100.0) in noktalar
    assert ("FORD OTOSAN", "2026-02-01", 200.0) in noktalar
    assert ("TOFAŞ", "2026-02-01", 20.0) in noktalar


def test_firma_aylik_noktalari_alt_toplam_satirlarini_atlar():
    tablo = _tablo(
        _firma_satiri("FORD OTOSAN", "100"),
        ["Pay / Share %", *["1"] * 13],
        ["OTOMOBİL Toplam / Pass.Car Total", *["100"] * 13],
        ["Toplam Pay / Total Share", *["100"] * 13],
        ["", *[""] * 13],
    )
    adlar = {n[0] for n in firma_aylik_noktalari([tablo], 2026)}
    assert adlar == {"FORD OTOSAN"}


def test_firma_aylik_noktalari_ayni_firmayi_bolumler_arasi_toplar():
    """Bir firma birden çok araç tipi bölümünde görünür; toplanmalı."""
    t1 = _tablo(_firma_satiri("FORD OTOSAN", "100"))
    t2 = _tablo(_firma_satiri("FORD OTOSAN", "50"))
    noktalar = firma_aylik_noktalari([t1, t2], 2026)
    assert noktalar == [("FORD OTOSAN", "2026-01-01", 150.0)]


def test_firma_aylik_noktalari_bos_ayi_atlar():
    tablo = _tablo(_firma_satiri("KARSAN", "-", "5"))
    noktalar = firma_aylik_noktalari([tablo], 2026)
    assert noktalar == [("KARSAN", "2026-02-01", 5.0)]


# --- Öz-doğrulama ---

def _s2_tablosu(*satirlar):
    basliklar = ["FİRMALAR"] + [f"S{i}" for i in range(1, 17)] + ["TOPLAM Total", "%"]
    return [basliklar, *satirlar]


def _s2_satiri(ad, toplam):
    return [ad, *["-"] * 16, toplam, "-"]


def test_ay_toplamlari_toplam_sutununu_okur():
    tablo = _s2_tablosu(
        _s2_satiri("FORD OTOSAN", "36.548"),
        _s2_satiri("TOPLAM / TOTAL", "105.725"),
    )
    assert ay_toplamlari(tablo) == {"FORD OTOSAN": 36548.0}


def test_dogrula_tutan_toplamda_sessiz():
    noktalar = [("FORD OTOSAN", "2026-07-01", 36548.0)]
    dogrula(noktalar, {"FORD OTOSAN": 36548.0}, "2026-07-01")


def test_dogrula_tutmayan_toplamda_yukselir():
    """Şablon değişirse sessizce eksik veri üretmek yerine kırılmalı."""
    noktalar = [("FORD OTOSAN", "2026-07-01", 30000.0)]
    with pytest.raises(RuntimeError, match="FORD OTOSAN"):
        dogrula(noktalar, {"FORD OTOSAN": 36548.0}, "2026-07-01")


def test_dogrula_eksik_firmada_yukselir():
    with pytest.raises(RuntimeError, match="TOFAŞ"):
        dogrula([], {"TOFAŞ": 100.0}, "2026-07-01")
