"""OSD (Otomotiv Sanayii Derneği) aylık üretim bülteni istemcisi.

Bültenler yalnızca PDF olarak yayımlanıyor ve indirme URL'leri yükleme
tarihini gömdüğü için türetilemiyor — indeks sayfası kazınmak zorunda.

Firma aylık toplamı için 6–9. sayfalar okunur (firma × ay, araç tipi
bölümlerinde). Bir bülten o yılın tamamını taşıdığından tarihsel doldurma
yılda tek PDF ister; 2. sayfayı (tek ay) okumak aynı pencere için on kat
daha fazla indirme demek olurdu.

Öz-doğrulama: 6–9. sayfaların firma toplamı, 2. sayfanın TOPLAM sütunuyla
karşılaştırılır. Canlı bültende 13 firmanın 13'ünde de fark 0 ölçüldü.
Tutmazsa RuntimeError yükselir — OSD şablonu değiştiğinde sessizce eksik
veri üretmektense ingest'in kırılması istenir.
"""

from __future__ import annotations

import io
import re
from collections import defaultdict
from datetime import date

import pandas as pd
import pdfplumber
import requests

TABAN = "https://www.osd.org.tr"
INDEKS_URL = f"{TABAN}/osd-yayinlari/otomotiv-sanayii-uretim-bultenleri"
VARSAYILAN_GECMIS_YIL = 5

# 2022 alt çizgi, 2023+ tire kullanıyor; ikisi de kabul edilir.
_BAGLANTI = re.compile(
    r'href="(/saved-files[^"]*?Otomotiv_Sanayii_Uretim_Bulteni[-_](\d{4}\.\d{2})\.pdf)"'
)

_ATLANACAK_ONEKLER = ("Pay /", "Toplam Pay", "Tipler")


def bulten_baglantilari(html: str) -> dict[str, str]:
    """İndeks HTML'inden `"YYYY.MM" -> tam URL` eşlemesi çıkarır.

    HTML'deki yollar ters bölülü (`/saved-files\\PDF\\2026\\...`); düz bölüye
    çevrilir. Hiç bağlantı bulunamazsa RuntimeError: site yapısı değiştiyse
    boş liste döndürüp sessizce devam etmek, veriyi sessizce kaybetmektir.
    """
    baglantilar = {
        anahtar: TABAN + yol.replace("\\", "/")
        for yol, anahtar in _BAGLANTI.findall(html)
    }
    if not baglantilar:
        raise RuntimeError(
            f"OSD indeksinde bülten bağlantısı bulunamadı ({INDEKS_URL}) — "
            "sayfa yapısı değişmiş olabilir"
        )
    return baglantilar


def cekilecek_bultenler(baglantilar: dict[str, str], bugun: date) -> list[str]:
    """Her yılın Aralık bülteni + en güncel bülten.

    Bir bülten o yılın tüm aylarını taşıdığı için yıl başına bir dosya yeter.
    Ocak'ta en güncel bülten zaten önceki yılın Aralık'ıdır; küme kullanımı
    tekrarı önler.
    """
    en_eski_yil = bugun.year - VARSAYILAN_GECMIS_YIL
    secilen = {
        a for a in baglantilar
        if a.endswith(".12") and int(a[:4]) >= en_eski_yil
    }
    guncel = max(baglantilar)
    if int(guncel[:4]) >= en_eski_yil:
        secilen.add(guncel)
    return sorted(secilen)


def firma_adini_normalize(ham: str) -> str:
    """Null baytı, satır sonlarını ve fazla boşluğu temizler.

    Eski bültenlerde font kodlaması Türkçe karakterlerde `\\x00` sızdırıyor
    (`"T\\x00pler"`); normalizasyon olmazsa firma katalogla eşleşmez.
    """
    return " ".join(ham.replace("\x00", "").split())


def sayi_parse(ham: str | None) -> float | None:
    """Türkçe biçimli tam sayı: `36.548` → 36548.0. `-` ve boş → None."""
    metin = (ham or "").strip()
    if not metin or metin == "-":
        return None
    try:
        return float(metin.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _firma_satiri_mi(ad: str) -> bool:
    if not ad or ad.startswith(_ATLANACAK_ONEKLER):
        return False
    # "OTOMOBİL Toplam / Pass.Car Total", "TOPLAM / TOTAL" gibi toplam
    # satırları büyük/küçük harf farkı gözetmeksizin elenir.
    kucuk = ad.lower()
    return "toplam" not in kucuk and "total" not in kucuk


def firma_aylik_noktalari(tablolar: list, yil: int) -> list[tuple[str, str, float]]:
    """6–9. sayfa tablolarından `(firma, "YYYY-MM-01", adet)` üretir.

    Bir firma birden çok araç tipi bölümünde görünür (Ford Otosan hem
    kamyonette hem minibüste); bölümler boyunca TOPLANIR — firma toplam
    üretimi budur ve 2. sayfanın TOPLAM sütunuyla birebir tutar.
    """
    toplam: dict[tuple[str, str], float] = defaultdict(float)
    for tablo in tablolar:
        for satir in tablo[1:]:
            ad = firma_adini_normalize(satir[0] or "")
            if not _firma_satiri_mi(ad):
                continue
            for ay in range(1, 13):
                deger = sayi_parse(satir[ay])
                if deger is not None:
                    toplam[(ad, f"{yil}-{ay:02d}-01")] += deger
    return [(ad, tarih, deger) for (ad, tarih), deger in toplam.items()]


def ay_toplamlari(s2_tablosu: list) -> dict[str, float]:
    """2. sayfanın `TOPLAM` sütunundan `firma -> adet` çıkarır (sütun 17)."""
    toplamlar = {}
    for satir in s2_tablosu[1:]:
        ad = firma_adini_normalize(satir[0] or "")
        if not _firma_satiri_mi(ad):
            continue
        deger = sayi_parse(satir[17])
        if deger is not None:
            toplamlar[ad] = deger
    return toplamlar


def dogrula(
    noktalar: list[tuple[str, str, float]],
    toplamlar: dict[str, float],
    ay_tarihi: str,
) -> None:
    """6–9. sayfa toplamını 2. sayfanın TOPLAM sütunuyla karşılaştırır."""
    ay_noktalari = {ad: deger for ad, tarih, deger in noktalar if tarih == ay_tarihi}
    for ad, beklenen in toplamlar.items():
        bulunan = ay_noktalari.get(ad)
        if bulunan is None:
            raise RuntimeError(
                f"OSD öz-doğrulama: {ad} 2. sayfada var ({beklenen:,.0f}) ama "
                f"6–9. sayfalarda {ay_tarihi} için hiç noktası yok"
            )
        if abs(bulunan - beklenen) > 0.5:
            raise RuntimeError(
                f"OSD öz-doğrulama: {ad} {ay_tarihi} — 6–9. sayfa toplamı "
                f"{bulunan:,.0f}, 2. sayfa TOPLAM {beklenen:,.0f}"
            )


ZAMAN_ASIMI = 60
_SAYFA_FIRMA_AY = (5, 6, 7, 8)  # 6–9. sayfalar (0-tabanlı)
_SAYFA_AY_TOPLAM = 1            # 2. sayfa


def _indeks_cek(session=None) -> dict[str, str]:
    http = session or requests
    yanit = http.get(INDEKS_URL, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"OSD indeksi HTTP {yanit.status_code}")
    return bulten_baglantilari(yanit.text)


def _pdf_indir(url: str, session=None) -> bytes:
    http = session or requests
    yanit = http.get(url, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"OSD bülteni HTTP {yanit.status_code} ({url})")
    return yanit.content


def _bulteni_ayristir(baytlar: bytes, anahtar: str) -> list[tuple[str, str, float]]:
    """Bir bültenin firma×ay noktalarını çıkarır ve öz-doğrulamayı koşar."""
    yil, ay = int(anahtar[:4]), int(anahtar[5:7])
    with pdfplumber.open(io.BytesIO(baytlar)) as pdf:
        tablolar = [
            t for i in _SAYFA_FIRMA_AY for t in pdf.pages[i].extract_tables()
        ]
        noktalar = firma_aylik_noktalari(tablolar, yil)
        toplamlar = ay_toplamlari(pdf.pages[_SAYFA_AY_TOPLAM].extract_tables()[0])
    dogrula(noktalar, toplamlar, f"{yil}-{ay:02d}-01")
    return noktalar


def seri_cek(seri, onbellek: dict | None = None, session=None,
             bugun: date | None = None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `onbellek` verilirse indeks ve ayrıştırılmış bülten noktaları koşu
    boyunca paylaşılır: 13 seri aynı beş PDF'i okuduğu için yoksa 65
    indirme olurdu.

    Firma OSD bültenlerinde zaman içinde ad değiştirebilir (ör. HYUNDAI
    ASSAN -> HYUNDAI MOTOR TÜRKİYE); `seri.osd_eski_adlar` verilirse eski
    adlarla yazılmış noktalar da toplanır. Ayrıca her çekilen bülten AYRI
    AYRI kontrol edilir: firma (hangi adıyla olursa olsun) o bültende hiç
    yoksa RuntimeError yükselir — beş bültenden birinde kısmi kayıp olması
    "hiç eşleşme yok" durumuna göre çok daha sık ve sessizce geçebilir,
    bu yüzden toplam kontrolü yeterli değildir. Firmanın gerçekten henüz
    üretime başlamadığı dönemler için kaçış yolu `start_date`: o tarihin
    yılından ÖNCEKİ bültenler bu kontrolden muaftır.
    """
    bugun = bugun or date.today()
    onbellek = {} if onbellek is None else onbellek

    if "indeks" not in onbellek:
        onbellek["indeks"] = _indeks_cek(session)
    baglantilar = onbellek["indeks"]

    isimler = {seri.osd_firma, *(getattr(seri, "osd_eski_adlar", None) or ())}
    baslangic_yili = int(seri.start_date[:4]) if seri.start_date else None

    kendi: dict[str, float] = {}
    for anahtar in cekilecek_bultenler(baglantilar, bugun):
        if anahtar not in onbellek:
            baytlar = _pdf_indir(baglantilar[anahtar], session)
            onbellek[anahtar] = _bulteni_ayristir(baytlar, anahtar)

        bu_bultendeki_noktalar = [
            (ad, tarih, deger) for ad, tarih, deger in onbellek[anahtar]
            if ad in isimler
        ]
        if not bu_bultendeki_noktalar:
            bulten_yili = int(anahtar[:4])
            if baslangic_yili is not None and bulten_yili < baslangic_yili:
                continue  # start_date'ten önceki yıl — firma henüz yok, muaf
            raise RuntimeError(
                f"OSD bülteninde firma bulunamadı: {seri.osd_firma!r} "
                f"({seri.id}) — bülten {anahtar} — katalogdaki ad(lar) "
                "bültenle eşleşmiyor olabilir (ad değişmiş olabilir, "
                "osd_eski_adlar'a eklemeyi düşünün)"
            )
        for _, tarih, deger in bu_bultendeki_noktalar:
            kendi[tarih] = deger

    if not kendi:
        raise RuntimeError(
            f"OSD bültenlerinde firma bulunamadı: {seri.osd_firma!r} "
            f"({seri.id}) — katalogdaki ad bültenle eşleşmiyor olabilir"
        )

    df = pd.DataFrame(sorted(kendi.items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)
