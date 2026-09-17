"""Gerçek kaynak ↔ referans sayfa değer bütünlüğü (evds_kko.html).

Referansın mevsimsellik izleri (Oca–Ara, üç yıl) bizim EVDS CSV'mizden
üretilen mevsimsellikle birebir; tek fark referansın yayınlanmamış
ayları 0 doldurması (biz NaN — veri yokluğu görünür kalır, bkz.
core/charts.py kismi_aylari_dus).
"""

from __future__ import annotations

from pathlib import Path

from core.charts import mevsimsellik_figuru

KOK = Path(__file__).resolve().parents[1]


def _referans_2026() -> list[float]:
    import json
    import re

    yol = KOK / ".firecrawl" / "evds_kko.html"
    if not yol.exists():
        import pytest

        pytest.skip("referans anlık görüntüsü yok")
    metin = yol.read_text(encoding="utf-8")
    m = re.search(r"(?:var|const|let)\s+CHARTS\s*=\s*", metin)
    assert m is not None, "Referans sayfada CHARTS tanımı bulunamadı"
    grafikler = json.JSONDecoder().raw_decode(metin[m.end():])[0]
    return next(
        d["data"][:8]
        for d in grafikler[0]["data"]["datasets"]
        if d["label"] == "2026"
    )


def test_kko_mevsimselligi_2026_birebir():
    import pandas as pd

    df = pd.read_csv(
        f"{KOK}/data/sanayi/kapasite-kullanim.csv", parse_dates=["date"]
    ).set_index("date")
    fig = mevsimsellik_figuru(df, "KKO %", agg="mean", freq="monthly")
    iz26 = next(t for t in fig.data if t.name == "2026")
    bizim = [float(v) for v in list(iz26.y)[:8]]
    referans = _referans_2026()
    assert bizim == referans
