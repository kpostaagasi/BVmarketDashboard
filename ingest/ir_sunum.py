"""Şirket yatırımcı ilişkileri (IR) PDF/HTML kaynaklarının ortak yardımcıları.

`bigchefs.py`, `migros.py`, `tabgida.py` üç ayrı şirketin üç ayrı sitesini
kazıyor ama ikisi aynı iki tuhaflıkla karşılaşıyor:

1. **Java `byte[]` sarmalayıcısı.** Bazı IR barındırma altyapıları (WordPress
   medya deposu VE Azure blob CDN'i — ikisi de gözlemlendi, aralarında ilgi
   yok, muhtemelen paylaşılan bir CDN/önbellek katmanının hatası) gerçek PDF
   baytlarını bir Java `byte[]` serileştirme akışının içine gömüp yine de
   `Content-Type: application/pdf` ve `200 OK` döndürüyor. İlk 4 bayt
   `\\xac\\xed\\x00\\x05` (Java serialization magic + version 5) ile
   başlıyor; hemen ardından `byte[]` sınıf tanımı ve 4 baytlık dizi uzunluğu
   geliyor, sonra gerçek `%PDF-1.7...%%EOF` verisi eksiksiz olarak yer
   alıyor. Ölçüldü (2026-09-18): bu ikisi etkilendi —
   `bigchefs.com.tr/wp-content/uploads/2026/04/31.03.2026 Bilgilendirme
   Notu.pdf` ve `migroskurumsalstr.blob.core.windows.net`'teki "Ara Dönem
   Faaliyet Raporu" dosyaları (iki farklı çeyrek denendi, ikisi de) — AYNI
   sunuculardaki DİĞER dosyalar (ör. şube bildirimleri, yatırımcı sunumu
   PDF'leri) etkilenmedi. `requests`/`urllib` farkı yok, tekrar denemede de
   aynı bayt dizisi geliyor — geçici bir WAF meydan okuması değil, kalıcı.
   `pdf_ayikla` `%PDF` imzasından itibaren dilimleyerek gerçek içeriği
   çıkarır.
2. **Türkçe biçimli sayılar.** Nokta binlik ayıracı, virgül ondalık, negatif
   için parantez, opsiyonel yüzde işareti. `tr_sayi` bunları float'a çevirir.
"""

from __future__ import annotations

import re

_JAVA_SARMALAYICI = b"\xac\xed\x00\x05"


def pdf_ayikla(ham: bytes) -> bytes:
    """Java `byte[]` serileştirme sarmalayıcısı varsa `%PDF` imzasından
    itibaren gerçek PDF baytlarını döndürür; yoksa `ham`'ı olduğu gibi döner.
    """
    if ham[:4] == _JAVA_SARMALAYICI:
        idx = ham.find(b"%PDF")
        if idx > 0:
            return ham[idx:]
    return ham


def tr_sayi(ham: str) -> float:
    """Türkçe biçimli sayıyı float'a çevirir.

    `1.234.567,89` -> 1234567.89, `(%2,8)` -> -2.8, `%15,2` -> 15.2,
    `(32.229.759)` -> -32229759.0. Boş ya da `-` girdide `ValueError`
    yükseltir — çağıran, ilgili dönemin kaynakta hiç raporlanmadığını
    böyle ayırt eder (sessizce 0 üretmek yerine).
    """
    metin = ham.strip()
    if not metin or metin == "-":
        raise ValueError(f"boş sayı alanı: {ham!r}")
    negatif = metin.startswith("(") and metin.endswith(")")
    if negatif:
        metin = metin[1:-1]
    metin = metin.replace("%", "").strip()
    metin = metin.replace(".", "").replace(",", ".")
    deger = float(metin)
    return -deger if negatif else deger


def pdf_metnini_normallestir(metin: str) -> str:
    """pdfplumber çıktısındaki tipografik kesme işaretlerini (U+2019 `'`,
    U+2018 `'`) düz ASCII kesme işaretine (`'`) çevirir. PDF üreticileri
    (Word/InDesign) "Türkiye'de" gibi ekleri sıkça tipografik kesme
    işaretiyle diziyor; regex desenleri düz `'` beklerse sessizce
    eşleşmez (ölçüldü: BigChefs "Şirket Profili" paragrafı)."""
    return metin.replace("\u2019", "'").replace("\u2018", "'")


_CEYREK_ILK_AY = {1: "01", 2: "04", 3: "07", 4: "10"}

_DONEM_FY = re.compile(r"\bFY\s*(\d{4})\b")
_DONEM_KUMULATIF_AY = re.compile(r"\b(\d{1,2})A\s*(\d{4})\b")
_DONEM_CEYREK = re.compile(r"\b(\d)Ç\s*(\d{4})\b")


def donem_tarihi(baslik_metni: str) -> str:
    """Çeyreklik bir IR belgesinin dönem başlığından ("1Ç 2026", "9A 2025",
    "FY 2025") o dönemin AİT OLDUĞU ÇEYREĞİN İLK AYINA damgalanmış
    "YYYY-MM-01" tarihini üretir (repo genelindeki çeyreklik→aylık damgalama
    kuralı): 1Ç→o yılın 01'i, 6A (2Ç kümülatif)→04'ü, 9A (3Ç kümülatif)→07'si,
    FY/12A→10'u. Hiçbiri eşleşmezse RuntimeError.
    """
    m = _DONEM_FY.search(baslik_metni)
    if m:
        return f"{m.group(1)}-{_CEYREK_ILK_AY[4]}-01"
    m = _DONEM_KUMULATIF_AY.search(baslik_metni)
    if m:
        ay_sayisi, yil = int(m.group(1)), m.group(2)
        ceyrek = min((ay_sayisi - 1) // 3 + 1, 4)
        return f"{yil}-{_CEYREK_ILK_AY[ceyrek]}-01"
    m = _DONEM_CEYREK.search(baslik_metni)
    if m:
        ceyrek, yil = int(m.group(1)), m.group(2)
        return f"{yil}-{_CEYREK_ILK_AY[ceyrek]}-01"
    raise RuntimeError(
        f"Dönem başlığı tanınamadı (ne 'NÇ YYYY', ne 'NA YYYY', ne 'FY YYYY'): "
        f"{baslik_metni[:200]!r}"
    )
