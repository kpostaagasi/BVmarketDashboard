"""DHMİ 6 büyük havalimanı trafik istemcisi testleri.

Bülten baytları openpyxl ile üretilir: gerçek dosyanın şablonu (satır 1 =
dönem başlıkları — "<yıl> <AY> SONU" / "<yıl> YILI <AY> SONU (Kesin
Olmayan)" — satır 2 = İç Hat/Dış Hat/Toplam alt başlıkları, ardından
havalimanı satırları). Gerçek dosyada ölçülen tuhaflık (bazı havalimanı
adları "(*)" ekiyle gelir, ör. "İstanbul Sabiha Gökçen (*)") regresyon
testi olarak sabitlenmiştir.
"""

from __future__ import annotations

import io
from types import SimpleNamespace

import openpyxl
import pytest

from ingest.dhmi import (
    SAYFA,
    _donem_coz,
    _sayfa_noktalari,
    dosya_listesi,
    seri_cek,
)

_HAVALIMANLARI_HAM = (
    ("İstanbul (*)", 100.0, 200.0),
    ("İstanbul Sabiha Gökçen (*)", 10.0, 20.0),
    ("Ankara Esenboğa", 5.0, 5.0),
    ("İzmir Adnan Menderes", 3.0, 3.0),
    ("Antalya", 8.0, 8.0),
    ("Muğla Dalaman", 1.0, 1.0),
)


def _kargo_satiri(ad, ic_karsi, dis_karsi, ic_cari, dis_cari):
    return (
        ad,
        ic_karsi, dis_karsi, ic_karsi + dis_karsi,
        ic_cari, dis_cari, ic_cari + dis_cari,
        0.0, 0.0, 0.0,
    )


def _sayfa_govdesi(yil_karsi: int, yil_cari: int, ay: str, carpan: float = 1.0):
    satirlar = [
        ("YOLCU TRAFİĞİ (Gelen-Giden)",) + (None,) * 9,
        ("Havalimanları ", f"{yil_karsi} {ay} SONU\n", None, None,
         f"{yil_cari} YILI {ay} SONU\n(Kesin Olmayan)", None, None, None, None, None),
        (None, "İç Hat", "Dış Hat", "Toplam", "İç Hat", "Dış Hat", "Toplam",
         "İç Hat", "Dış Hat", "Toplam"),
    ]
    for ad, ic, dis in _HAVALIMANLARI_HAM:
        satirlar.append(_kargo_satiri(ad, ic, dis, ic * carpan, dis * carpan))
    satirlar.append(("TÜRKİYE GENELİ", 0, 0, 0, 0, 0, 0, 0, 0, 0))
    return satirlar


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


def dhmi_seri(**kwargs):
    varsayilan = dict(id="havacilik/dhmi-6-buyuk-havalimani-yolcu-toplam", dhmi_olcut="yolcu-toplam")
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


class SahteYanit:
    def __init__(self, content=b"", text="", status_code=200):
        self.content = content
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class SahteOturum:
    def __init__(self, sayfa_html, dosya_baytlar: dict):
        self.sayfa_html = sayfa_html
        self.dosya_baytlar = dosya_baytlar
        self.calls: list[str] = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        if url == SAYFA:
            return SahteYanit(text=self.sayfa_html, status_code=200)
        return SahteYanit(content=self.dosya_baytlar[url], status_code=200)


def _sayfa_html(urls: list[str]) -> str:
    # Gerçek sayfa "Ü" gibi karakterleri HTML entity ile kodluyor
    # (&#220;) — dosya_listesi bunu html.unescape ile çözer.
    linkler = "".join(f'<a href="{u}">TÜMÜ.xlsx</a>' for u in urls)
    return f"<html><body>{linkler}</body></html>"


# --- _donem_coz ---


def test_donem_coz_ay_ve_yili_ayirir():
    assert _donem_coz("2026 YILI AĞUSTOS SONU\n(Kesin Olmayan)") == (2026, "AĞUSTOS")
    assert _donem_coz("2025 OCAK SONU\n") == (2025, "OCAK")


def test_donem_coz_ay_bulunamazsa_hata():
    with pytest.raises(RuntimeError, match="dönem başlığı çözülemedi"):
        _donem_coz("2026 BİLİNMEYEN SONU")


# --- _sayfa_noktalari: şablon kayması ---


def test_sayfa_noktalari_olmayan_sayfa_hata():
    baytlar = _kitap_baytlari({"KARGO": _sayfa_govdesi(2025, 2026, "TEMMUZ")})
    with pytest.raises(RuntimeError, match="'YOLCU' sayfası yok"):
        _sayfa_noktalari(baytlar, "YOLCU")


def test_sayfa_noktalari_sutun_sablonu_degisirse_hata():
    govde = _sayfa_govdesi(2025, 2026, "TEMMUZ")
    satirlar = [list(s) for s in govde]
    satirlar[2][1] = "Beklenmeyen Başlık"
    baytlar = _kitap_baytlari({"YOLCU": [tuple(s) for s in satirlar]})
    with pytest.raises(RuntimeError, match="sütun şablonu değişmiş"):
        _sayfa_noktalari(baytlar, "YOLCU")


def test_sayfa_noktalari_havalimani_satiri_eksikse_hata():
    govde = [s for s in _sayfa_govdesi(2025, 2026, "TEMMUZ") if "Antalya" not in str(s[0])]
    baytlar = _kitap_baytlari({"YOLCU": govde})
    with pytest.raises(RuntimeError, match="'Antalya' havalimanı satırı yok"):
        _sayfa_noktalari(baytlar, "YOLCU")


def test_sayfa_noktalari_iki_yil_farkli_ay_gosterirse_hata():
    govde = _sayfa_govdesi(2025, 2026, "TEMMUZ")
    satirlar = [list(s) for s in govde]
    satirlar[1][4] = "2026 YILI AĞUSTOS SONU\n(Kesin Olmayan)"
    baytlar = _kitap_baytlari({"YOLCU": [tuple(s) for s in satirlar]})
    with pytest.raises(RuntimeError, match="farklı ayı gösteriyor"):
        _sayfa_noktalari(baytlar, "YOLCU")


def test_sayfa_noktalari_yildizli_havalimani_adi_normalize_edilir():
    baytlar = _kitap_baytlari({"YOLCU": _sayfa_govdesi(2025, 2026, "TEMMUZ")})
    noktalar = _sayfa_noktalari(baytlar, "YOLCU")
    # "İstanbul Sabiha Gökçen (*)" -> kısa ad "sabiha-gokcen" ile eşleşmeli
    assert noktalar[(2026, "TEMMUZ")]["sabiha-gokcen"] == (10.0, 20.0, 30.0)


# --- dosya_listesi ---


def test_dosya_listesi_html_entity_cozer():
    html = '<a href="https://www.dhmi.gov.tr/Lists/Istatislikler/Attachments/442/T&#220;M&#220;.xlsx">x</a>'
    oturum = SahteOturum(html, {})
    assert dosya_listesi(session=oturum) == [
        "https://www.dhmi.gov.tr/Lists/Istatislikler/Attachments/442/TÜMÜ.xlsx"
    ]


# --- seri_cek: uçtan uca aylık akış ---


def test_seri_cek_ardisik_kumulatif_farki_aylik_akisa_cevirir():
    """6 havalimanının TOPLAM'ı: Ocak kümülatifi kendisi, Şubat farkı alınır."""
    url_ocak = "https://www.dhmi.gov.tr/Lists/Istatislikler/Attachments/1/TÜMÜ.xlsx"
    url_subat = "https://www.dhmi.gov.tr/Lists/Istatislikler/Attachments/2/TÜMÜ.xlsx"
    baytlar = {
        url_ocak: _kitap_baytlari({"YOLCU": _sayfa_govdesi(2025, 2026, "OCAK", carpan=1.0)}),
        url_subat: _kitap_baytlari({"YOLCU": _sayfa_govdesi(2025, 2026, "ŞUBAT", carpan=2.0)}),
    }
    oturum = SahteOturum(_sayfa_html([url_ocak, url_subat]), baytlar)
    df = seri_cek(dhmi_seri(dhmi_olcut="yolcu-toplam"), onbellek={}, session=oturum)

    # 6 havalimanının cari-yıl Toplam'ları: (100+200)+(10+20)+(5+5)+(3+3)+(8+8)+(1+1) = 364
    ocak_toplam = 364.0
    subat_toplam = 364.0 * 2  # carpan=2.0
    satir_ocak = df[df["date"] == "2026-01-01"].iloc[0]
    satir_subat = df[df["date"] == "2026-02-01"].iloc[0]
    assert satir_ocak["value"] == ocak_toplam
    assert satir_subat["value"] == subat_toplam - ocak_toplam


def test_seri_cek_dis_hat_olcutu_sadece_dis_hat_kolonunu_toplar():
    url = "https://www.dhmi.gov.tr/Lists/Istatislikler/Attachments/1/TÜMÜ.xlsx"
    baytlar = {url: _kitap_baytlari({"YOLCU": _sayfa_govdesi(2025, 2026, "OCAK", carpan=2.0)})}
    oturum = SahteOturum(_sayfa_html([url]), baytlar)
    df = seri_cek(dhmi_seri(dhmi_olcut="yolcu-dis-hat"), onbellek={}, session=oturum)
    # Dış Hat toplamı (cari yıl, carpan=2): (200+20+5+3+8+1)*2 = 474
    satir_2026 = df[df["date"] == "2026-01-01"].iloc[0]
    assert satir_2026["value"] == 474.0


def test_seri_cek_farkli_sayfa_gerektiren_olcutler_ayri_sayfa_okur():
    url = "https://www.dhmi.gov.tr/Lists/Istatislikler/Attachments/1/TÜMÜ.xlsx"
    baytlar = {
        url: _kitap_baytlari({
            "YOLCU": _sayfa_govdesi(2025, 2026, "OCAK"),
            "KARGO": _sayfa_govdesi(2025, 2026, "OCAK", carpan=3.0),
        })
    }
    oturum = SahteOturum(_sayfa_html([url]), baytlar)
    df_yolcu = seri_cek(dhmi_seri(dhmi_olcut="yolcu-toplam"), onbellek={}, session=oturum)
    df_kargo = seri_cek(dhmi_seri(dhmi_olcut="kargo-toplam"), onbellek={}, session=oturum)
    yolcu_2026 = df_yolcu[df_yolcu["date"] == "2026-01-01"]["value"].iloc[0]
    kargo_2026 = df_kargo[df_kargo["date"] == "2026-01-01"]["value"].iloc[0]
    assert kargo_2026 == yolcu_2026 * 3.0


def test_seri_cek_onbellegi_dosya_listesini_ve_baytlari_paylasir():
    url = "https://www.dhmi.gov.tr/Lists/Istatislikler/Attachments/1/TÜMÜ.xlsx"
    baytlar = {url: _kitap_baytlari({
        "YOLCU": _sayfa_govdesi(2025, 2026, "OCAK"),
        "KARGO": _sayfa_govdesi(2025, 2026, "OCAK"),
    })}
    oturum = SahteOturum(_sayfa_html([url]), baytlar)
    onbellek: dict = {}
    seri_cek(dhmi_seri(dhmi_olcut="yolcu-toplam"), onbellek=onbellek, session=oturum)
    ilk_cagri = len(oturum.calls)
    seri_cek(dhmi_seri(dhmi_olcut="kargo-toplam"), onbellek=onbellek, session=oturum)
    assert len(oturum.calls) == ilk_cagri, "ikinci seri sayfayı/dosyayı yeniden indirmemeli"


def test_dosya_listesi_http_hatasi_yukselir():
    oturum = SahteOturum("", {})
    oturum.get = lambda url, timeout=None: SahteYanit(status_code=500)
    with pytest.raises(RuntimeError, match="HTTP 500"):
        dosya_listesi(session=oturum)
