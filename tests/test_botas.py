"""BOTAŞ doğal gaz toptan satış fiyat tarifesi istemcisi testleri."""

from types import SimpleNamespace

import pytest

from ingest.botas import (
    _dagitim_bolumu,
    _kategori_belirle,
    guncel_tarife_url,
    kategori_fiyatlarini_cikar,
    seri_cek,
    yururluk_tarihi,
)


def botas_seri(**kwargs):
    varsayilan = dict(id="botas-dogalgaz/konut", kaynak_tipi="botas", botas_kategori="konut")
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


_BASLIK = "<h1>4 Nisan 2026 Tarihinden İtibaren Geçerli BOTAŞ Doğal Gaz Toptan Satış Fiyat Tarifesi</h1>"


def _detay_tablosu():
    return (
        _BASLIK
        + '<table><tbody>'
        + '<tr><td colspan="11"><div><strong><center>...Dağıtım Şirketleri İçin...</center></strong></div></td></tr>'
        + '<tr><td><strong>Konut Tüketicileri (Evsel Tüketiciler) Kademe-1</strong></td><td colspan="2"><center>10,625000</center></td></tr>'
        + '<tr><td><strong>Konut Tüketicileri (Evsel Tüketiciler) Kademe-2</strong></td><td colspan="2"><center>18,000000</center></td></tr>'
        + '<tr><td><strong>Şehit Ailesi ve Muharip/Malul Gazi Olan Konut Tüketicileri (Evsel Tüketiciler)</strong></td><td colspan="2"><center>5,312500</center></td></tr>'
        + '<tr><td><div><strong>Ekmek &Uuml;reticileri</strong></div></td><td><div>10,395938</div></td></tr>'
        + '<tr><td><div><strong>Elektrik &Uuml;retimi Amacı Dışındaki Kullanım</strong></div></td><td><div>18,000000</div></td></tr>'
        + '<tr><td><div><strong>Elektrik &Uuml;retimi Amaçlı Kullanım</strong></div></td><td><div>18,000000</div></td></tr>'
        + '<tr><td colspan="4"><div><strong><center>...Organize Sanayi Bölgeleri...</center></strong></div></td></tr>'
        + '<tr><td><div><strong>Ekmek &Uuml;reticileri</strong></div></td><td><div>999,000000</div></td></tr>'
        + '</tbody></table>'
    )


# --- yururluk_tarihi ---


def test_yururluk_tarihi_basliktan_dogru_tarihi_cikarir():
    assert yururluk_tarihi(_BASLIK) == "2026-04-04"


def test_yururluk_tarihi_baslik_yoksa_hata():
    with pytest.raises(RuntimeError, match="yürürlük tarihi"):
        yururluk_tarihi("<h1>Alakasız Sayfa</h1>")


# --- guncel_tarife_url ---


def test_guncel_tarife_url_tarihli_baglantiyi_bulur():
    html = (
        '<a href="https://www.botas.gov.tr/Sayfa/tarifeler/9">Tarifeler</a>'
        '<a href="https://www.botas.gov.tr/Sayfa/4-nisan-2026-tarihinden-itibaren-gecerli-botas-dogal-gaz-toptan-satis-fiyat-tarifesi/812">Detay</a>'
    )
    assert guncel_tarife_url(html) == "https://www.botas.gov.tr/Sayfa/4-nisan-2026-tarihinden-itibaren-gecerli-botas-dogal-gaz-toptan-satis-fiyat-tarifesi/812"


def test_guncel_tarife_url_genel_tarifeler_linkini_atlar():
    """'/Sayfa/tarifeler/9' 'tarife' alt dizesini içerir ama tarihli DEĞİL —
    seçilmemeli (ölçülen gerçek regresyon)."""
    html = '<a href="https://www.botas.gov.tr/Sayfa/tarifeler/9">Tarifeler</a>'
    with pytest.raises(RuntimeError, match="bağlantısı bulunamadı"):
        guncel_tarife_url(html)


# --- _kategori_belirle / kategori_fiyatlarini_cikar / _dagitim_bolumu ---


def test_kategori_belirle_bes_kategoriyi_dogru_esler():
    assert _kategori_belirle("Konut Tüketicileri (Evsel Tüketiciler) Kademe-1") == "konut"
    assert _kategori_belirle("Şehit Ailesi ve Muharip/Malul Gazi Olan...") == "sehit-ailesi"
    assert _kategori_belirle("Ekmek Üreticileri") == "ekmek-ureticileri"
    assert _kategori_belirle("Elektrik Üretimi Amaçlı Kullanım") == "elektrik-uretimi-amacli"
    assert _kategori_belirle("Elektrik Üretimi Amacı Dışındaki Kullanım") == "elektrik-uretimi-disi"


def test_kategori_belirle_kademe_2_ve_cng_none_doner():
    assert _kategori_belirle("Konut Tüketicileri (Evsel Tüketiciler) Kademe-2") is None
    assert _kategori_belirle("CNG Fiyat - 1") is None


def test_dagitim_bolumu_osb_tablosundan_once_keser():
    bolum = _dagitim_bolumu(_detay_tablosu())
    assert "Organize Sanayi" not in bolum
    assert "10,625000" in bolum


def test_kategori_fiyatlarini_cikar_bes_kategoriyi_dondurur():
    sonuc = kategori_fiyatlarini_cikar(_detay_tablosu())
    assert sonuc == {
        "konut": 10.625,
        "sehit-ailesi": 5.3125,
        "ekmek-ureticileri": 10.395938,
        "elektrik-uretimi-disi": 18.0,
        "elektrik-uretimi-amacli": 18.0,
    }


def test_kategori_fiyatlarini_cikar_osb_bolumundeki_tekrari_almaz():
    """OSB tablosundaki İKİNCİ 'Ekmek Üreticileri' (999) değil, Dağıtım
    Şirketleri tablosundaki İLK değer (10,395938) alınmalı."""
    sonuc = kategori_fiyatlarini_cikar(_detay_tablosu())
    assert sonuc["ekmek-ureticileri"] == pytest.approx(10.395938)


# --- seri_cek: ağ kabuğu ---


class SahteOturum:
    def __init__(self, indeks_html, detay_html):
        self.indeks_html = indeks_html
        self.detay_html = detay_html
        self.cagrilar = []

    def get(self, url, timeout=None):
        self.cagrilar.append(url)
        html = self.indeks_html if "satis-fiyat-tarifesi/439" in url else self.detay_html
        return SimpleNamespace(status_code=200, text=html)


def _indeks_html():
    return '<a href="https://www.botas.gov.tr/Sayfa/4-nisan-2026-tarihinden-itibaren-gecerli-botas-dogal-gaz-toptan-satis-fiyat-tarifesi/812">Detay</a>'


def test_seri_cek_dogru_kategoriyi_ve_tarihi_dondurur():
    oturum = SahteOturum(_indeks_html(), _detay_tablosu())
    df = seri_cek(botas_seri(), onbellek={}, session=oturum)
    assert list(df["date"]) == ["2026-04-04"]
    assert df["value"].iloc[0] == pytest.approx(10.625)


def test_seri_cek_onbellegi_paylasir():
    oturum = SahteOturum(_indeks_html(), _detay_tablosu())
    onbellek = {}
    seri_cek(botas_seri(), onbellek=onbellek, session=oturum)
    cagri_sayisi = len(oturum.cagrilar)
    seri_cek(botas_seri(botas_kategori="ekmek-ureticileri"), onbellek=onbellek, session=oturum)
    assert len(oturum.cagrilar) == cagri_sayisi


def test_seri_cek_bilinmeyen_kategoride_hata():
    oturum = SahteOturum(_indeks_html(), _detay_tablosu())
    with pytest.raises(RuntimeError, match="tarife sayfasında bulunamadı"):
        seri_cek(botas_seri(botas_kategori="yok-olan-kategori"), onbellek={}, session=oturum)


def test_seri_cek_indeks_http_hatasi_yukselir():
    class HataliOturum:
        def get(self, url, timeout=None):
            return SimpleNamespace(status_code=500, text="")

    with pytest.raises(RuntimeError, match="HTTP 500"):
        seri_cek(botas_seri(), onbellek={}, session=HataliOturum())
