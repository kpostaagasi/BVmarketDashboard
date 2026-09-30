"""BigChefs (BIST: BIGCH) yatırımcı ilişkileri istemcisi testleri."""

from types import SimpleNamespace

import pytest

from ingest.bigchefs import (
    GECERLI_METRIKLER,
    _donem_coz,
    _finansal_bilgi_baglantilari,
    _metrik_deger,
    _sube_bilgisi,
    seri_cek,
)


# 30.06.2026 Bilgilendirme Notu'nun ÖLÇÜLMÜŞ başlığı ve "Grup Hakkında"
# paragrafı (canlı PDF'ten birebir, 2026-09-30).
_2C26_METIN = (
    "6A 2026 Finansal ve Operasyonel Özet\nYıllık Rakamsal Yıllık Yüzdesel\n"
    "Sistem genelinde net satışlar (1) 5.035.568.954 4.944.086.800 91.482.154 %1,9\n"
    "Grup Hakkında\n2009 yılında Ankara'da kurulan Büyük Şefler; bünyesindeki BigChefs, NumNum, "
    "Buselik, NumNum Streetfood ve Kont markalarıyla; 30 Haziran 2026 tarihi itibarıyla "
    "Türkiye'de 29 şehirde 124 şube; yurt dışında 4 ülkede 4 şube olmak üzere toplam 128 şube "
    "ve kendi bünyesinde 1.501 çalışan ile hizmet vermektedir."
)


def bigch_seri(**kwargs):
    varsayilan = dict(id="restoran/bigch-sube-sayisi", bigchefs_metrik="sube-sayisi")
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


# --- _sube_bilgisi: "Şirket Profili" / "Grup Hakkında" paragrafı ---

_AYLIK_METIN = (
    "Özel Durum Açıklaması (Genel)\n2 Mart 2026\nAylık şube sayısı bildirimi - Mart 2026\n"
    "Türkiye'de 29 şehirde 125 şube, yurt dışında 10 ülkede 13 şube olmak üzere, toplam 138\n"
    "şubeye sahip olan şirketimizin, 2 Mart 2026 tarihi itibarıyla Türkiye'de faaliyet gösterdiği şehir\n"
    "sayısı 30'a yükselmiş olup; şube sayısında değişiklik olmamıştır.\n"
    "Şirket Profili\n2009 yılında Ankara'da kurulan Büyük Şefler; bünyesindeki BigChefs, Numnum ve\n"
    "Buselik markalarıyla; 2 Mart 2026 tarihi itibarıyla Türkiye'de 30 şehirde 125 şube; yurt\n"
    "dışında 10 ülkede 13 şube olmak üzere toplam 138 şube ile hizmet vermektedir."
)

_CEYREKLIK_METIN = (
    "FY 2025\nGrup Hakkında\n2009 yılında Ankara'da kurulan Büyük Şefler; bünyesindeki BigChefs, NumNum, "
    "Buselik markalarıyla; 31 Aralık 2025 tarihi itibarıyla Türkiye'de 29 şehirde 127 şube; yurt "
    "dışında 10 ülkede 13 şube olmak üzere toplam 140 şube ve kendi bünyesinde 1.545 çalışan ile "
    "hizmet vermektedir."
)


def test_sube_bilgisi_aylik_bildirimden_toplam_sehir_ulke_cikarir():
    toplam, sehir, ulke, calisan = _sube_bilgisi(_AYLIK_METIN)
    assert (toplam, sehir, ulke) == (138.0, 30.0, 10.0)
    assert calisan is None  # aylık bildirimde çalışan sayısı yok


def test_sube_bilgisi_satir_sonu_kirigina_dayanikli():
    """pdfplumber cümle içi satır sonu ekleyebiliyor (ölçüldü); \\s+ ile eşleşmeli."""
    kirilmis = _AYLIK_METIN.replace("yurt\ndışında", "yurt \n dışında")
    toplam, sehir, ulke, _ = _sube_bilgisi(kirilmis)
    assert (toplam, sehir, ulke) == (138.0, 30.0, 10.0)


def test_sube_bilgisi_ceyreklik_notta_calisan_sayisini_da_cikarir():
    toplam, sehir, ulke, calisan = _sube_bilgisi(_CEYREKLIK_METIN)
    assert (toplam, sehir, ulke, calisan) == (140.0, 29.0, 10.0, 1545.0)


def test_sube_bilgisi_eslesme_yoksa_none_doner():
    assert _sube_bilgisi("ilgisiz metin") is None


# --- _metrik_deger: "Finansal ve Operasyonel Özet" tablosu satırları ---

_OZET_TABLO = (
    "Sistem genelinde net satışlar 2.228.882.651 2.180.722.156 48.160.495 %2,2\n"
    "Net satışlar 1.170.003.689 1.103.785.758 66.217.931 %6,0\n"
    "Brüt kar marjı %15,2 %13,5\n"
    "Net kar (32.229.759) (34.956.607) 2.726.848 %7,8\n"
    "Net kar marjı (%2,8) (%3,2)\n"
)


def test_metrik_deger_ilk_sayiyi_alir_cari_donem():
    assert _metrik_deger(_OZET_TABLO, "Net satışlar") == 1170003689.0


def test_metrik_deger_yuzde_etiketini_parse_eder():
    assert _metrik_deger(_OZET_TABLO, "Brüt kar marjı") == 15.2


def test_metrik_deger_negatif_parantezi_dogru_isaretler():
    assert _metrik_deger(_OZET_TABLO, "Net kar") == -32229759.0
    assert _metrik_deger(_OZET_TABLO, "Net kar marjı") == -2.8


def test_metrik_deger_uzun_etiket_kisa_etikete_yanlislikla_eslemez():
    """'Net kar' etiketi 'Net kar marjı' satırına yanlışlıkla eşleşmemeli."""
    yalniz_marji = "Net kar marjı (%2,8) (%3,2)\n"
    assert _metrik_deger(yalniz_marji, "Net kar") is None


def test_metrik_deger_bulunamayan_etiket_none_doner():
    assert _metrik_deger(_OZET_TABLO, "Olmayan Satır") is None


# --- seri_cek: uçtan uca dispatch (ağ çağrıları monkeypatch'lenir) ---


def test_seri_cek_bilinmeyen_metrik_hata_verir():
    with pytest.raises(RuntimeError, match="Bilinmeyen bigchefs_metrik"):
        seri_cek(bigch_seri(bigchefs_metrik="olmayan-metrik"))


def test_seri_cek_aylik_metrik_belgelerden_deger_bulamazsa_patlar(monkeypatch):
    import ingest.bigchefs as bigchefs_modul

    monkeypatch.setattr(
        bigchefs_modul, "_duyuru_listesi",
        lambda session=None: [
            {"tarih": "2026-01-01", "konu": "Aylık Şube Sayısı Bildirimi", "url": "http://x/1.pdf"},
        ],
    )
    monkeypatch.setattr(
        bigchefs_modul, "_belge_metnini_getir",
        lambda url, onbellek, session=None: "ilgisiz içerik",
    )
    with pytest.raises(RuntimeError, match="değer bulunamadı"):
        seri_cek(bigch_seri(bigchefs_metrik="sube-sayisi"))


def test_seri_cek_aylik_metrik_dogru_seriyi_uretir(monkeypatch):
    import ingest.bigchefs as bigchefs_modul

    monkeypatch.setattr(
        bigchefs_modul, "_duyuru_listesi",
        lambda session=None: [
            {"tarih": "2026-03-01", "konu": "Aylık Şube Sayısı Bildirimi", "url": "http://x/mart.pdf"},
            {"tarih": "2026-02-01", "konu": "Aylık Şube Sayısı Bildirimi", "url": "http://x/subat.pdf"},
            {"tarih": None, "konu": "BuyukSefler 1C2026 Bilgilendirme Notu", "url": "http://x/not.pdf"},
        ],
    )
    icerikler = {
        "http://x/mart.pdf": _AYLIK_METIN,
        "http://x/subat.pdf": _AYLIK_METIN,
        "http://x/not.pdf": _CEYREKLIK_METIN,
    }
    monkeypatch.setattr(
        bigchefs_modul, "_belge_metnini_getir",
        lambda url, onbellek, session=None: icerikler[url],
    )
    df = seri_cek(bigch_seri(bigchefs_metrik="sehir-sayisi"))
    assert list(df["date"]) == ["2026-02-01", "2026-03-01"]
    assert list(df["value"]) == [30.0, 30.0]


def test_gecerli_metrikler_tum_dogrudan_etiketleri_kapsar():
    assert "net-kar-marji" in GECERLI_METRIKLER
    assert "fis-ortalamasi-bigchefs" in GECERLI_METRIKLER
    assert "calisan-sayisi" in GECERLI_METRIKLER


# --- /finansal-bilgiler/ sayfası: düz ikon bağlantısı + ayrı <h2> etiketi ---

# Ham sayfadan ölçülen kalıbın KÜÇÜLTÜLMÜŞ hali (2026-09-30): çeyrek
# başlığı, sonra her belge için <a class="elementor-icon" href="...pdf">
# ve BAĞLANTIDAN SONRA ayrı bir <h2> etiketi.
_FINANSAL_HTML = """
<h2 class="elementor-heading-title">2.Çeyrek</h2>
<a class="elementor-icon elementor-animation-float"
   href="https://x/wp-content/uploads/2026/07/BIGCHEFS%20Bilgilendirme%20Notu%2030.06.2026.pdf"
   target="_blank"><i class="fas fa-file-pdf"></i></a>
<h2 class="elementor-heading-title elementor-size-default">Bilgilendirme Notu</h2>
<a class="elementor-icon elementor-animation-float"
   href="https://x/wp-content/uploads/2026/08/BigChefs%202026%202Cq.pdf" target="_blank"></a>
<h2 class="elementor-heading-title elementor-size-default">Yatırımcı Sunumu</h2>
"""


def test_finansal_bilgi_ikon_baglantisini_sonraki_h2_etiketiyle_eslestirir():
    baglantilar = _finansal_bilgi_baglantilari(_FINANSAL_HTML)
    assert [b["konu"] for b in baglantilar] == ["Bilgilendirme Notu", "Yatırımcı Sunumu"]
    assert baglantilar[0]["url"].endswith("BIGCHEFS%20Bilgilendirme%20Notu%2030.06.2026.pdf")
    assert baglantilar[0]["tarih"] is None  # dönem belge içinden okunur


def test_finansal_bilgi_sayfasinda_etiketsiz_baglanti_atlanir():
    """Mobil akordiyon bloğunda başlıklar PDF'lerden ÖNCE geliyor; iki PDF
    arası etiket yoksa yalnızca sonuncusu eşleşir, diğeri düşer."""
    html = """
    <h2>3.Çeyrek</h2>
    <a class="elementor-icon" href="https://x/a.pdf"></a>
    <a class="elementor-icon" href="https://x/b.pdf"></a>
    <h2>2.Çeyrek</h2>
    """
    baglantilar = _finansal_bilgi_baglantilari(html)
    assert [(b["konu"], b["url"]) for b in baglantilar] == [("2.Çeyrek", "https://x/b.pdf")]


def test_finansal_bilgi_sayfasinda_pdf_olmayan_baglanti_etiketi_yemez():
    html = """
    <a class="elementor-menu-toggle" href="#"></a>
    <h2>Bilgilendirme Notu</h2>
    """
    assert _finansal_bilgi_baglantilari(html) == []


def test_duyuru_listesi_ucuncu_sayfayi_da_tarar():
    """2Ç 2026 notu /duyurular/ ve /yatirimci-iliskileri/'de YOK."""
    import ingest.bigchefs as bigchefs_modul

    sayfalar = {bigchefs_modul.DUYURULAR_URL: "", bigchefs_modul.YI_URL: "",
                bigchefs_modul.FINANSAL_BILGILER_URL: _FINANSAL_HTML}

    class _Yanit:
        encoding = None

        def __init__(self, metin):
            self.text = metin

        def raise_for_status(self):
            pass

    class _Http:
        def get(self, url, headers=None, timeout=None):
            return _Yanit(sayfalar[url])

    belgeler = bigchefs_modul._duyuru_listesi(session=_Http())
    not_konulu = [b for b in belgeler if "Bilgilendirme Notu" in b["konu"]]
    assert [(b["tarih"], b["url"]) for b in not_konulu] == [
        (None, "https://x/wp-content/uploads/2026/07/"
              "BIGCHEFS%20Bilgilendirme%20Notu%2030.06.2026.pdf")
    ]


def test_seri_cek_aylik_seri_ceyreklik_notla_doldurulur(monkeypatch):
    """Mart 2026'dan sonra aylık bildirim yok; 2Ç 2026 notu 2026-04-01'i besler."""
    import ingest.bigchefs as bigchefs_modul

    belgeler = [
        {"tarih": "2026-03-01", "konu": "Aylık Şube Sayısı Bildirimi", "url": "http://x/mart.pdf"},
        {"tarih": None, "konu": "Bilgilendirme Notu", "url": "http://x/not.pdf"},
    ]
    icerikler = {"http://x/mart.pdf": _AYLIK_METIN, "http://x/not.pdf": _2C26_METIN}
    monkeypatch.setattr(bigchefs_modul, "_duyuru_listesi", lambda session=None: belgeler)
    monkeypatch.setattr(bigchefs_modul, "_belge_metnini_getir",
                        lambda url, onbellek, session=None: icerikler[url])
    df = seri_cek(bigch_seri(bigchefs_metrik="sube-sayisi"))
    assert list(df["date"]) == ["2026-03-01", "2026-04-01"]
    assert list(df["value"]) == [138.0, 128.0]


def test_seri_cek_ceyreklik_not_aylik_serinin_eski_noktalarini_ezmez(monkeypatch):
    """Çeyreklik not, aylık bildirimin kendi tarihindeki değerini değiştirmez
    (kapsam farkı var: aylık 138 şube/10 ülke, çeyreklik 128 şube/4 ülke)."""
    import ingest.bigchefs as bigchefs_modul

    belgeler = [
        {"tarih": "2026-03-01", "konu": "Aylık Şube Sayısı Bildirimi", "url": "http://x/mart.pdf"},
        {"tarih": "2025-12-01", "konu": "Aylık Şube Sayısı Bildirimi", "url": "http://x/aralik.pdf"},
        {"tarih": None, "konu": "Bilgilendirme Notu", "url": "http://x/not.pdf"},
    ]
    icerikler = {"http://x/mart.pdf": _AYLIK_METIN, "http://x/aralik.pdf": _AYLIK_METIN,
                 "http://x/not.pdf": _2C26_METIN}
    monkeypatch.setattr(bigchefs_modul, "_duyuru_listesi", lambda session=None: belgeler)
    monkeypatch.setattr(bigchefs_modul, "_belge_metnini_getir",
                        lambda url, onbellek, session=None: icerikler[url])
    df = seri_cek(bigch_seri(bigchefs_metrik="ulke-sayisi"))
    assert list(df["date"]) == ["2025-12-01", "2026-03-01", "2026-04-01"]
    assert list(df["value"]) == [10.0, 10.0, 4.0]


def test_seri_cek_6a_basligi_2ci_2026_donemine_damgalar(monkeypatch):
    """2Ç 2026 notu '6A 2026 Finansal ve Operasyonel Özet' başlığıyla gelir;
    kümülatif ay eşlemesi 6A -> 2026-04-01 üretmeli."""
    import ingest.bigchefs as bigchefs_modul

    belgeler = [{"tarih": None, "konu": "Bilgilendirme Notu", "url": "http://x/not.pdf"}]
    monkeypatch.setattr(bigchefs_modul, "_duyuru_listesi", lambda session=None: belgeler)
    monkeypatch.setattr(bigchefs_modul, "_belge_metnini_getir",
                        lambda url, onbellek, session=None: _2C26_METIN)
    df = seri_cek(bigch_seri(bigchefs_metrik="calisan-sayisi"))
    assert list(df["date"]) == ["2026-04-01"]
    assert list(df["value"]) == [1501.0]


def test_donem_coz_tanimlanmayan_belgede_none_doner():
    """2023 öncesi notlar CEO mektubuyla başlıyor; dönem başlığı yok."""
    assert _donem_coz("Büyük Şefler CEO'su Altan Kosova'nın Değerlendirmesi\n") is None
    assert _donem_coz(_2C26_METIN) == "2026-04-01"


def test_seri_cek_donemsiz_belge_seriyi_dusurmez(monkeypatch):
    """`/finansal-bilgiler/` eski notları da listeliyor; dönemi çözülemeyen
    tek bir belge tüm seriyi patlatmamalı."""
    import ingest.bigchefs as bigchefs_modul

    belgeler = [
        {"tarih": None, "konu": "Bilgilendirme Notu", "url": "http://x/eski.pdf"},
        {"tarih": None, "konu": "Bilgilendirme Notu", "url": "http://x/yeni.pdf"},
    ]
    icerikler = {"http://x/eski.pdf": _2C26_METIN.replace("6A 2026", "Belirsiz"),
                 "http://x/yeni.pdf": _2C26_METIN}
    monkeypatch.setattr(bigchefs_modul, "_duyuru_listesi", lambda session=None: belgeler)
    monkeypatch.setattr(bigchefs_modul, "_belge_metnini_getir",
                        lambda url, onbellek, session=None: icerikler[url])
    df = seri_cek(bigch_seri(bigchefs_metrik="calisan-sayisi"))
    assert list(df["date"]) == ["2026-04-01"]
