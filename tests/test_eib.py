"""EİB (Ege İhracatçı Birlikleri) ESÜHMİB aylık ihracat istatistiği istemcisi
testleri."""

from datetime import date
from io import BytesIO
from types import SimpleNamespace

import openpyxl
import pytest

from ingest.eib import (
    _dogrula,
    ay_baglantilarini_cikar,
    hedef_ay_linki,
    seri_cek,
    yil_verisini_cikar,
    yillara_ayir,
)


def eib_seri(**kwargs):
    varsayilan = dict(
        id="su-urunleri/toplam-ihracat", eib_kalem="SU ÜRÜNLERİ", eib_olcut="fobusd",
        start_date=None,
    )
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


# --- yillara_ayir / ay_baglantilarini_cikar: HTML ayrıştırma ---


def test_yillara_ayir_h3_basliklariyla_boler():
    icerik = "<p>giriş</p><h3>2026</h3><p>2026 içerik</p><h3>2025</h3><p>2025 içerik</p>"
    sonuc = yillara_ayir(icerik)
    assert sonuc == {"2026": "<p>2026 içerik</p>", "2025": "<p>2025 içerik</p>"}


def test_ay_baglantilarini_cikar_etiket_ve_url_esler():
    yil_html = (
        '<p><strong>Ağustos: </strong> '
        '<a href="https://eib.li/D339C" target="_blank">EİB Aylık</a>, '
        '<a href="https://eib.li/8BEC7" target="_blank">Türkiye Geneli Aylık</a></p>'
    )
    sonuc = ay_baglantilarini_cikar(yil_html)
    assert sonuc["AĞUSTOS"] == {
        "EİB Aylık": "https://eib.li/D339C",
        "Türkiye Geneli Aylık": "https://eib.li/8BEC7",
    }


def test_ay_baglantilarini_cikar_bozuk_urlu_duzeltir():
    """Kaynakta ölçülen gerçek anomalı: Şubat 2024 `http://https//eib.li/BE6FE`."""
    yil_html = (
        '<p><strong>Şubat: </strong> '
        '<a href="http://https//eib.li/BE6FE" target="_blank">EİB Aylık</a></p>'
    )
    sonuc = ay_baglantilarini_cikar(yil_html)
    assert sonuc["ŞUBAT"]["EİB Aylık"] == "https://eib.li/BE6FE"


def test_ay_baglantilarini_cikar_ay_olmayan_baslikligi_atlar():
    yil_html = '<p><strong>Genel Bilgi: </strong> <a href="https://eib.li/X">Bağlantı</a></p>'
    assert ay_baglantilarini_cikar(yil_html) == {}


# --- hedef_ay_linki: cari yıl en son ay, geçmiş yıl Aralık ---


def test_hedef_ay_linki_cari_yilda_en_son_ayi_secer():
    ay_linkleri = {
        "OCAK": {"EİB": "u1"},
        "ŞUBAT": {"EİB Aylık": "u2"},
        "AĞUSTOS": {"EİB Aylık": "u3"},
    }
    ay, url = hedef_ay_linki(2026, ay_linkleri, date(2026, 9, 18))
    assert (ay, url) == ("AĞUSTOS", "u3")


def test_hedef_ay_linki_gecmis_yilda_araligi_secer():
    ay_linkleri = {"OCAK": {"EİB Aylık": "u1"}, "ARALIK": {"EİB Aylık": "u12"}}
    ay, url = hedef_ay_linki(2025, ay_linkleri, date(2026, 9, 18))
    assert (ay, url) == ("ARALIK", "u12")


def test_hedef_ay_linki_ocakta_tek_eib_etiketini_kabul_eder():
    ay, url = hedef_ay_linki(2026, {"OCAK": {"EİB": "u1", "TÜRKİYE GENELİ": "u2"}}, date(2026, 1, 15))
    assert (ay, url) == ("OCAK", "u1")


def test_hedef_ay_linki_bos_yilda_none_doner():
    assert hedef_ay_linki(2026, {}, date(2026, 9, 18)) is None


def test_hedef_ay_linki_eib_aylik_yoksa_hata():
    with pytest.raises(RuntimeError, match="EİB Aylık"):
        hedef_ay_linki(2026, {"OCAK": {"TÜRKİYE GENELİ": "u2"}}, date(2026, 1, 15))


# --- yil_verisini_cikar: XLSX bütünlük testi ---


def _yillik_dosya_baytlari(satirlar, sayfa_adi="GTIP ULKE GB TARIH"):
    """`satirlar`: [(ay, ürün_grubu, alt_grup1, agirlik_kg, fobusd)] listesi
    ile gerçekçi ama minimal bir yıllık bülten üretir."""
    kitap = openpyxl.Workbook()
    sayfa = kitap.active
    sayfa.title = sayfa_adi
    sayfa.append(["Aylar", "ürün grubu", "alt grup 1 ", "alt grup 2", "GTIP", "GTIPAD", "ULKEAD", "AGIRLIK", "FOBUSD", "FOBEUR"])
    for ay, urun, alt1, agirlik, fob in satirlar:
        sayfa.append([ay, urun, alt1, "alt2", "000000", "ürün adı", "ÜLKE", agirlik, fob, fob * 0.9])
    arabellek = BytesIO()
    kitap.save(arabellek)
    return arabellek.getvalue()


_TEMEL_SATIRLAR = [
    ("OCAK", "SU ÜRÜNLERİ", "LEVREK", 1000.0, 5000.0),
    ("OCAK", "SU ÜRÜNLERİ", "ÇİPURA", 500.0, 2000.0),
    ("OCAK", "SU ÜRÜNLERİ", "DİĞER SU ÜRÜNLERİ", 100.0, 300.0),
    ("OCAK", "KANATLI", "KANATLI", 200.0, 900.0),
    ("OCAK", "YUMURTA", "YUMURTA", 50.0, 400.0),
]


def test_yil_verisini_cikar_su_urunleri_kalan_diger_urunlere_katlanir():
    """Levrek/Çipura dışındaki her şey (alt grubu ne olursa olsun) TOPLAM −
    2 adlandırılmış üründen hesaplanan DİĞER SU ÜRÜNLERİ'nde toplanır."""
    noktalar = yil_verisini_cikar(_yillik_dosya_baytlari(_TEMEL_SATIRLAR), 2025)
    assert noktalar[("LEVREK", "fobusd")]["2025-01-01"] == pytest.approx(5000.0)
    assert noktalar[("ÇİPURA", "fobusd")]["2025-01-01"] == pytest.approx(2000.0)
    assert noktalar[("DİĞER SU ÜRÜNLERİ", "fobusd")]["2025-01-01"] == pytest.approx(300.0)
    assert noktalar[("SU ÜRÜNLERİ", "fobusd")]["2025-01-01"] == pytest.approx(7300.0)


def test_yil_verisini_cikar_agirligi_kg_dan_tona_cevirir():
    noktalar = yil_verisini_cikar(_yillik_dosya_baytlari(_TEMEL_SATIRLAR), 2025)
    assert noktalar[("LEVREK", "agirlik")]["2025-01-01"] == pytest.approx(1.0)


def test_yil_verisini_cikar_hayvansal_toplami_gruplarin_toplamidir():
    noktalar = yil_verisini_cikar(_yillik_dosya_baytlari(_TEMEL_SATIRLAR), 2025)
    assert noktalar[("HAYVANSAL_TOPLAM", "fobusd")]["2025-01-01"] == pytest.approx(1300.0)


def test_yil_verisini_cikar_sayfa_adi_farkli_olsa_da_baslikla_bulunur():
    """Sayfa adı yıldan yıla değişiyor (2024: 'Sayfa1', 2026: 'GTIP ULKE GB
    TARIH') — başlık satırının ilk hücresi 'AYLAR' olan sayfa bulunmalı."""
    noktalar = yil_verisini_cikar(_yillik_dosya_baytlari(_TEMEL_SATIRLAR, sayfa_adi="Sayfa1"), 2025)
    assert noktalar[("SU ÜRÜNLERİ", "fobusd")]["2025-01-01"] == pytest.approx(7300.0)


def test_yil_verisini_cikar_su_urunleri_yoksa_hata():
    with pytest.raises(RuntimeError, match="SU ÜRÜNLERİ"):
        yil_verisini_cikar(_yillik_dosya_baytlari([("OCAK", "KANATLI", "KANATLI", 1.0, 1.0)]), 2025)


def test_yil_verisini_cikar_hayvansal_grup_yoksa_hata():
    with pytest.raises(RuntimeError, match="hayvansal"):
        yil_verisini_cikar(
            _yillik_dosya_baytlari([("OCAK", "SU ÜRÜNLERİ", "LEVREK", 1.0, 1.0)]), 2025,
        )


def test_dogrula_su_alt_kirilimi_yoksa_hata():
    aile = {("OCAK", "SU ÜRÜNLERİ"): [1.0, 1.0], ("OCAK", "KANATLI"): [1.0, 1.0]}
    su_alt = {("OCAK", "SU ÜRÜNLERİ"): [1.0, 1.0]}  # 2024 tarzı: kırılım yok
    with pytest.raises(RuntimeError, match="Levrek/Çipura"):
        _dogrula(aile, su_alt, 2024)


# --- seri_cek: ağ kabuğu ---


class SahteYanit:
    def __init__(self, status_code=200, json_veri=None, content=b"", url="https://x"):
        self.status_code = status_code
        self._json = json_veri
        self.content = content
        self.url = url

    def json(self):
        return self._json


class SahteOturum:
    def __init__(self, icerik_html, dosya_baytlari):
        self.icerik_html = icerik_html
        self.dosya_baytlari = dosya_baytlari
        self.cagrilar = []

    def get(self, url, params=None, timeout=None):
        self.cagrilar.append(url)
        if "Sayfa_Icerik_JSON" in url:
            return SahteYanit(json_veri={"icerik": self.icerik_html})
        return SahteYanit(content=self.dosya_baytlari)


def _tek_yillik_icerik_html(yil=2026, ay="Ağustos"):
    return f'<h3>{yil}</h3><p><strong>{ay}: </strong> <a href="https://eib.li/X">EİB Aylık</a></p>'


def test_seri_cek_dogru_deger_dondurur():
    oturum = SahteOturum(_tek_yillik_icerik_html(), _yillik_dosya_baytlari(_TEMEL_SATIRLAR))
    df = seri_cek(
        eib_seri(eib_kalem="LEVREK", eib_olcut="fobusd"),
        onbellek={}, session=oturum, bugun=date(2026, 9, 18),
    )
    assert df["value"].iloc[0] == pytest.approx(5000.0)


def test_seri_cek_onbellegi_paylasir():
    oturum = SahteOturum(_tek_yillik_icerik_html(), _yillik_dosya_baytlari(_TEMEL_SATIRLAR))
    onbellek = {}
    seri_cek(eib_seri(eib_kalem="LEVREK", eib_olcut="fobusd"), onbellek=onbellek, session=oturum, bugun=date(2026, 9, 18))
    cagri_sayisi = len(oturum.cagrilar)
    seri_cek(eib_seri(eib_kalem="ÇİPURA", eib_olcut="fobusd"), onbellek=onbellek, session=oturum, bugun=date(2026, 9, 18))
    assert len(oturum.cagrilar) == cagri_sayisi


def test_seri_cek_start_date_oncesini_kirpar():
    satirlar = _TEMEL_SATIRLAR + [("ŞUBAT", "SU ÜRÜNLERİ", "LEVREK", 10.0, 100.0)]
    icerik = '<h3>2026</h3><p><strong>Ocak: </strong> <a href="https://eib.li/X">EİB</a></p><p><strong>Şubat: </strong> <a href="https://eib.li/Y">EİB Aylık</a></p>'
    oturum = SahteOturum(icerik, _yillik_dosya_baytlari(satirlar))
    df = seri_cek(
        eib_seri(eib_kalem="LEVREK", eib_olcut="fobusd", start_date="2026-02-01"),
        onbellek={}, session=oturum, bugun=date(2026, 2, 18),
    )
    assert list(df["date"]) == ["2026-02-01"]


def test_seri_cek_bilinmeyen_kombinasyonda_hata():
    oturum = SahteOturum(_tek_yillik_icerik_html(), _yillik_dosya_baytlari(_TEMEL_SATIRLAR))
    with pytest.raises(RuntimeError, match="bulunamadı"):
        seri_cek(eib_seri(eib_kalem="YOK-OLAN-KALEM", eib_olcut="fobusd"), onbellek={}, session=oturum, bugun=date(2026, 9, 18))


def test_seri_cek_icerik_http_hatasi_yukselir():
    class HataliOturum:
        def get(self, url, params=None, timeout=None):
            return SahteYanit(status_code=500)

    with pytest.raises(RuntimeError, match="HTTP 500"):
        seri_cek(eib_seri(), onbellek={}, session=HataliOturum(), bugun=date(2026, 9, 18))
