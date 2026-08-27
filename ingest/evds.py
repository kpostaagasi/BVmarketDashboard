"""TCMB EVDS3 istemcisi.

Dokümante edilmemiş davranışlar (repo'daki eski TypeScript modülünde
keşfedilip doğrulanmıştır — sıfırdan yeniden keşfetmeye çalışmayın):

- Endpoint resmi evds2 REST'i değil; POST /igmevdsms-dis/fe, key HTTP
  header'ında gider.
- Tarih alanı frekansa göre iki farklı biçimde döner: aylık "YYYY-MM"
  (gün yok), günlük/haftalık "DD-MM-YYYY".
- Yanıttaki değer alanının adı, seri kodunun noktalarının alt çizgiye
  çevrilmiş halidir.
- groupSeperator:true istendiği için değerler binlik ayraç içerir.
"""

from __future__ import annotations

import math
import re
from datetime import date

import pandas as pd
import requests

from core.catalog import Seri

ENDPOINT = "https://evds3.tcmb.gov.tr/igmevdsms-dis/fe"
ZAMAN_ASIMI = 60

_AYLIK = re.compile(r"^(\d{4})-(\d{2})$")
_GUNLUK = re.compile(r"^(\d{2})-(\d{2})-(\d{4})$")


def alan_adi(evds_code: str) -> str:
    return evds_code.replace(".", "_")


def tarih_parse(tarih: str) -> str | None:
    metin = str(tarih).strip()
    aylik = _AYLIK.match(metin)
    if aylik:
        return f"{aylik.group(1)}-{aylik.group(2)}-01"
    gunluk = _GUNLUK.match(metin)
    if gunluk:
        return f"{gunluk.group(3)}-{gunluk.group(2)}-{gunluk.group(1)}"
    return None


def deger_parse(ham: object) -> float | None:
    if ham is None:
        return None
    metin = str(ham).replace(",", "").strip()
    if not metin:
        return None
    try:
        deger = float(metin)
    except ValueError:
        return None
    return deger if math.isfinite(deger) else None


def tarih_formatla(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def istek_govdesi(
    evds_code: str, evds_frequency: str, baslangic: str, bitis: str
) -> dict:
    return {
        "type": "json",
        "series": f"-{evds_code}",
        "aggregationTypes": "-avg",
        "formulas": "-0",
        "startDate": baslangic,
        "endDate": bitis,
        "frequency": evds_frequency,
        "decimalSeperator": ".",
        "decimal": "5",
        "dateFormat": "0",
        "lang": "TR",
        "yon": "1",
        "sira": "1",
        "ozelFormuller": [],
        "groupSeperator": True,
        "isRaporSayfasi": False,
    }


def noktalari_ayikla(yanit: dict, evds_code: str) -> list[tuple[str, float]]:
    alan = alan_adi(evds_code)
    noktalar: list[tuple[str, float]] = []
    for satir in yanit.get("items") or []:
        tarih = tarih_parse(satir.get("Tarih", ""))
        deger = deger_parse(satir.get(alan))
        if tarih is None or deger is None:
            continue
        noktalar.append((tarih, deger))
    noktalar.sort(key=lambda n: n[0])
    return noktalar


def _pencere(seri: Seri, bugun: date) -> tuple[str, str]:
    if seri.start_date:
        baslangic = date.fromisoformat(seri.start_date)
    else:
        try:
            baslangic = bugun.replace(year=bugun.year - 15)
        except ValueError:
            # 29 Şubat: hedef yıl artık yıl değil, 28'ine düşülür
            baslangic = bugun.replace(year=bugun.year - 15, day=28)
    return tarih_formatla(baslangic), tarih_formatla(bugun)


def seri_cek(seri: Seri, api_key: str, session: requests.Session | None = None,
             bugun: date | None = None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı)."""
    bugun = bugun or date.today()
    baslangic, bitis = _pencere(seri, bugun)
    http = session or requests

    yanit = http.post(
        ENDPOINT,
        headers={"key": api_key, "Content-Type": "application/json"},
        json=istek_govdesi(seri.evds_code, seri.evds_frequency, baslangic, bitis),
        timeout=ZAMAN_ASIMI,
    )
    if yanit.status_code != 200:
        raise RuntimeError(
            f"EVDS HTTP {yanit.status_code} ({seri.evds_code})"
        )

    noktalar = noktalari_ayikla(yanit.json(), seri.evds_code)
    if not noktalar:
        raise RuntimeError(f"EVDS boş seri döndürdü ({seri.evds_code})")

    return pd.DataFrame(noktalar, columns=["date", "value"])
