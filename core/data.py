"""Veri okuma: repodaki CSV'lere açılan tek kapı.

Bugün veri repoda CSV olarak duruyor. İleride harici bir veritabanına
geçilirse yalnızca `load_series()`'in içi değişir; sayfalar etkilenmez.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from core.catalog import KOK

VERI_DIZINI = KOK / "data"


class VeriYokHatasi(FileNotFoundError):
    """Seri katalogda var ama veri dosyası üretilmemiş."""


def seri_yolu(seri_id: str) -> Path:
    return VERI_DIZINI / f"{seri_id}.csv"


def seri_csv_oku(yol: Path) -> pd.DataFrame:
    if not yol.exists():
        raise VeriYokHatasi(
            f"Veri dosyası yok: {yol}\n"
            "Veriyi üretmek için `python -m ingest.run` çalıştırın."
        )
    df = pd.read_csv(yol, parse_dates=["date"])
    df = df.dropna(subset=["value"]).sort_values("date").set_index("date")
    df.index.name = "date"
    return df[["value"]].astype({"value": "float64"})


@st.cache_data(show_spinner=False)
def load_series(seri_id: str) -> pd.DataFrame:
    """Katalogdaki bir serinin verisini döndürür (önbellekli)."""
    return seri_csv_oku(seri_yolu(seri_id))
