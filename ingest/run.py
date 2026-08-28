"""Ingest orchestrator.

Bir serinin başarısızlığı diğerlerini düşürmez: başarılı seriler yine
yazılır, hatalar toplanıp raporlanır, en az bir hata varsa exit kodu 1
olur ki Actions kırmızıya dönsün.
"""

from __future__ import annotations

import argparse
import os
import sys

import requests

from core.catalog import Seri, seri_listele
from core.data import seri_yolu
from ingest import epias, evds, yahoo


def _cek(seri: Seri, api_key: str | None, tgt: str | None, oturum):
    """Seriyi kaynak tipine göre doğru istemciye yönlendirir."""
    if seri.kaynak_tipi == "evds":
        return evds.seri_cek(seri, api_key, session=oturum)
    if seri.kaynak_tipi == "yahoo":
        return yahoo.seri_cek(seri, session=oturum)
    if seri.kaynak_tipi == "epias":
        return epias.seri_cek(seri, tgt, session=oturum)
    raise ValueError(f"Bilinmeyen kaynak tipi: {seri.kaynak_tipi}")


def seriyi_yaz(seri: Seri, df) -> int:
    yol = seri_yolu(seri.id)
    yol.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(yol, index=False, float_format="%.5f")
    return len(df)


def main() -> int:
    ayristirici = argparse.ArgumentParser(
        description="Katalogdaki serileri kaynaklarından çeker"
    )
    ayristirici.add_argument(
        "--only", help="Yalnızca bu seri id'sini çek (hata ayıklama için)"
    )
    args = ayristirici.parse_args()

    seriler = seri_listele()
    if args.only:
        seriler = [s for s in seriler if s.id == args.only]
        if not seriler:
            print(f"HATA: katalogda yok: {args.only}", file=sys.stderr)
            return 2

    api_key = os.environ.get("EVDS_API_KEY")
    if any(s.kaynak_tipi == "evds" for s in seriler) and not api_key:
        print("HATA: EVDS_API_KEY tanımlı değil veya boş", file=sys.stderr)
        return 2

    tgt = None
    if any(s.kaynak_tipi == "epias" for s in seriler):
        kullanici = os.environ.get("EPIAS_USERNAME")
        parola = os.environ.get("EPIAS_PASSWORD")
        if not (kullanici and parola):
            print(
                "HATA: EPIAS_USERNAME veya EPIAS_PASSWORD tanımlı değil",
                file=sys.stderr,
            )
            return 2

    basarili: list[str] = []
    hatalar: list[tuple[str, str]] = []

    with requests.Session() as oturum:
        epias_seriler = [s for s in seriler if s.kaynak_tipi == "epias"]
        if epias_seriler:
            try:
                tgt = epias.tgt_al(kullanici, parola, session=oturum)
            except Exception as hata:  # noqa: BLE001 — modül bazlı izolasyon
                # EPİAŞ girişi başarısızsa (parola süresi dolar, giriş
                # sunucusu 503 verir) yalnızca epias serileri düşer;
                # EVDS/Yahoo serileri koşmaya devam etmeli (docstring:
                # "bir serinin başarısızlığı diğerlerini düşürmez").
                for seri in epias_seriler:
                    hatalar.append((seri.id, f"EPİAŞ girişi başarısız: {hata}"))
                    print(
                        f"  ✗ {seri.id} — EPİAŞ girişi başarısız: {hata}",
                        file=sys.stderr,
                    )

        for seri in seriler:
            if seri.kaynak_tipi == "epias" and tgt is None:
                continue  # giriş başarısız — hatalar listesine zaten eklendi
            try:
                df = _cek(seri, api_key, tgt, oturum)
                adet = seriyi_yaz(seri, df)
                basarili.append(f"{seri.id} ({adet} nokta)")
                print(f"  ✓ {seri.id} — {adet} nokta")
            except Exception as hata:  # noqa: BLE001 — modül bazlı izolasyon
                hatalar.append((seri.id, str(hata)))
                print(f"  ✗ {seri.id} — {hata}", file=sys.stderr)

    print(f"\n{len(basarili)}/{len(seriler)} seri başarılı")
    if hatalar:
        print(f"{len(hatalar)} seri başarısız:", file=sys.stderr)
        for seri_id, mesaj in hatalar:
            print(f"  - {seri_id}: {mesaj}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
