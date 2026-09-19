"""ORGE Enerji Elektrik Taahhüt A.Ş. çeyreklik Yatırımcı Sunumu istemcisi.

Şirket her çeyrek `https://www.orge.com.tr/<yıl>-yatirimci-sunumlari/`
sayfasında bir PDF slayt sunumu yayımlar (dosya adı `sunum_q<çeyrek>_<yıl>.pdf`).
Metin katmanı çıkarılabilir (görüntü değil) — "3A ve Sonrası Önemli
Gelişmeler" bölümünde iki rakam SABİT şablonla geçiyor (ölçüldü, 2026 Ç1 ve
Ç2 sunumları):

    "<GG.AA.YYYY> tarihi itibarıyla **Yeni Alınan İşler** toplamımız
    **<sayı> TL+KDV** tutarındadır."
    "<GG.AA.YYYY> tarihi itibarıyla **Devam Eden İşler** büyüklüğümüz
    **(backlog) <sayı> TL+KDV** seviyesinde bulunmaktadır."

Sayfa URL'si YIL bazında değişir (`<yıl>-yatirimci-sunumlari`); dosya adı
ÇEYREK bazında (`sunum_q1_2026.pdf`, `sunum_q2_2026.pdf`, …). Bu yüzden her
çeyrek için URL üretilir ve denenir (yıl başına sayfa taranıp dosya
bağlantıları çözülür), 404/bulunamayan = o çeyrek henüz yayımlanmamış
(gerçek eksiklik, atlanır).

"Backlog / Son 12 Ay Satış Oranı" ve "Piyasa Değeri / Backlog Oranı" AYRI
SERİ DEĞİLDİR — ilki TTM Hasılat (finansal tablo, bu adaptörün kapsamı
dışında), ikincisi BIST fiyatı × pay adedi ÷ USD/TRY gerektirir; ikisi de
`core/stats.py` katmanında, ilgili bileşen seriler eklendiğinde
hesaplanmalı (bkz. görev raporu "bloke"/gelecek iş notları).

Kalemler `orge_metrik` alanıyla seçilir (bkz.
`core.catalog.GECERLI_ORGE_METRIKLERI`).
"""

from __future__ import annotations

import re
from datetime import date

import pandas as pd
import requests

from core.catalog import GECERLI_ORGE_METRIKLERI

TABAN = "https://www.orge.com.tr"
ZAMAN_ASIMI = 60
ILK_YIL = 2023  # ölçülmedi geriye — 2026 Ç1/Ç2 doğrulandı, öncesi aynı şablon varsayılır.
# Sayfa yalnızca User-Agent ile isteklere 406 Not Acceptable döner (ölçüldü);
# Accept/Accept-Language de gerekiyor.
BASLIKLAR = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}

# pdfplumber ham metninde markdown kalın işareti (**) YOK — bu yalnızca bazı
# görüntüleme araçlarının OCR/markdown dönüşüm katmanına ait bir artefakt
# (ölçüldü 2026-09-19). Cümle içinde satır sonu düşebilir (ör. "...backlog)
# 5.589.950.948 TL+KDV seviyesinde\nbulunmaktadır") — bu SAYIYI etkilemiyor,
# yakalama grubu her iki sayıdan önce biter.
_TARIH_DESENI = r"\d{2}\.\d{2}\.\d{4}"
_SAYI = r"([\d.]+)\s*TL\+KDV"
YENI_IS_DESENI = re.compile(
    rf"{_TARIH_DESENI} tarihi itibarıyla Yeni Alınan İşler toplamımız {_SAYI}",
)
BACKLOG_DESENI = re.compile(
    rf"{_TARIH_DESENI} tarihi itibarıyla Devam Eden İşler büyüklüğümüz \(backlog\) {_SAYI}",
)

_METRIK_DESENLERI = {"backlog": BACKLOG_DESENI, "yeni-is-ytd": YENI_IS_DESENI}
assert set(_METRIK_DESENLERI) == GECERLI_ORGE_METRIKLERI


def _sayfa_url(yil: int) -> str:
    return f"{TABAN}/{yil}-yatirimci-sunumlari/"


_SUNUM_BAGLANTISI = re.compile(r'href="([^"]*sunum_q(\d)_(\d{4})\.pdf)"', re.I)


def _sunum_baglantilari(session: requests.Session, yil: int) -> dict[int, str]:
    """`{yıl}-yatirimci-sunumlari` sayfasından `{çeyrek: pdf_url}` çıkarır."""
    yanit = session.get(_sayfa_url(yil), timeout=ZAMAN_ASIMI, headers=BASLIKLAR)
    if yanit.status_code == 404:
        return {}
    yanit.raise_for_status()
    bulunan: dict[int, str] = {}
    for url, ceyrek_str, yil_str in _SUNUM_BAGLANTISI.findall(yanit.text):
        if int(yil_str) == yil:
            bulunan[int(ceyrek_str)] = url if url.startswith("http") else TABAN + url
    return bulunan


def _pdf_metnini_cek(session: requests.Session, url: str) -> str:
    import io

    import pdfplumber

    yanit = session.get(url, timeout=ZAMAN_ASIMI, headers=BASLIKLAR)
    yanit.raise_for_status()
    with pdfplumber.open(io.BytesIO(yanit.content)) as pdf:
        return "\n".join(sayfa.extract_text() or "" for sayfa in pdf.pages)


def deger_cek(metin: str, metrik: str) -> float:
    desen = _METRIK_DESENLERI[metrik]
    m = desen.search(metin)
    if not m:
        raise RuntimeError(f"ORGE: {metrik!r} için beklenen ifade PDF metninde bulunamadı — şablon değişmiş olabilir")
    return float(m.group(1).replace(".", "")) / 1_000_000  # TL -> Milyon TL


def _ceyrek_tarihi(yil: int, ceyrek: int) -> str:
    """Katalog sözleşmesi: çeyreksel seri tarihi çeyreğin İLK ayı (ör. Ç2 -> Nisan)."""
    ay = {1: 1, 2: 4, 3: 7, 4: 10}[ceyrek]
    return date(yil, ay, 1).isoformat()


def cekilecek_ceyrekler(bugun: date) -> list[tuple[int, int]]:
    donemler = []
    for yil in range(ILK_YIL, bugun.year + 1):
        son_ceyrek = 4 if yil < bugun.year else (bugun.month - 1) // 3 + 1
        for ceyrek in range(1, son_ceyrek + 1):
            donemler.append((yil, ceyrek))
    return donemler


def _tum_noktalari_getir(onbellek: dict, metrik: str, session=None, bugun: date | None = None) -> list[tuple[str, float]]:
    cache_key = f"noktalar:{metrik}"
    if cache_key in onbellek:
        return onbellek[cache_key]
    http = session or requests.Session()
    bugun = bugun or date.today()
    baglanti_onbellegi: dict[int, dict[int, str]] = onbellek.setdefault("baglantilar", {})
    metin_onbellegi: dict[str, str] = onbellek.setdefault("metinler", {})
    noktalar = []
    for yil, ceyrek in cekilecek_ceyrekler(bugun):
        if yil not in baglanti_onbellegi:
            baglanti_onbellegi[yil] = _sunum_baglantilari(http, yil)
        url = baglanti_onbellegi[yil].get(ceyrek)
        if url is None:
            continue  # bu çeyrek henüz yayımlanmamış (gerçek eksiklik)
        if url not in metin_onbellegi:
            metin_onbellegi[url] = _pdf_metnini_cek(http, url)
        deger = deger_cek(metin_onbellegi[url], metrik)
        noktalar.append((_ceyrek_tarihi(yil, ceyrek), deger))
    if not noktalar:
        raise RuntimeError(f"ORGE: {metrik!r} için hiçbir çeyrekte veri bulunamadı")
    onbellek[cache_key] = noktalar
    return noktalar


def seri_cek(seri, *, onbellek: dict | None = None, session=None, bugun: date | None = None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `date` çeyreğin İLK ayının 1'i (ör. 2026 Ç2 -> 2026-04-01).
    """
    onbellek = onbellek if onbellek is not None else {}
    metrik = seri.orge_metrik
    if metrik not in GECERLI_ORGE_METRIKLERI:
        raise RuntimeError(f"ORGE: bilinmeyen orge_metrik={metrik!r}")
    noktalar = _tum_noktalari_getir(onbellek, metrik, session, bugun)
    return pd.DataFrame(noktalar, columns=["date", "value"])
