"""TEPAV (`ingest/tepav.py`) TEGE bülten istemcisi testleri.

Kapsam: PDF dosya adından dönem çıkarma (ad + numara varyantı), negatif
yüzde/&nbsp; içeren cümlelerin doğru ayrıştırılması, hub/yıl sayfası
bağlantı taraması ve `seri_cek`'in önbellek davranışı.
"""

from types import SimpleNamespace

import pytest

from ingest.tepav import (
    HUB_URL,
    haber_baglantilarini_bul,
    haberden_noktalari_cikar,
    seri_cek,
    yil_sayfalarini_bul,
)


class SahteYanit:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code


class SahteOturum:
    def __init__(self, yanit_haritasi):
        self.yanit_haritasi = yanit_haritasi
        self.cagrilar = []

    def get(self, url, timeout=None, headers=None):
        self.cagrilar.append(url)
        return self.yanit_haritasi[url]


def tepav_seri(**kwargs):
    varsayilan = dict(id="tepav/x", tepav_seri="tege-aylik", start_date=None)
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


def _haber_html(pdf_adi: str, aylik=None, yillik=None, kktc=None) -> str:
    parcalar = [f'<a href="https://files.tepav.org.tr/upload/files/x.{pdf_adi}">bülten</a>']
    if aylik is not None:
        parcalar.append(f"1-25 ayında derlenen verilere göre aylık gıda enflasyonu yüzde {aylik} olarak hesaplandı.")
    if yillik is not None:
        parcalar.append(f"yıllık gıda enflasyonu ise yüzde {yillik} olarak hesapladı.")
    if kktc is not None:
        parcalar.append(f"KKTC-TEGE kapsamında derlenen verilerle aylık gıda enflasyonu yüzde {kktc} olarak hesaplandı.")
    return " ".join(parcalar)


def test_haberden_noktalari_cikar_ad_kalibi_dosya_adindan_donemi_okur():
    html = _haber_html("TEGEAgustos2026.pdf", aylik="1,07", yillik="30,9", kktc="2,72")
    assert haberden_noktalari_cikar(html, 2026) == (
        "2026-08-01", {"tege-aylik": 1.07, "tege-yillik": 30.9, "kktc-tege-aylik": 2.72},
    )


def test_haberden_noktalari_cikar_altcizgili_ad_kalibi():
    html = _haber_html("TEGE_Mart_2026.pdf", aylik="2,90", yillik="33,4")
    tarih, degerler = haberden_noktalari_cikar(html, 2026)
    assert tarih == "2026-03-01"
    assert degerler == {"tege-aylik": 2.90, "tege-yillik": 33.4}


def test_haberden_noktalari_cikar_numara_kalibi_ay_adi_yoksa():
    """'TEGE07.pdf' gibi yalnızca 2 haneli ay numarası taşıyan dosyalar da
    (yıl sayfadan context olarak gelir, dosya adında yıl yok)."""
    html = _haber_html("TEGE07.pdf", aylik="0,93")
    tarih, _degerler = haberden_noktalari_cikar(html, 2026)
    assert tarih == "2026-07-01"


def test_haberden_noktalari_cikar_negatif_yuzde_dogru_parse_edilir():
    html = _haber_html("TEGEHaziran_2026.pdf", aylik="-0,23", yillik="32,6")
    _tarih, degerler = haberden_noktalari_cikar(html, 2026)
    assert degerler["tege-aylik"] == pytest.approx(-0.23)


def test_haberden_noktalari_cikar_donem_bulunamazsa_none():
    assert haberden_noktalari_cikar("<html>hiç TEGE bülten linki yok</html>", 2026) is None


def test_haberden_noktalari_cikar_bilinmeyen_ay_adi_none():
    html = _haber_html("TEGEBilinmeyenay2026.pdf", aylik="1,0")
    assert haberden_noktalari_cikar(html, 2026) is None


def test_yil_sayfalarini_bul_gercek_html_yapisindan_yil_cikarir():
    html = (
        '<a target="_blank" href="https://www.tepav.org.tr/tr/calismalarimiz/s/492">'
        '<span><strong>2026</strong></span></a>'
        '<a target="_blank" href="https://www.tepav.org.tr/tr/calismalarimiz/s/484">'
        '<span><strong>2025</strong></span></a>'
    )
    assert yil_sayfalarini_bul(html) == {
        2026: "/tr/calismalarimiz/s/492", 2025: "/tr/calismalarimiz/s/484",
    }


def test_yil_sayfalarini_bul_baglanti_yoksa_bos_sozluk():
    assert yil_sayfalarini_bul("<html>boş</html>") == {}


def test_haber_baglantilarini_bul_tekrarlari_tekillestirir():
    html = 'href="/tr/haberler/s/11292" href="/tr/haberler/s/11292" href="/tr/haberler/s/11265"'
    assert haber_baglantilarini_bul(html) == ["/tr/haberler/s/11265", "/tr/haberler/s/11292"]


# --- seri_cek: ağ kabuğu + önbellek ---


def _tam_test_ortami():
    hub_html = (
        '<a href="https://www.tepav.org.tr/tr/calismalarimiz/s/492">'
        '<strong>2026</strong></a>'
    )
    yil_html = 'href="/tr/haberler/s/11292" href="/tr/haberler/s/11265"'
    haber1 = _haber_html("TEGEAgustos2026.pdf", aylik="1,07", yillik="30,9", kktc="2,72")
    haber2 = _haber_html("TEGE07.pdf", aylik="0,93", yillik="32,8")
    return SahteOturum({
        HUB_URL: SahteYanit(text=hub_html),
        "https://www.tepav.org.tr/tr/calismalarimiz/s/492": SahteYanit(text=yil_html),
        "https://www.tepav.org.tr/tr/haberler/s/11292": SahteYanit(text=haber1),
        "https://www.tepav.org.tr/tr/haberler/s/11265": SahteYanit(text=haber2),
    })


def test_seri_cek_dogru_deger_ve_onbellek_paylasir():
    oturum = _tam_test_ortami()
    onbellek = {}
    df = seri_cek(tepav_seri(tepav_seri="tege-aylik"), onbellek=onbellek, session=oturum)
    assert list(df["date"]) == ["2026-07-01", "2026-08-01"]
    assert list(df["value"]) == [0.93, 1.07]
    cagri_sayisi = len(oturum.cagrilar)

    df2 = seri_cek(tepav_seri(tepav_seri="tege-yillik"), onbellek=onbellek, session=oturum)
    assert list(df2["value"]) == [32.8, 30.9]
    assert len(oturum.cagrilar) == cagri_sayisi  # ikinci seri ağa çıkmadı


def test_seri_cek_kktc_yalnizca_veri_olan_aylari_doner():
    oturum = _tam_test_ortami()
    df = seri_cek(tepav_seri(tepav_seri="kktc-tege-aylik"), onbellek={}, session=oturum)
    assert list(df["date"]) == ["2026-08-01"]


def test_seri_cek_bilinmeyen_tepav_seri_hata():
    oturum = _tam_test_ortami()
    with pytest.raises(RuntimeError, match="tepav/x"):
        seri_cek(tepav_seri(tepav_seri="olmayan"), onbellek={}, session=oturum)
