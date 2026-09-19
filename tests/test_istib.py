"""İstanbul Ticaret Borsası (İTB) haftalık tescil bülteni istemcisi testleri."""

from datetime import date
from types import SimpleNamespace

import pytest

from ingest.istib import (
    URUN_ESLEME,
    _taban_ad,
    kumes_hayvani_satirlarini_cikar,
    ondalik_cevir,
    pazartesileri_uret,
    seri_cek,
    urun_agirlikli_fiyat,
)


def istib_seri(**kwargs):
    varsayilan = dict(id="kanatli/pilic-kanat", kaynak_tipi="istib", istib_urun="piliç-kanat")
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


def _satir(ad, en_az, en_cok, ortalama, miktar, tutar, birim="Kg"):
    return (
        f"<tr><td></td><td></td><td>{ad}</td><td>1 Peşin</td>"
        f"<td>{en_az}</td><td>{en_cok}</td><td>{ortalama}</td>"
        f"<td>{miktar}</td><td>{birim}</td><td>{tutar}</td></tr>"
    )


def _bulten(satirlar, sonraki_grup=True):
    govde = "".join(satirlar)
    kuyruk = '<tr><td colspan="10"><div class="group-title">BAKLİYAT</div></td></tr>' if sonraki_grup else ""
    return f'<div>KÜMES HAYVANI ETİ</div>{govde}{kuyruk}'


# --- ondalik_cevir / _taban_ad ---


def test_ondalik_cevir_binlik_ve_ondalik_ayracini_cozer():
    assert ondalik_cevir("10.236,18") == pytest.approx(10236.18)


def test_taban_ad_parantez_ekini_atar():
    assert _taban_ad("PİLİÇ KANAT (HTS)") == "PİLİÇ KANAT"
    assert _taban_ad("HİNDİ ETİ KEMİKSİZ (Vadeli Kg HTA  )") == "HİNDİ ETİ KEMİKSİZ"


# --- kumes_hayvani_satirlarini_cikar ---


def test_kumes_hayvani_satirlarini_cikar_eslesen_urunu_bulur():
    html = _bulten([_satir("PİLİ&#199; KANAT (HTS)", "460,00", "460,00", "460,00", "113,26", "52.097,30")])
    sonuc = kumes_hayvani_satirlarini_cikar(html)
    assert sonuc == {"piliç-kanat": [{"ortalama": 460.0, "miktar": 113.26}]}


def test_kumes_hayvani_satirlarini_cikar_eslesmeyen_urunu_atlar():
    html = _bulten([_satir("PİLİÇ KANAT (HTS)", "1", "1", "1", "1", "1"), _satir("İNEK ETİ (GTTS)", "500", "600", "550", "10", "5500")])
    sonuc = kumes_hayvani_satirlarini_cikar(html)
    assert set(sonuc) == {"piliç-kanat"}


def test_kumes_hayvani_satirlarini_cikar_grup_baslamadan_bos_doner():
    assert kumes_hayvani_satirlarini_cikar("<div>BAKLİYAT VE MAMÜLLERİ</div>") == {}


def test_kumes_hayvani_satirlarini_cikar_sonraki_grubu_sizdirmaz():
    """Bir sonraki `group-title` grubundaki (ör. BAKLİYAT) satırlar dahil edilmemeli."""
    html = (
        '<div>KÜMES HAYVANI ETİ</div>'
        + _satir("PİLİÇ KANAT (HTS)", "1", "1", "1", "1", "1")
        + '<div class="group-title">BAKLİYAT</div>'
        + _satir("PİLİÇ KANAT (HTS)", "999", "999", "999", "999", "999")
    )
    sonuc = kumes_hayvani_satirlarini_cikar(html)
    assert sonuc["piliç-kanat"] == [{"ortalama": 1.0, "miktar": 1.0}]


def test_kumes_hayvani_satirlarini_cikar_coklu_cins_satirini_biriktirir():
    html = _bulten([
        _satir("HİNDİ ETİ KEMİKLİ (HTA)", "100", "120", "110", "50", "5500"),
        _satir("HİNDİ ETİ KEMİKLİ (HTS)", "200", "220", "210", "10", "2100"),
    ])
    sonuc = kumes_hayvani_satirlarini_cikar(html)
    assert len(sonuc["hindi-eti-kemikli"]) == 2


def test_urun_esleme_dort_urunu_kapsar():
    assert set(URUN_ESLEME) == {"PİLİÇ ETİ KEMİKSİZ", "HİNDİ ETİ KEMİKLİ", "HİNDİ ETİ KEMİKSİZ", "PİLİÇ KANAT"}


# --- urun_agirlikli_fiyat ---


def test_urun_agirlikli_fiyat_tek_satirda_kendi_ortalamasini_doner():
    """Bültenin Ortalama Fiyat sütunu Tutar/Miktar'a EŞİT DEĞİL (ölçüldü) —
    tek satırlı hafta doğrudan o satırın ortalamasını taşımalı."""
    assert urun_agirlikli_fiyat([{"ortalama": 237.69, "miktar": 10236.18}]) == pytest.approx(237.69)


def test_urun_agirlikli_fiyat_coklu_satirda_miktar_agirlikli_ortalama():
    satirlar = [{"ortalama": 100.0, "miktar": 10.0}, {"ortalama": 200.0, "miktar": 30.0}]
    # (100*10 + 200*30) / 40 = 175
    assert urun_agirlikli_fiyat(satirlar) == pytest.approx(175.0)


def test_urun_agirlikli_fiyat_sifir_miktarda_hata():
    with pytest.raises(RuntimeError, match="sıfır miktarlı"):
        urun_agirlikli_fiyat([{"ortalama": 1.0, "miktar": 0.0}])


# --- pazartesileri_uret ---


def test_pazartesileri_uret_gecmis_pazartesiyi_dahil_eder():
    pazartesiler = pazartesileri_uret(date(2026, 9, 18), adet=3)  # Cuma
    assert pazartesiler == [date(2026, 8, 31), date(2026, 9, 7), date(2026, 9, 14)]


def test_pazartesileri_uret_bugun_pazartesiyse_kendini_icerir():
    pazartesiler = pazartesileri_uret(date(2026, 9, 14), adet=2)
    assert pazartesiler[-1] == date(2026, 9, 14)


def test_pazartesileri_uret_artan_siralidir():
    pazartesiler = pazartesileri_uret(date(2026, 9, 18), adet=5)
    assert pazartesiler == sorted(pazartesiler)


# --- seri_cek: ağ kabuğu ---


class SahteOturum:
    def __init__(self, html_haritasi):
        self.html_haritasi = html_haritasi
        self.cagrilar = []

    def get(self, url, params=None, timeout=None):
        self.cagrilar.append(params)
        hafta = params["hafta"]
        html = self.html_haritasi.get(hafta, _bulten([]))
        return SimpleNamespace(status_code=200, text=html)


def test_seri_cek_dogru_deger_ve_tarih_dondurur():
    html_haritasi = {
        "2026-09-07": _bulten([_satir("PİLİÇ KANAT (HTS)", "460", "460", "460,00", "113,26", "52097,30")]),
    }
    oturum = SahteOturum(html_haritasi)
    df = seri_cek(istib_seri(), onbellek={}, session=oturum, bugun=date(2026, 9, 8))
    assert list(df["date"]) == ["2026-09-07"]
    assert df["value"].iloc[0] == pytest.approx(460.0)


def test_seri_cek_onbellegi_paylasir():
    """4 ürün aynı haftalık HTML'i paylaşır: onbellek bir kez çekmeli."""
    html_haritasi = {
        "2026-09-07": _bulten([
            _satir("PİLİÇ KANAT (HTS)", "1", "1", "1", "1", "1"),
            _satir("HİNDİ ETİ KEMİKLİ (HTS)", "1", "1", "1", "1", "1"),
        ]),
    }
    oturum = SahteOturum(html_haritasi)
    onbellek = {}
    seri_cek(istib_seri(), onbellek=onbellek, session=oturum, bugun=date(2026, 9, 8))
    cagri_sayisi = len(oturum.cagrilar)
    seri_cek(istib_seri(istib_urun="hindi-eti-kemikli"), onbellek=onbellek, session=oturum, bugun=date(2026, 9, 8))
    assert len(oturum.cagrilar) == cagri_sayisi


def test_seri_cek_veri_yoksa_hata():
    oturum = SahteOturum({})
    with pytest.raises(RuntimeError, match="hiç veri yok"):
        seri_cek(istib_seri(), onbellek={}, session=oturum, bugun=date(2026, 9, 8))


def test_seri_cek_http_hatasi_yukselir():
    class HataliOturum:
        def get(self, url, params=None, timeout=None):
            return SimpleNamespace(status_code=500, text="")

    with pytest.raises(RuntimeError, match="HTTP 500"):
        seri_cek(istib_seri(), onbellek={}, session=HataliOturum(), bugun=date(2026, 9, 8))
