"""FRED `fredgraph.csv` istemcisi.

Anahtar gerektirmeyen deterministik uç nokta; MarketVisuals'un
"FRED (OECD/Eurostat)" etiketli serileri bu biçimde kamuya açık. Katalog
`fred_code` alanıyla kod sabitlenir; kod yanlışsa değerler uymaz ve
regresyon testi bunu yakalar. CSV biçimi: `observation_date,<KOD>`;
boş gözlemler "." dizedir — None'a düşürülür.
"""

from __future__ import annotations

import pandas as pd
import requests

from ingest.http import durum_kodu_yukselt

from core.catalog import Seri

TABAN = "https://fred.stlouisfed.org/graph/fredgraph.csv"
ZAMAN_ASIMI = 120


def seri_cek(seri: Seri, session=None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı)."""
    http = session or requests
    yanit = http.get(f"{TABAN}?id={seri.fred_code}", timeout=ZAMAN_ASIMI)
    durum_kodu_yukselt(yanit)
    df = pd.read_csv(pd.io.common.StringIO(yanit.text))
    df = df.rename(columns={"observation_date": "date", seri.fred_code: "value"})
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"].astype(str).str.strip(), errors="coerce")
    df = df.dropna(subset=["value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df[["date", "value"]].reset_index(drop=True)
