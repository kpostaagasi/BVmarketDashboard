"""SGK (Sosyal Güvenlik Kurumu) Aylık Sağlık İstatistik Bülteni istemcisi.

Bülten `https://www.sgk.gov.tr/Istatistik/Aylik/...` sayfasından "Sağlık
İstatistikleri" (statisticType=2) seçilerek indirilir. Uç, ASP.NET Core
anti-forgery token'ı ister: önce sayfa GET edilir (token + oturum çerezi
alınır), sonra `/StatisticData/YilListesi` ve `/StatisticData/AyListesi`
POST'ları EN GÜNCEL yıl/ay'ı bulur, son olarak
`/download/downloadfilestatistic?k=2&y=<yıl>&m=<ay>` XLSX'i döner.

Ölçüldü (2026-09-19): TEK XLSX dosyası TÜM tarihsel pencereyi taşır (2012'den
bugüne aylık) — EIB/TÜRKBESD gibi yıl yıl indirmeye gerek yok, en güncel ay
dosyası yeterli.

İki tablo okunuyor:

* `21.SGK Hastane Aylar (Baş.Türü)` — "TABLO 21- SAĞLIK HİZMET SUNUCUSU
  TÜRÜNE GÖRE FATURA BİLGİLERİ": yıl bazlı tek blok, satır = ay. Sütunlar
  (0-indeksli): 0=YIL (yalnızca yılın ilk satırında), 1=AY ("Nisan - April"
  biçiminde), 2-6=MÜRACAAT SAYISI (Bin Adet: Devlet2, Devlet3, Özel,
  Üniversite, TOPLAM), 7-11=FATURA TUTARI KDV Hariç (Bin TL: aynı sıra).
  12-16=ORTALAMA MALİYET (TL) — türetilmiş (Fatura/Müracaat), OKUNMUYOR.
  Yıl satırları arasına "GENEL TOPLAM" satırı serpiştirilmiş, atlanıyor.

* `23.SGK-Kamu Reçete Aylar` — "TABLO 23- SGK ECZANE PROVİZYON SİSTEMİ
  REÇETE ANALİZİ": DÖRT paralel 5-sütunluk blok yan yana (0-4, 5-9, 10-14,
  15-19), her blok kendi içinde 3 yıllık dikey dilimler taşır (13 satır:
  12 ay + "GENEL TOPLAM"). Bloklar KRONOLOJİK DEĞİL — 2015-2020 aralığı
  blok0/blok1'e çapraz dağılmış (blok0: 2015,2017,2019; blok1:
  2016,2018,2020), 2021 sonrası blok2/blok3'e sıralı (blok2: 2021-2023,
  blok3: 2024-2026). Parser bu yüzden POZİSYONA değil, her bloğun kendi
  YIL hücresine (yeni yıl = yeni 13 satırlık dilim) bakarak ilerliyor —
  blok sırası önemsiz. Sütunlar (blok içi 0-indeksli): 0=YIL, 1=AY,
  2=Reçete Sayısı (Bin Adet), 3=Fatura Tutarı (Bin TL), 4=Reçete Başı
  Fatura Tutarı (TL) — türetilmiş, OKUNMUYOR.

Kalemler `sgk_metrik` alanıyla seçilir (bkz. `core.catalog.GECERLI_SGK_METRIKLERI`).
"Özel Hastane Müracaat Payı" ve "Reçete Başı Ortalama Maliyet" gibi oran
kartları burada AYRI seri değildir: bileşenler (müracaat/fatura,
reçete/fatura) ingest edilir, oran `core/stats.py` katmanında hesaplanmalı.
"""

from __future__ import annotations

import re
from datetime import date

import pandas as pd
import requests

from core.catalog import GECERLI_SGK_METRIKLERI

SAYFA_URL = "https://www.sgk.gov.tr/Istatistik/Aylik/42919466-593f-4600-937d-1f95c9e252e6"
YIL_LISTESI_URL = "https://www.sgk.gov.tr/StatisticData/YilListesi"
AY_LISTESI_URL = "https://www.sgk.gov.tr/StatisticData/AyListesi"
INDIRME_URL = "https://www.sgk.gov.tr/download/downloadfilestatistic"
SAGLIK_ISTATISTIK_TIPI = 2
ZAMAN_ASIMI = 60

HASTANE_SAYFASI = "21.SGK Hastane Aylar (Baş.Türü)"
ECZANE_SAYFASI = "23.SGK-Kamu Reçete Aylar"

# Hastane sayfasının sütun haritası: sgk_metrik -> (müracaat_sütunu, fatura_sütunu).
_HASTANE_SUTUNLARI = {
    "hastane-ozel-muracaat": ("muracaat", 4),
    "hastane-ozel-fatura": ("fatura", 9),
    "hastane-toplam-muracaat": ("muracaat", 6),
    "hastane-toplam-fatura": ("fatura", 11),
}
_ECZANE_METRIKLERI = {"eczane-recete-sayisi": 2, "eczane-fatura-tutari": 3}

assert set(_HASTANE_SUTUNLARI) | set(_ECZANE_METRIKLERI) == GECERLI_SGK_METRIKLERI

_AY_ESLEME = {
    "Ocak": 1, "Şubat": 2, "Mart": 3, "Nisan": 4, "Mayıs": 5, "Haziran": 6,
    "Temmuz": 7, "Ağustos": 8, "Eylül": 9, "Ekim": 10, "Kasım": 11, "Aralık": 12,
}
_AY_DESENI = re.compile(r"^([A-Za-zÇĞİÖŞÜçğıöşü]+)")


def _ay_no(ay_hucresi: str) -> int | None:
    """`'Nisan - April'` / `'Kasım -November'` -> 4 / 11. Tanımadığı metin (ör.
    'GENEL TOPLAM' ya da dipnot) için None döner — çağıran bunu atlamalı."""
    m = _AY_DESENI.match(str(ay_hucresi).strip())
    if not m:
        return None
    return _AY_ESLEME.get(m.group(1))


def _antiforgery_al(session: requests.Session) -> str:
    yanit = session.get(SAYFA_URL, timeout=ZAMAN_ASIMI)
    yanit.raise_for_status()
    m = re.search(r'name="__RequestVerificationToken" type="hidden" value="([^"]+)"', yanit.text)
    if not m:
        raise RuntimeError("SGK: sayfada __RequestVerificationToken bulunamadı (şablon değişmiş olabilir)")
    return m.group(1)


def en_guncel_donem(session: requests.Session, token: str) -> tuple[int, int]:
    """Sağlık istatistikleri için yayımlanmış EN GÜNCEL (yıl, ay) çiftini bulur."""
    yanit = session.post(
        YIL_LISTESI_URL,
        data={"statisticType": SAGLIK_ISTATISTIK_TIPI, "__RequestVerificationToken": token},
        timeout=ZAMAN_ASIMI,
    )
    yanit.raise_for_status()
    yillar = sorted({kayit["year"] for kayit in yanit.json()}, reverse=True)
    if not yillar:
        raise RuntimeError("SGK: yıl listesi boş döndü")
    for yil in yillar:
        yanit_ay = session.post(
            AY_LISTESI_URL,
            data={"statisticType": SAGLIK_ISTATISTIK_TIPI, "year": yil, "__RequestVerificationToken": token},
            timeout=ZAMAN_ASIMI,
        )
        yanit_ay.raise_for_status()
        aylar = [kayit["month"] for kayit in yanit_ay.json() if kayit.get("month")]
        if aylar:
            return yil, max(aylar)
    raise RuntimeError("SGK: hiçbir yıl için ay listesi bulunamadı")


def _xlsx_indir(session: requests.Session, yil: int, ay: int) -> bytes:
    yanit = session.get(INDIRME_URL, params={"k": SAGLIK_ISTATISTIK_TIPI, "y": yil, "m": ay}, timeout=ZAMAN_ASIMI)
    yanit.raise_for_status()
    if "spreadsheet" not in yanit.headers.get("Content-Type", ""):
        raise RuntimeError(f"SGK: {yil}-{ay:02d} için beklenen XLSX değil (Content-Type={yanit.headers.get('Content-Type')})")
    return yanit.content


def hastane_verisini_ayikla(kitap) -> dict[tuple[int, int], dict[str, dict[int, float]]]:
    """`{(yıl, ay): {"muracaat": {2:..,4:..,6:..}, "fatura": {...}}}` döner.

    Anahtar iç sözlükler sütun indeksiyle (4=özel, 6=toplam, 9=özel fatura,
    11=toplam fatura) tutulur; `seri_cek` bunları `_HASTANE_SUTUNLARI` ile eşler.
    """
    ws = kitap[HASTANE_SAYFASI]
    sonuc: dict[tuple[int, int], dict[str, dict[int, float]]] = {}
    yil_gunceli = None
    for satir in ws.iter_rows(values_only=True):
        if satir[0] is not None:
            try:
                yil_gunceli = int(satir[0])
            except (TypeError, ValueError):
                yil_gunceli = None
                continue
        ay = _ay_no(satir[1]) if satir[1] is not None else None
        if ay is None or yil_gunceli is None:
            continue
        if satir[4] is None:
            continue
        sonuc[(yil_gunceli, ay)] = {
            "muracaat": {4: satir[4], 6: satir[6]},
            "fatura": {9: satir[9], 11: satir[11]},
        }
    if not sonuc:
        raise RuntimeError(f"SGK: '{HASTANE_SAYFASI}' sayfasından hiç veri noktası okunamadı (şablon değişmiş olabilir)")
    return sonuc


def eczane_verisini_ayikla(kitap) -> dict[tuple[int, int], dict[int, float]]:
    """`{(yıl, ay): {2: reçete_sayısı, 3: fatura_tutarı}}` döner.

    Dört paralel 5-sütunluk blok taranır; her blok kendi YIL hücresini
    (yeni yıl = yeni 13 satırlık dilim) izler, blok sırası/kronolojisi
    varsayılmaz (bkz. modül docstring'i).
    """
    ws = kitap[ECZANE_SAYFASI]
    satirlar = list(ws.iter_rows(values_only=True))
    genislik = len(satirlar[5])
    if genislik % 5 != 0:
        raise RuntimeError(f"SGK: '{ECZANE_SAYFASI}' sütun sayısı 5'in katı değil ({genislik}) — şablon değişmiş olabilir")
    blok_sayisi = genislik // 5
    sonuc: dict[tuple[int, int], dict[int, float]] = {}
    for b in range(blok_sayisi):
        c = b * 5
        yil_gunceli = None
        for satir in satirlar[6:]:
            if satir[c] is not None:
                try:
                    yil_gunceli = int(satir[c])
                except (TypeError, ValueError):
                    yil_gunceli = None
                    continue
            ay_hucre = satir[c + 1]
            if ay_hucre is None or yil_gunceli is None:
                continue
            ay = _ay_no(ay_hucre)
            if ay is None:
                continue
            recete, fatura = satir[c + 2], satir[c + 3]
            if recete is None or fatura is None:
                continue
            sonuc[(yil_gunceli, ay)] = {2: recete, 3: fatura}
    if not sonuc:
        raise RuntimeError(f"SGK: '{ECZANE_SAYFASI}' sayfasından hiç veri noktası okunamadı (şablon değişmiş olabilir)")
    return sonuc


def _kitabi_getir(onbellek: dict, session: requests.Session | None = None):
    if "kitap" in onbellek:
        return onbellek["kitap"]
    import openpyxl

    http = session or requests.Session()
    token = _antiforgery_al(http)
    yil, ay = en_guncel_donem(http, token)
    baytlar = _xlsx_indir(http, yil, ay)
    kitap = openpyxl.load_workbook(__import__("io").BytesIO(baytlar), data_only=True, read_only=True)
    onbellek["kitap"] = kitap
    onbellek["donem"] = (yil, ay)
    return kitap


def seri_cek(seri, *, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `date` ayın 1'i (aylık seri). `seri.sgk_metrik` hangi kalemin
    okunacağını belirler (bkz. `core.catalog.GECERLI_SGK_METRIKLERI`).
    """
    onbellek = onbellek if onbellek is not None else {}
    kitap = _kitabi_getir(onbellek, session)
    metrik = seri.sgk_metrik

    if metrik in _HASTANE_SUTUNLARI:
        alan, sutun = _HASTANE_SUTUNLARI[metrik]
        if "hastane" not in onbellek:
            onbellek["hastane"] = hastane_verisini_ayikla(kitap)
        veri = onbellek["hastane"]
        noktalar = [
            (date(yil, ay, 1).isoformat(), degerler[alan][sutun])
            for (yil, ay), degerler in sorted(veri.items())
        ]
    elif metrik in _ECZANE_METRIKLERI:
        sutun = _ECZANE_METRIKLERI[metrik]
        if "eczane" not in onbellek:
            onbellek["eczane"] = eczane_verisini_ayikla(kitap)
        veri = onbellek["eczane"]
        noktalar = [
            (date(yil, ay, 1).isoformat(), degerler[sutun])
            for (yil, ay), degerler in sorted(veri.items())
        ]
    else:
        raise RuntimeError(f"SGK: bilinmeyen sgk_metrik={metrik!r}")

    return pd.DataFrame(noktalar, columns=["date", "value"])
