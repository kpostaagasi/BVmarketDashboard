"""TAB Gıda çeyreklik "Finansal Bülten" PDF ayrıştırma testleri.

Şebeke bağımlılığı yok. Canlı ölçüm 30 Eylül 2026: WAF sorunu
`_WafAdapter` ile çözüldü (docstring), 12 bültenin 12'si de okundu — bu
testler yalnızca ayrıştırma mantığını kanıtlar, HTML örnekleri canlı
sayfadan birebir alınmış satırlardır."""

from types import SimpleNamespace

import pytest
import requests

from ingest.tabgida import (
    GECERLI_METRIKLER,
    _bulten_listesi,
    fis_sayisini_ayikla,
    restoran_sayisini_ayikla,
    seri_cek,
)


def tabgd_seri(**kwargs):
    varsayilan = dict(id="restoran/tabgd-restoran-sayisi", tabgida_metrik="restoran-sayisi")
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


class _Yanit:
    """`_bulten_listesi` yalnızca `.text` ve `.raise_for_status()` kullanıyor."""

    def __init__(self, metin, kod=200):
        self.text = metin
        self.status_code = kod

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(f"HTTP {self.status_code}")


class _SahteOturum(requests.Session):
    """Gerçek `requests.Session` — `_oturum` bu sınıfa `mount` uyguluyor."""

    def __init__(self, sayfa):
        super().__init__()
        self._sayfa = sayfa
        self.istenen: list[str] = []

    def get(self, url, headers=None, timeout=None, **kwargs):
        self.istenen.append(url)
        return _Yanit(self._sayfa)


def test_restoran_sayisini_ayikla_toplam_ulastirdik_kalibi():
    metin = "30 Haziran 2026 itibarıyla toplam restoran sayımızı 2.100'e ulaştırdık."
    assert restoran_sayisini_ayikla(metin) == 2100.0


def test_restoran_sayisini_ayikla_yili_kapatti_kalibi():
    """FY bültenlerinde farklı ifade biçimi: 'yılı N lokasyonla kapattık'."""
    metin = "restoran sayımızda 2.000'i aştık ve yılı 2.030 lokasyonla kapattık."
    assert restoran_sayisini_ayikla(metin) == 2030.0


def test_restoran_sayisini_ayikla_satir_ortasinda_bolunen_cumle():
    """2Ç 2026 PDF'inde cümle satır ortasında bölünüyor (canlı ölçüm)."""
    metin = (
        "30 Haziran 2026 itibarıyla toplam restoran sayımızı 2.100'e\n"
        "ulaştırdık. Bu çeyrekte açılan restoranların yarısı franchise.\n"
    )
    assert restoran_sayisini_ayikla(metin) == 2100.0


def test_restoran_sayisini_ayikla_lokasyona_ulaştik_kalibi():
    """4Ç 2024 canlı metni: 'Açtığımız 246 yeni restoranla toplamda 1.830\nlokasyona ulaştık.'"""
    metin = "Açtığımız 246 yeni restoranla toplamda 1.830\nlokasyona ulaştık.\n"
    assert restoran_sayisini_ayikla(metin) == 1830.0


def test_restoran_sayisini_ayikla_portfoy_kalibi():
    """1Ç 2025 canlı metni: 'restoran portföyümüz 1.854 lokasyona ulaştı'."""
    metin = "Çeyrek sonu itibariyle restoran portföyümüz 1.854 lokasyona ulaştı ve franchise.\n"
    assert restoran_sayisini_ayikla(metin) == 1854.0


def test_restoran_sayisini_ayikla_ye_soneki_ve_toplamsiz_kalip():
    """3Ç 2023 canlı metni: "toplam restoran sayımızı 1.572'ye çıkardık" —
    ek `y` içeren sonek. 1Ç 2024'te "toplam" kelimesi YOK:
    "restoran sayımızı 1.654'e çıkardık"."""
    assert restoran_sayisini_ayikla(
        "3Ç 2023'te net 38 restoran açarak toplam restoran sayımızı 1.572'ye çıkardık.\n"
    ) == 1572.0
    assert restoran_sayisini_ayikla(
        "3Ç 2024'te 61 yeni restoran açarak restoran sayımızı 1.654'e çıkardık.\n"
    ) == 1654.0


def test_restoran_sayisini_ayikla_yalnizca_yeni_acilan_sayi_eslesmez():
    """3Ç 2024/1Ç 2026 yalnızca 'N yeni restoran açtık' diyor; çeyreklik
    toplam bildirmediği için seri o dönem boş kalmalı (sessiz 0 üretmemek)."""
    metin = "3. çeyrekte 76 yeni restoran açtık.\n"
    assert restoran_sayisini_ayikla(metin) is None


def test_restoran_sayisini_ayikla_eslesme_yoksa_none():
    assert restoran_sayisini_ayikla("ilgisiz içerik") is None


def test_fis_sayisini_ayikla_ikinci_sayiyi_alir_cari_donem():
    """TAB Gıda tablo sırası BigChefs'in TERSİ: önceki yıl önce, cari sonra."""
    metin = "Fiş sayısı ('000) 207.648 247.196 %19,0 207.648 247.196 %19,0\n"
    assert fis_sayisini_ayikla(metin) == 247196.0


def test_fis_sayisini_ayikla_4c_fy_tablosunda_fy_degerini_alir():
    """4Ç 2023 canlı satırı: ikinci alan 4Ç 2023 (47.081), FY 2023 BEŞİNCİ
    alanda (203.718). İkinciyi almak yıl değil çeyrek fiş sayısı üretirdi."""
    metin = "Fiş sayısı ('000) 47.287 47.081 %0 183.140 203.718 %11\n"
    assert fis_sayisini_ayikla(metin) == 203718.0


def test_fis_sayisini_ayikla_ingilizce_satir_etiketini_kabul_eder():
    """4Ç 2024 tek çeyrekte İngilizce yayımlandı: 'Number of tickets'."""
    metin = "Number of tickets ('000) 47.081 51.309 %9 203.718 207.648 %2\n"
    assert fis_sayisini_ayikla(metin) == 207648.0


def test_fis_sayisini_ayikla_yalniz_fy_ozeti_tablosu():
    """Yalnızca FY özeti olan tabloda (3Ç 2023, 4. satır) ikinci alan zaten FY."""
    metin = "(Milyon TL) FY 2022 FY 2023 Yıllık değişim\nFiş sayısı 183.140 203.718 %11\n"
    assert fis_sayisini_ayikla(metin) == 203718.0


def test_fis_sayisini_ayikla_bin_adet_olceginde_kalir():
    """Değer zaten bin adet cinsinden — ayrıca 1000 ile çarpılmamalı."""
    metin = "Fiş sayısı ('000) 100.000 150.000 %50,0 100.000 150.000 %50,0\n"
    assert fis_sayisini_ayikla(metin) == 150000.0  # 150 milyon fiş değil


def test_fis_sayisini_ayikla_anlatim_cumlesi_eslesmez():
    """4Ç 2024'te anlatım cümlesi var ('Fiş sayısı 51,3 milyona ulaşarak') —
    tablo satırı olmadığı için eşleşmemeli."""
    metin = "Fiş sayısı 4Ç 2024'te yıllık bazda %9 artışla 51,3 milyona ulaşarak.\n"
    assert fis_sayisini_ayikla(metin) is None


def _sayfa(*satirlar: str) -> str:
    govde = "".join(
        f'<tr><td>{c}. Çeyrek</td><td><a href="sunum-{c}.pdf">İncele</a></td>'
        f'<td><a href="{h}">İncele</a></td></tr>'
        for c, h in satirlar
    )
    return f"<thead><tr><th>2026</th></tr></thead><tbody>{govde}</tbody>"


def test_bulten_listesi_bozuk_href_i_temizler():
    """2024/4.Çeyrek canlı HTML'de `href="<../cmsfiles/..."` — baştaki `<`
    fazlalık. Ayırıcı temizlenmeli, bağlantı atlanmamalı."""
    oturum = _SahteOturum(_sayfa(("4", "<../cmsfiles/yatirimci-iliskileri/fy.pdf")))
    liste = _bulten_listesi(session=oturum)
    assert [b["url"] for b in liste] == [
        "https://www.tabgida.com.tr/cmsfiles/yatirimci-iliskileri/fy.pdf"
    ]


def test_fis_sayisini_ayikla_yalniz_fy_ozeti_tablosu():
    """4Ç 2023'ün ikinci tablosunda satır etiketi 'Fiş sayısı ('000)' ve
    yalnızca iki değer var (FY 2022 / FY 2023) → ikincisi zaten FY."""
    metin = "(Milyon TL) FY 2022 FY 2023 Yıllık değişim\nFiş sayısı ('000) 183.140 203.718 %11\n"
    assert fis_sayisini_ayikla(metin) == 203718.0



def test_bulten_listesi_onuclsuz_href_i_atlar_sağlamlari_oku():
    """Onarılamayan bağlantı ayrıştırıcıyı düşürmez, atlanır; sağlam
    bültenler yine okunur."""
    oturum = _SahteOturum(
        _sayfa(
            ("1", "cmsfiles/<bozuk.pdf"),
            ("2", "../cmsfiles/saglam.pdf"),
            ("3", " "),
        )
    )
    liste = _bulten_listesi(session=oturum)
    assert [b["ceyrek"] for b in liste] == [2]
    assert liste[0]["url"] == "https://www.tabgida.com.tr/cmsfiles/saglam.pdf"


def test_bulten_listesi_bos_sayfada_hata_verir():
    oturum = _SahteOturum("<html>şablon değişti</html>")
    with pytest.raises(RuntimeError, match="hiç 'Finansal Bülten' bağlantısı"):
        _bulten_listesi(session=oturum)


def test_seri_cek_bilinmeyen_metrik_hata_verir():
    with pytest.raises(RuntimeError, match="Bilinmeyen tabgida_metrik"):
        seri_cek(tabgd_seri(tabgida_metrik="olmayan"))


def test_seri_cek_fis_sayisi_yalniz_4_ceyrek_bultenlerini_kullanir(monkeypatch):
    import ingest.tabgida as tabgida_modul

    monkeypatch.setattr(
        tabgida_modul, "_bulten_listesi",
        lambda session=None: [
            {"yil": 2025, "ceyrek": 4, "url": "http://x/fy.pdf"},
            {"yil": 2025, "ceyrek": 2, "url": "http://x/2c.pdf"},
        ],
    )
    icerikler = {"http://x/fy.pdf": "Fiş sayısı ('000) 207.648 247.196 %19,0 207.648 247.196 %19,0\n"}
    monkeypatch.setattr(
        tabgida_modul, "_belge_metnini_getir",
        lambda url, onbellek, session=None: icerikler[url],
    )
    df = seri_cek(tabgd_seri(tabgida_metrik="fis-sayisi"))
    assert list(df["date"]) == ["2025-10-01"]
    assert list(df["value"]) == [247196.0]


def test_seri_cek_bozuk_bulteni_atlar_sağlam_bultenleri_kaydeder(monkeypatch):
    """TEK erişilemeyen bülten tüm seriyi düşürmemeli — `_belge_metnini_getir`
    404/ana sayfaya yönlenen 200'de `None` döner, döngü atlar."""
    import ingest.tabgida as tabgida_modul

    monkeypatch.setattr(
        tabgida_modul, "_bulten_listesi",
        lambda session=None: [
            {"yil": 2024, "ceyrek": 1, "url": "http://x/bozuk.pdf"},
            {"yil": 2025, "ceyrek": 1, "url": "http://x/saglam.pdf"},
        ],
    )
    icerikler = {"http://x/bozuk.pdf": None,
                 "http://x/saglam.pdf":
                     "Çeyrek sonu itibariyle restoran portföyümüz 1.854 lokasyona ulaştı.\n"}
    monkeypatch.setattr(
        tabgida_modul, "_belge_metnini_getir",
        lambda url, onbellek, session=None: icerikler[url],
    )
    df = seri_cek(tabgd_seri())
    assert list(df["date"]) == ["2025-01-01"]
    assert list(df["value"]) == [1854.0]


def test_belge_metnini_getir_pdf_imzasi_olmayan_yaniti_reddeder():
    """CMS yolu tutmazsa sunucu 200 döndürüp ana sayfaya YÖNLENDİRİR
    (canlı ölçüm: 36.378 bayt `text/html`); bu PDF değildir, `None` döner."""
    import ingest.tabgida as tabgida_modul

    class _Html200:
        status_code = 200
        content = b"<!doctype html><html><title>TAB Gida</title>"

    oturum = _SahteOturum("")
    oturum.get = lambda url, headers=None, timeout=None: _Html200()
    assert tabgida_modul._belge_metnini_getir("http://x/a.pdf", {}, session=oturum) is None


def test_oturum_paylasilan_oturuma_waf_adaptorunu_takar():
    """`ingest.run` paylaşılan `requests.Session` verir; onun `https://`
    bağdaştırıcısı varsayılan şifre listesiyle WAF'a takılır. Bu kaynak
    için sunucu önekli bağdaştırıcı değiştirilir, diğer kaynaklar etkilenmez."""
    from ingest.tabgida import _WafAdapter, _oturum

    oturum = requests.Session()
    diger = oturum.get_adapter("https://ornek.gov.tr")
    assert _oturum(oturum) is oturum
    assert isinstance(oturum.get_adapter("https://www.tabgida.com.tr/x"), _WafAdapter)
    assert oturum.get_adapter("https://ornek.gov.tr") is diger


def test_belge_metnini_getir_baglanti_hatasinda_seriyi_dusurmez():
    import ingest.tabgida as tabgida_modul

    class _Hata(_SahteOturum):
        def get(self, url, headers=None, timeout=None, **kwargs):
            raise requests.ConnectionError("WAF el sıfırladı")

    assert tabgida_modul._belge_metnini_getir("http://x/a.pdf", {}, session=_Hata("")) is None


def test_gecerli_metrikler_iki_seriyi_kapsar():
    assert GECERLI_METRIKLER == {"restoran-sayisi", "fis-sayisi"}
