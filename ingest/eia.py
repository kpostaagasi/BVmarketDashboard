"""EIA (U.S. Energy Information Administration) `dnav` Excel istemcisi.

EIA'nın v2 JSON API'si (`api.eia.gov`) API ANAHTARI ister. Bunun yerine
eski "dnav" (data navigator) sistemini kullanıyoruz: seri başına tek bir
`.xls` (BIFF, eski biçim) dosyası, ANAHTARSIZ (ölçüldü 2026-09-20, hem
User-Agent'sız hem de kimlik bilgisiz düz `requests.get` ile HTTP 200):

    https://www.eia.gov/dnav/pet/hist_xls/<SourceKey>d.xls

Dosyanın "Data 1" sayfası ÜÇ metadata satırıyla başlar (başlık, Sourcekey,
kolon başlığı; ölçüldü — ilk sürümde "iki" sanılıp `skiprows=2` yazılmış,
kolon başlığı satırı NaN'a düşüp `dropna` ile sessizce elenmişti, ama
`pd.to_datetime` karışık dize+datetime sütununda uyarı veriyordu); 4.
satırdan itibaren `(Tarih, Değer)` çiftleri — seri genelde 1990'a kadar
kesintisiz gider. `xlrd` bu eski `.xls` biçimini okur (yalnızca
`requirements-ingest.txt`ta; `openpyxl` yalnızca `.xlsx` okur, ikisi
birbirinin yerini TUTMAZ).

Doğrulandı (2026-09-20): `EER_EPJK_PF4_RGC_DPG` (U.S. Gulf Coast
Kerosene-Type Jet Fuel Spot Price FOB, USD/gal) 2026-09-15 değeri 4.705 —
MarketVisuals'ın "Jet Yakıtı (ABD Gulf Coast)" kartının aynı tarihli
`latestVal`i (4.71) ile birebir (yuvarlama farkı hariç). Aynı sonuç v2 JSON
API'sinde paylaşımlı `DEMO_KEY` (api.data.gov kuralı) ile de doğrulandı;
`dnav` anahtar gerektirmediği için tercih edildi.
"""

from __future__ import annotations

from io import BytesIO

import pandas as pd
import requests

from core.catalog import Seri

TABAN = "https://www.eia.gov/dnav/pet/hist_xls/{kod}d.xls"
ZAMAN_ASIMI = 60


def seri_cek(seri: Seri, session: requests.Session | None = None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı)."""
    http = session or requests
    url = TABAN.format(kod=seri.eia_series_id)
    yanit = http.get(url, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"EIA HTTP {yanit.status_code} ({seri.eia_series_id})")

    df = pd.read_excel(
        BytesIO(yanit.content), sheet_name="Data 1", skiprows=3, header=None,
        names=["date", "value"],
    )
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["date", "value"]).reset_index(drop=True)
    if df.empty:
        raise RuntimeError(f"EIA boş seri döndürdü ({seri.eia_series_id})")

    if seri.start_date:
        df = df[df["date"] >= seri.start_date].reset_index(drop=True)
    return df[["date", "value"]]
