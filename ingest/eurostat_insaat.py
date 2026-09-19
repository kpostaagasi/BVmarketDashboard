"""Eurostat sts_copr_m (İnşaat Üretim Endeksi / "Production in construction")
istemcisi.

Kaynak: Eurostat JSON-stat REST API (`sts_copr_m`, aylık, Türkiye). Uç:
GET https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/
sts_copr_m?format=JSON&geo=TR&indic_bt=PRD&s_adj=NSA&unit=I21 — `nace_r2`
(F/F41/F42/F43) katalogda seçilen TEK eksendir, kalan parametreler sabittir:
`indic_bt=PRD` ("Production (volume)"), `s_adj=NSA` (mevsim/takvimden
arındırılmamış ham endeks), `unit=I21` (2021=100).

NOT: `ingest/eurostat.py` (nrg_pc_204/205 elektrik fiyatları, kaynak_tipi:
`eurostat`) ile AYNI KAYNAK_TIPI DEĞİL — o adaptörün ekseni (dataset × geo ×
para birimi) burada uygun değil (para birimi kavramı yok, eksen `nace_r2`).
`ingest/eurostat_turizm.py` (tour_occ_nim, kaynak_tipi: `eurostat_turizm`)
ile AYNI ŞEKİLDE ayrı bir kaynak_tipi — bu modül onun tek-serbest-eksenli
desenini birebir izler.

JSON-stat gövdesinde boyut sırası [freq, indic_bt, nace_r2, s_adj, unit, geo,
time]; freq/indic_bt/s_adj/unit/geo bu sorguda hep boyut-1 (tek kategori)
olduğundan düz değer dizisindeki indeks = nace_r2_indeksi * zaman_uzunluğu +
zaman_indeksi (bkz. `ingest/eurostat_turizm.py` docstring'i, aynı geometri).

Ölçüldü (2026-09-20): Temmuz 2026 F=119,6 / F41=134,3 / F42=88,8 / F43=107,3
— marketvisuals.net'in evds_insaat.html "İnşaat Üretim Endeksi -
Toplam/Bina/Bina Dışı/Özel Faaliyetler" kartlarıyla DÖRDÜ DE BİREBİR eşleşti.

Sözleşme: seri_cek(seri, *, onbellek=None, session=None) -> DataFrame[date,value]
"""

from __future__ import annotations

import pandas as pd
import requests

from core.catalog import GECERLI_EUROSTAT_INSAAT_NACE

UC = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/sts_copr_m"
ZAMAN_ASIMI = 60
PARAMETRELER = {
    "format": "JSON", "lang": "EN", "geo": "TR", "freq": "M",
    "indic_bt": "PRD", "s_adj": "NSA", "unit": "I21",
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

    nace = seri.eurostat_insaat_nace
    if nace not in GECERLI_EUROSTAT_INSAAT_NACE:
        raise RuntimeError(f"Geçersiz eurostat_insaat_nace: {nace!r}")

    boyut = veri["dimension"]
    zaman_indeks = boyut["time"]["category"]["index"]
    nace_indeks = boyut["nace_r2"]["category"]["index"]
    if nace not in nace_indeks:
        raise RuntimeError(
            f"Eurostat sts_copr_m'de '{nace}' nace_r2 yok: {sorted(nace_indeks)}"
        )
    nace_i = nace_indeks[nace]
    zaman_uzunlugu = veri["size"][-1]
    degerler = veri["value"]

    satirlar = []
    for zaman, zaman_i in zaman_indeks.items():
        duz_indeks = nace_i * zaman_uzunlugu + zaman_i
        ham = degerler.get(str(duz_indeks))
        if ham is None:
            continue
        yil, ay = zaman.split("-")
        satirlar.append((f"{yil}-{ay}-01", float(ham)))

    df = pd.DataFrame(satirlar, columns=["date", "value"]).sort_values("date")
    return df.reset_index(drop=True)
