"""TÇÜD (Türkiye Çelik Üreticileri Derneği) aylık basın bülteni istemcisi
testleri."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from ingest.tcud import (
    GECERLI_TCUD_KALEMLERI,
    KALEM_CIN,
    KALEM_DUNYA,
    KALEM_HINDISTAN,
    KALEM_IHRACAT_DEGER,
    KALEM_IHRACAT_MIKTAR,
    KALEM_ITHALAT_DEGER,
    KALEM_ITHALAT_MIKTAR,
    KALEM_TUKETIM,
    KALEM_URETIM,
    _icerik_govdesini_ayikla,
    _kumulatifi_ayliga_cevir,
    bulten_url,
    bulteni_ayikla,
    cekilecek_bultenler,
    seri_cek,
)


def tcud_seri(**kwargs):
    varsayilan = dict(id="test/celik-uretimi", tcud_kalem=KALEM_URETIM, start_date=None)
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


# --- bulten_url / cekilecek_bultenler ---


def test_bulten_url_turkce_karakterli_aylari_ascii_kok_bicimine_cevirir():
    assert bulten_url(2026, 2).endswith("/basin-buelteni-subat-2026")
    assert bulten_url(2026, 5).endswith("/basin-buelteni-mayis-2026")
    assert bulten_url(2025, 8).endswith("/basin-buelteni-agustos-2025")
    assert bulten_url(2025, 12).endswith("/basin-buelteni-aralik-2025")


def test_cekilecek_bultenler_baslangictan_bugunun_ayina_kadar_listeler():
    assert cekilecek_bultenler(date(2025, 3, 15)) == [(2025, 1), (2025, 2), (2025, 3)]


def test_cekilecek_bultenler_yil_sinirini_gecer():
    aylar = cekilecek_bultenler(date(2026, 2, 1))
    assert aylar[-3:] == [(2025, 12), (2026, 1), (2026, 2)]
    assert aylar[0] == (2025, 1)


# --- _icerik_govdesini_ayikla: <article> izolasyonu ---


def test_icerik_govdesini_ayikla_etiketleri_temizler_ve_varliklari_cozer():
    html = (
        '<html><head><meta name="description" content="ALAKASIZ 999 milyon ton"/></head>'
        '<body><article class="max-w-none space-y-6 ">'
        "<h3>ÇELİK ÜRETİMİ</h3><p>Türkiye&#8217;nin üretimi 3,4 milyon ton &amp; artış</p>"
        "</article></body></html>"
    )
    metin = _icerik_govdesini_ayikla(html)
    assert "ALAKASIZ" not in metin
    assert "<h3>" not in metin and "<p>" not in metin
    assert "Türkiye’nin üretimi 3,4 milyon ton & artış" in metin


def test_icerik_govdesini_ayikla_govde_yoksa_hata():
    with pytest.raises(RuntimeError, match="içerik gövdesi"):
        _icerik_govdesini_ayikla("<html><body>alakasız sayfa</body></html>")


# --- bulteni_ayikla: gerçek şablona uygun sentetik bülten ---


def _bulten_html(
    *,
    yil=2026,
    ay_adi="Temmuz",
    uretim="3,4 milyon ton",
    uretim_yon="artışla",
    tuketim="3,5 milyon ton",
    tuketim_yon="azalışla",
    ihr_miktar="1,2 milyon ton",
    ihr_miktar_yon="oranında artışla",
    ihr_deger="827,3 milyon dolar",
    ihr_deger_yon="artışla",
    ith_miktar="1,5 milyon ton",
    ith_miktar_yon="azalışla",
    ith_deger="1,1 milyar dolar",
    ith_deger_yon="azalışla",
    dunya="149,2 milyon ton",
    dunya_yon="azalışla",
    cin="577 milyon ton",
    cin_yon="azalış ile",
    hindistan="101,1 milyon tona",
    hindistan_yon="artışla",
):
    """Gerçek TÇÜD şablonuna uygun minimal bülten HTML'i (ölçülen canlı
    yapıya birebir: `<article class="max-w-none space-y-6">` içinde
    `<h3>`/`<p>`, bkz. ingest/tcud.py modül docstring'i)."""
    govde = (
        "<h3>ÇELİK ÜRETİMİ</h3>"
        f"<p>{yil} yılının {ay_adi} ayında Türkiye’nin ham çelik üretimi, geçen yılın aynı "
        f"ayına göre %7 {uretim_yon} {uretim} yükseldi.</p>"
        "<h3>ÇELİK TÜKETİMİ</h3>"
        f"<p>Nihai mamul tüketimi {yil} yılının {ay_adi} ayında, kıyasla %5,1 {tuketim_yon} "
        f"{tuketim} gerçekleşti.</p>"
        "<h3>DIŞ TİCARET</h3>"
        f"<p>{yil} yılının {ay_adi} ayında çelik ürünleri ihracatı, miktar yönünden %2,9 "
        f"{ihr_miktar_yon} {ihr_miktar}, değer yönünden ise %4,4 {ihr_deger_yon} {ihr_deger} "
        "oldu.</p>"
        "<h4>İthalat</h4>"
        f"<p>{yil} yılının {ay_adi} ayında çelik ürünleri ithalatı, miktar yönünden %19,7 "
        f"{ith_miktar_yon} {ith_miktar}, değer yönünden ise %17,6 {ith_deger_yon} {ith_deger} "
        "oldu.</p>"
        "<h3>DÜNYA ÇELİK ÜRETİMİ</h3>"
        "<p>Dünya Çelik Derneği (worldsteel) verilerine göre, dünya ham çelik üretimi, "
        f"geçtiğimiz yılın aynı ayına kıyasla, %0,3 {dunya_yon} {dunya}, Ocak-{ay_adi} "
        "döneminde ise %0,6 azalışla 1,1 milyar ton seviyesinde gerçekleşti.</p>"
        f"<p>Ocak-{ay_adi} döneminde Çin’in ham çelik üretimi, geçen yılın aynı dönemine göre, "
        f"%3,1 {cin_yon} {cin} seviyesinde gerçekleşti. Hindistan’ın ham çelik üretimi, %6,1 "
        f"{hindistan_yon} {hindistan} yükselirken, ABD’nin üretimi de arttı.</p>"
    )
    return f'<html><body><article class="max-w-none space-y-6 ">{govde}</article></body></html>'


def _metin(**kwargs) -> str:
    return _icerik_govdesini_ayikla(_bulten_html(**kwargs))


def test_bulteni_ayikla_tum_alanlari_dogru_cikarir():
    """Temmuz 2026 canlı ölçümüyle birebir (bkz. ingest/tcud.py docstring'i)."""
    sonuc = bulteni_ayikla(_metin(), 2026, 7)
    assert sonuc == {
        KALEM_URETIM: 3400.0,
        KALEM_TUKETIM: 3500.0,
        KALEM_IHRACAT_MIKTAR: 1200.0,
        KALEM_IHRACAT_DEGER: 827.3,
        KALEM_ITHALAT_MIKTAR: 1500.0,
        KALEM_ITHALAT_DEGER: 1100.0,  # 1,1 milyar -> 1100 milyon
        KALEM_DUNYA: 149.2,
        KALEM_CIN: 577.0,
        KALEM_HINDISTAN: 101.1,
    }


def test_bulteni_ayikla_bin_ton_carpilmiyor_milyon_ton_1000ile_carpilir():
    """Ocak 2026 ölçümü: ihracat miktarı '911,8 bin ton' (<1M ton olduğu
    için bülten bin ton yazıyor) — 1000 ile çarpılmamalı."""
    sonuc = bulteni_ayikla(_metin(ihr_miktar="911,8 bin ton"), 2026, 1)
    assert sonuc[KALEM_IHRACAT_MIKTAR] == pytest.approx(911.8)
    assert sonuc[KALEM_URETIM] == pytest.approx(3400.0)  # milyon ton -> bin ton


def test_bulteni_ayikla_milyar_dolar_1000_ile_carpilir_milyon_dolar_carpilmiyor():
    sonuc = bulteni_ayikla(_metin(ith_deger="1 milyar dolar", ihr_deger="600,1 milyon dolar"), 2026, 1)
    assert sonuc[KALEM_ITHALAT_DEGER] == pytest.approx(1000.0)
    assert sonuc[KALEM_IHRACAT_DEGER] == pytest.approx(600.1)


def test_bulteni_ayikla_virgulsuz_ve_bitisik_baglac_varyasyonlarini_kabul_eder():
    """'artışla' (bitişik) virgülsüz de, 'oranında' eklentisi de her ikisi
    de kabul edilmeli (ölçüldü: yazardan yazara değişiyor)."""
    sonuc = bulteni_ayikla(
        _metin(uretim_yon="oranında azalışla", tuketim_yon="artışla"),
        2026, 7,
    )
    assert sonuc[KALEM_URETIM] == pytest.approx(3400.0)


def test_bulteni_ayikla_alan_eksikse_hata():
    bozuk = _bulten_html().replace("Nihai mamul tüketimi", "Tüketim verisi bu ay yok")
    metin = _icerik_govdesini_ayikla(bozuk)
    with pytest.raises(RuntimeError, match="nihai mamul tüketimi"):
        bulteni_ayikla(metin, 2026, 7)


def test_bulteni_ayikla_eski_ulac_kalibinda_sessizce_yanlis_yerine_hata():
    """2021-2024 bültenleri 'artarak'/'kaydederek' (ulaç) kullanıyor —
    ILK_YIL=2025 sınırının gerekçesi: bu kalıp sessizce yanlış değer
    üretmek yerine RuntimeError vermeli (bkz. ingest/tcud.py docstring'i)."""
    with pytest.raises(RuntimeError, match="ham çelik üretimi"):
        bulteni_ayikla(_metin(uretim_yon="artarak"), 2026, 7)


# --- _kumulatifi_ayliga_cevir ---


def test_kumulatifi_ayliga_cevir_ocak_kendi_basina_aylik():
    assert _kumulatifi_ayliga_cevir({"2026-01-01": 75.3}) == {"2026-01-01": 75.3}


def test_kumulatifi_ayliga_cevir_referans_degerleriyle_birebir():
    """Canlı ölçüm (2026-09-18): Şubat kümülatifi (160,3) − Ocak (75,3) =
    85,0 — MarketVisuals referansıyla (85.0) birebir; aynı teknikle
    Hindistan 28,9 − 15,1 = 13,8."""
    aylik = _kumulatifi_ayliga_cevir({"2026-01-01": 75.3, "2026-02-01": 160.3})
    assert aylik["2026-02-01"] == pytest.approx(85.0)


def test_kumulatifi_ayliga_cevir_onceki_ay_eksikse_o_ay_atlanir():
    aylik = _kumulatifi_ayliga_cevir({"2026-01-01": 10.0, "2026-03-01": 40.0})
    assert aylik == {"2026-01-01": 10.0}  # Şubat eksik -> Mart hesaplanamaz


# --- seri_cek: ağ kabuğu ---


class SahteYanit:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class SahteOturum:
    def __init__(self, sayfalar: dict[str, str | "SahteYanit"]):
        self.sayfalar = sayfalar
        self.cagrilar: list[str] = []

    def get(self, url, timeout=None, **kwargs):
        self.cagrilar.append(url)
        deger = self.sayfalar.get(url)
        if isinstance(deger, SahteYanit):
            return deger
        if deger is not None:
            return SahteYanit(200, deger)
        return SahteYanit(404, "")


def _oturum_iki_ay():
    """Ocak+Şubat 2026 bültenleri: Çin/Hindistan kümülatif farkı 85,0/13,8
    üretmeli (bkz. referans testi yukarıda)."""
    return SahteOturum({
        bulten_url(2026, 1): _bulten_html(yil=2026, ay_adi="Ocak", cin="75,3 milyon ton", hindistan="15,1 milyon tona"),
        bulten_url(2026, 2): _bulten_html(yil=2026, ay_adi="Şubat", cin="160,3 milyon ton", hindistan="28,9 milyon tona"),
    })


def test_seri_cek_dogrudan_kalemde_aylik_deger_dondurur():
    oturum = _oturum_iki_ay()
    df = seri_cek(tcud_seri(tcud_kalem=KALEM_URETIM), onbellek={}, session=oturum, bugun=date(2026, 2, 28))
    assert list(df["date"]) == ["2026-01-01", "2026-02-01"]
    assert (df["value"] == 3400.0).all()


def test_seri_cek_cin_kaleminde_kumulatiften_aylik_hesaplar():
    oturum = _oturum_iki_ay()
    df = seri_cek(tcud_seri(tcud_kalem=KALEM_CIN), onbellek={}, session=oturum, bugun=date(2026, 2, 28))
    satir = df.set_index("date")["value"]
    assert satir["2026-01-01"] == pytest.approx(75.3)
    assert satir["2026-02-01"] == pytest.approx(85.0)


def test_seri_cek_hindistan_kaleminde_kumulatiften_aylik_hesaplar():
    oturum = _oturum_iki_ay()
    df = seri_cek(tcud_seri(tcud_kalem=KALEM_HINDISTAN), onbellek={}, session=oturum, bugun=date(2026, 2, 28))
    satir = df.set_index("date")["value"]
    assert satir["2026-02-01"] == pytest.approx(13.8)


def test_seri_cek_onbellegi_paylasir():
    """9 kalem aynı aylık bülten kümesini paylaşır; onbellek olmadan her
    kalem kendi indirmesini yapardı."""
    oturum = _oturum_iki_ay()
    onbellek: dict = {}
    seri_cek(tcud_seri(tcud_kalem=KALEM_URETIM), onbellek=onbellek, session=oturum, bugun=date(2026, 2, 28))
    ilk_cagri = len(oturum.cagrilar)
    seri_cek(tcud_seri(tcud_kalem=KALEM_TUKETIM), onbellek=onbellek, session=oturum, bugun=date(2026, 2, 28))
    assert len(oturum.cagrilar) == ilk_cagri  # ikinci kalem ağa hiç çıkmadı


def test_seri_cek_yayimlanmamis_cari_ayi_atlar():
    """404 'henüz yayımlanmadı' demek; seri o ayı içermeden devam etmeli."""
    oturum = SahteOturum({bulten_url(2026, 1): _bulten_html(yil=2026, ay_adi="Ocak")})
    df = seri_cek(tcud_seri(tcud_kalem=KALEM_URETIM), onbellek={}, session=oturum, bugun=date(2026, 2, 15))
    assert list(df["date"]) == ["2026-01-01"]


def test_seri_cek_http_hatasi_yukselir():
    """404 'henüz yok' demek; 500 sessizce yutulmamalı."""
    oturum = SahteOturum({bulten_url(2026, 1): SahteYanit(500, "")})
    with pytest.raises(RuntimeError, match="HTTP 500"):
        seri_cek(tcud_seri(), onbellek={}, session=oturum, bugun=date(2026, 1, 31))


def test_seri_cek_start_date_oncesini_kirpar():
    oturum = _oturum_iki_ay()
    df = seri_cek(
        tcud_seri(tcud_kalem=KALEM_URETIM, start_date="2026-02-01"),
        onbellek={}, session=oturum, bugun=date(2026, 2, 28),
    )
    assert list(df["date"]) == ["2026-02-01"]


def test_seri_cek_bilinmeyen_kalemde_hata():
    with pytest.raises(RuntimeError, match="bilinmeyen kalem"):
        seri_cek(tcud_seri(tcud_kalem="yok-olan-kalem"), onbellek={}, session=SahteOturum({}), bugun=date(2026, 2, 28))


def test_seri_cek_hic_veri_toplanamazsa_hata():
    oturum = SahteOturum({})  # her ay 404
    with pytest.raises(RuntimeError, match="hiç veri toplanamadı"):
        seri_cek(tcud_seri(), onbellek={}, session=oturum, bugun=date(2025, 1, 15))


def test_gecerli_tcud_kalemleri_dokuz_kalem_icerir():
    assert len(GECERLI_TCUD_KALEMLERI) == 9
