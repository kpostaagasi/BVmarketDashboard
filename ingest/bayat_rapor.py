"""Ingest sonrası bayat seri raporu: `python -m ingest.bayat_rapor`.

`core.takvim` ile aynı tazelik mantığını kullanır; gecikmiş / verisi olmayan /
okunamayan serileri kaynak başına gruplayıp yazdırır. GitHub Actions'ta
`GITHUB_STEP_SUMMARY` varsa oraya da yazar. Koşuyu asla kırmaz (çıkış 0):
kaynak geç kalmış olabilir, rapor yalnızca görünürlük içindir.
"""

from __future__ import annotations

import os
from collections import defaultdict

from core.takvim import GECIKMIS, OKUNAMADI, VERI_YOK, TakvimSatiri, takvim

SORUNLU = (OKUNAMADI, VERI_YOK, GECIKMIS)


def rapor_uret(satirlar: list[TakvimSatiri]) -> str:
    sorunlu = [s for s in satirlar if s.durum in SORUNLU]
    baslik = f"## Bayat seri raporu: {len(sorunlu)} / {len(satirlar)} seri sorunlu"
    if not sorunlu:
        return baslik + "\n\nTüm seriler eşik içinde."
    notlu = sum(1 for s in sorunlu if s.seri.yayin_notu)
    notsuz = len(sorunlu) - notlu
    kaynaklar: dict[str, list[TakvimSatiri]] = defaultdict(list)
    for s in sorunlu:
        kaynaklar[s.seri.kaynak_tipi].append(s)
    satir = [
        baslik,
        "",
        f"Notu olan (kaynak geride): {notlu}. Notu olmayan (bakılacak): {notsuz}.",
        "",
        "| Kaynak tipi | Sorunlu | Durum | En eski bekleme |",
        "|---|---:|---|---:|",
    ]
    for tip, liste in sorted(kaynaklar.items(), key=lambda k: -len(k[1])):
        durumlar = ", ".join(f"{d} {sum(s.durum == d for s in liste)}" for d in SORUNLU
                             if any(s.durum == d for s in liste))
        bekleme = max((s.bekleme_gunu or 0) for s in liste)
        satir.append(f"| {tip} | {len(liste)} | {durumlar} | {bekleme} gün |")
    satir += ["", "Örnekler (kaynak başına en fazla 3):", ""]
    for tip, liste in sorted(kaynaklar.items()):
        for s in liste[:3]:
            ek = f" ({s.bekleme_gunu} gün)" if s.bekleme_gunu is not None else ""
            notu = f" — {s.seri.yayin_notu}" if s.seri.yayin_notu else ""
            satir.append(f"- `{s.seri.id}` [{tip}]: {s.durum}{ek}{notu}")
    return "\n".join(satir)


def main() -> int:
    metin = rapor_uret(takvim())
    print(metin)
    ozet = os.environ.get("GITHUB_STEP_SUMMARY")
    if ozet:
        with open(ozet, "a", encoding="utf-8") as f:
            f.write(metin + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
