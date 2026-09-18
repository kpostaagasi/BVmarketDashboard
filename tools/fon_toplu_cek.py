"""TEFAS toplu fon geçmişi: ay penceresi başına tek istek, tüm fonlar.

Tek-fon modu fon başına 25 istek isterdi (966 fon = 24 bin istek); bu uç
`fonKodu=None` ile bir ayın TÜM fonlarını tek yanıtta döndürüyor (ölçüm
2026-09-17: 42.544 satır / 2.038 fon / 21 gün / 3,8 sn). Çıktı
`data/fonlar/<kod>.csv` — `ingest.run` sözleşmesiyle aynı geniş biçim.

Kullanım: python -m tools.fon_toplu_cek 2024-09 2026-09
"""

from __future__ import annotations

import json
import sys
import time
from calendar import monthrange
from datetime import date

import pandas as pd
import requests

from ingest.tefas import BASLIKLAR, UC, ZAMAN_ASIMI, _istek_govdesi

from pathlib import Path

# Ölçülen hız sınırı: ay penceresi isteği ağır; 7 sn aralık EMK 2025-04'te
# 429 (ERR-224) verdi, aralık 10 sn'ye çıkarıldı ve geri çekilme eklendi.
ISTEK_ARALIGI = 10.0
GERI_CEKILME = 60.0
AZAMI_DENEME = 5
ONBELLEK = Path(".tefas_onbellek")
SUTUNLAR = {
    "tarih": "date", "fiyat": "fiyat", "tedPaySayisi": "pay",
    "kisiSayisi": "hesap", "portfoyBuyukluk": "buyukluk",
}


def aylar(bas: str, bit: str) -> list[tuple[date, date]]:
    ilk = date.fromisoformat(f"{bas}-01")
    son_ay = date.fromisoformat(f"{bit}-01")
    pencereler = []
    while ilk <= son_ay:
        pencereler.append(
            (ilk, date(ilk.year, ilk.month, monthrange(ilk.year, ilk.month)[1]))
        )
        ilk = date(ilk.year + ilk.month // 12, ilk.month % 12 + 1, 1)
    return pencereler


def ay_cek(tip: str, bas: date, bit: date, oturum) -> list[dict]:
    """Bir ay penceresi; 429'da geri çekilip yeniden dener.

    Ağır pencere isteği 7 sn aralıkla da hız sınırına takılabiliyor
    (ölçüm: EMK 2025-04'te 429); kısmi veri yazmak sessiz eksik geçmiş
    demek olduğu için hata yutulmaz, beklenip tekrar denenir.
    """
    govde = json.loads(_istek_govdesi(tip, bas))
    govde["bitTarih"] = bit.strftime("%Y%m%d")
    govde["bitSira"] = 100000
    for deneme in range(AZAMI_DENEME):
        yanit = oturum.post(UC, data=json.dumps(govde), headers=BASLIKLAR,
                            timeout=ZAMAN_ASIMI * 3)
        if yanit.status_code == 429:
            if deneme == AZAMI_DENEME - 1:
                raise RuntimeError(f"TEFAS hız sınırı ({tip} {bas})")
            time.sleep(GERI_CEKILME)
            continue
        if yanit.status_code != 200:
            raise RuntimeError(f"TEFAS HTTP {yanit.status_code} ({tip} {bas})")
        break
    sonuc = yanit.json()
    satirlar = sonuc.get("resultList") or []
    if not satirlar:
        mesaj = sonuc.get("errorMessage") or ""
        if "out of bounds" in mesaj:
            return []
        raise RuntimeError(f"TEFAS beklenmeyen boş yanıt ({tip} {bas}): {mesaj}")
    if int(sonuc["toplamSayi"]) != len(satirlar):
        raise RuntimeError(f"TEFAS kırpılmış pencere ({tip} {bas})")
    return satirlar


def main() -> int:
    bas, bit = sys.argv[1], sys.argv[2]
    oturum = requests.Session()
    ONBELLEK.mkdir(parents=True, exist_ok=True)
    parcalar: list[pd.DataFrame] = []
    for tip in ("YAT", "EMK"):
        for pencere_bas, pencere_bit in aylar(bas, bit):
            # Pencere önbelleği: 429 sonrası yeniden başlatma çekileni tekrar çekmesin.
            yol = ONBELLEK / f"{tip}-{pencere_bas:%Y-%m}.csv"
            if yol.exists():
                parcalar.append(pd.read_csv(yol, dtype={"fonKodu": str}))
                print(f"{tip} {pencere_bas:%Y-%m}: önbellek", flush=True)
                continue
            satirlar = ay_cek(tip, pencere_bas, pencere_bit, oturum)
            print(f"{tip} {pencere_bas:%Y-%m}: {len(satirlar)} satır", flush=True)
            if satirlar:
                blok = pd.DataFrame(satirlar)[["fonKodu", *SUTUNLAR]]
                blok.to_csv(yol, index=False)
                parcalar.append(blok)
            time.sleep(ISTEK_ARALIGI)

    ham = pd.concat(parcalar, ignore_index=True)
    ham = ham[["fonKodu", *SUTUNLAR]].rename(columns=SUTUNLAR)
    ham["date"] = pd.to_datetime(ham["date"]).dt.strftime("%Y-%m-%d")
    ham = ham.drop_duplicates(["fonKodu", "date"]).sort_values(["fonKodu", "date"])

    hedef = __import__("pathlib").Path("data/fonlar")
    hedef.mkdir(parents=True, exist_ok=True)
    yazilan = 0
    for kod, blok in ham.groupby("fonKodu"):
        blok.drop(columns="fonKodu").to_csv(
            hedef / f"{str(kod).lower()}.csv", index=False,
        )
        yazilan += 1
    print(f"{yazilan} fon CSV'si yazıldı ({len(ham)} satır)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
