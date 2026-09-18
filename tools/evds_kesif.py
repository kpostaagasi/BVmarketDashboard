"""EVDS keşif yardımcısı: veri grubu ara, grubun serilerini listele.

Ölçülen uç biçimi (2026-09-17): sorgu parametreleri YOLUN PARÇASI —
`/serieList/fe/type=json&code=<grup>`. `?code=` olarak gönderilirse uç boş
liste döndürür (sessiz yanlış sonuç), bu yüzden burada tek noktada tutuluyor.

Kullanım:
    python -m tools.evds_kesif gruplar "ciro"      # grup adında ara
    python -m tools.evds_kesif seriler bie_tcirosanay2021
"""

from __future__ import annotations

import os
import sys

import requests

TABAN = "https://evds3.tcmb.gov.tr/igmevdsms-dis"


def _oturum() -> requests.Session:
    oturum = requests.Session()
    oturum.headers["key"] = os.environ["EVDS_API_KEY"]
    return oturum


def gruplar(desen: str) -> list[tuple[str, str, str]]:
    """Konu/grup adı `desen` içeren tüm veri gruplarını döndürür."""
    yanit = _oturum().get(f"{TABAN}/categories/withDatagroups/type=json", timeout=60)
    yanit.raise_for_status()
    bulunan = []
    for konu in yanit.json():
        for grup in konu.get("DATAGROUPS", []):
            metin = f"{konu.get('TOPIC_TITLE_TR','')} {grup.get('DATAGROUP_TYPE','')}"
            if desen.casefold() in metin.casefold():
                bulunan.append((
                    grup["DATAGROUP_CODE"], grup["DATAGROUP_TYPE"],
                    grup.get("FREQUENCY_STR", ""),
                ))
    return bulunan


def seriler(grup_kodu: str) -> list[tuple[str, str, str]]:
    """Grubun serileri: (SERIE_CODE, SERIE_NAME, FREQUENCY_STR)."""
    yanit = _oturum().get(
        f"{TABAN}/serieList/fe/type=json&code={grup_kodu}", timeout=60,
    )
    yanit.raise_for_status()
    return [
        (s["SERIE_CODE"], s["SERIE_NAME"], s.get("FREQUENCY_STR", ""))
        for s in yanit.json()
    ]


def main() -> int:
    komut, arg = sys.argv[1], sys.argv[2]
    satirlar = gruplar(arg) if komut == "gruplar" else seriler(arg)
    for kod, ad, frekans in satirlar:
        print(f"{kod:32s} | {frekans:10s} | {ad[:90]}")
    print(f"{len(satirlar)} kayıt", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
