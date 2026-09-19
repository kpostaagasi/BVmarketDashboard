"""ORGE Enerji çeyreklik Yatırımcı Sunumu istemcisi testleri."""

from datetime import date
from types import SimpleNamespace

import pytest

from ingest.orge import (
    _sunum_baglantilari,
    cekilecek_ceyrekler,
    deger_cek,
    seri_cek,
)

# pdfplumber ham metni örneği (2026 Ç2 sunumundan alınmış gerçek cümle
# yapısı — satır sonu "seviyesinde\nbulunmaktadır" arasında düşer).
_ORNEK_METIN = (
    "30.06.2026 tarihi itibarıyla Yeni Alınan İşler toplamımız 1.631.076.996 TL+KDV "
    "tutarındadır. Bu büyüklük 30.06.2025 tarihi itibarıyla 532.582.793 TL+KDV "
    "seviyesinde gerçekleşmişti.\n"
    "• 30.06.2026 tarihi itibarıyla Devam Eden İşler büyüklüğümüz (backlog) "
    "5.589.950.948 TL+KDV seviyesinde\nbulunmaktadır. Bu büyüklük 30.06.2025 "
    "tarihi itibarıyla 3.060.215.893 TL+KDV seviyesinde gerçekleşmişti."
)


# --- deger_cek: gerçek cümle yapısına karşı regex ---


def test_deger_cek_backlog():
    assert deger_cek(_ORNEK_METIN, "backlog") == pytest.approx(5589.950948)


def test_deger_cek_yeni_is_ytd():
    assert deger_cek(_ORNEK_METIN, "yeni-is-ytd") == pytest.approx(1631.076996)


def test_deger_cek_karsilastirma_cumlesini_degil_carisini_yakalar():
    """Cümlede İKİ 'tarihi itibarıyla ... TL+KDV' geçiyor (cari + geçen yıl
    karşılaştırması); yalnızca CARİ (etiketli) değer okunmalı."""
    assert deger_cek(_ORNEK_METIN, "backlog") != pytest.approx(3060.215893)


def test_deger_cek_sablon_degismisse_hata():
    with pytest.raises(RuntimeError, match="backlog.*bulunamadı|bulunamadı"):
        deger_cek("bu metinde beklenen ifade yok", "backlog")


# --- cekilecek_ceyrekler: gelecek çeyrek üretilmez ---


def test_cekilecek_ceyrekler_cari_ceyrekte_durur():
    donemler = cekilecek_ceyrekler(date(2026, 7, 15))  # Ç3 içinde
    assert donemler[-1] == (2026, 3)
    assert (2026, 4) not in donemler


# --- _sunum_baglantilari: sayfadan PDF bağlantılarını çıkarma ---


class _SahteYanit:
    def __init__(self, status_code=200, text="", content=b""):
        self.status_code = status_code
        self.text = text
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _SahteOturum:
    def __init__(self, sayfalar: dict[int, str], pdfler: dict[str, bytes]):
        self.sayfalar = sayfalar
        self.pdfler = pdfler

    def get(self, url, **kwargs):
        for yil, html in self.sayfalar.items():
            if f"{yil}-yatirimci-sunumlari" in url:
                return _SahteYanit(text=html)
        if url in self.pdfler:
            return _SahteYanit(content=self.pdfler[url])
        return _SahteYanit(status_code=404)


def test_sunum_baglantilari_iki_ceyregi_bulur():
    html = (
        '<a href="/wp-content/uploads/2026/05/sunum_q1_2026.pdf">Q1</a>'
        '<a href="/wp-content/uploads/2026/08/sunum_q2_2026.pdf">Q2</a>'
    )
    oturum = _SahteOturum({2026: html}, {})
    baglantilar = _sunum_baglantilari(oturum, 2026)
    assert baglantilar == {
        1: "https://www.orge.com.tr/wp-content/uploads/2026/05/sunum_q1_2026.pdf",
        2: "https://www.orge.com.tr/wp-content/uploads/2026/08/sunum_q2_2026.pdf",
    }


def test_sunum_baglantilari_sayfa_yoksa_bos_doner():
    oturum = _SahteOturum({}, {})
    assert _sunum_baglantilari(oturum, 2099) == {}


# --- seri_cek: uçtan uca, gerçek metin fikstürüyle ---



def test_seri_cek_ceyrek_verisini_dondurur(monkeypatch):
    monkeypatch.setattr("ingest.orge._pdf_metnini_cek", lambda session, url: _ORNEK_METIN)
    html = '<a href="/wp-content/uploads/2026/08/sunum_q2_2026.pdf">Q2</a>'
    oturum = _SahteOturum({2026: html}, {})
    df = seri_cek(
        SimpleNamespace(orge_metrik="backlog"), onbellek={}, session=oturum, bugun=date(2026, 9, 19),
    )
    son_satir = df.iloc[-1]
    assert son_satir["date"] == "2026-04-01"  # Ç2 -> çeyreğin ilk ayı (Nisan)
    assert son_satir["value"] == pytest.approx(5589.950948)


def test_seri_cek_yayimlanmamis_ceyrek_atlanir(monkeypatch):
    monkeypatch.setattr("ingest.orge._pdf_metnini_cek", lambda session, url: _ORNEK_METIN)
    html = '<a href="/wp-content/uploads/2026/05/sunum_q1_2026.pdf">Q1</a>'  # yalnızca Ç1
    oturum = _SahteOturum({2026: html}, {})
    df = seri_cek(
        SimpleNamespace(orge_metrik="backlog"), onbellek={}, session=oturum, bugun=date(2026, 9, 19),
    )
    assert list(df["date"]) == ["2026-01-01"]  # Ç2 yayımlanmadığı için yok


def test_seri_cek_bilinmeyen_metrikte_hata():
    with pytest.raises(RuntimeError, match="bilinmeyen orge_metrik"):
        seri_cek(SimpleNamespace(orge_metrik="olmayan"), onbellek={}, session=_SahteOturum({}, {}))
