"""Fon katalog girdilerini üretir: her TEFAS fonu için bir `tefas_fon` serisi.

Fon listesi ve unvanlar referans platformun yayımladığı fon meta dosyasından
alınır (958 fon; 690 yatırım + 268 emeklilik). Üretilen blok
`catalog/series.yaml` sonuna eklenir — elle 10 bin satır YAML yazmak yerine
kaynak listesinden türetilir.

Kullanım: python -m tools.fon_katalog_uret > /tmp/fonlar.yaml
"""

from __future__ import annotations

import sys

import requests

META_UC = "https://marketvisuals.net/assets/tefas_fon_compare.json"
TIP_ESLEME = {"Yatırım Fonu": "YAT", "Emeklilik Fonu": "EMK"}
BASLANGIC = "2024-09-01"


def yaml_kacir(metin: str) -> str:
    return metin.replace('"', "'")


def girdi(kod: str, unvan: str, tefas_tip: str) -> str:
    return "\n".join([
        f"- id: fonlar/{kod.lower()}",
        f'  title: "{yaml_kacir(unvan)} ({kod})"',
        "  category: fonlar",
        '  kaynak: { name: TEFAS, url: "https://www.tefas.gov.tr" }',
        "  kaynak_tipi: tefas_fon",
        f"  tefas_tip: {tefas_tip}",
        f"  tefas_kod: {kod}",
        f'  start_date: "{BASLANGIC}"',
        '  unit: "TL"',
        "  freq: daily",
        "  monthly_agg: last",
        "  charts: [fon]",
        "",
    ])


def main() -> int:
    meta = requests.get(META_UC, timeout=60).json()
    bloklar = []
    for kod, kayit in sorted(meta.items()):
        tip = TIP_ESLEME.get(kayit["tip"])
        if tip is None:
            raise RuntimeError(f"Bilinmeyen fon tipi: {kayit['tip']} ({kod})")
        bloklar.append(girdi(kod, kayit["unvan"], tip))
    sys.stdout.write("\n" + "\n".join(bloklar))
    print(f"{len(bloklar)} fon girdisi üretildi", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
