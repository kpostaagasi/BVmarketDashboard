"""Pegasus çeyreklik Yatırımcı Sunumu istemcisi (`pgsus_ir` kaynak_tipi)
testleri.

Sayfa metinleri pdfplumber `extract_text()` çıktısıyla AYNI biçimde
sentetik metin olarak verilir; gerçek PDF üretmeye gerek yok (bkz.
`ingest/pgsus.py` modül docstring'i — bu sayfaların hiçbiri grafik/x0
konum eşlemesi gerektirmez, THY'nin Net Borç/Passenger RASK grafiklerinin
aksine).
"""

from types import SimpleNamespace

import pytest

from ingest.pgsus import (
    SUNUMLARIMIZ_SAYFASI,
    _arti_nakit_noktasi,
    _buyuk_tablo_noktalari,
    _ceyrek_tarihi,
    _ceyrekleri_uret,
    _filo_noktalari,
    _intl_sayi,
    _net_borc_noktalari,
    _teslim_sayisi,
    sunum_bilgisi,
    sunum_seri_cek,
)


def pgsus_ir_seri(**kwargs):
    varsayilan = dict(id="havacilik/test", pgsus_metrik="rask", start_date=None)
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


class SahteYanit:
    def __init__(self, content, status_code=200):
        self.content = content
        self.status_code = status_code

    @property
    def text(self):
        return self.content.decode("utf-8", errors="replace") if isinstance(self.content, bytes) else self.content


class SahteOturum:
    def __init__(self, yanit_haritasi):
        self.yanit_haritasi = yanit_haritasi

    def get(self, url, **kwargs):
        return self.yanit_haritasi[url]


# --- _intl_sayi / _ceyrek_tarihi / _ceyrekleri_uret ---


def test_intl_sayi_virgul_binlik_nokta_ondalik():
    assert _intl_sayi("1,091") == 1091.0
    assert _intl_sayi("4.49") == 4.49
    assert _intl_sayi("-92") == -92.0
    assert _intl_sayi("3,126") == 3126.0


def test_ceyrek_tarihi_ceyregin_ilk_ayina_damgalar():
    assert _ceyrek_tarihi(2026, 1) == "2026-01-01"
    assert _ceyrek_tarihi(2026, 2) == "2026-04-01"
    assert _ceyrek_tarihi(2026, 3) == "2026-07-01"
    assert _ceyrek_tarihi(2026, 4) == "2026-10-01"


def test_ceyrekleri_uret_geriye_dogru_on_ceyrek_eskiden_yeniye():
    ceyrekler = _ceyrekleri_uret(2026, 2, 10)
    assert ceyrekler[0] == (2024, 1)
    assert ceyrekler[-1] == (2026, 2)
    assert len(ceyrekler) == 10


def test_ceyrekleri_uret_yil_sinirini_dogru_gecer():
    ceyrekler = _ceyrekleri_uret(2025, 1, 3)
    assert ceyrekler == [(2024, 3), (2024, 4), (2025, 1)]


# --- _buyuk_tablo_noktalari: OPERASYONEL VE FİNANSAL VERİLER ---


_BUYUK_TABLO_SATIRLARI_ORNEK = {
    "Toplam Gelirler (mln Euro)": "519 763 1,091 753 622 876 1,103 814 642 865",
    "Yan Gelirler (mln Euro)": "198 262 318 281 262 317 363 332 287 311",
    "FAVÖK (mln Euro)*": "39 230 443 176 42 254 395 148 3 80",
    "Net kar/zarar": "-103 112 301 51 -62 122 227 15 -153 -92",
    "RASK, (€c)": "3.66 4.51 5.76 4.49 3.86 4.41 4.97 4.03 3.66 4.49",
    "CASK, (€c)": "3.97 3.64 3.87 3.97 4.20 3.65 3.72 3.90 4.28 4.67",
}


def _buyuk_tablo_metni(haric_etiket=None):
    baslik = "12A 12A % değ. 1Ç 2Ç 3Ç 4Ç 1Ç 2Ç 3Ç 4Ç 1Ç 2Ç % değ. 6A 6A % değ.\n"
    satirlar = "".join(
        f"{etiket} 1,000 1,100 10% {ceyrekler} -1% 2,000 2,100 1%\n"
        for etiket, ceyrekler in _BUYUK_TABLO_SATIRLARI_ORNEK.items()
        if etiket != haric_etiket
    )
    return baslik + satirlar


def test_buyuk_tablo_noktalari_on_ceyrek_dogru_deger_verir():
    ceyrekler = _ceyrekleri_uret(2026, 2, 10)
    sonuc = _buyuk_tablo_noktalari(_buyuk_tablo_metni(), ceyrekler)
    assert sonuc["satis-gelirleri"]["2026-04-01"] == 865.0
    assert sonuc["satis-gelirleri"]["2024-01-01"] == 519.0
    assert len(sonuc["satis-gelirleri"]) == 10
    assert sonuc["net-kar"]["2026-04-01"] == -92.0
    assert sonuc["rask"]["2026-04-01"] == 4.49


def test_buyuk_tablo_noktalari_baslik_yoksa_hata():
    with pytest.raises(RuntimeError, match="başlık sütunları"):
        _buyuk_tablo_noktalari("rastgele metin", _ceyrekleri_uret(2026, 2, 10))


def test_buyuk_tablo_noktalari_satir_eksikse_hata():
    metin = _buyuk_tablo_metni(haric_etiket="Yan Gelirler (mln Euro)")
    with pytest.raises(RuntimeError, match="yan-gelirler.*satırı bulunamadı"):
        _buyuk_tablo_noktalari(metin, _ceyrekleri_uret(2026, 2, 10))


# --- _net_borc_noktalari: BİLANÇO YAPISI ---


def _bilanco_yapisi_metni(deger1=2749, deger2=2942, deger3=3156, ay="Haziran"):
    return (
        f"31 Aralık 31 Aralık 30 {ay}\nMilyon Euro\n2024 2025 2026\n"
        f"Net Borç, mn Euro {deger1} {deger2} {deger3}\n"
    )


def test_net_borc_noktalari_uc_donem_dogru_deger_verir():
    sonuc = _net_borc_noktalari(_bilanco_yapisi_metni())
    assert sonuc["2024-10-01"] == 2749.0
    assert sonuc["2025-10-01"] == 2942.0
    assert sonuc["2026-04-01"] == 3156.0


def test_net_borc_noktalari_baslik_bulunamazsa_hata():
    with pytest.raises(RuntimeError, match="başlık sütunları"):
        _net_borc_noktalari("rastgele metin")


def test_net_borc_noktalari_satir_bulunamazsa_hata():
    baslik = "31 Aralık 31 Aralık 30 Haziran\nMilyon Euro\n2024 2025 2026\n"
    with pytest.raises(RuntimeError, match="Net Borç"):
        _net_borc_noktalari(baslik)


# --- _arti_nakit_noktasi: NAKİT POZİSYONU cümlesi ---


def test_arti_nakit_noktasi_cari_donemi_dogru_okur():
    metin = "Artı nakit pozisyonu Haziran 2026 sonunda 548 milyon Euro'dur."
    sonuc = _arti_nakit_noktasi(metin, 2026, 2)
    assert sonuc == {"2026-04-01": 548.0}


def test_arti_nakit_noktasi_cumle_yoksa_hata():
    with pytest.raises(RuntimeError, match="cümlesi bulunamadı"):
        _arti_nakit_noktasi("ilgisiz metin", 2026, 2)


def test_arti_nakit_noktasi_donem_uyusmazsa_hata():
    """Cümledeki ay/yıl sunum meta verisiyle (yıl, çeyrek) uyuşmuyorsa —
    şablon kayması ya da yanlış sayfa eşleşmesi anlamına gelir."""
    metin = "Artı nakit pozisyonu Mart 2026 sonunda 548 milyon Euro'dur."
    with pytest.raises(RuntimeError, match="uyuşmuyor"):
        _arti_nakit_noktasi(metin, 2026, 2)


# --- _teslim_sayisi: sipariş durum cümlesi ---


def test_teslim_sayisi_hepsi_teslim_alindi():
    assert _teslim_sayisi("hepsi teslim alındı", 42) == 42


def test_teslim_sayisi_n_adet_teslim_alindi():
    assert _teslim_sayisi("69 adet teslim alındı", 108) == 69


def test_teslim_sayisi_henuz_baslamadi():
    assert _teslim_sayisi("teslimatlar henüz başlamadı", 100) == 0


def test_teslim_sayisi_arada_yabanci_metin_olsa_bile_calisir():
    """Sayfa iki sütunlu düzende (bülten + tablo iç içe) — durum metni
    arada tablo satırı taşıyabilir (bkz. modül docstring'i)."""
    karisik = "69 adet\nAirbus A320ceo - - 6 6\nteslim alındı"
    assert _teslim_sayisi(karisik, 108) == 69


def test_teslim_sayisi_taninmayan_durum_hata():
    with pytest.raises(RuntimeError, match="tanınamadı"):
        _teslim_sayisi("bilinmeyen durum ifadesi", 10)


# --- _filo_noktalari: FİLO sayfası ---


def _filo_metni():
    return (
        "Boeing 737-800 4 5 0 9\n"
        "Airbus A320ceo - - 6 6\n"
        "Airbus A320neo - 29 17 46\n"
        "Airbus A321neo - 69 1 70\n"
        "Toplam 4 103 24 131\n"
        "5,5 yıl ortalama yaş\n"
        "Sipariş planı: 42 A320neo (hepsi teslim alındı), 108 A321neo (69 adet "
        "teslim alındı) ve 100 Boeing MAX-10 (teslimatlar henüz başlamadı)\n"
    )


def test_filo_noktalari_tip_yas_ve_siparis_bakiyesini_dondurur():
    sonuc = _filo_noktalari(_filo_metni(), "2026-04-01")
    assert sonuc["filo-a321-neo"]["2026-04-01"] == 70.0
    assert sonuc["filo-ortalama-yas"]["2026-04-01"] == 5.5
    assert sonuc["siparis-bakiye-a320neo"]["2026-04-01"] == 0.0
    assert sonuc["siparis-bakiye-a321neo"]["2026-04-01"] == 39.0
    assert sonuc["siparis-bakiye-max10"]["2026-04-01"] == 100.0


def test_filo_noktalari_tip_toplami_uyusmazsa_hata():
    metin = _filo_metni().replace("Toplam 4 103 24 131", "Toplam 4 103 24 132")
    with pytest.raises(RuntimeError, match="Toplam satırı"):
        _filo_noktalari(metin, "2026-04-01")


def test_filo_noktalari_tip_satiri_eksikse_hata():
    metin = _filo_metni().replace("Airbus A321neo - 69 1 70\n", "")
    with pytest.raises(RuntimeError, match="filo-a321-neo"):
        _filo_noktalari(metin, "2026-04-01")


def test_filo_noktalari_yas_cumlesi_yoksa_hata():
    metin = _filo_metni().replace("5,5 yıl ortalama yaş\n", "")
    with pytest.raises(RuntimeError, match="ortalama yaş"):
        _filo_noktalari(metin, "2026-04-01")


def test_filo_noktalari_siparis_cumlesi_yoksa_hata():
    metin = _filo_metni().split("5,5 yıl ortalama yaş")[0] + "5,5 yıl ortalama yaş\n"
    with pytest.raises(RuntimeError, match="Sipariş planı"):
        _filo_noktalari(metin, "2026-04-01")


# --- sunum_bilgisi: sayfa kazıma ---


def test_sunum_bilgisi_ilk_baglantiyi_ve_donemi_link_metninden_ayristirir():
    """URL slug'ı çeyreği güvenilir yansıtmıyor (bkz. modül docstring'i) —
    yıl/çeyrek LİNK METNİNDEN gelmeli, URL'den değil."""
    html = (
        '<a href="/medium/image/pgsus-2026-2-ceyrek-yatirimci-sunumu_1802/view.aspx" '
        'target="_blank" class="ico-pdf %>">2026 2. Çeyrek Yatırımcı Sunumu</a>'
        '<a href="/medium/image/pgsusciptur_1676/view.aspx" target="_blank" '
        'class="ico-pdf %>">2026 1. Çeyrek Yatırımcı Sunumu</a>'
    )
    oturum = SahteOturum({SUNUMLARIMIZ_SAYFASI: SahteYanit(html.encode("utf-8"))})
    url, yil, ceyrek = sunum_bilgisi(session=oturum)
    assert url.endswith("pgsus-2026-2-ceyrek-yatirimci-sunumu_1802/view.aspx")
    assert (yil, ceyrek) == (2026, 2)


def test_sunum_bilgisi_baglanti_yoksa_hata():
    oturum = SahteOturum({SUNUMLARIMIZ_SAYFASI: SahteYanit(b"<html></html>")})
    with pytest.raises(RuntimeError, match="bulunamadı"):
        sunum_bilgisi(session=oturum)


def test_sunum_bilgisi_http_hatasi_yukselir():
    oturum = SahteOturum({SUNUMLARIMIZ_SAYFASI: SahteYanit(b"", status_code=503)})
    with pytest.raises(RuntimeError, match="HTTP 503"):
        sunum_bilgisi(session=oturum)


# --- sunum_seri_cek: önbellek + hata yolları ---


def test_sunum_seri_cek_onbellekten_okur_ve_tarihe_gore_sirali_doner():
    onbellek = {"noktalar": {"rask": {"2026-04-01": 4.49, "2025-04-01": 4.41}}}
    df = sunum_seri_cek(pgsus_ir_seri(pgsus_metrik="rask"), onbellek=onbellek)
    assert list(df["date"]) == ["2025-04-01", "2026-04-01"]
    assert list(df["value"]) == [4.41, 4.49]


def test_sunum_seri_cek_bilinmeyen_metrikte_hata():
    onbellek = {"noktalar": {"rask": {"2026-04-01": 4.49}}}
    with pytest.raises(RuntimeError, match="pgsus_metrik"):
        sunum_seri_cek(pgsus_ir_seri(pgsus_metrik="cask"), onbellek=onbellek)


def test_sunum_seri_cek_start_date_oncesini_kirpar():
    onbellek = {"noktalar": {"rask": {"2025-04-01": 4.41, "2026-04-01": 4.49}}}
    df = sunum_seri_cek(pgsus_ir_seri(pgsus_metrik="rask", start_date="2026-01-01"), onbellek=onbellek)
    assert list(df["date"]) == ["2026-04-01"]
