"""Eurostat euro bölgesi güven endeksleri (İş ve Tüketici Anketleri) istemcisi.

Kaynak: Eurostat JSON-stat REST API. Uç:
GET https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/<küme>
?format=JSON&lang=EN&geo=EA21&s_adj=SA&indic=<gösterge> — `eurostat_guven_gosterge`
katalogda seçilen TEK eksendir (tüketici / imalat).

Neden FRED değil: FRED'in OECD/Eurostat aynası (CSCICP02EZM460S, BSCICP02EZM460S)
Ocak 2026'da kesildi; Eurostat aynı ay sonrasını yayımlamaya devam ediyor
(ölçüldü 2026-10-02: son veri 2026-09).

`geo=EA21` bilerek seçildi: Bulgaristan 2026-01'de euro'ya geçince `EA20`
2025-12'de kesildi, `EA` ise boş döner. Bileşim değişikliği Ocak 2026
örtüşmesinde ≤0,2 puan kayma yaratıyor (EA20 ile EA21 aynı ay karşılaştırıldı).
Geçmiş EA21 serisi tüketicide 1985-01'den, imalatta 1980-01'den başlar.

Dönem ekseni dışındaki tüm boyutlar sorguda tek kategoriye indiği için düz
değer dizisindeki indeks doğrudan zaman indeksidir.

Sözleşme: seri_cek(seri, *, onbellek=None, session=None) -> DataFrame[date,value]
"""

from __future__ import annotations

import pandas as pd
import requests

TABAN = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
ZAMAN_ASIMI = 60
# gösterge -> (veri kümesi, indic kodu)
GOSTERGELER = {
    "tuketici": ("ei_bsco_m", "BS-CSMCI"),
    "imalat": ("ei_bssi_m_r2", "BS-ICI-BAL"),
}


def seri_cek(seri, *, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    gosterge = seri.eurostat_guven_gosterge
    if gosterge not in GOSTERGELER:
        raise RuntimeError(f"Geçersiz eurostat_guven_gosterge: {gosterge!r}")
    kume, indic = GOSTERGELER[gosterge]
    http = session or requests
    yanit = http.get(
        TABAN + kume,
        params={"format": "JSON", "lang": "EN", "geo": "EA21", "s_adj": "SA", "indic": indic},
        timeout=ZAMAN_ASIMI,
    )
    yanit.raise_for_status()
    veri = yanit.json()

    zaman_indeks = veri["dimension"]["time"]["category"]["index"]
    degerler = veri["value"]
    satirlar = []
    for zaman, zaman_i in zaman_indeks.items():
        ham = degerler.get(str(zaman_i))
        if ham is None:
            continue
        yil, ay = zaman.split("-")
        satirlar.append((f"{yil}-{ay}-01", float(ham)))
    if not satirlar:
        raise RuntimeError(f"Eurostat {kume}/{indic} EA21 için değer dönmedi")
    df = pd.DataFrame(satirlar, columns=["date", "value"]).sort_values("date")
    return df.reset_index(drop=True)
