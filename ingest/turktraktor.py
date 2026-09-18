"""TürkTraktör (BIST: TTRAK) "OSD'ye Bildirilen Üretim ve Satış Adetleri"
aylık PDF istemcisi.

Üretim (yalnızca traktör üreten tek ürünlü firma) zaten OSD'nin kendi aylık
Üretim Bülteni'nden `ingest/osd.py::seri_cek` (`osd_firma: TÜRK TRAKTÖR`) ile
karşılanıyor — çapraz doğrulandı (Ağustos 2026: iki kaynak da 1.023 adet).
Bu modül yalnızca OSD bülteninde HİÇ olmayan iki seriyi ekliyor: fabrika
satışı (iç pazar) ve yurtdışı satışı (ihracat) — ki bunların toplamı da
"Toplam Satış" kartını verir.

Kaynak: şirketin kendi IR sitesindeki aylık arşiv sayfası
(`/yatirimci-iliskileri/finansal-sonuclar/osdye-bildirilen-uretim-satis-adetleri`).
Dosya yolları GUID içeriyor, türetilemez — indeks sayfası her koşuda yeniden
taranmak zorunda (OSD'nin kendi bülten indeksiyle aynı gerekçe). Dosya adı
`{Ay-ASCII}[-_]{Yıl}[-_]?OSD[-_]URETIM[-_]SATIS...pdf` kalıbını taşıyor (iki
farklı ayraç stili gözlemlendi, ikisi de kabul edilir). 2020-2023 arası bazı
aylar dosya adında yıl TAŞIMIYOR (yalnızca "Ekim.pdf" gibi) — bu ayların
yılını sayfa konumundan çıkarmak kırılgan olacağından bu ay'lar ATLANIR;
seri o aralıkta seyrek olabilir ama 2024'ten itibaren tam.

Her PDF tek sayfa, tek tablo: "TRAKTÖR" satırının "Aylık"/"Kümülatif" alt
satırlarında Fabrika Satış / Yurtdışı Satış, ayrı bir "ÜRETİLEN TRAKTÖR"
mini-tablosunda "TOPLAM" satırında üretim (A=aylık, B=kümülatif).

Ölçüldü (2026-09-18, Ağustos 2026 belgesi, marketvisuals.net/turktraktor_osd.html
ile birebir): Fabrika Satış (İç Pazar) aylık 592, Yurtdışı Satış (İhracat)
aylık 441, Toplam Satış = 1033, Üretim aylık 1023 (OSD ile çapraz doğrulandı).
"""

from __future__ import annotations

import io
import re

import pandas as pd
import pdfplumber
import requests

TABAN = "https://www.turktraktor.com.tr"
INDEKS_URL = (
    f"{TABAN}/yatirimci-iliskileri/finansal-sonuclar/"
    "osdye-bildirilen-uretim-satis-adetleri"
)
ZAMAN_ASIMI = 60
_BASLIKLAR = {"User-Agent": "Mozilla/5.0"}

_AYLAR = {
    "ocak": "01", "subat": "02", "mart": "03", "nisan": "04", "mayis": "05",
    "haziran": "06", "temmuz": "07", "agustos": "08", "eylul": "09",
    "ekim": "10", "kasim": "11", "aralik": "12",
}

_DOSYA_BAGLANTISI = re.compile(
    r'href="(/get(?:media|attachment)/[0-9a-f-]+/([A-Za-z]+)[-_](\d{4})'
    r'[-_]?OSD[-_]URETIM[-_]SATIS[^"]*\.pdf)(?:\?[^"]*)?"',
    re.I,
)

_AYLIK_SATIR = re.compile(r"Aylık\s+([\d.]+)\s+([\d.]+)")
_TOPLAM_SATIR = re.compile(r"ÜRETİLEN TRAKTÖR.*?TOPLAM\s+([\d.]+)\s+([\d.]+)", re.S)

GECERLI_METRIKLER = {"fabrika-satis", "yurtdisi-satis", "toplam-satis"}


def _sayi(ham: str) -> float:
    return float(ham.replace(".", ""))


def bulten_baglantilari(html: str) -> dict[str, str]:
    """İndeks HTML'inden `"YYYY-MM" -> tam URL` eşlemesi çıkarır."""
    baglantilar: dict[str, str] = {}
    for yol, ay_adi, yil in _DOSYA_BAGLANTISI.findall(html):
        ay = _AYLAR.get(ay_adi.lower())
        if ay is None:
            continue
        anahtar = f"{yil}-{ay}"
        baglantilar[anahtar] = yol if yol.startswith("http") else TABAN + yol
    return baglantilar


def _indeks_cek(session=None) -> dict[str, str]:
    http = session or requests
    yanit = http.get(INDEKS_URL, headers=_BASLIKLAR, timeout=ZAMAN_ASIMI)
    yanit.raise_for_status()
    baglantilar = bulten_baglantilari(yanit.text)
    if not baglantilar:
        raise RuntimeError(
            "TürkTraktör OSD üretim/satış indeks sayfasında hiç bağlantı "
            "ayrıştırılamadı — şablon değişmiş olabilir"
        )
    return baglantilar


def ay_verilerini_ayikla(metin: str) -> tuple[float, float, float]:
    """Tek bir aylık PDF'in metninden (fabrika_satis, yurtdisi_satis, uretim)
    aylık değerlerini çıkarır. Beklenen iki satır bulunamazsa RuntimeError.
    """
    m1 = _AYLIK_SATIR.search(metin)
    if not m1:
        raise RuntimeError(
            f"TürkTraktör bülteninde 'Aylık' satırı bulunamadı — şablon "
            f"değişmiş olabilir: {metin[:200]!r}"
        )
    m2 = _TOPLAM_SATIR.search(metin)
    if not m2:
        raise RuntimeError(
            f"TürkTraktör bülteninde üretim TOPLAM satırı bulunamadı — "
            f"şablon değişmiş olabilir: {metin[:200]!r}"
        )
    fabrika_satis = _sayi(m1.group(1))
    yurtdisi_satis = _sayi(m1.group(2))
    uretim = _sayi(m2.group(1))
    return fabrika_satis, yurtdisi_satis, uretim


def _bulten_verisini_getir(anahtar: str, baglantilar: dict[str, str],
                            onbellek: dict, session=None) -> tuple[float, float, float]:
    if anahtar in onbellek:
        return onbellek[anahtar]
    http = session or requests
    yanit = http.get(baglantilar[anahtar], headers=_BASLIKLAR, timeout=ZAMAN_ASIMI)
    yanit.raise_for_status()
    with pdfplumber.open(io.BytesIO(yanit.content)) as pdf:
        metin = "\n".join(sayfa.extract_text() or "" for sayfa in pdf.pages)
    veri = ay_verilerini_ayikla(metin)
    onbellek[anahtar] = veri
    return veri


def seri_cek(seri, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı)."""
    onbellek = onbellek if onbellek is not None else {}
    metrik = seri.turktraktor_metrik
    if metrik not in GECERLI_METRIKLER:
        raise RuntimeError(f"Bilinmeyen turktraktor_metrik: {metrik!r}")

    if "baglantilar" not in onbellek:
        onbellek["baglantilar"] = _indeks_cek(session=session)
    baglantilar = onbellek["baglantilar"]

    noktalar: list[tuple[str, float]] = []
    for anahtar in sorted(baglantilar):
        fabrika, yurtdisi, _uretim = _bulten_verisini_getir(
            anahtar, baglantilar, onbellek, session=session,
        )
        if metrik == "fabrika-satis":
            deger = fabrika
        elif metrik == "yurtdisi-satis":
            deger = yurtdisi
        else:
            deger = fabrika + yurtdisi
        noktalar.append((f"{anahtar}-01", deger))

    if not noktalar:
        raise RuntimeError("TürkTraktör OSD üretim/satış serisinde hiç nokta üretilmedi")
    df = pd.DataFrame(noktalar, columns=["date", "value"]).sort_values("date")
    return df.reset_index(drop=True)
