"""TÜİK kümes hayvancılığı üretim istatistiği — Eurostat aynası istemcisi.

TÜİK'in kendisi bu kırılımı (kümes eti üretimi/kesilen tavuk sayısı, aylık,
makine-okunur) yayımlamıyor; ama TÜİK'in Eurostat'a bildirdiği ham veri
`apro_mt_pwgtm` ("Poultry production and productivity") veri kümesinde
AYNEN yer alıyor — kaynağı hâlâ TÜİK'tir, Eurostat yalnızca dağıtım ucu
(marketvisuals.net'in kartları da "TÜİK / Eurostat apro_mt_pwgtm" diye
ikisini birlikte anıyor). Uç dokümante ve kamuya açık:
`https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/
apro_mt_pwgtm?format=JSON&geo=TR&meat=<kod>&unit=<kod>`.

JSON-stat 2.0 biçimi: `value` seyrek bir `{düz_indeks: değer}` sözlüğü;
düz indeks `id` sırasındaki eksenler (`freq, meatitem, meat, unit, geo,
time`) üzerinden satır-öncelikli hesaplanır. `geo=TR` tek coğrafya
döndürdüğünden ve `meatitem=SLAUGHT` (Kesimler) tek değerli sabit eksen
olduğundan, iki gerçek eksen `meat` (et türü) ve `unit` (birim) kalıyor.

Üç kart üç (meat, unit) çiftine karşılık gelir — hepsi Temmuz 2026
değerleriyle commodity_poultry.html'e BİREBİR doğrulandı (ölçüldü
2026-09-18):
- Toplam Kümes Eti Üretimi: meat=B7000 (Poultry meat) unit=THS_T (Bin ton)
  → 257,0 * 1000 = 257.000 ton (kart: 257.000,0 ton).
- Tavuk Eti Üretimi: meat=B7100 (Chicken) unit=THS_T → 251,86 * 1000 =
  251.860 ton (kart: 251.860,0 ton).
- Kesilen Tavuk Sayısı: meat=B7100 unit=THS_HD (Bin baş) → 133.407,03 BİN
  adet, ölçeksiz (kart zaten "bin adet" gösteriyor).

THS_T "bin ton" geldiğinden `ton`a çevirmek için katalogda `olcek: 1000`
gerekir (AGENTS.md: "tek ölçekleme noktası" `ingest.run.olcekle`);
THS_HD zaten "bin adet" olduğundan ölçeksiz bırakılır.
"""

from __future__ import annotations

import pandas as pd
import requests

from core.catalog import GECERLI_TUIK_KANATLI_OLCUTLERI, Seri

UC = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/apro_mt_pwgtm"
ZAMAN_ASIMI = 60
GEO = "TR"

# `tuik_kanatli_olcut` -> Eurostat (meat, unit) kodu. GECERLI_TUIK_KANATLI_
# OLCUTLERI ile birebir eşleşmeli.
OLCUT_KODLARI = {
    "toplam-uretim": ("B7000", "THS_T"),
    "tavuk-uretim": ("B7100", "THS_T"),
    "kesilen-tavuk": ("B7100", "THS_HD"),
}
assert set(OLCUT_KODLARI) == GECERLI_TUIK_KANATLI_OLCUTLERI


def _json_cek(session=None) -> dict:
    http = session or requests
    meat_kodlari = sorted({m for m, _ in OLCUT_KODLARI.values()})
    unit_kodlari = sorted({u for _, u in OLCUT_KODLARI.values()})
    yanit = http.get(
        UC,
        params={
            "format": "JSON", "lang": "EN", "geo": GEO,
            "meat": meat_kodlari, "unit": unit_kodlari,
        },
        timeout=ZAMAN_ASIMI,
    )
    if yanit.status_code != 200:
        raise RuntimeError(f"Eurostat HTTP {yanit.status_code} (apro_mt_pwgtm)")
    return yanit.json()


def noktalari_ayikla(veri: dict, meat_kodu: str, unit_kodu: str) -> list[tuple[str, float]]:
    """JSON-stat seyrek `value` sözlüğünden bir (meat, unit) çiftinin serisini çıkarır.

    Düz indeks satır-öncelikli: `id` sırası (freq, meatitem, meat, unit,
    geo, time); freq/meatitem/geo boyutu burada hep 1 (tek geo istendi),
    bu yüzden `((meat_idx * unit_boyutu) + unit_idx) * time_boyutu + t`.
    """
    boyut = veri["dimension"]
    meat_idx_haritasi = boyut["meat"]["category"]["index"]
    unit_idx_haritasi = boyut["unit"]["category"]["index"]
    zaman_idx_haritasi = boyut["time"]["category"]["index"]
    if meat_kodu not in meat_idx_haritasi:
        raise RuntimeError(f"Eurostat: meat kodu yanıtta yok: {meat_kodu}")
    if unit_kodu not in unit_idx_haritasi:
        raise RuntimeError(f"Eurostat: unit kodu yanıtta yok: {unit_kodu}")

    zaman_etiketleri = {idx: etiket for etiket, idx in zaman_idx_haritasi.items()}
    zaman_boyutu = len(zaman_idx_haritasi)
    unit_boyutu = len(unit_idx_haritasi)
    taban = (meat_idx_haritasi[meat_kodu] * unit_boyutu + unit_idx_haritasi[unit_kodu]) * zaman_boyutu

    degerler = veri["value"]
    noktalar = []
    for t in range(zaman_boyutu):
        anahtar = str(taban + t)
        if anahtar not in degerler:
            continue  # Eurostat o ay için henüz/hiç veri bildirmemiş
        ay_etiketi = zaman_etiketleri[t]  # "YYYY-MM"
        noktalar.append((f"{ay_etiketi}-01", float(degerler[anahtar])))
    return noktalar


def _tum_noktalari_getir(onbellek: dict, session=None) -> dict[str, list[tuple[str, float]]]:
    if "noktalar" in onbellek:
        return onbellek["noktalar"]

    veri = _json_cek(session=session)
    noktalar = {
        olcut: noktalari_ayikla(veri, meat_kodu, unit_kodu)
        for olcut, (meat_kodu, unit_kodu) in OLCUT_KODLARI.items()
    }
    onbellek["noktalar"] = noktalar
    return noktalar


def seri_cek(seri: Seri, onbellek: dict | None = None, session: requests.Session | None = None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker; Eurostat tek istekte 1950'den bugüne
    tüm ayları döndürdüğünden pencere sınırlaması yok."""
    if onbellek is None:
        onbellek = {}

    tum_noktalar = _tum_noktalari_getir(onbellek, session=session)
    noktalar = tum_noktalar.get(seri.tuik_kanatli_olcut, [])
    if not noktalar:
        raise RuntimeError(f"Eurostat: '{seri.tuik_kanatli_olcut}' için hiç veri yok")

    df = pd.DataFrame(noktalar, columns=["date", "value"])
    return df.reset_index(drop=True)
