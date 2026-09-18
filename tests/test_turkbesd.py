"""TÜRKBESD (Türkiye Beyaz Eşya Sanayicileri Derneği) yıllık ürün kırılımı
istemcisi testleri."""

import io
from types import SimpleNamespace

import openpyxl
import pytest

from ingest.turkbesd import (
    _baglantilari_cikar,
    seri_cek,
    yil_verisini_ayikla,
)


def turkbesd_seri(**kwargs):
    varsayilan = dict(
        id="test/ic-satis-buzdolabi",
        turkbesd_olcut="ic-satis",
        turkbesd_urun="buzdolabi",
        start_date=None,
    )
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


def _sayfa_html(olcutler):
    """`olcutler`: iterable of (anchor, xlsx_url) — sayfanın İNDİR bağlantıları."""
    bloklar = "".join(
        f"<div id='{anchor}' title='x'>\n"
        f'    <a class="downloadExcel" href="{url}" target="_blank" title="x">İNDİR</a>\n'
        "</div>\n"
        for anchor, url in olcutler
    )
    return f"<html><body>{bloklar}</body></html>"


def _xlsx_bytes(baslik, urun_satirlari, yillar=(2024, 2025)):
    """`urun_satirlari`: [(etiket, [değerler])] — İ, IE ürün satırı + TOPLAM."""
    kitap = openpyxl.Workbook()
    sayfa = kitap.active
    sayfa.append([baslik, *yillar])
    for etiket, degerler in urun_satirlari:
        sayfa.append([etiket, *degerler])
    tampon = io.BytesIO()
    kitap.save(tampon)
    return tampon.getvalue()


_TAM_URUN_SATIRLARI = [
    ("BUZDOLABI", [100, 110]),
    ("DERİN DONDURUCU", [10, 11]),
    ("ÇAMAŞIR MAKİNESİ", [20, 22]),
    ("BULAŞIK MAKİNESİ", [30, 33]),
    ("FIRIN", [40, 44]),
    ("KURUTUCU", [50, 55]),
    ("TOPLAM", [250, 275]),
]


# --- _baglantilari_cikar: sayfadan 4 İNDİR bağlantısını kazıma ---


def test_baglantilari_cikar_dort_olcutu_bulur():
    html = _sayfa_html(
        [
            ("ic-satis", "/upload/a-icsatis-1.xlsx"),
            ("uretim", "/upload/b-uretim-2.xlsx"),
            ("ihracat", "/upload/c-ihracat-3.xlsx"),
            ("ithalat", "/upload/d-ithalat-4.xlsx"),
        ]
    )
    assert _baglantilari_cikar(html) == {
        "ic-satis": "/upload/a-icsatis-1.xlsx",
        "uretim": "/upload/b-uretim-2.xlsx",
        "ihracat": "/upload/c-ihracat-3.xlsx",
        "ithalat": "/upload/d-ithalat-4.xlsx",
    }


def test_baglantilari_cikar_eksik_anchorda_hata():
    html = _sayfa_html([("ic-satis", "/upload/a.xlsx")])
    with pytest.raises(RuntimeError, match="bulunamadı"):
        _baglantilari_cikar(html)


# --- yil_verisini_ayikla: XLSX şablonu ---


def test_yil_verisini_ayikla_dogru_degerleri_cikarir():
    baytlar = _xlsx_bytes("İÇ SATIŞ", _TAM_URUN_SATIRLARI)
    sonuc = yil_verisini_ayikla(baytlar, "ic-satis")
    assert sonuc["buzdolabi"] == {2024: 100.0, 2025: 110.0}
    assert sonuc["kurutucu"] == {2024: 50.0, 2025: 55.0}
    assert "TOPLAM" not in sonuc  # toplam satırı hiçbir seriye eşlenmez


def test_yil_verisini_ayikla_baslik_kaymasinda_hata():
    baytlar = _xlsx_bytes("YANLIŞ BAŞLIK", _TAM_URUN_SATIRLARI)
    with pytest.raises(RuntimeError, match="başlığı"):
        yil_verisini_ayikla(baytlar, "ic-satis")


def test_yil_verisini_ayikla_urun_satiri_eksikse_hata():
    eksik = [s for s in _TAM_URUN_SATIRLARI if s[0] != "KURUTUCU"]
    baytlar = _xlsx_bytes("İÇ SATIŞ", eksik)
    with pytest.raises(RuntimeError, match="kurutucu"):
        yil_verisini_ayikla(baytlar, "ic-satis")


def test_yil_verisini_ayikla_toplam_satiri_eksikse_hata():
    eksik = [s for s in _TAM_URUN_SATIRLARI if s[0] != "TOPLAM"]
    baytlar = _xlsx_bytes("İÇ SATIŞ", eksik)
    with pytest.raises(RuntimeError, match="TOPLAM"):
        yil_verisini_ayikla(baytlar, "ic-satis")


# --- seri_cek: ağ kabuğu + önbellek ---


class SahteYanit:
    def __init__(self, status_code=200, text="", content=b""):
        self.status_code = status_code
        self.text = text
        self.content = content


class SahteOturum:
    """XLSX içeriği ölçüt bazında sabit; her ölçüt kendi (baslik, satirlar)
    çiftini taşır — gerçek TÜRKBESD'in 4 ayrı dosyasını simüle eder."""

    def __init__(self, sayfa_html, xlsx_icerikleri):
        self.sayfa_html = sayfa_html
        self.xlsx_icerikleri = xlsx_icerikleri  # {url: bytes}
        self.cagrilar = []

    def get(self, url, timeout=None):
        self.cagrilar.append(url)
        if url.endswith("turkbesd-son-5-yilin-rakamlari/"):
            return SahteYanit(text=self.sayfa_html)
        return SahteYanit(content=self.xlsx_icerikleri[url])


def _standart_oturum():
    html = _sayfa_html(
        [
            ("ic-satis", "https://www.turkbesd.org/upload/icsatis.xlsx"),
            ("uretim", "https://www.turkbesd.org/upload/uretim.xlsx"),
            ("ihracat", "https://www.turkbesd.org/upload/ihracat.xlsx"),
            ("ithalat", "https://www.turkbesd.org/upload/ithalat.xlsx"),
        ]
    )
    icerikler = {
        "https://www.turkbesd.org/upload/icsatis.xlsx": _xlsx_bytes(
            "İÇ SATIŞ", _TAM_URUN_SATIRLARI
        ),
        "https://www.turkbesd.org/upload/uretim.xlsx": _xlsx_bytes(
            "ÜRETİM", _TAM_URUN_SATIRLARI
        ),
        "https://www.turkbesd.org/upload/ihracat.xlsx": _xlsx_bytes(
            "İHRACAT", _TAM_URUN_SATIRLARI
        ),
        "https://www.turkbesd.org/upload/ithalat.xlsx": _xlsx_bytes(
            "İTHALAT", _TAM_URUN_SATIRLARI
        ),
    }
    return SahteOturum(html, icerikler)


def test_seri_cek_dogru_deger_dondurur():
    oturum = _standart_oturum()
    df = seri_cek(turkbesd_seri(), onbellek={}, session=oturum)
    assert list(df["date"]) == ["2024-01-01", "2025-01-01"]
    assert list(df["value"]) == [100.0, 110.0]


def test_seri_cek_start_date_filtreler():
    oturum = _standart_oturum()
    df = seri_cek(
        turkbesd_seri(start_date="2025-01-01"), onbellek={}, session=oturum
    )
    assert list(df["date"]) == ["2025-01-01"]


def test_seri_cek_onbellek_ayni_xlsxi_tekrar_indirmez():
    """24 seri (6 ürün × 4 ölçüt) 4 dosyayı paylaşır: aynı ölçütün 6 ürünü
    tek indirme yapmalı."""
    oturum = _standart_oturum()
    onbellek: dict = {}
    for urun in ("buzdolabi", "derin-dondurucu", "camasir-makinesi",
                 "bulasik-makinesi", "firin", "kurutucu"):
        seri_cek(
            turkbesd_seri(turkbesd_olcut="ic-satis", turkbesd_urun=urun),
            onbellek=onbellek, session=oturum,
        )
    # sayfa HTML'i 1 kez, ic-satis XLSX'i 1 kez = 2 ağ çağrısı (6 ürün için değil).
    assert len(oturum.cagrilar) == 2


def test_seri_cek_bilinmeyen_urunde_hata():
    oturum = _standart_oturum()
    with pytest.raises(RuntimeError, match="hiç veri bulunamadı"):
        seri_cek(
            turkbesd_seri(turkbesd_urun="yok-olan-urun"),
            onbellek={}, session=oturum,
        )
