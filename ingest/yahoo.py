"""Yahoo Finance chart API istemcisi.

Dokümante edilmemiş davranışlar. Bunlar Faz 0'daki TypeScript modülünde
keşfedilip 2026-08-27'de yeniden doğrulanmıştır — sıfırdan keşfetmeye
çalışmayın:

- Yahoo tarayıcı User-Agent'larını 429 ile reddeder; Googlebot UA'sı
  kabul edilir.
- Semboldeki "=" URL'de kodlanmalıdır: BZ=F -> BZ%3DF
- Günlük barlar borsa yerel gece yarısına damgalanır. Timestamp'i en yakın
  UTC gece yarısına yuvarlamak DST'nin her iki yönünde de borsa yerel
  takvim gününü verir; meta.gmtoffset'e bağlanmak mevsimsel kayma üretir.
- close[] dizisi tatil ve işlem durması günlerinde null içerir.

Yedek kaynak yoktur (bilinçli karar): başarısızlık yüksek sesle olur.
Googlebot UA bağımlılığı yalnızca üretimde doğrulanabilir; test edilemez.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from urllib.parse import quote

import pandas as pd
import requests

from core.catalog import Seri

ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart"
ARALIK = "15y"
ZAMAN_ASIMI = 60
KULLANICI_AJANI = (
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)


def sembol_kodla(sembol: str) -> str:
    return quote(sembol, safe="")


def gun_yuvarla(ts: int) -> str:
    """Borsa yerel gece yarısına damgalı timestamp'i takvim gününe çevirir."""
    gun = round(ts / 86400) * 86400
    return datetime.fromtimestamp(gun, tz=timezone.utc).date().isoformat()


def noktalari_ayikla(yanit: dict) -> list[tuple[str, float]]:
    sonuclar = (yanit.get("chart") or {}).get("result") or []
    if not sonuclar:
        return []

    ilk = sonuclar[0]
    zamanlar = ilk.get("timestamp") or []
    kotalar = (ilk.get("indicators") or {}).get("quote") or [{}]
    kapanislar = kotalar[0].get("close") or []

    noktalar: list[tuple[str, float]] = []
    onceki: str | None = None
    for zaman, kapanis in zip(zamanlar, kapanislar):
        if kapanis is None or not math.isfinite(kapanis):
            continue
        tarih = gun_yuvarla(zaman)
        if tarih == onceki:
            continue
        onceki = tarih
        noktalar.append((tarih, float(kapanis)))
    return noktalar


def seri_cek(seri: Seri, session: requests.Session | None = None) -> pd.DataFrame:
    """Sembolün son 15 yıllık günlük kapanışlarını çeker."""
    http = session or requests
    url = (
        f"{ENDPOINT}/{sembol_kodla(seri.yahoo_symbol)}"
        f"?range={ARALIK}&interval=1d"
    )
    yanit = http.get(
        url,
        headers={"User-Agent": KULLANICI_AJANI, "Accept": "application/json"},
        timeout=ZAMAN_ASIMI,
    )
    if yanit.status_code != 200:
        raise RuntimeError(f"Yahoo HTTP {yanit.status_code} ({seri.yahoo_symbol})")

    noktalar = noktalari_ayikla(yanit.json())
    if not noktalar:
        raise RuntimeError(f"Yahoo boş seri döndürdü ({seri.yahoo_symbol})")

    return pd.DataFrame(noktalar, columns=["date", "value"])
