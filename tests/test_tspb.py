"""TSPB (`ingest/tspb.py`) "Veriler" sayfası istemcisi testleri.

Kapsam: "PYŞ Aylık" grup/kategori sütun haritalama (fazladan "Ortalama
Portföy Büyüklüğü" grubunun — aynı kategori sırasını taşısa da —
kullanılmayan bir grup olarak zararsızca haritaya girmesi; şablon
kayması durumunda gerçekten eksik bir grubun RuntimeError vermesi),
"Krediler" sayfasının 2025-öncesi ÇEYREKSEL (çeyrek sonu ayı -> çeyrek
ilk ayı kaydırması) / 2025+ AYLIK karma tarih biçimi, ARŞİV+GÜNCEL dosya
birleştirmesi ve `seri_cek`'in ağ/önbellek davranışı.
"""

import io
from types import SimpleNamespace

import openpyxl
import pytest

from ingest.tspb import (
    VERILER_API_URL,
    _baglanti_bul,
    _kredili_kolon_haritasi,
    _kredili_satirlarini_cikar,
    _pys_kolon_haritasi,
    _pys_satirlarini_cikar,
    _PYS_ARSIV,
    _PYS_GUNCEL,
    seri_cek,
)


def _kitap_baytlari(sayfalar: dict) -> bytes:
    kitap = openpyxl.Workbook()
    kitap.remove(kitap.active)
    for ad, satirlar in sayfalar.items():
        sayfa = kitap.create_sheet(ad)
        for satir in satirlar:
            sayfa.append(list(satir))
    tampon = io.BytesIO()
    kitap.save(tampon)
    return tampon.getvalue()


def _kitabi_ac(sayfalar: dict):
    return openpyxl.load_workbook(io.BytesIO(_kitap_baytlari(sayfalar)), data_only=True)


class SahteYanit:
    def __init__(self, content=b"", data=None, status_code=200):
        self.content = content
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data


class SahteOturum:
    def __init__(self, yanit_haritasi):
        self.yanit_haritasi = yanit_haritasi
        self.cagrilar = []

    def get(self, url, timeout=None, headers=None):
        self.cagrilar.append(url)
        return self.yanit_haritasi[url]


def tspb_seri(**kwargs):
    varsayilan = dict(
        id="tspb/x", tspb_tablo="portfoy-buyuklugu", tspb_kategori="toplam", start_date=None,
    )
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


# --- "PYŞ Aylık" sayfası: satır 4 (grup) + satır 6 (kategori) düzeni ---

# Gerçek dosyadaki sabit kategori sırası (bkz. ingest/tspb.py PYS_KOLON_ETIKETLERI).
_KATEGORI_SIRASI = [
    "Bireysel Portföy Yönetimi", "Yatırım Ortaklığı", "Emeklilik Yatırım Fonu",
    "Yatırım Fonu", "Toplam",
]
_MUSTERI_GRUBU = " Ay Sonu Müşteri / Fon Sayısı"
_AUM_GRUBU = " Ay Sonu Portföy Büyüklüğü (TL)"
_ORTALAMA_GRUBU = "Aylık Ortalama Portföy Büyüklüğü (TL)"
_GELIR_GRUBU = "PYŞ'lerin Aylık Portföy Yönetimi Geliri (TL)"


def _pys_basliklari(grup_etiketleri: list[str]) -> tuple[tuple, tuple, dict[str, int]]:
    """`grup_etiketleri` sırasıyla hizalı (grup_satiri, kategori_satiri,
    {grup: baslangic_sutunu}) üretir. Her grup TAM 6 sütun kaplar (5
    kategori + 1 ayraç None) — gerçek dosyadaki gibi grup_satiri ve
    kategori_satiri HER ZAMAN aynı uzunlukta kalır.
    """
    grup_satiri: list = [None, None]
    kategori_satiri: list = [None, None]
    baslangiclar: dict[str, int] = {}
    for etiket in grup_etiketleri:
        baslangiclar[etiket] = len(grup_satiri)
        grup_satiri.append(etiket)
        grup_satiri.extend([None] * 5)
        kategori_satiri.extend(_KATEGORI_SIRASI)
        kategori_satiri.append(None)
    return tuple(grup_satiri), tuple(kategori_satiri), baslangiclar


def _pys_veri_satiri(tarih: str, grup_degerleri: dict[str, dict], baslangiclar: dict, uzunluk: int):
    """`{grup: {kategori: değer}}`den, `_pys_basliklari` ile aynı hizada
    tek bir veri satırı üretir."""
    satir = [None] * uzunluk
    satir[1] = tarih
    for grup, degerler in grup_degerleri.items():
        taban = baslangiclar[grup]
        for off, kategori in enumerate(_KATEGORI_SIRASI):
            if kategori in degerler:
                satir[taban + off] = degerler[kategori]
    return tuple(satir)


def _pys_kitabi(grup_etiketleri: list[str], veri_satirlari: list[tuple[str, dict]]):
    grup_satiri, kategori_satiri, baslangiclar = _pys_basliklari(grup_etiketleri)
    uzunluk = len(grup_satiri)
    ust_basliklar = [
        (None,),
        (None, "PORTFÖY YÖNETİM ŞİRKETLERİ - AYLIK ÖZET VERİLER"),
        (None, "ASSET MANAGEMENT COMPANIES - MONTHLY SUMMARY DATA"),
        grup_satiri,
        (None, "Tarih"),
        kategori_satiri,
        (None,),
    ]
    veriler = [_pys_veri_satiri(t, g, baslangiclar, uzunluk) for t, g in veri_satirlari]
    return _kitabi_ac({"PYŞ Aylık": ust_basliklar + veriler}), baslangiclar


def test_pys_kolon_haritasi_ortalama_grubu_kullanilmadan_haritaya_girer():
    """'Ortalama Portföy Büyüklüğü' de AYNI 5'li kategori sırasını taşır —
    filtre bunu ELEMEZ, sadece `PYS_TABLO_GRUP_BASLIGI` onu referans
    almadığı için zararsızca kullanılmaz kalır."""
    grup_satiri, kategori_satiri, _ = _pys_basliklari([_MUSTERI_GRUBU, _AUM_GRUBU, _ORTALAMA_GRUBU])
    satirlar = [None, None, None, grup_satiri, None, kategori_satiri, None]
    harita = _pys_kolon_haritasi(satirlar)
    assert set(harita) == {
        "Ay Sonu Müşteri / Fon Sayısı", "Ay Sonu Portföy Büyüklüğü (TL)",
        "Aylık Ortalama Portföy Büyüklüğü (TL)",
    }
    assert harita["Ay Sonu Portföy Büyüklüğü (TL)"]["Toplam"] == 12


def test_pys_kolon_haritasi_farkli_kategori_sirali_grubu_atlar():
    """Gerçek dosyadaki 'Yatırım Fonu Yönetimi Geliri Dağılımı' grubu
    (Kurucu/Yönetici/Dağıtıcı/Toplam) beklenen 5'li sırayla eşleşmez —
    haritaya asla girmez."""
    grup_satiri = (None, None, "Farklı Grup", None, None, None, None, None)
    kategori_satiri = (None, None, "Kurucu", "Yönetici", "Dağıtıcı", "Toplam", None, None)
    satirlar = [None, None, None, grup_satiri, None, kategori_satiri, None]
    assert _pys_kolon_haritasi(satirlar) == {}


def test_pys_satirlarini_cikar_musteri_grubu_eksikse_hata():
    """Portföy Yönetimi Geliri grubu (şablon kayması) hiç yoksa sessizce
    eksik veri üretmez, RuntimeError yükseltir."""
    kitap, baslangiclar = _pys_kitabi([_MUSTERI_GRUBU, _AUM_GRUBU], [
        ("202601", {_MUSTERI_GRUBU: {"Toplam": 100.0}, _AUM_GRUBU: {"Toplam": 10.0}}),
    ])
    with pytest.raises(RuntimeError, match="Portföy Yönetimi Geliri"):
        _pys_satirlarini_cikar(kitap)


def test_pys_satirlarini_cikar_tarih_ve_deger_dogru_okunur():
    kitap, _ = _pys_kitabi([_MUSTERI_GRUBU, _AUM_GRUBU, _GELIR_GRUBU], [
        ("202601", {
            _MUSTERI_GRUBU: {"Toplam": 100.0},
            _AUM_GRUBU: {
                "Bireysel Portföy Yönetimi": 1.0, "Yatırım Ortaklığı": 2.0,
                "Emeklilik Yatırım Fonu": 3.0, "Yatırım Fonu": 4.0, "Toplam": 10.0,
            },
            _GELIR_GRUBU: {"Toplam": 5.0},
        }),
        ("202602", {
            _MUSTERI_GRUBU: {"Toplam": 110.0},
            _AUM_GRUBU: {"Toplam": 12.0},
            _GELIR_GRUBU: {"Toplam": 6.0},
        }),
    ])
    satirlar = _pys_satirlarini_cikar(kitap)
    assert [t for t, _ in satirlar] == ["2026-01-01", "2026-02-01"]
    ilk = satirlar[0][1]
    assert ilk[_AUM_GRUBU.strip()] == {
        "Bireysel Portföy Yönetimi": 1.0, "Yatırım Ortaklığı": 2.0,
        "Emeklilik Yatırım Fonu": 3.0, "Yatırım Fonu": 4.0, "Toplam": 10.0,
    }
    assert ilk[_MUSTERI_GRUBU.strip()]["Toplam"] == 100.0


def test_pys_satirlarini_cikar_tarihsiz_satiri_atlar():
    kitap, _ = _pys_kitabi([_MUSTERI_GRUBU, _AUM_GRUBU, _GELIR_GRUBU], [
        ("202601", {_MUSTERI_GRUBU: {"Toplam": 100.0}, _AUM_GRUBU: {"Toplam": 10.0}, _GELIR_GRUBU: {"Toplam": 5.0}}),
    ])
    # "Kaynak: TSPB" gibi alt bilgi satırları da workbook'a eklenip
    # tarih deseniyle eşleşmediği için atlanmalı.
    ws = kitap["PYŞ Aylık"]
    ws.append([None, "Kaynak: TSPB"])
    satirlar = _pys_satirlarini_cikar(kitap)
    assert len(satirlar) == 1


# --- "Krediler" sayfası: karma çeyreksel/aylık tarih biçimi ---


_KREDILI_BASLIK = [
    (None, "ARACI KURUMLAR - KREDİLİ İŞLEMLER"),
    (None, "BROKERAGE FIRMS - MARGIN TRADING"),
    (None,),
    (None, None, "Aracı Kurum Sayısı*", "Kredi Sözleşmeli Yatırımcı Sayısı",
     "Kredi Kullanan Yatırımcı Sayısı", "Kredi Hacmi (TL)", "Yatırımcı Başına Kredi Hacmi (TL)"),
    (None, "Tarih", "No. of Brokerage Firms*", "...", "...", "...", "..."),
]


def test_kredili_kolon_haritasi_yildizli_ve_birimli_etiketleri_bulur():
    harita = _kredili_kolon_haritasi(_KREDILI_BASLIK)
    assert harita == {
        "araci-kurum-sayisi": 2, "sozlesmeli-yatirimci-sayisi": 3,
        "kullanan-yatirimci-sayisi": 4, "kredi-hacmi": 5,
    }


def test_kredili_kolon_haritasi_sutun_yoksa_hata():
    baslik_kredi_hacmi_olmadan = _KREDILI_BASLIK[:3] + [
        (None, None, "Aracı Kurum Sayısı*", "Kredi Sözleşmeli Yatırımcı Sayısı",
         "Kredi Kullanan Yatırımcı Sayısı"),
    ]
    with pytest.raises(RuntimeError, match="Kredi Hacmi"):
        _kredili_kolon_haritasi(baslik_kredi_hacmi_olmadan)


def test_kredili_satirlarini_cikar_ceyrek_sonu_ayi_ceyrek_ilk_ayina_kaydirilir():
    """2024 çeyreksel dönem: '2024-12' (Q4 sonu) -> '2024-10-01' (Q4 ilk ayı)."""
    kitap = _kitabi_ac({"Krediler": _KREDILI_BASLIK + [
        (None, "2024-12", 51, 586955, 43576, 62656227330, 1437860.9),
    ]})
    satirlar = _kredili_satirlarini_cikar(kitap)
    assert satirlar == [("2024-10-01", {
        "araci-kurum-sayisi": 51, "sozlesmeli-yatirimci-sayisi": 586955,
        "kullanan-yatirimci-sayisi": 43576, "kredi-hacmi": 62656227330,
    })]


def test_kredili_satirlarini_cikar_2025_sonrasi_aylik_ay_degismez():
    """2025+ '2025 - 01' (boşluklu tire) biçimi zaten aylık; ay kaydırılmaz."""
    kitap = _kitabi_ac({"Krediler": _KREDILI_BASLIK + [
        (None, "2025 - 01", 51, 549403, 46096, 66543212761, 1443578.9),
    ]})
    satirlar = _kredili_satirlarini_cikar(kitap)
    assert satirlar[0][0] == "2025-01-01"


def test_kredili_satirlarini_cikar_ceyreksel_donemde_beklenmeyen_ay_hata():
    kitap = _kitabi_ac({"Krediler": _KREDILI_BASLIK + [
        (None, "2024-05", 51, 1, 1, 1, 1),
    ]})
    with pytest.raises(RuntimeError, match="beklenmeyen ay"):
        _kredili_satirlarini_cikar(kitap)


def test_kredili_satirlarini_cikar_arsiv_ve_guncel_araliksiz_birlesir():
    arsiv = _kitabi_ac({"Krediler": _KREDILI_BASLIK + [
        (None, "2024-12", 51, 100, 10, 1000.0, 100.0),
    ]})
    guncel = _kitabi_ac({"Krediler": _KREDILI_BASLIK + [
        (None, "2025 - 01", 52, 200, 20, 2000.0, 100.0),
    ]})
    birlesik = _kredili_satirlarini_cikar(arsiv) + _kredili_satirlarini_cikar(guncel)
    assert [t for t, _ in birlesik] == ["2024-10-01", "2025-01-01"]


# --- _baglanti_bul: dört dosya deseninin regex eşleşmesi ---


def test_baglanti_bul_pys_guncel_ve_arsiv_desenleri_eslesir():
    html = (
        '<a href="https://tspb.org.tr/wp-content/uploads/2026/09/'
        'BTVY-PYS-Aylik-Veri-AMC-Monthly-Data_20260917_133802.xlsx">güncel</a>'
        '<a href="https://tspb.org.tr/wp-content/uploads/2026/02/'
        'BTVY-PYS-Aylik-Veri-AMC-Monthly-Data-201701-202512.xlsx">arşiv</a>'
    )
    assert _baglanti_bul(html, _PYS_GUNCEL, "x").endswith("20260917_133802.xlsx")
    assert _baglanti_bul(html, _PYS_ARSIV, "x").endswith("201701-202512.xlsx")


def test_baglanti_bul_bulunamazsa_hata():
    with pytest.raises(RuntimeError, match="test-dosyası"):
        _baglanti_bul("<html>boş</html>", _PYS_GUNCEL, "test-dosyası")


# --- seri_cek: ağ kabuğu + önbellek + iki dataset ---


def _wp_json_yaniti(html: str) -> SahteYanit:
    return SahteYanit(data=[{"content": {"rendered": html}}])


def _tam_test_ortami():
    """Tam bir koşuyu simüle eden sahte oturum: wp-json sayfası + PYŞ
    arşiv/güncel + Krediler arşiv/güncel — 5 URL."""
    pys_arsiv_url = "https://tspb.org.tr/wp-content/uploads/2026/02/BTVY-PYS-Aylik-Veri-AMC-Monthly-Data-201701-202512.xlsx"
    pys_guncel_url = "https://tspb.org.tr/wp-content/uploads/2026/09/BTVY-PYS-Aylik-Veri-AMC-Monthly-Data_20260917_133802.xlsx"
    kredili_arsiv_url = "https://tspb.org.tr/wp-content/uploads/2026/02/BTVY_Krediler_2002-202512.xlsx"
    kredili_guncel_url = "https://tspb.org.tr/wp-content/uploads/2026/09/BTVY_Araci_Kurumlarin_Kredili_Islemleri_20260914_080007.xlsx"
    html = (
        f'<a href="{pys_guncel_url}">güncel pys</a>'
        f'<a href="{pys_arsiv_url}">arşiv pys</a>'
        f'<a href="{kredili_guncel_url}">güncel kredili</a>'
        f'<a href="{kredili_arsiv_url}">arşiv kredili</a>'
    )
    gruplar = [_MUSTERI_GRUBU, _AUM_GRUBU, _GELIR_GRUBU]
    pys_arsiv_kitap, _ = _pys_kitabi(gruplar, [
        ("202512", {_MUSTERI_GRUBU: {"Toplam": 90.0}, _AUM_GRUBU: {"Toplam": 9.6}, _GELIR_GRUBU: {"Toplam": 4.0}}),
    ])
    pys_guncel_kitap, _ = _pys_kitabi(gruplar, [
        ("202601", {_MUSTERI_GRUBU: {"Toplam": 100.0}, _AUM_GRUBU: {"Toplam": 10.0}, _GELIR_GRUBU: {"Toplam": 5.0}}),
    ])
    kredili_arsiv_kitap = _kitap_baytlari({"Krediler": _KREDILI_BASLIK + [
        (None, "2024-12", 51, 586955, 43576, 62656227330.0, 1437860.9),
    ]})
    kredili_guncel_kitap = _kitap_baytlari({"Krediler": _KREDILI_BASLIK + [
        (None, "2025 - 01", 51, 549403, 46096, 66543212761.0, 1443578.9),
    ]})

    def _kitap_bayt(kitap):
        tampon = io.BytesIO()
        kitap.save(tampon)
        return tampon.getvalue()

    oturum = SahteOturum({
        VERILER_API_URL: _wp_json_yaniti(html),
        pys_arsiv_url: SahteYanit(content=_kitap_bayt(pys_arsiv_kitap)),
        pys_guncel_url: SahteYanit(content=_kitap_bayt(pys_guncel_kitap)),
        kredili_arsiv_url: SahteYanit(content=kredili_arsiv_kitap),
        kredili_guncel_url: SahteYanit(content=kredili_guncel_kitap),
    })
    return oturum


def test_seri_cek_pys_toplam_aum_dogru_deger_ve_onbellek_paylasir():
    oturum = _tam_test_ortami()
    onbellek = {}
    df = seri_cek(
        tspb_seri(tspb_tablo="portfoy-buyuklugu", tspb_kategori="toplam"),
        onbellek=onbellek, session=oturum,
    )
    assert list(df["date"]) == ["2025-12-01", "2026-01-01"]
    assert list(df["value"]) == [9.6, 10.0]
    cagri_sayisi = len(oturum.cagrilar)

    df2 = seri_cek(
        tspb_seri(tspb_tablo="musteri-fon-sayisi", tspb_kategori="toplam"),
        onbellek=onbellek, session=oturum,
    )
    assert list(df2["value"]) == [90.0, 100.0]
    assert len(oturum.cagrilar) == cagri_sayisi  # ikinci PYŞ serisi ağa çıkmadı


def test_seri_cek_kredili_dogru_deger_ve_pys_dosyalarini_cekmez():
    oturum = _tam_test_ortami()
    onbellek = {}
    df = seri_cek(
        tspb_seri(tspb_tablo="kredili", tspb_kategori="kullanan-yatirimci-sayisi"),
        onbellek=onbellek, session=oturum,
    )
    assert list(df["date"]) == ["2024-10-01", "2025-01-01"]
    assert list(df["value"]) == [43576, 46096]
    # wp-json + kredili arşiv + kredili güncel: PYŞ dosyaları hiç çekilmedi.
    assert len(oturum.cagrilar) == 3


def test_seri_cek_bilinmeyen_kategoride_hata():
    oturum = _tam_test_ortami()
    with pytest.raises(RuntimeError, match="tspb/x"):
        seri_cek(
            tspb_seri(tspb_tablo="kredili", tspb_kategori="olmayan-kategori"),
            onbellek={}, session=oturum,
        )


def test_seri_cek_start_date_oncesini_kirpar():
    oturum = _tam_test_ortami()
    df = seri_cek(
        tspb_seri(tspb_tablo="portfoy-buyuklugu", tspb_kategori="toplam", start_date="2026-01-01"),
        onbellek={}, session=oturum,
    )
    assert list(df["date"]) == ["2026-01-01"]
