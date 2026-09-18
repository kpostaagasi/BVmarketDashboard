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
    """Yıl başına en güncel bülteni seçer.

    Bir bülten o yılın tüm aylarını taşıdığı için yıl başına bir dosya
    yeter. Önceki sürüm yalnızca `.12` (Aralık) bültenlerini seçiyordu;
    indeks bir yıl için Aralık yerine başka bir ay sunarsa (ör. `.11`) o
    yıl sessizce tamamen düşüyordu. Burada varsayım yok: her yıl için
    indeksteki EN GÜNCEL bülten seçilir (ay ne olursa olsun). Bu, eski
    `max()` özel durumunu da yutar — cari yılın en güncel bülteni zaten
    o yılın seçimi olur.
    """
    en_eski_yil = bugun.year - VARSAYILAN_GECMIS_YIL
    en_iyi: dict[int, str] = {}
    for a in baglantilar:
        y = int(a[:4])
        if y >= en_eski_yil:
            en_iyi[y] = max(en_iyi.get(y, ""), a)
    return sorted(en_iyi.values())


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

def firma_aylik_noktalari_arac_tipli(
    tablolar: list, yil: int,
) -> list[tuple[str, str, str, float]]:
    """6–9. sayfa tablolarından `(firma, araç_tipi, "YYYY-MM-01", adet)` üretir.

    `firma_aylik_noktalari`nin aksine araç tipi bölümünü (OTOMOBİL, K.KAMYON,
    B.KAMYON, KAMYONET, OTOBÜS, MİNİBÜS, MİDİBÜS, TRAKTÖR) KORUR — marka
    sayfalarındaki (ör. ASUZU Hafif Kamyon Üretimi) tek-tip kartlar bunu
    ister. Tip adı, bölümü kapatan "<TİP> Toplam / ..." satırından çıkarılır;
    bir firma o bölümde hiç üretmediyse (satırı yoksa ya da tüm ayları "-")
    o (firma, tip) için hiç nokta üretilmez — bu sessiz veri kaybı değil,
    gerçek iş durumudur (osd_arac_tipi filtreli okuma bunu 0 değil "o
    dönemde üretim yok" olarak yorumlar, tıpkı kaynağın kendisi gibi).
    """
    sonuc: list[tuple[str, str, str, float]] = []
    for tablo in tablolar:
        arabellek: list[tuple[str, str, float]] = []
        for satir in tablo[1:]:
            ad = firma_adini_normalize(satir[0] or "")
            if not ad or ad.startswith(_ATLANACAK_ONEKLER):
                continue
            if "toplam" in ad.lower():
                tip = re.split(r"\s+Toplam\b", ad, maxsplit=1, flags=re.IGNORECASE)[0].strip()
                sonuc.extend((firma, tip, tarih, deger) for firma, tarih, deger in arabellek)
                arabellek = []
                continue
            for ay in range(1, 13):
                deger = sayi_parse(satir[ay])
                if deger is not None:
                    arabellek.append((ad, f"{yil}-{ay:02d}-01", deger))
    return sonuc


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


# Bülten 13 firma içerir. `toplamlar` bundan az firma taşıyorsa (ör. OSD
# 2. sayfaya bir sütun eklerse/araya sayfa sokarsa `sayi_parse` tüm satırlar
# için None döner ve `ay_toplamlari` neredeyse boş kalır) bu, döngünün hiç
# dönmediği (ya da az döndüğü) anlamına gelir — dilimin TEK güvenlik ağı
# sessizce no-op'a düşer. Bu yüzden döngüden önce sayı ayrıca kontrol edilir.
ASGARI_FIRMA_SAYISI = 13


def dogrula(
    noktalar: list[tuple[str, str, float]],
    toplamlar: dict[str, float],
    ay_tarihi: str,
) -> None:
    """6–9. sayfa toplamını 2. sayfanın TOPLAM sütunuyla karşılaştırır."""
    if len(toplamlar) < ASGARI_FIRMA_SAYISI:
        raise RuntimeError(
            f"OSD öz-doğrulama: 2. sayfada yalnızca {len(toplamlar)} firma "
            f"bulundu, beklenen en az {ASGARI_FIRMA_SAYISI} — sayfa yapısı "
            "değişmiş olabilir (sütun kayması, araya sayfa eklenmesi vb.)"
        )
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

def _bulten_baytlarini_getir(
    anahtar: str, baglantilar: dict[str, str], onbellek: dict, session=None,
) -> bytes:
    """PDF baytlarını önbellekler — toplam ve araç-tipli okuma aynı indirmeyi
    paylaşsın diye (`_bulteni_ayristir` yalnızca ayrıştırılmış SONUCU
    önbellekler, baytların kendisini değil)."""
    bayt_anahtari = f"{anahtar}:baytlar"
    if bayt_anahtari not in onbellek:
        onbellek[bayt_anahtari] = _pdf_indir(baglantilar[anahtar], session)
    return onbellek[bayt_anahtari]


def _bultendeki_tipli_noktalar(baytlar: bytes, anahtar: str) -> list[tuple[str, str, str, float]]:
    """Bir bültenin (firma, araç_tipi, tarih, adet) noktalarını çıkarır.

    Ayrı öz-doğrulama YOK: aynı bülten baytları toplam yoluyla zaten
    `dogrula()`den geçmiş olur (ikisi aynı `onbellek` altında paylaşılır);
    tip kırılımı yalnızca doğrulanmış toplamın nasıl dağıldığını gösterir.
    """
    yil = int(anahtar[:4])
    with pdfplumber.open(io.BytesIO(baytlar)) as pdf:
        tablolar = [t for i in _SAYFA_FIRMA_AY for t in pdf.pages[i].extract_tables()]
    return firma_aylik_noktalari_arac_tipli(tablolar, yil)


def _uretim_arac_tipi_cek(
    seri, onbellek: dict, session, bugun: date, arac_tipi: str,
) -> pd.DataFrame:
    """`osd_arac_tipi` verilen seriler: firma toplamı yerine tek araç tipi
    bölümünün adedini döner (bkz. `firma_aylik_noktalari_arac_tipli`).

    Firma HİÇBİR bültende yoksa RuntimeError (yazım hatası koruması, ana
    yoldaki "bilinmeyen firma" korumasıyla aynı gerekçe). Firma bültende
    var ama o TİPTE hiç üretmediyse (ör. ASUZU'nun kamyonet üretmediği
    aylar) nokta üretilmez — bu gerçek iş durumudur, hata değil.

    # ponytail: ana yoldaki bülten-bazlı kısmi kayıp kontrolü (her bültende
    # AYRI AYRI "firma var mı") burada yok — firma işlenen bültenlerin
    # TÜMÜNDE hiç bulunamazsa hata verir. Marka sayfalarındaki mevcut firma
    # kümesi için yeterli; tek bültende kısmi kayıp senaryosu önemli
    # olursa ana yoldaki per-bülten kontrolü buraya da taşınabilir.
    """
    if "indeks" not in onbellek:
        onbellek["indeks"] = _indeks_cek(session)
    baglantilar = onbellek["indeks"]

    isimler = {seri.osd_firma, *(getattr(seri, "osd_eski_adlar", None) or ())}

    kendi: dict[str, float] = {}
    firma_bulundu = False
    for anahtar in cekilecek_bultenler(baglantilar, bugun):
        tipli_anahtar = f"{anahtar}:tipli"
        if tipli_anahtar not in onbellek:
            baytlar = _bulten_baytlarini_getir(anahtar, baglantilar, onbellek, session)
            onbellek[tipli_anahtar] = _bultendeki_tipli_noktalar(baytlar, anahtar)

        for ad, tip, tarih, deger in onbellek[tipli_anahtar]:
            if ad not in isimler:
                continue
            firma_bulundu = True
            if tip == arac_tipi:
                kendi[tarih] = kendi.get(tarih, 0.0) + deger

    if not firma_bulundu:
        raise RuntimeError(
            f"OSD bültenlerinde firma bulunamadı: {seri.osd_firma!r} "
            f"({seri.id}) — katalogdaki ad bültenle eşleşmiyor olabilir"
        )

    df = pd.DataFrame(sorted(kendi.items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)


# --- OSD Aylık Değerlendirme Raporu: "Dış Satışlar" (ihracat) ---
#
# Üretim Bülteni'nde ihracat verisi YOK (yalnızca üretim). İhracat, OSD'nin
# AYRI bir aylık belgesinde ("Otomotiv Sektörü Aylık Değerlendirme Raporu")
# "Dış Satışlar" başlıklı 2 sayfalık bir bölümde yayımlanır: özet tablo
# (araç tipi × ay, tüm firmalar toplu) + yedi firma-bazlı tablo (araç tipi
# başına biri). Üretim tarafının B.KAMYON (Ağır Kamyon) / K.KAMYON (Hafif
# Kamyon) ayrımı burada firma bazında YOK — ikisi "KAMYON" adıyla tek
# tabloda birleşik gelir (özet tabloda hâlâ iki ayrı satırdır).
#
# Ölçüldü (2026-09-18, Ağustos 2026 raporu): A.I.O.S. Otobüs/Midibüs
# ihracatı 19/44, OTOKAR Kamyon/Otobüs/Midibüs 16/113/20, KARSAN
# Otobüs/Minibüs 5/2 — referans platformla birebir.

DEGERLENDIRME_INDEKS_URL = f"{TABAN}/osd-yayinlari/otomotiv-sektoru-aylik-degerlendirme-raporlari"

# Dosya adı ayı ve yılı NN-YYYY sırasıyla taşır (ör. "08-2026-OSD_Aylik_
# Degerlendirme_Raporu.pdf"); ayraç hem tire hem alt çizgi olarak görülüyor
# (Üretim Bülteni'ndeki 2022 alt çizgi / 2023+ tire deseniyle aynı neden).
_DEGERLENDIRME_BAGLANTI = re.compile(
    r'href="(/saved-files[^"]*?(\d{2})[-_](\d{4})[-_]OSD_Aylik_Degerlendirme_Raporu[^"]*?\.pdf)"'
)


def degerlendirme_baglantilari(html: str) -> dict[str, str]:
    """İndeks HTML'inden `"YYYY.MM" -> tam URL` eşlemesi çıkarır.

    Bazı eski aylar farklı bir dosya adı şablonu kullanıyor (ör. 2025
    Temmuz'un "Aylık Rapor_07.pdf" olması) — bu ay eşleşmeden sessizce
    dışarıda kalır; `cekilecek_bultenler` o yıl için DİĞER (çoğunluk) aylar
    üzerinden yine bir seçim yapabildiği sürece bu, o yılı kaybettirmez.
    """
    baglantilar = {
        f"{yil}.{ay}": TABAN + yol.replace("\\", "/")
        for yol, ay, yil in _DEGERLENDIRME_BAGLANTI.findall(html)
    }
    if not baglantilar:
        raise RuntimeError(
            "OSD Aylık Değerlendirme Raporu indeksinde bağlantı bulunamadı "
            f"({DEGERLENDIRME_INDEKS_URL}) — sayfa yapısı değişmiş olabilir"
        )
    return baglantilar


def _dis_satis_indeks_cek(session=None) -> dict[str, str]:
    http = session or requests
    yanit = http.get(DEGERLENDIRME_INDEKS_URL, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"OSD Değerlendirme Raporu indeksi HTTP {yanit.status_code}")
    return degerlendirme_baglantilari(yanit.text)


_DIS_SATIS_BASLIK = "Otomotiv Sanayii Dış Satışlar"
# Firma bazlı tabloların (özet tablo hariç) rapordaki sabit sırası.
DIS_SATIS_TIP_SIRASI = (
    "OTOMOBİL", "KAMYONET", "MİNİBÜS", "KAMYON", "MİDİBÜS", "OTOBÜS", "TRAKTÖR",
)


def _dis_satis_sayfalarini_bul(pdf) -> list[int]:
    return [
        i for i, sayfa in enumerate(pdf.pages)
        if _DIS_SATIS_BASLIK in (sayfa.extract_text() or "")
    ]


def dis_satis_noktalari(baytlar: bytes) -> list[tuple[str, str, str, float]]:
    """Değerlendirme Raporu'nun "Dış Satışlar" sayfalarından
    `(firma, araç_tipi, "YYYY-MM-01", adet)` üretir.

    Öz-doğrulama: her firma-bazlı tablonun kendi "TOPLAM - Total" satırı,
    o tablodaki firma satırlarının toplamıyla karşılaştırılır; tablo sayısı
    beklenenden (7) farklıysa da RuntimeError — sayfa şablonu değişmiş
    olabilir, sessizce eksik/yanlış veri üretmektense ingest kırılmalı.
    """
    with pdfplumber.open(io.BytesIO(baytlar)) as pdf:
        sayfalar = _dis_satis_sayfalarini_bul(pdf)
        if len(sayfalar) < 2:
            raise RuntimeError(
                f"OSD Değerlendirme Raporu'nda '{_DIS_SATIS_BASLIK}' sayfaları "
                f"bulunamadı ({len(sayfalar)} sayfa) — şablon değişmiş olabilir"
            )
        yil_eslesme = re.search(r"\b(20\d{2})\b", pdf.pages[sayfalar[0]].extract_text() or "")
        if not yil_eslesme:
            raise RuntimeError("OSD Dış Satışlar sayfasında yıl bulunamadı")
        yil = int(yil_eslesme.group(1))

        tablolar: list[list] = []
        for sayfa_no in sayfalar:
            for t in pdf.pages[sayfa_no].extract_tables():
                baslik = firma_adini_normalize(t[0][0] or "") if t and t[0] else ""
                if baslik.startswith(("Araç Tipleri", "Arac Tipleri")):
                    continue  # özet tablo — firma bazlı değil, atlanır
                tablolar.append(t)

        if len(tablolar) != len(DIS_SATIS_TIP_SIRASI):
            raise RuntimeError(
                f"OSD Dış Satışlar'da {len(tablolar)} firma tablosu bulundu, "
                f"beklenen {len(DIS_SATIS_TIP_SIRASI)} — şablon değişmiş olabilir"
            )

        sonuc: list[tuple[str, str, str, float]] = []
        for tip, tablo in zip(DIS_SATIS_TIP_SIRASI, tablolar):
            toplam_satiri = None
            firma_satirlari: list[tuple[str, list]] = []
            for satir in tablo[1:]:
                ad = firma_adini_normalize(satir[0] or "")
                if not ad:
                    continue
                if ad.upper().startswith("TOPLAM"):
                    toplam_satiri = satir
                    continue
                firma_satirlari.append((ad, satir))

            if toplam_satiri is None:
                raise RuntimeError(f"OSD Dış Satışlar — {tip} tablosunda TOPLAM satırı yok")

            for ay in range(1, 13):
                beklenen = sayi_parse(toplam_satiri[ay]) or 0.0
                bulunan = sum(sayi_parse(satir[ay]) or 0.0 for _, satir in firma_satirlari)
                if abs(bulunan - beklenen) > 0.5:
                    raise RuntimeError(
                        f"OSD Dış Satışlar öz-doğrulama — {tip} {yil}-{ay:02d}: "
                        f"firma toplamı {bulunan:,.0f}, TOPLAM satırı {beklenen:,.0f}"
                    )

            for ad, satir in firma_satirlari:
                for ay in range(1, 13):
                    deger = sayi_parse(satir[ay])
                    if deger is not None:
                        sonuc.append((ad, tip, f"{yil}-{ay:02d}-01", deger))

    return sonuc


def _ihracat_cek(
    seri, onbellek: dict, session, bugun: date, arac_tipi: str | None,
) -> pd.DataFrame:
    """`osd_veri_tipi="ihracat"` serileri: Değerlendirme Raporu'nun "Dış
    Satışlar" bölümünden firma×araç-tipi ihracat adedi.

    `arac_tipi` None ise firmanın TÜM tiplerdeki ihracatı toplanır (firma
    toplamı); verilmişse yalnızca o tip.
    """
    if "dis_satis_indeks" not in onbellek:
        onbellek["dis_satis_indeks"] = _dis_satis_indeks_cek(session)
    baglantilar = onbellek["dis_satis_indeks"]

    isimler = {seri.osd_firma, *(getattr(seri, "osd_eski_adlar", None) or ())}

    kendi: dict[str, float] = {}
    firma_bulundu = False
    for anahtar in cekilecek_bultenler(baglantilar, bugun):
        nokta_anahtari = f"dis_satis:{anahtar}"
        if nokta_anahtari not in onbellek:
            bayt_anahtari = f"dis_satis:{anahtar}:baytlar"
            if bayt_anahtari not in onbellek:
                onbellek[bayt_anahtari] = _pdf_indir(baglantilar[anahtar], session)
            onbellek[nokta_anahtari] = dis_satis_noktalari(onbellek[bayt_anahtari])

        for ad, tip, tarih, deger in onbellek[nokta_anahtari]:
            if ad not in isimler:
                continue
            firma_bulundu = True
            if arac_tipi is None or tip == arac_tipi:
                kendi[tarih] = kendi.get(tarih, 0.0) + deger

    if not firma_bulundu:
        raise RuntimeError(
            f"OSD Dış Satışlar raporunda firma bulunamadı: {seri.osd_firma!r} "
            f"({seri.id}) — katalogdaki ad raporla eşleşmiyor olabilir"
        )

    df = pd.DataFrame(sorted(kendi.items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)


def seri_cek(seri, onbellek: dict | None = None, session=None,
             bugun: date | None = None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `osd_arac_tipi`/`osd_veri_tipi` verilmemişse (mevcut 13 firma serisi)
    davranış TAMAMEN değişmez: firma toplamı, Üretim Bülteni'nden. İkisinden
    biri verilirse `_uretim_arac_tipi_cek`/`_ihracat_cek`'e devredilir (bkz.
    o fonksiyonların docstring'i).

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

    veri_tipi = getattr(seri, "osd_veri_tipi", None) or "uretim"
    arac_tipi = getattr(seri, "osd_arac_tipi", None)
    if veri_tipi == "ihracat":
        return _ihracat_cek(seri, onbellek, session, bugun, arac_tipi)
    if arac_tipi is not None:
        return _uretim_arac_tipi_cek(seri, onbellek, session, bugun, arac_tipi)

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
        # Aynı bültende hem eski hem yeni ad AYNI ay için nokta üretebilir
        # (alias çakışması); üzerine yazmak yerine TOPLANIR, aksi halde
        # biri sessizce kaybolur. Farklı bültenler arasında ise en son
        # işlenen bültenin değeri geçerli olur (revizyonları yakalamak
        # için istenen davranış budur).
        bu_bulten: dict[str, float] = defaultdict(float)
        for _, tarih, deger in bu_bultendeki_noktalar:
            bu_bulten[tarih] += deger
        kendi.update(bu_bulten)

    if not kendi:
        raise RuntimeError(
            f"OSD bültenlerinde firma bulunamadı: {seri.osd_firma!r} "
            f"({seri.id}) — katalogdaki ad bültenle eşleşmiyor olabilir"
        )

    df = pd.DataFrame(sorted(kendi.items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)
