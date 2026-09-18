"""ebebek Mağazacılık aylık operasyonel veri istemcisi testleri.

`duyuru_listesi` HTML ayrıştırması gerçek `yatirimci-duyurulari` sayfa
parçacığıyla test edilir. PDF indirme + metin çıkarma adımı (`_pdf_metni`)
monkeypatch'lenip ayrıştırıcılara (satış/ziyaret/mağaza) 2026-09-18'de CANLI
ölçülmüş gerçek KAP bildirim metinleri (kısaltılmış) beslenir — ağa ya da
pdfplumber'a girmeden regex davranışını, önbellek paylaşımını ve bilinen
kaynak anomalisini (Nisan 2025 Ziyaretçi Sayısı — başlıkla uyuşmayan içerik)
pinler.
"""

from types import SimpleNamespace

import pytest

import ingest.ebebek as ebebek
from ingest.ebebek import magaza_noktalari, satis_noktalari, seri_cek, ziyaret_noktalari

# --- Gerçek belgelerden alınmış (2026-09-18 ölçümü), kısaltılmış metinler ---

_SATIS_AGUSTOS_2026 = (
    "KAP'ta yayınlanma tarihi ve saati: 07.09.2026 21:06:23 "
    "EBEBEK MAĞAZACILIK A.Ş. Özel Durum Açıklaması (Genel) Özet Bilgi "
    "Ağustos 2026 Satış Adetleri Bildirim İçeriği Açıklamalar "
    "Ağustos 2026'da Türkiye'de ebebek mağazaları ve e-ticaret kanalından "
    "satılan toplam ürün adedi 10.737.113 olarak gerçekleşmişken, bu sayı "
    "Ağustos 2025'te 8.676.273'tür. Ağustos 2026'da sona eren 8 aylık "
    "dönemde Türkiye'de ebebek mağazaları ve e-ticaret kanalından satılan "
    "toplam ürün adedi 82.546.307 olarak gerçekleşmişken, bu sayı 2025'in "
    "aynı döneminde 67.876.582'dir."
)

_SATIS_EBEBEK_ONEKLI_AGUSTOS_2024 = (
    "Özel Durum Açıklaması 6 Eylül 2024 Ağustos 2024 Satış Adetleri "
    "Ağustos 2024’te Türkiye’de ebebek mağazaları ve e-ticaret kanalından "
    "satılan toplam ürün adedi 7.445.297 olarak gerçekleşmişken, bu sayı "
    "Ağustos 2023’te 6.642.939’dur."
)

_ZIYARET_AGUSTOS_2026 = (
    "KAP'ta yayınlanma tarihi ve saati: 03.09.2026 18:34:41 "
    "EBEBEK MAĞAZACILIK A.Ş. Özel Durum Açıklaması (Genel) Özet Bilgi "
    "Ağustos 2026 Ziyaretçi Sayısı Bildirim İçeriği Açıklamalar "
    "Ağustos 2026'da Türkiye'deki ebebek mağazalarını ziyaret eden "
    "ziyaretçi sayısı 4.992.875 olarak gerçekleşmiş olup bu sayı Ağustos "
    "2025'te 4.586.675'tir. Ağustos 2026'da sona eren 8 aylık dönemde "
    "Türkiye'deki ebebek mağazalarını ziyaret eden ziyaretçi sayısı "
    "39.132.243, 2025 yılının aynı döneminde ise 35.111.762 olarak "
    "gerçekleşmiştir. Ağustos 2026'da ebebek.com internet sitesi ziyaret "
    "sayısı 10.978.359 olarak gerçekleşmiş olup bu sayı Ağustos 2025'te "
    "10.451.442'dir. Ağustos 2026'da sona eren 8 aylık dönemde ebebek.com "
    "internet sitesini ziyaret eden ziyaretçi sayısı 96.122.744, 2025 "
    "yılının aynı döneminde ise 91.724.081 olarak gerçekleşmiştir."
)

# Bilinen kaynak anomalisi: bu belge "Nisan 2025 Ziyaretçi Sayıları" başlığı
# altında listelenir ama içeriği aslında Mağaza Sayısı metnidir (ebebek IR
# sitesinin kendi dosya eşleme hatası) — ziyaretçi kalıpları hiç geçmez.
_NISAN_2025_YANLIS_ESLESEN_ICERIK = (
    "Özel Durum Açıklaması 2 Mayıs 2025 Nisan 2025 Mağaza Sayısı "
    "31 Mart 2025 tarihi itibarıyla 260 tanesi geleneksel, 13 tanesi ise "
    "mini mağaza konseptinde olmak üzere Türkiye’de toplam 273 mağazaya "
    "sahip olan şirketimizin mağaza sayısı 30 Nisan 2025 tarihi itibarıyla "
    "261 tanesi geleneksel, 15 tanesi mini olmak üzere 276’a ulaşmıştır."
)

_MAGAZA_EKIM_2023_ESKI_SABLON = (
    "Özel Durum Açıklaması 1 Kasım 2023 Ekim 2023 Mağaza Sayısı "
    "30 Eylül 2023 tarihi itibarıyla 220 tanesi geleneksel, 4 tanesi ise "
    "mini mağaza konseptinde olmak üzere Türkiye’de toplam 224 mağazaya "
    "sahip olan şirketimizin mağaza sayısı 31 Ekim 2023 tarihi itibarıyla "
    "221 tanesi geleneksel, 4 tanesi mini olmak üzere 225’e ulaşmıştır. "
    "30 Eylül - 31 Ekim 2023 tarihleri arasında; 1 Iğdır’da, 1 Manisa’da "
    "olmak üzere toplam 2 mağaza açılmıştır ve 1 mağaza Ayvalık’ta "
    "kapanmıştır."
)

# Değişmeyen ay: "X'e ulaşmıştır" yerine "olarak devam etmektedir" kalıbı.
_MAGAZA_DEGISMEYEN_ESKI_SABLON = (
    "Özel Durum Açıklaması 1 Haziran 2024 Mayıs 2024 Mağaza Sayısı "
    "30 Nisan 2024 tarihi itibarıyla 240 tanesi geleneksel, 7 tanesi ise "
    "mini mağaza konseptinde olmak üzere Türkiye’de toplam 247 mağazaya "
    "sahip olan şirketimizin mağaza sayısı 31 Mayıs 2024 tarihi itibarıyla "
    "240 tanesi geleneksel, 7 tanesi mini olmak üzere 247 olarak devam "
    "etmektedir."
)

_MAGAZA_AGUSTOS_2026_YENI_SABLON = (
    "KAP'ta yayınlanma tarihi ve saati: 01.09.2026 21:37:09 "
    "EBEBEK MAĞAZACILIK A.Ş. Özel Durum Açıklaması (Genel) Özet Bilgi "
    "Ağustos 2026 Mağaza Sayısı Bildirim İçeriği Açıklamalar "
    "Şirketimiz, Ağustos 2026 döneminde Zonguldak'ta açtığı 1 yeni mağaza "
    "ve Mersin'de kapattığı 1 mağazayla birlikte Türkiye'deki mağaza "
    "sayısını 316'da sabit tutmuştur. 31 Ağustos 2026 itibarıyla toplam "
    "mağaza durumumuz aşağıdaki gibidir: - Türkiye (316 Mağaza): 2 mega, "
    "282 standart, 32 mini - Yurt Dışı (4 Mağaza): 3 Birleşik Krallık, "
    "1 Kuzey Irak"
)


def ebebek_seri(**kwargs):
    varsayilan = dict(
        id="perakende/ebebek-satis-adedi",
        kaynak_tipi="ebebek",
        ebebek_metrik="satis_adedi",
        start_date=None,
    )
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


class SahteYanit:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class SahteOturum:
    def __init__(self, yanit):
        self.yanit = yanit
        self.cagrilar = 0

    def get(self, url, **kwargs):
        self.cagrilar += 1
        return self.yanit


def _duyuru_sayfasi(kayitlar, yabanci_grup_da_ekle=True):
    """`kayitlar`: [(başlık, url)] -> yatirimci-duyurulari sayfa parçacığı."""
    bloklar = [
        f'<div data-gtm-doc="{baslik}" data-gtm-doc-group="Özel Durum '
        f'Açıklamaları"><a href="{url}" target="_blank">indir</a></div>'
        for baslik, url in kayitlar
    ]
    if yabanci_grup_da_ekle:
        # Başka bir grup (Finansal Tablolar) — filtre bunu ASLA almamalı.
        bloklar.append(
            '<div data-gtm-doc="Esas Sözleşme" data-gtm-doc-group='
            '"Finansal Tablolar"><a href="https://kurumsal.ebebek.com/'
            'download?path=sozlesme.pdf">indir</a></div>'
        )
    return "<html><body>" + "".join(bloklar) + "</body></html>"


# --- duyuru_listesi: HTML ayrıştırma ---


def test_duyuru_listesi_yalniz_ozel_durum_grubunu_alir():
    kayitlar = [
        ("Ağustos 2026 Satış Adetleri", "https://kurumsal.ebebek.com/download?path=a.pdf"),
        ("Ağustos 2026 Mağaza Sayısı", "https://kurumsal.ebebek.com/download?path=b.pdf"),
    ]
    oturum = SahteOturum(SahteYanit(text=_duyuru_sayfasi(kayitlar)))
    sonuc = ebebek.duyuru_listesi(session=oturum)
    assert sonuc == kayitlar
    assert oturum.cagrilar == 1


def test_duyuru_listesi_http_hatasi_yukselir():
    oturum = SahteOturum(SahteYanit(status_code=500, text=""))
    with pytest.raises(RuntimeError, match="HTTP 500"):
        ebebek.duyuru_listesi(session=oturum)


def test_duyuru_listesi_hic_kayit_yoksa_hata():
    oturum = SahteOturum(SahteYanit(text=_duyuru_sayfasi([], yabanci_grup_da_ekle=False)))
    with pytest.raises(RuntimeError, match="Özel Durum Açıklamaları"):
        ebebek.duyuru_listesi(session=oturum)


# --- satis_noktalari ---


def test_satis_noktalari_gercek_deger_dondurur(monkeypatch):
    """Ağustos 2026 Satış Adedi — CANLI ölçülen referans kart değeriyle birebir."""
    kayitlar = [("Ağustos 2026 Satış Adetleri", "https://x/a.pdf")]
    monkeypatch.setattr(ebebek, "duyuru_listesi", lambda session=None: kayitlar)
    monkeypatch.setattr(ebebek, "_pdf_metni", lambda url, session=None: _SATIS_AGUSTOS_2026)

    noktalar = satis_noktalari()
    assert noktalar == {"2026-08-01": 10_737_113}


def test_satis_noktalari_ebebek_onekli_baslik_taninir(monkeypatch):
    kayitlar = [("ebebek Ağustos 2024 Satış Adetleri", "https://x/a.pdf")]
    monkeypatch.setattr(ebebek, "duyuru_listesi", lambda session=None: kayitlar)
    monkeypatch.setattr(
        ebebek, "_pdf_metni", lambda url, session=None: _SATIS_EBEBEK_ONEKLI_AGUSTOS_2024
    )

    noktalar = satis_noktalari()
    assert noktalar == {"2024-08-01": 7_445_297}


def test_satis_noktalari_deger_ayiklanamazsa_hata(monkeypatch):
    kayitlar = [("Ocak 2024 Satış Adetleri", "https://x/a.pdf")]
    monkeypatch.setattr(ebebek, "duyuru_listesi", lambda session=None: kayitlar)
    monkeypatch.setattr(ebebek, "_pdf_metni", lambda url, session=None: "alakasız içerik")

    with pytest.raises(RuntimeError, match="ayıklanamadı"):
        satis_noktalari()


def test_satis_noktalari_celisen_yinelenen_anahtarda_hata(monkeypatch):
    kayitlar = [
        ("Ağustos 2026 Satış Adetleri", "https://x/a.pdf"),
        ("Ağustos 2026 Satış Adedi", "https://x/b.pdf"),
    ]
    metinler = {
        "https://x/a.pdf": _SATIS_AGUSTOS_2026,
        "https://x/b.pdf": _SATIS_AGUSTOS_2026.replace("10.737.113", "1.234.567"),
    }
    monkeypatch.setattr(ebebek, "duyuru_listesi", lambda session=None: kayitlar)
    monkeypatch.setattr(ebebek, "_pdf_metni", lambda url, session=None: metinler[url])

    with pytest.raises(RuntimeError, match="çelişen"):
        satis_noktalari()


def test_satis_noktalari_ayni_degerli_yinelenen_sessizce_tekillesir(monkeypatch):
    """ebebek IR sitesinde bazı aylar aynı kategoriyi iki kez listeler
    (ör. gerçek 'Aralık 2024 Mağaza Sayısı' — bkz. modül docstring'i);
    değerler eşitse hata değil, tekil kayıt üretilmeli."""
    kayitlar = [
        ("Ağustos 2026 Satış Adetleri", "https://x/a.pdf"),
        ("Ağustos 2026 Satış Adedi", "https://x/b.pdf"),
    ]
    monkeypatch.setattr(ebebek, "duyuru_listesi", lambda session=None: kayitlar)
    monkeypatch.setattr(ebebek, "_pdf_metni", lambda url, session=None: _SATIS_AGUSTOS_2026)

    noktalar = satis_noktalari()
    assert noktalar == {"2026-08-01": 10_737_113}


# --- ziyaret_noktalari ---


def test_ziyaret_noktalari_iki_degeri_ayirir(monkeypatch):
    """Mağaza ziyaretçi ve web ziyaret — CANLI ölçülen referans değerlerle birebir."""
    kayitlar = [("Ağustos 2026 Ziyaretçi Sayısı", "https://x/a.pdf")]
    monkeypatch.setattr(ebebek, "duyuru_listesi", lambda session=None: kayitlar)
    monkeypatch.setattr(ebebek, "_pdf_metni", lambda url, session=None: _ZIYARET_AGUSTOS_2026)

    noktalar = ziyaret_noktalari()
    assert noktalar == {"2026-08-01": (4_992_875, 10_978_359)}


def test_ziyaret_noktalari_baslikla_uyusmayan_icerikte_hata(monkeypatch):
    """Regresyon: gerçek ebebek IR sitesinde 'Nisan 2025 Ziyaretçi
    Sayıları' başlıklı duyurunun PDF'i yanlışlıkla Mağaza Sayısı içeriği
    taşıyor — sessizce atlanmamalı, RuntimeError vermeli."""
    kayitlar = [("Nisan 2025 Ziyaretçi Sayıları", "https://x/a.pdf")]
    monkeypatch.setattr(ebebek, "duyuru_listesi", lambda session=None: kayitlar)
    monkeypatch.setattr(
        ebebek, "_pdf_metni", lambda url, session=None: _NISAN_2025_YANLIS_ESLESEN_ICERIK
    )

    with pytest.raises(RuntimeError, match="ayıklanamadı"):
        ziyaret_noktalari()


# --- magaza_noktalari ---


def test_magaza_noktalari_eski_sablon_geleneksel_mini(monkeypatch):
    kayitlar = [("Ekim 2023 Mağaza Sayısı", "https://x/a.pdf")]
    monkeypatch.setattr(ebebek, "duyuru_listesi", lambda session=None: kayitlar)
    monkeypatch.setattr(
        ebebek, "_pdf_metni", lambda url, session=None: _MAGAZA_EKIM_2023_ESKI_SABLON
    )

    noktalar = magaza_noktalari()
    assert noktalar == {"2023-10-01": {"toplam": 225, "standart": 221, "mini": 4}}
    assert "mega" not in noktalar["2023-10-01"]


def test_magaza_noktalari_eski_sablon_degismeyen_ay(monkeypatch):
    """'...ulaşmıştır' yerine '...olarak devam etmektedir' kalıbı (sayı
    değişmediğinde) da tanınmalı."""
    kayitlar = [("Mayıs 2024 Mağaza Sayısı", "https://x/a.pdf")]
    monkeypatch.setattr(ebebek, "duyuru_listesi", lambda session=None: kayitlar)
    monkeypatch.setattr(
        ebebek, "_pdf_metni", lambda url, session=None: _MAGAZA_DEGISMEYEN_ESKI_SABLON
    )

    noktalar = magaza_noktalari()
    assert noktalar == {"2024-05-01": {"toplam": 247, "standart": 240, "mini": 7}}


def test_magaza_noktalari_yeni_sablon_mega_kirilimi(monkeypatch):
    """Ağustos 2026'dan itibaren KAP bildirimi mega/standart/mini
    kırılımını farklı bir cümle kalıbıyla verir — CANLI ölçülen referans
    kart değerleriyle birebir."""
    kayitlar = [("Ağustos 2026 Mağaza Sayısı", "https://x/a.pdf")]
    monkeypatch.setattr(ebebek, "duyuru_listesi", lambda session=None: kayitlar)
    monkeypatch.setattr(
        ebebek, "_pdf_metni", lambda url, session=None: _MAGAZA_AGUSTOS_2026_YENI_SABLON
    )

    noktalar = magaza_noktalari()
    assert noktalar == {"2026-08-01": {"toplam": 316, "standart": 282, "mini": 32, "mega": 2}}


def test_magaza_noktalari_sablonsuz_metinde_hata(monkeypatch):
    kayitlar = [("Ocak 2024 Mağaza Sayısı", "https://x/a.pdf")]
    monkeypatch.setattr(ebebek, "duyuru_listesi", lambda session=None: kayitlar)
    monkeypatch.setattr(ebebek, "_pdf_metni", lambda url, session=None: "alakasız içerik")

    with pytest.raises(RuntimeError, match="ayıklanamadı"):
        magaza_noktalari()


# --- seri_cek: ağ kabuğu, önbellek, start_date ---


def test_seri_cek_satis_adedi_dogru_deger_dondurur(monkeypatch):
    kayitlar = [("Ağustos 2026 Satış Adetleri", "https://x/a.pdf")]
    monkeypatch.setattr(ebebek, "duyuru_listesi", lambda session=None: kayitlar)
    monkeypatch.setattr(ebebek, "_pdf_metni", lambda url, session=None: _SATIS_AGUSTOS_2026)

    df = seri_cek(ebebek_seri(), onbellek={})
    assert list(df["date"]) == ["2026-08-01"]
    assert df["value"].iloc[0] == 10_737_113


def test_seri_cek_ziyaret_onbellegi_iki_seri_arasinda_paylasilir(monkeypatch):
    """`magaza_ziyaretci` ve `web_ziyaret` aynı PDF kategorisini okur;
    önbellek paylaşılmazsa aynı ~35 belge iki kez indirilirdi."""
    cagri_sayaci = {"n": 0}

    def sahte_duyuru_listesi(session=None):
        cagri_sayaci["n"] += 1
        return [("Ağustos 2026 Ziyaretçi Sayısı", "https://x/a.pdf")]

    monkeypatch.setattr(ebebek, "duyuru_listesi", sahte_duyuru_listesi)
    monkeypatch.setattr(ebebek, "_pdf_metni", lambda url, session=None: _ZIYARET_AGUSTOS_2026)

    onbellek: dict = {}
    df1 = seri_cek(ebebek_seri(ebebek_metrik="magaza_ziyaretci"), onbellek=onbellek)
    df2 = seri_cek(ebebek_seri(ebebek_metrik="web_ziyaret"), onbellek=onbellek)

    assert cagri_sayaci["n"] == 1
    assert df1["value"].iloc[0] == 4_992_875
    assert df2["value"].iloc[0] == 10_978_359


def test_seri_cek_mega_magaza_sadece_yeni_sablon_aylarini_icerir(monkeypatch):
    """Eski şablon aylarında 'mega' kavramı yok; `mega_magaza` serisi bu
    ayları sessizce atlar (uydurma 0 değeri YASAK), yalnızca yeni şablonun
    kapsadığı ayları döner."""
    kayitlar = [
        ("Ekim 2023 Mağaza Sayısı", "https://x/eski.pdf"),
        ("Ağustos 2026 Mağaza Sayısı", "https://x/yeni.pdf"),
    ]
    metinler = {
        "https://x/eski.pdf": _MAGAZA_EKIM_2023_ESKI_SABLON,
        "https://x/yeni.pdf": _MAGAZA_AGUSTOS_2026_YENI_SABLON,
    }
    monkeypatch.setattr(ebebek, "duyuru_listesi", lambda session=None: kayitlar)
    monkeypatch.setattr(ebebek, "_pdf_metni", lambda url, session=None: metinler[url])

    df = seri_cek(ebebek_seri(ebebek_metrik="mega_magaza", start_date="2026-08-01"), onbellek={})
    assert list(df["date"]) == ["2026-08-01"]
    assert df["value"].iloc[0] == 2

    df_toplam = seri_cek(ebebek_seri(ebebek_metrik="toplam_magaza"), onbellek={})
    assert list(df_toplam["date"]) == ["2023-10-01", "2026-08-01"]


def test_seri_cek_start_date_oncesini_kirpar(monkeypatch):
    kayitlar = [
        ("Ekim 2023 Mağaza Sayısı", "https://x/eski.pdf"),
        ("Ağustos 2026 Mağaza Sayısı", "https://x/yeni.pdf"),
    ]
    metinler = {
        "https://x/eski.pdf": _MAGAZA_EKIM_2023_ESKI_SABLON,
        "https://x/yeni.pdf": _MAGAZA_AGUSTOS_2026_YENI_SABLON,
    }
    monkeypatch.setattr(ebebek, "duyuru_listesi", lambda session=None: kayitlar)
    monkeypatch.setattr(ebebek, "_pdf_metni", lambda url, session=None: metinler[url])

    df = seri_cek(
        ebebek_seri(ebebek_metrik="toplam_magaza", start_date="2025-01-01"), onbellek={}
    )
    assert list(df["date"]) == ["2026-08-01"]


def test_seri_cek_bilinmeyen_metrikte_hata():
    with pytest.raises(RuntimeError, match="bilinmeyen ebebek_metrik"):
        seri_cek(ebebek_seri(ebebek_metrik="uydurma"), onbellek={})
