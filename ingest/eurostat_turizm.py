"""Eurostat tour_occ_nim (konaklama tesislerinde geceleme sayısı) istemcisi.

Kaynak: Eurostat JSON-stat REST API (`tour_occ_nim`, aylık, Türkiye). Uç:
GET https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/
tour_occ_nim?format=JSON&lang=EN&geo=TR&unit=NR&nace_r2=I551-I553&freq=M
— `c_resid` (TOTAL/DOM/FOR) katalogda seçilen TEK eksendir, kalan
parametreler sabittir (yalnızca Türkiye'nin toplam konaklama tesislerinde
geceleme sayısı izlenir).

NOT: `ingest/eurostat.py` (nrg_pc_204/205 elektrik fiyatları, `kaynak_tipi:
eurostat`) ile AYNI KAYNAK_TIPI DEĞİL — o adaptörün ekseni (dataset × geo ×
para birimi) burada uygun değil (para birimi kavramı yok, eksen `c_resid`).
Bu yüzden ayrı `kaynak_tipi` (`eurostat_turizm`) ve ayrı modül; EPDK'nın
`epdk`/`epdk_dogalgaz`/`epdk_fiyat` ayrımıyla aynı gerekçe (aynı kurum, eksen
farklı → ayrı tip).

JSON-stat gövdesinde boyut sırası [freq, c_resid, unit, nace_r2, geo, time];
freq/unit/nace_r2/geo bu sorguda hep boyut-1 (tek kategori) olduğundan düz
değer dizisindeki indeks = c_resid_indeksi * zaman_uzunluğu + zaman_indeksi.

Ölçüldü (2026-09-18): Aralık 2025 TOTAL=12.272.844, DOM=6.903.812,
FOR=5.369.032 — marketvisuals.net "Geceleme - Toplam/Yerli/Yabancı"
kartlarıyla tam eşleşiyor.

Sözleşme: seri_cek(seri, *, onbellek=None, session=None) -> DataFrame[date,value]
"""

from __future__ import annotations

import pandas as pd
import requests

from core.catalog import GECERLI_EUROSTAT_TURIZM_RESID

UC = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/tour_occ_nim"
ZAMAN_ASIMI = 60
PARAMETRELER = {
    "format": "JSON", "lang": "EN", "geo": "TR", "unit": "NR",
    "nace_r2": "I551-I553", "freq": "M",
}


def _veriyi_cek(session=None) -> dict:
    http = session or requests
    yanit = http.get(UC, params=PARAMETRELER, timeout=ZAMAN_ASIMI)
    yanit.raise_for_status()
    return yanit.json()


def seri_cek(seri, *, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    onbellek = {} if onbellek is None else onbellek
    if "veri" not in onbellek:
        onbellek["veri"] = _veriyi_cek(session=session)
    veri = onbellek["veri"]

    resid = seri.eurostat_turizm_resid
    if resid not in GECERLI_EUROSTAT_TURIZM_RESID:
        raise RuntimeError(f"Geçersiz eurostat_turizm_resid: {resid!r}")

    boyut = veri["dimension"]
    zaman_indeks = boyut["time"]["category"]["index"]
    resid_indeks = boyut["c_resid"]["category"]["index"]
    if resid not in resid_indeks:
        raise RuntimeError(
            f"Eurostat tour_occ_nim'de '{resid}' c_resid yok: {sorted(resid_indeks)}"
        )
    resid_i = resid_indeks[resid]
    zaman_uzunlugu = veri["size"][-1]
    degerler = veri["value"]

    satirlar = []
    for zaman, zaman_i in zaman_indeks.items():
        duz_indeks = resid_i * zaman_uzunlugu + zaman_i
        ham = degerler.get(str(duz_indeks))
        if ham is None:
            continue
        yil, ay = zaman.split("-")
        satirlar.append((f"{yil}-{ay}-01", float(ham)))

    df = pd.DataFrame(satirlar, columns=["date", "value"]).sort_values("date")
    return df.reset_index(drop=True)
