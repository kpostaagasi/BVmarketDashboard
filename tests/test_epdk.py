"""EPDK Petrol Piyasası aylık sektör raporu istemcisi testleri.

Gerçek kaynaktan ölçülen üç şablon tuhaflığı ayrı ayrı pinlenir: yılın ilk
ayında (Ocak) "Aylık Bazda" tabloların ay-adı yerine tek "Miktar" sütunu
kullanması, Tablo 11'in Ocak'ta satır/sütunu DEVİRMESİ (satır=ay,
sütun=ürün), ve granüler bir alt kalemin (ör. E10 benzin varyantı) bazı
aylarda satırın kendisiyle birlikte tamamen kaybolması (0 sayılmalı).
Ayrıca liste sayfasındaki pdf/excel link SIRASININ ay ay değiştiği ve
"Lisans Sahibinin Ünvanı"/"Unvanı" yazımının kararsız olduğu ölçüldü.
"""

import io
from types import SimpleNamespace

import openpyxl
import pytest

from ingest.epdk import (
    ILK_AY,
    ILK_YIL,
    _ay_sutun_bul,
    _norm,
    _sayfa_bul,
    alt_tablo_satirlarini_bul,
    aylik_urun_tablosu,
    ayin_tum_olculerini_cikar,
    cekilecek_dosyalar,
    dosyalari_ayikla,
    seri_cek,
    tablo1_uretim,
    tablo12_yurtici_satis,
)


def epdk_seri(**kwargs):
    varsayilan = dict(
        id="petrol-piyasasi/rafineri-uretimi-benzin",
        kaynak_tipi="epdk",
        epdk_olcut="rafineri-uretimi",
        epdk_urun="benzin",
        start_date=None,
    )
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


# --- dosyalari_ayikla: liste sayfası HTML kazıma ---


def _ay_girdisi_html(yil, ay_adi, data_id="1000", pdf_id="PDFID", excel_id="XLSID",
                      sira="pdf-excel", excel_var=True):
    baslik = (
        f'<a data-toggle="collapse" data-target="#kesmebedel_{data_id}" '
        f'data-type="True" data-id="{data_id}" onclick="ShowDetailList(this);">'
        f'<i class="far fa-arrow-alt-circle-right"></i>{yil} Yılı Petrol Piyasası '
        f"{ay_adi} Ayı Sekt&#246;r Raporu   &nbsp;<span style='color:#EF3A50;'></span></a>\r\n"
        "<br />\r\n"
    )
    pdf_link = (
        f'<a style="float: right;" href="/Detay/DownloadDocument?id={pdf_id}" '
        f'target="_blank" title="{yil} rapor"><img src =\'/Content/img/pdf.png\' '
        "style='width:20px;height:20px;' /></a>\r\n"
    )
    excel_link = (
        f'<a style="float: right;" href="/Detay/DownloadDocument?id={excel_id}" '
        f'target="_blank" title="{ay_adi} {yil}"><img src =\'/Content/img/excel.png\' '
        "style='width:20px;height:20px;' /></a>\r\n"
    ) if excel_var else ""
    linkler = f"{pdf_link}{excel_link}" if sira == "pdf-excel" else f"{excel_link}{pdf_link}"
    return baslik + linkler + f'<div id="kesmebedel_{data_id}" class="collapse"><br /></div>\r\n'


def test_dosyalari_ayikla_temel_girdiyi_bulur():
    html = _ay_girdisi_html(2026, "Temmuz", data_id="35580", excel_id="EXCEL7")
    sonuc = dosyalari_ayikla(html)
    assert sonuc == [{"yil": 2026, "ay": 7, "url": "/Detay/DownloadDocument?id=EXCEL7"}]


def test_dosyalari_ayikla_excel_pdf_sirasi_tersse_de_bulur():
    """Şubat/Mart 2026'da gözlenen sıra: excel linki pdf'ten ÖNCE gelir."""
    html = _ay_girdisi_html(2026, "Şubat", data_id="35277", excel_id="EXCEL2", sira="excel-pdf")
    sonuc = dosyalari_ayikla(html)
    assert sonuc == [{"yil": 2026, "ay": 2, "url": "/Detay/DownloadDocument?id=EXCEL2"}]


def test_dosyalari_ayikla_excel_eki_yoksa_atlar():
    """Yalnızca ana rapor (pdf/word) yayımlanmış, excel eki henüz yok."""
    html = _ay_girdisi_html(2026, "Ağustos", data_id="99999", excel_var=False)
    assert dosyalari_ayikla(html) == []


def test_dosyalari_ayikla_birden_fazla_donemi_ayirir():
    html = (
        _ay_girdisi_html(2026, "Ocak", data_id="1", excel_id="X1")
        + _ay_girdisi_html(2026, "Şubat", data_id="2", excel_id="X2")
        + _ay_girdisi_html(2025, "Aralık", data_id="3", excel_id="X3")
    )
    sonuc = dosyalari_ayikla(html)
    assert sonuc == [
        {"yil": 2026, "ay": 1, "url": "/Detay/DownloadDocument?id=X1"},
        {"yil": 2026, "ay": 2, "url": "/Detay/DownloadDocument?id=X2"},
        {"yil": 2025, "ay": 12, "url": "/Detay/DownloadDocument?id=X3"},
    ]


# --- cekilecek_dosyalar: format kırılması öncesi dönemleri eler ---


def test_cekilecek_dosyalar_2026_oncesini_eler():
    """Aralık 2025 ve öncesi eski ('il bazında teslimler') formatta —
    bu adaptör okumuyor, bkz. modül docstring'i."""
    liste = [
        {"yil": 2025, "ay": 12, "url": "/eski"},
        {"yil": 2026, "ay": 1, "url": "/yeni"},
    ]
    assert cekilecek_dosyalar(liste) == [{"yil": 2026, "ay": 1, "url": "/yeni"}]
    assert (ILK_YIL, ILK_AY) == (2026, 1)


def test_cekilecek_dosyalar_eskiden_yeniye_siralar():
    liste = [
        {"yil": 2026, "ay": 3, "url": "/mart"},
        {"yil": 2026, "ay": 1, "url": "/ocak"},
        {"yil": 2026, "ay": 2, "url": "/subat"},
    ]
    assert [d["ay"] for d in cekilecek_dosyalar(liste)] == [1, 2, 3]


# --- tablo1_uretim: granüler satırların 5 ürün grubuna toplanması ---


def _tablo1_satirlari(ek_satirlar=(), sil=()):
    """Temmuz 2026'dan ölçülen gerçek değerlerle Tablo 1 satırlarını üretir
    (ölçüm: MarketVisuals kartlarıyla birebir eşleşti, bkz. modül docstring'i)."""
    taban = {
        "Kurşunsuz Benzin 95 Oktan": 565954.022,
        "Kurşunsuz Benzin 98 Oktan": 1742.874,
        "Kurşunsuz Benzin 98 Oktan (E10)": 0,
        "Motorin": 1513247.43,
        "Motorin (Biodizel ihtiva eden)": 34986.472,
        "Atmosferik Straight Run Fuel Oil": -162825.638,
        "Fuel Oil (Kükürt Oranı %0,1'i geçmeyenler)": 0,
        "Fuel Oil (Kükürt Oranı %0,5'i geçen fakat %1'i geçmeyenler)": -4595.518,
        "Kalorifer Yakıtı (Kükürt Oranı %0,1'i geçen ancak %0,5'i geçmeyenler)": 0,
        "Kalorifer Yakıtı (Kükürt Oranı %0,1'i geçmeyenler)": 0,
        "Kalorifer Yakıtı (Kükürt Oranı %0,5'i geçen fakat %1'i geçmeyenler)": 2950.658,
        "Yüksek Kükürtlü Fuel Oil (Kükürt oranı %1'i geçenler)": -332.764,
        "Jet Yakıtı (Kerosen)": 578570.154,
        "Jet Yakıtı (Benzin)": 0,
        "Denizcilik Yakıtı (Artık)": 43206.457,
        "Denizcilik Yakıtı (Damıtık)": 36339.738,
        "Baz yağ": 10416.432,  # eşlemeye girmeyen alakasız satır
    }
    for ad in sil:
        del taban[ad]
    for ad, deger in ek_satirlar:
        taban[ad] = deger
    satirlar = [("Ürün Türü", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", " Genel Toplam")]
    for ad, deger in taban.items():
        satirlar.append((ad, None, None, None, None, None, None, deger, None))
    return satirlar


def test_tablo1_uretim_gruplari_dogru_toplar():
    sonuc = tablo1_uretim(_tablo1_satirlari(), "Temmuz")
    assert sonuc["benzin"] == pytest.approx(567696.896)
    assert sonuc["motorin"] == pytest.approx(1548233.902)
    assert sonuc["fuel-oil"] == pytest.approx(-164803.262)
    assert sonuc["havacilik"] == pytest.approx(578570.154)
    assert sonuc["denizcilik"] == pytest.approx(79546.195)


def test_tablo1_uretim_eksik_alt_kalem_sifir_sayilir():
    """Mart 2026'da ölçüldü: E10 satırı 0 olduğunda tablodan tamamen
    düşüyor (Temmuz'da 0 değerle mevcuttu) — grup toplamı etkilenmemeli."""
    tam = tablo1_uretim(_tablo1_satirlari(), "Temmuz")
    eksik = tablo1_uretim(_tablo1_satirlari(sil=("Kurşunsuz Benzin 98 Oktan (E10)",)), "Temmuz")
    assert eksik["benzin"] == pytest.approx(tam["benzin"])


def test_tablo1_uretim_baslik_yoksa_hata():
    satirlar = [("Yanlış Başlık", "Ocak")]
    with pytest.raises(RuntimeError, match="Ürün Türü"):
        tablo1_uretim(satirlar, "Temmuz")


def test_tablo1_uretim_ay_sutunu_yoksa_hata():
    with pytest.raises(RuntimeError, match="sütunu bulunamadı"):
        tablo1_uretim(_tablo1_satirlari(), "Ağustos")


def test_tablo1_uretim_ocakta_miktar_sutununa_duser():
    """Yılın ilk ayı: 'Ocak' sütun adı yerine tek 'Miktar' sütunu var."""
    satirlar = [
        ("Ürün Türü", "Miktar"),
        ("Kurşunsuz Benzin 95 Oktan", 470317.392),
        ("Kurşunsuz Benzin 98 Oktan", 2699.639),
        ("Motorin", 1359011.176),
        ("Motorin (Biodizel ihtiva eden)", 0),
        ("Jet Yakıtı (Kerosen)", 511781.071),
        ("Jet Yakıtı (Benzin)", 0),
        ("Denizcilik Yakıtı (Artık)", 6399.599),
        ("Denizcilik Yakıtı (Damıtık)", 29661.513),
        ("Atmosferik Straight Run Fuel Oil", -38067.812),
    ]
    sonuc = tablo1_uretim(satirlar, "Ocak")
    assert sonuc["benzin"] == pytest.approx(470317.392 + 2699.639)
    assert sonuc["havacilik"] == pytest.approx(511781.071)


# --- alt_tablo_satirlarini_bul: birleşik sayfadan alt tablo dilimleme ---


def test_alt_tablo_satirlarini_bul_araligi_dogru_keser():
    satirlar = [
        ("Tablo 2: Ülkelere Göre İthalat",),
        ("Rusya", 100),
        ("Tablo 5: Aylık Bazda İthalat",),
        ("Ürün Türleri", "Temmuz"),
        ("Benzin Türleri", 55.2),
        ("Tablo 6: Ham Petrol İthalatı",),
        ("Toplam", 999),
    ]
    dilim = alt_tablo_satirlarini_bul(satirlar, 5)
    assert dilim[0][0] == "Tablo 5: Aylık Bazda İthalat"
    assert dilim[-1] == ("Benzin Türleri", 55.2)
    assert not any(row[0] == "Tablo 6: Ham Petrol İthalatı" for row in dilim)


def test_alt_tablo_satirlarini_bul_bulunamazsa_hata():
    with pytest.raises(RuntimeError, match="Tablo 5"):
        alt_tablo_satirlarini_bul([("Tablo 2: X",)], 5)


# --- aylik_urun_tablosu: normal + devrik (Ocak) yönelim ---


def test_aylik_urun_tablosu_normal_yonelim():
    satirlar = [
        ("Ürün Türleri", "Ocak", "Şubat", "Temmuz", "Genel Toplam"),
        ("Benzin Türleri", 1.0, 2.0, 55188.754, 999),
        ("Motorin Türleri", 1.0, 2.0, 1146508.762, 999),
        ("Fuel Oil Türleri", 1.0, 2.0, 12000.0, 999),
        ("Havacılık Yakıtları", 1.0, 2.0, 74570.36, 999),
        ("Denizcilik Yakıtları", 1.0, 2.0, 11649.635, 999),
        ("Genel Toplam", 5.0, 10.0, 1299917.511, 999),
    ]
    sonuc = aylik_urun_tablosu(satirlar, "Temmuz", 5)
    assert sonuc["benzin"] == pytest.approx(55188.754)
    assert sonuc["fuel-oil"] == pytest.approx(12000.0)


def test_aylik_urun_tablosu_buyuk_harf_baslik_toleransli():
    """Ocak 2026'da Tablo 5 başlığı 'ÜRÜN TÜRLERİ' büyük harfle geldi."""
    satirlar = [
        ("ÜRÜN TÜRLERİ", "Miktar", "Genel Toplam"),
        ("Benzin Türleri", 323.41, 323.41),
        ("Motorin Türleri", 722721.732, 722721.732),
        ("Fuel Oil Türleri", 38324.441, 38324.441),
        ("Havacılık Yakıtları", 57559.915, 57559.915),
        ("Denizcilik Yakıtları", 9127.0, 9127.0),
        ("Toplam", 1040972.901, 1040972.901),
    ]
    sonuc = aylik_urun_tablosu(satirlar, "Ocak", 5)
    assert sonuc["benzin"] == pytest.approx(323.41)


def test_aylik_urun_tablosu_devrik_yonelim_ocak():
    """Ocak 2026'da Tablo 11: satır=ay, sütun=ürün adı (diğer aylarda ters)."""
    satirlar = [
        ("Ay", "Benzin Türleri", "Denizcilik Yakıtları", "Diğer Ürünler",
         "Fuel Oil Türleri", "Havacılık Yakıtları", "Motorin Türleri", "Genel Toplam"),
        ("Ocak", 39842.894, 55823.336, 346302.807, 54685.577, 452986.637, 120307.823, 1069949.074),
        ("Toplam", 39842.894, 55823.336, 346302.807, 54685.577, 452986.637, 120307.823, 1069949.074),
    ]
    sonuc = aylik_urun_tablosu(satirlar, "Ocak", 11)
    assert sonuc["benzin"] == pytest.approx(39842.894)
    assert sonuc["havacilik"] == pytest.approx(452986.637)
    assert sonuc["fuel-oil"] == pytest.approx(54685.577)


def test_aylik_urun_tablosu_beklenen_sutun_yoksa_hata():
    satirlar = [
        ("Ürün Türleri", "Temmuz"),
        ("Benzin Türleri", 1.0),
        ("Motorin Türleri", 1.0),
        ("Havacılık Yakıtları", 1.0),
        ("Denizcilik Yakıtları", 1.0),
    ]
    with pytest.raises(RuntimeError, match="Fuel Oil Türleri"):
        aylik_urun_tablosu(satirlar, "Temmuz", 5)


def test_aylik_urun_tablosu_hicbir_baslik_yoksa_hata():
    with pytest.raises(RuntimeError, match="başlık satırı bulunamadı"):
        aylik_urun_tablosu([("Alakasız", 1)], "Temmuz", 5)


# --- tablo12_yurtici_satis: şirket bazlı tablonun Toplam satırı ---


def _tablo12_satirlari(baslik_etiketi="Lisans Sahibinin Ünvanı", toplam_etiketi="Toplam"):
    return [
        (baslik_etiketi, "Lisans Türü", "Benzin Türleri", "Motorin Türleri",
         "Fuel Oil Türleri", "Havacılık Yakıtları", "Denizcilik Yakıtları", "Genel Toplam"),
        ("PETROL OFİSİ", "Dağıtıcı", 151552.635, 686512.455, 2501.9, 16529.267, 200.0, 857304.042),
        (toplam_etiketi, None, 616717.150, 2658266.219, 8315.73, 123899.414, 2345.393, 3425591.104),
    ]


def test_tablo12_yurtici_satis_toplam_satirini_okur():
    sonuc = tablo12_yurtici_satis(_tablo12_satirlari())
    assert sonuc["benzin"] == pytest.approx(616717.150)
    assert sonuc["havacilik"] == pytest.approx(123899.414)


def test_tablo12_yurtici_satis_unvani_yazim_varyanti_kabul_eder():
    """Nisan/Mayıs/Haziran 2026'da 'Ünvanı' yerine 'Unvanı' (dotless) geldi."""
    sonuc = tablo12_yurtici_satis(_tablo12_satirlari(baslik_etiketi="Lisans Sahibinin Unvanı"))
    assert sonuc["motorin"] == pytest.approx(2658266.219)


def test_tablo12_yurtici_satis_toplam_yoksa_hata():
    satirlar = [_tablo12_satirlari()[0], _tablo12_satirlari()[1]]
    with pytest.raises(RuntimeError, match="Toplam"):
        tablo12_yurtici_satis(satirlar)


def test_tablo12_yurtici_satis_beklenen_sutun_yoksa_hata():
    satirlar = [
        ("Lisans Sahibinin Ünvanı", "Benzin Türleri", "Motorin Türleri",
         "Havacılık Yakıtları", "Denizcilik Yakıtları"),
        ("Toplam", 1.0, 1.0, 1.0, 1.0),
    ]
    with pytest.raises(RuntimeError, match="Fuel Oil Türleri"):
        tablo12_yurtici_satis(satirlar)


# --- _sayfa_bul / _norm / _ay_sutun_bul: küçük yardımcılar ---


class _SahteKitap:
    def __init__(self, sheetnames):
        self.sheetnames = sheetnames

    def __getitem__(self, ad):
        return f"sayfa:{ad}"


def test_sayfa_bul_tire_ve_ampersand_varyantlarini_esler():
    kitap = _SahteKitap(["Tablo 1", "Tablo2&6", "Tablo 7-8", "Tablo 11"])
    assert _sayfa_bul(kitap, "2-6") == "sayfa:Tablo2&6"
    assert _sayfa_bul(kitap, "7-8") == "sayfa:Tablo 7-8"
    assert _sayfa_bul(kitap, "11") == "sayfa:Tablo 11"


def test_sayfa_bul_bulunamazsa_hata():
    with pytest.raises(RuntimeError, match="Tablo 99"):
        _sayfa_bul(_SahteKitap(["Tablo 1"]), "99")


def test_ay_sutun_bul_miktar_yedegi():
    assert _ay_sutun_bul(["Ürün Türü", "Miktar"], "Ocak", 1) == 1
    assert _ay_sutun_bul(["Ürün Türü", "Ocak", "Şubat"], "Şubat", 1) == 2


# --- ayin_tum_olculerini_cikar: gerçek XLSX bütünlük testi ---


def _ek_dosyasi_baytlari():
    """Tablo 1/2-6(içinde 5)/11/12'yi taşıyan minimal ama gerçekçi bir EK
    XLSX'i üretir (Şubat 2026 biçimi: normal yönelim, tek harf varyantı yok)."""
    kitap = openpyxl.Workbook()
    kitap.remove(kitap.active)

    t1 = kitap.create_sheet("Tablo 1")
    t1.append(("Tablo 1: Aylık Bazda Rafineri Üretimi (Ocak-Şubat 2026)",))
    t1.append(("Ürün Türü", "Ocak", "Şubat", "Genel Toplam"))
    for ad, oca, sub in [
        ("Kurşunsuz Benzin 95 Oktan", 470317.392, 399671.063),
        ("Motorin", 1359011.176, 1203133.818),
        ("Jet Yakıtı (Kerosen)", 511781.071, 488028.305),
        ("Denizcilik Yakıtı (Artık)", 6399.599, 5891.083),
        ("Denizcilik Yakıtı (Damıtık)", 29661.513, 43856.968),
        ("Atmosferik Straight Run Fuel Oil", -38067.812, -61776.607),
    ]:
        t1.append((ad, oca, sub, oca + sub))

    t26 = kitap.create_sheet("Tablo 2-6")
    t26.append(("Tablo 5: Aylık Bazda Petrol Ürünleri İthalat Miktarları",))
    t26.append(("Ürün Türleri", "Ocak", "Şubat", "Genel Toplam"))
    for ad, oca, sub in [
        ("Benzin Türleri", 323.41, 0.0),
        ("Motorin Türleri", 722721.732, 702189.348),
        ("Fuel Oil Türleri", 38324.441, 13000.0),
        ("Havacılık Yakıtları", 57559.915, 58606.604),
        ("Denizcilik Yakıtları", 9127.0, 15597.484),
    ]:
        t26.append((ad, oca, sub, oca + sub))
    t26.append(("Tablo 6: Aylık Bazda Ham Petrol İthalat Miktarları",))

    t11 = kitap.create_sheet("Tablo 11")
    t11.append(("Tablo 11: Aylık Bazda Ürün Türlerine Göre İhracat Miktarı",))
    t11.append(("Ürün Türleri", "Ocak", "Şubat", "Genel Toplam"))
    for ad, oca, sub in [
        ("Benzin Türleri", 39843.178, 7224.543),
        ("Motorin Türleri", 120307.823, 86394.1),
        ("Fuel Oil Türleri", 0.0, 0.0),
        ("Havacılık Yakıtları", 452986.637, 401942.0),
        ("Denizcilik Yakıtları", 55823.336, 52538.32),
    ]:
        t11.append((ad, oca, sub, oca + sub))

    t12 = kitap.create_sheet("Tablo 12")
    t12.append(("Tablo 12: Şubat 2026 Dönemi Lisans Sahibi Şirketlere Göre Yurtiçi Satışlar",))
    t12.append(("Lisans Sahibinin Ünvanı", "Lisans Türü", "Benzin Türleri", "Motorin Türleri",
                 "Fuel Oil Türleri", "Havacılık Yakıtları", "Denizcilik Yakıtları", "Genel Toplam"))
    t12.append(("PETROL OFİSİ", "Dağıtıcı", 100000.0, 400000.0, 1000.0, 50000.0, 500.0, 551500.0))
    t12.append(("Toplam", None, 417800.0, 1834500.0, 19700.0, 89400.0, 1200.0, 2362600.0))

    tampon = io.BytesIO()
    kitap.save(tampon)
    return tampon.getvalue()


def test_ayin_tum_olculerini_cikar_dort_olcutu_de_dondurur():
    baytlar = _ek_dosyasi_baytlari()
    sonuc = ayin_tum_olculerini_cikar(baytlar, "Şubat")
    assert set(sonuc) == {"rafineri-uretimi", "yurtici-satis", "ithalat", "ihracat"}
    for olcut in sonuc:
        assert set(sonuc[olcut]) == {"benzin", "motorin", "fuel-oil", "havacilik", "denizcilik"}
    assert sonuc["rafineri-uretimi"]["motorin"] == pytest.approx(1203133.818)
    assert sonuc["ithalat"]["benzin"] == pytest.approx(0.0)
    assert sonuc["ihracat"]["havacilik"] == pytest.approx(401942.0)
    assert sonuc["yurtici-satis"]["fuel-oil"] == pytest.approx(19700.0)


# --- seri_cek: ağ kabuğu ---


class SahteYanit:
    def __init__(self, status_code, content=b"", text=""):
        self.status_code = status_code
        self.content = content
        self.text = text


class SahteOturum:
    def __init__(self, liste_html, dosya_yanitlari):
        """`dosya_yanitlari`: url -> bytes (200 varsayılır)."""
        self.liste_html = liste_html
        self.dosya_yanitlari = dosya_yanitlari
        self.cagrilar = []

    def get(self, url, timeout=None):
        self.cagrilar.append(url)
        if url.endswith("petrolaylik-sektor-raporu"):
            return SahteYanit(200, text=self.liste_html)
        for parca, baytlar in self.dosya_yanitlari.items():
            if url.endswith(parca):
                return SahteYanit(200, content=baytlar)
        return SahteYanit(404)


def _tek_aylik_liste_html():
    return _ay_girdisi_html(2026, "Şubat", data_id="1", excel_id="XLS-SUBAT")


def test_seri_cek_dogru_deger_dondurur():
    oturum = SahteOturum(_tek_aylik_liste_html(), {"XLS-SUBAT": _ek_dosyasi_baytlari()})
    df = seri_cek(epdk_seri(epdk_olcut="rafineri-uretimi", epdk_urun="motorin"),
                   onbellek={}, session=oturum)
    assert list(df["date"]) == ["2026-02-01"]
    assert df["value"].iloc[0] == pytest.approx(1203133.818)


def test_seri_cek_onbellegi_paylasir():
    """20 seri aynı dosya kümesini paylaşır; ikinci seri hiç indirmemeli."""
    oturum = SahteOturum(_tek_aylik_liste_html(), {"XLS-SUBAT": _ek_dosyasi_baytlari()})
    onbellek = {}
    seri_cek(epdk_seri(epdk_olcut="rafineri-uretimi", epdk_urun="motorin"),
             onbellek=onbellek, session=oturum)
    cagri_sayisi = len(oturum.cagrilar)
    seri_cek(epdk_seri(epdk_olcut="ithalat", epdk_urun="benzin"),
             onbellek=onbellek, session=oturum)
    assert len(oturum.cagrilar) == cagri_sayisi


def test_seri_cek_start_date_oncesini_kirpar():
    html = (
        _ay_girdisi_html(2026, "Ocak", data_id="1", excel_id="XLS-OCAK")
        + _ay_girdisi_html(2026, "Şubat", data_id="2", excel_id="XLS-SUBAT")
    )
    oturum = SahteOturum(html, {
        "XLS-OCAK": _ek_dosyasi_baytlari(), "XLS-SUBAT": _ek_dosyasi_baytlari(),
    })
    df = seri_cek(epdk_seri(start_date="2026-02-01"), onbellek={}, session=oturum)
    assert list(df["date"]) == ["2026-02-01"]


def test_seri_cek_liste_http_hatasi_yukselir():
    oturum = SahteOturum("", {})
    # 200 dönmeyen liste isteği simüle etmek için özel bir sahte oturum:
    class Hatali:
        def get(self, url, timeout=None):
            return SahteYanit(503)
    with pytest.raises(RuntimeError, match="HTTP 503"):
        seri_cek(epdk_seri(), onbellek={}, session=Hatali())


def test_seri_cek_dosya_indirme_hatasi_yukselir():
    class YarimOturum:
        def get(self, url, timeout=None):
            if url.endswith("petrolaylik-sektor-raporu"):
                return SahteYanit(200, text=_tek_aylik_liste_html())
            return SahteYanit(404)
    with pytest.raises(RuntimeError, match="HTTP 404"):
        seri_cek(epdk_seri(), onbellek={}, session=YarimOturum())


def test_seri_cek_bilinmeyen_kombinasyonda_hata():
    oturum = SahteOturum(_tek_aylik_liste_html(), {"XLS-SUBAT": _ek_dosyasi_baytlari()})
    with pytest.raises(RuntimeError, match="bulunamadı"):
        seri_cek(epdk_seri(epdk_urun="yanlis-urun"), onbellek={}, session=oturum)


def test_seri_cek_eski_format_donemlerini_eler():
    """2025 girdisi listede olsa da eski formatta olduğundan hiç indirilmemeli."""
    html = (
        _ay_girdisi_html(2025, "Aralık", data_id="1", excel_id="ESKI-FORMAT")
        + _ay_girdisi_html(2026, "Ocak", data_id="2", excel_id="XLS-OCAK")
    )
    oturum = SahteOturum(html, {"XLS-OCAK": _ek_dosyasi_baytlari()})
    df = seri_cek(epdk_seri(), onbellek={}, session=oturum)
    assert list(df["date"]) == ["2026-01-01"]
    assert not any("ESKI-FORMAT" in c for c in oturum.cagrilar)
