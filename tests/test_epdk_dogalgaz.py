"""EPDK Doğal Gaz Piyasası aylık sektör raporu istemcisi testleri.

Gerçek kaynaktan (Ocak/Mart/Temmuz 2026 EK dosyaları) canlı ölçülen üç şablon
tuhaflığı ayrı ayrı pinlenir: liste sayfasının başlık deseninin petrolden
FARKLI olması (yıl sonda, tek şirket adı), Tablo-6'nın satır etiketinin
Haziran 2026'da "DPF-34 - " önekiyle gelmesi, ve Tablo-8/Tablo-12'de bir
şirketin birden fazla il/lisans satırına bölünüp TOPLANMASI gerekmesi
(AHGAZ grubu 11 şirket, NATURELGAZ iki lisans satırı). Temmuz 2026 canlı
değerleriyle (BOTAŞ 3,06 milyar Sm³, AHGAZ tüketim 97,06 milyon Sm³, toplam
abone 2.174.051, serbest tüketici 79.304, NTGAZ 14,87 milyon Sm³, AYGAZ 8,65
milyon Sm³, depolama boru gazı 5,41 milyar Sm³, LNG 0,22 milyar Sm³)
MarketVisuals'ın epdk_dogalgaz_verileri.html kartlarıyla BİREBİR eşleşti.
"""

from types import SimpleNamespace

import pytest
from ingest.epdk import (
    AYGAZ_SIRKET_ADI,
    BOTAS_SIRKET_ADI,
    ILK_AY,
    ILK_YIL,
    NTGAZ_SIRKET_ADI,
    _dogalgaz_alt_tablo_bul,
    cekilecek_dosyalar,
    dogalgaz_abone_cek,
    dogalgaz_depolama_cek,
    dogalgaz_dosyalari_ayikla,
    dogalgaz_ithalat_cek,
    dogalgaz_seri_cek,
    dogalgaz_sirket_tuketim_cek,
)


def dogalgaz_seri(**kwargs):
    varsayilan = dict(
        id="dogalgaz/ahgaz-tuketim",
        kaynak_tipi="epdk_dogalgaz",
        epdk_dogalgaz_olcut="ahgaz-tuketim",
        start_date=None,
    )
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


# --- dogalgaz_dosyalari_ayikla: liste sayfası HTML kazıma (petrolden farklı desen) ---


def _dg_ay_girdisi_html(ay_adi, yil, data_id="1000", excel_id="XLSID", excel_var=True):
    """Doğal gaz liste sayfası deseni: '<Ay> <Yıl>' (yıl SONDA), tek excel
    linki, ardından pdf linki (canlı ölçülen gerçek sıra)."""
    baslik = (
        f'<a data-toggle="collapse" data-target="#kesmebedel_{data_id}" '
        f'data-type="True" data-id="{data_id}" onclick="ShowDetailList(this);">'
        f'<i class="far fa-arrow-alt-circle-right"></i>Doğal Gaz Piyasası '
        f"Sekt&#246;r Raporu {ay_adi} {yil} &nbsp;<span style='color:#EF3A50;'></span></a>\r\n"
        "<br />\r\n"
    )
    excel_link = (
        f'<a style="float: right;" href="/Detay/DownloadDocument?id={excel_id}" '
        f'target="_blank" title="Doğalgaz {ay_adi} {yil} Rapor Eki">'
        "<img src ='/Content/img/excel.png' style='width:20px;height:20px;' /></a>\r\n"
    ) if excel_var else ""
    pdf_link = (
        f'<a style="float: right;" href="/Detay/DownloadDocument?id=PDF{data_id}" '
        f'target="_blank" title="{ay_adi} {yil}">'
        "<img src ='/Content/img/pdf.png' style='width:20px;height:20px;' /></a>\r\n"
    )
    return (
        baslik + excel_link + pdf_link
        + f'<div id="kesmebedel_{data_id}" class="collapse"><br /></div>\r\n'
    )


def test_dogalgaz_dosyalari_ayikla_temel_girdiyi_bulur():
    html = _dg_ay_girdisi_html("Temmuz", 2026, data_id="35580", excel_id="EXCEL7")
    assert dogalgaz_dosyalari_ayikla(html) == [
        {"yil": 2026, "ay": 7, "url": "/Detay/DownloadDocument?id=EXCEL7"}
    ]


def test_dogalgaz_dosyalari_ayikla_excel_eki_yoksa_atlar():
    """2025 ve öncesi ay girdilerinde yalnızca ana rapor var, excel eki yok
    (canlı ölçüldü: Ağustos 2025 girdisinde tek link)."""
    html = _dg_ay_girdisi_html("Ağustos", 2025, data_id="99999", excel_var=False)
    assert dogalgaz_dosyalari_ayikla(html) == []


def test_dogalgaz_dosyalari_ayikla_birden_fazla_donemi_ayirir():
    html = (
        _dg_ay_girdisi_html("Ocak", 2026, data_id="1", excel_id="X1")
        + _dg_ay_girdisi_html("Şubat", 2026, data_id="2", excel_id="X2")
        + _dg_ay_girdisi_html("Aralık", 2025, data_id="3", excel_var=False)
    )
    assert dogalgaz_dosyalari_ayikla(html) == [
        {"yil": 2026, "ay": 1, "url": "/Detay/DownloadDocument?id=X1"},
        {"yil": 2026, "ay": 2, "url": "/Detay/DownloadDocument?id=X2"},
    ]


def test_dogalgaz_cekilecek_dosyalar_2026_oncesini_eler():
    """`cekilecek_dosyalar` petrolle PAYLAŞILAN genel fonksiyon; doğal gaz
    eki de yalnızca Ocak 2026'dan itibaren yayımlanıyor (canlı ölçüldü)."""
    liste = [{"yil": 2025, "ay": 12, "url": "/eski"}, {"yil": 2026, "ay": 1, "url": "/yeni"}]
    assert cekilecek_dosyalar(liste) == [{"yil": 2026, "ay": 1, "url": "/yeni"}]
    assert (ILK_YIL, ILK_AY) == (2026, 1)


# --- _dogalgaz_alt_tablo_bul: birleşik sayfada 'Tablo-N ' sınırı (petrolden farklı noktalama) ---


def test_dogalgaz_alt_tablo_bul_tabloyu_dogru_siniirlar():
    satirlar = [
        ("Tablo-3 İthal Edilen Gaz Miktarı (Sm3) (Şirketlere Göre)",),
        ("satir-3-a",),
        ("satir-3-b",),
        ("Tablo-4 İthal Edilen Gaz Miktarı (Sm3) (Gazın Türü ve Ülkelere Göre)",),
        ("satir-4-a",),
    ]
    sonuc = _dogalgaz_alt_tablo_bul(satirlar, 3)
    assert sonuc == satirlar[:3]


def test_dogalgaz_alt_tablo_bul_baslik_yoksa_hata():
    with pytest.raises(RuntimeError, match="Tablo-9"):
        _dogalgaz_alt_tablo_bul([("baska",)], 9)


# --- dogalgaz_ithalat_cek: Tablo-3, BOTAŞ + özel ithalatçı grubu ---


def _tablo3_satirlari(temmuz_ozel_bos=True):
    """Temmuz 2026'dan ölçülen gerçek değerlerle Tablo-3 satırları."""
    baslik = (None, "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Genel Toplam")
    akfel = ["AKFEL GAZ SANAYİ VE TİCARET ANONİM ŞİRKETİ", 203146162, 26205474, 183607905, 91903248]
    bosphorus = ["BOSPHORUS GAZ CORPORATİON ANONİM ŞİRKETİ", 366275729, 37024502, 239396085, 144856581]
    botas = [BOTAS_SIRKET_ADI, 7007288995.04, 5050171821.33,
             5643933245, 4350115292.49, 3643596483, 3059661255.02, 3063183821.54]
    kibar = ["KİBAR ENERJİ ANONİM ŞİRKETİ", 146510303, 146510303, 205217180, 143862222]
    if temmuz_ozel_bos:
        # Mayıs-Temmuz'da özel ithalatçı hücreleri BOŞ (canlı ölçüldü).
        akfel += [None, None, None]
        bosphorus += [None, None, None]
        kibar += [None, None, None]
    botas += [31817950913.41]
    return [
        tuple(baslik),
        tuple(akfel),
        tuple(bosphorus),
        tuple(botas),
        tuple(kibar),
    ]


def test_dogalgaz_ithalat_cek_botas_ve_ozel_toplami_temmuzde_dogru_okur():
    sonuc = dogalgaz_ithalat_cek(_tablo3_satirlari(), "Temmuz")
    assert sonuc["botas-ithalat"] == pytest.approx(3063183821.54)
    assert sonuc["ozel-ithalatci-ithalat"] == pytest.approx(0.0)


def test_dogalgaz_ithalat_cek_ozel_ithalatci_nisanda_toplanir():
    """Nisan 2026: üç özel ithalatçının hücreleri dolu — toplam 0,38
    milyar Sm³ karta birebir uyuyor (canlı ölçüldü)."""
    sonuc = dogalgaz_ithalat_cek(_tablo3_satirlari(), "Nisan")
    assert sonuc["ozel-ithalatci-ithalat"] == pytest.approx(380622051)


def test_dogalgaz_ithalat_cek_botas_satiri_yoksa_hata():
    satirlar = [(None, "Ocak"), ("BAŞKA ŞİRKET", 100)]
    with pytest.raises(RuntimeError, match="BOTAŞ"):
        dogalgaz_ithalat_cek(satirlar, "Ocak")


# --- dogalgaz_depolama_cek: Tablo-6, Haziran 2026'daki 'DPF-34 - ' önek kuvirki ---


def test_dogalgaz_depolama_cek_duz_etiketle_okur():
    satirlar = [
        (None, "Ocak", "Temmuz"),
        ("Boru Gazı", 3853987373.79, 5412894598.46),
        ("LNG", 402959058.98, 224788385.07),
        ("TOPLAM", 4256946432.77, 5637682983.53),
    ]
    sonuc = dogalgaz_depolama_cek(satirlar, "Temmuz")
    assert sonuc["depolama-borugazi"] == pytest.approx(5412894598.46)
    assert sonuc["depolama-lng"] == pytest.approx(224788385.07)


def test_dogalgaz_depolama_cek_tesis_kodu_onekiyle_de_okur():
    """Haziran 2026'da satır etiketi 'DPF-34 - Boru Gazı'/'DPF-34 - LNG'
    olarak geldi — canlı ölçüldü, `endswith` ile eşleşmeli."""
    satirlar = [
        (None, "Haziran"),
        ("DPF-34 - Boru Gazı", 4969932780.36),
        ("DPF-34 - LNG", 295824850.06),
        ("TOPLAM", 5265757630.42),
    ]
    sonuc = dogalgaz_depolama_cek(satirlar, "Haziran")
    assert sonuc["depolama-borugazi"] == pytest.approx(4969932780.36)
    assert sonuc["depolama-lng"] == pytest.approx(295824850.06)


def test_dogalgaz_depolama_cek_satir_yoksa_hata():
    satirlar = [(None, "Ocak"), ("BAŞKA", 1)]
    with pytest.raises(RuntimeError, match="Boru Gazı"):
        dogalgaz_depolama_cek(satirlar, "Ocak")


# --- dogalgaz_abone_cek: Tablo-8, il satırları + çok-il'li şirket toplamı ---


def test_dogalgaz_abone_cek_il_satirlarini_atlar_sirketleri_toplar():
    tablo8 = [
        ("İl/Şirket", "Abone Sayısı", "Serbest Tüketici Sayısı"),
        ("YALOVA", 26976, 693),  # il satırı — önek eşleşmediği için atlanır
        ("MARMARA YALOVA GAZ DAĞITIM ANONİM ŞİRKETİ", 26976, 693),
        ("KOCAELİ", 19778, 481),
        ("MARMARA YALOVA GAZ DAĞITIM ANONİM ŞİRKETİ", 19778, 481),
        ("ADANA", 282806, 2866),
        ("AKSA ÇUKUROVA DOĞAL GAZ DAĞITIM ANONİM ŞİRKETİ", 282806, 2866),  # AHGAZ dışı
    ]
    sonuc = dogalgaz_abone_cek(tablo8)
    # MARMARA YALOVA iki il satırında tekrarlanıyor — TOPLANMALI.
    assert sonuc["ahgaz-abone"] == pytest.approx(46754)
    assert sonuc["ahgaz-serbest"] == pytest.approx(1174)


def test_dogalgaz_abone_cek_baslik_yoksa_hata():
    with pytest.raises(RuntimeError, match="başlık"):
        dogalgaz_abone_cek([("Yanlış Başlık",)])


# --- dogalgaz_sirket_tuketim_cek: Tablo-12, çok lisanslı şirket + AHGAZ grubu ---


def test_dogalgaz_sirket_tuketim_cek_ntgaz_iki_lisans_satirini_toplar():
    tablo12 = [
        ("TÜRKİYE", "Lisans Tipi", "Konutlar", "Genel Toplam"),
        ("ENERYA KONYA GAZ DAĞITIM ANONİM ŞİRKETİ", "Dağıtım Lisansı", 100, 19875764.09),
        ("MARMARA ÇORLU GAZ DAĞITIM ANONİM ŞİRKETİ", "Dağıtım Lisansı", 100, 9595706.37),
        (NTGAZ_SIRKET_ADI, "İthalat Lisansı", 0, 128917.51),
        (None, "Sıkıştırılmış Doğalgaz Lisansı", 0, 14740498.97),
        (AYGAZ_SIRKET_ADI, "Toptan Satış Lisansı", 0, 8654967.23),
    ]
    sonuc = dogalgaz_sirket_tuketim_cek(tablo12)
    assert sonuc["ahgaz-tuketim"] == pytest.approx(19875764.09 + 9595706.37)
    assert sonuc["ntgaz-hacim"] == pytest.approx(128917.51 + 14740498.97)
    assert sonuc["aygaz-hacim"] == pytest.approx(8654967.23)


def test_dogalgaz_sirket_tuketim_cek_ntgaz_yoksa_hata():
    tablo12 = [
        ("TÜRKİYE", "Lisans Tipi", "Genel Toplam"),
        (AYGAZ_SIRKET_ADI, "Toptan Satış Lisansı", 100),
    ]
    with pytest.raises(RuntimeError, match="NATURELGAZ"):
        dogalgaz_sirket_tuketim_cek(tablo12)


def test_dogalgaz_sirket_tuketim_cek_genel_toplam_sutunu_yoksa_hata():
    tablo12 = [("TÜRKİYE", "Lisans Tipi", "Konutlar")]
    with pytest.raises(RuntimeError, match="Genel Toplam"):
        dogalgaz_sirket_tuketim_cek(tablo12)


# --- dogalgaz_ayin_tum_olculerini_cikar / dogalgaz_seri_cek: uçtan uca ---


class SahteYanit:
    def __init__(self, status_code, metin="", icerik=b""):
        self.status_code = status_code
        self.text = metin
        self.content = icerik


class SahteOturum:
    def __init__(self, yanitlar_by_url):
        self._yanitlar = yanitlar_by_url
        self.istekler: list[str] = []

    def get(self, url, timeout=None):
        self.istekler.append(url)
        for parca, yanit in self._yanitlar.items():
            if parca in url:
                return yanit
        raise AssertionError(f"beklenmeyen url: {url}")


def test_dogalgaz_seri_cek_dosya_listesi_bos_donerse_hata():
    html = _dg_ay_girdisi_html("Ağustos", 2025, excel_var=False)
    oturum = SahteOturum({"dogal-gazaylik-sektor-raporu": SahteYanit(200, metin=html)})
    with pytest.raises(RuntimeError, match="2026-01 sonrası"):
        dogalgaz_seri_cek(dogalgaz_seri(), onbellek={}, session=oturum)


def test_dogalgaz_seri_cek_liste_http_hatasinda_yukselir():
    oturum = SahteOturum({"dogal-gazaylik-sektor-raporu": SahteYanit(500)})
    with pytest.raises(RuntimeError, match="500"):
        dogalgaz_seri_cek(dogalgaz_seri(), onbellek={}, session=oturum)


def test_dogalgaz_seri_cek_gecersiz_olcutte_hata():
    """Sözleşme testi: onbellek ÖNCEDEN doldurulmuşsa ağ hiç çağrılmaz,
    yalnızca ölçüt anahtarı doğrulanır."""
    onbellek = {"dogalgaz_noktalar": {"ahgaz-tuketim": {"2026-07-01": 1.0}}}
    with pytest.raises(RuntimeError, match="ölçüt bulunamadı"):
        dogalgaz_seri_cek(
            dogalgaz_seri(epdk_dogalgaz_olcut="olmayan-olcut"),
            onbellek=onbellek,
            session=SahteOturum({}),
        )


def test_dogalgaz_seri_cek_onbellek_paylasilirsa_dosya_listesi_tekrar_cekilmez():
    onbellek = {"dogalgaz_noktalar": {"ahgaz-tuketim": {"2026-01-01": 5.0, "2026-07-01": 7.0}}}
    oturum = SahteOturum({})  # hiç istek beklenmiyor — onbellek zaten dolu
    df = dogalgaz_seri_cek(dogalgaz_seri(), onbellek=onbellek, session=oturum)
    assert list(df["date"]) == ["2026-01-01", "2026-07-01"]
    assert list(df["value"]) == [5.0, 7.0]
    assert oturum.istekler == []


def test_dogalgaz_seri_cek_start_date_filtreler():
    onbellek = {"dogalgaz_noktalar": {"ahgaz-tuketim": {"2026-01-01": 5.0, "2026-07-01": 7.0}}}
    df = dogalgaz_seri_cek(
        dogalgaz_seri(start_date="2026-03-01"), onbellek=onbellek, session=SahteOturum({})
    )
    assert list(df["date"]) == ["2026-07-01"]
