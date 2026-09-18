"""674 ülke×sektör serisini tek koşuda üretir (bülten önbelleği paylaşımlı).

`ingest.run --only` seri başına ayrı süreç açar ve her seferinde ~44 XLSX
dosyasını yeniden indirir. Bu betik `ulke_seri_cek`i tek süreçte, tek
önbellekle çağırır: 674 seri için ~44 indirme.
"""

from __future__ import annotations

import requests

from core.catalog import serileri_yukle
from ingest import tim
from ingest.run import seriyi_yaz


def main() -> int:
    seriler = [s for s in serileri_yukle() if s.kaynak_tipi == "tim_ulke"]
    oturum = requests.Session()
    onbellek: dict = {}
    hatalar = []
    for sira, seri in enumerate(seriler, start=1):
        try:
            df = tim.ulke_seri_cek(seri, onbellek=onbellek, session=oturum)
            adet = seriyi_yaz(seri, df)
            print(f"{sira}/{len(seriler)} {seri.id}: {adet} nokta", flush=True)
        except RuntimeError as hata:
            hatalar.append((seri.id, str(hata)))
            print(f"{sira}/{len(seriler)} {seri.id}: HATA {hata}", flush=True)
    print(f"{len(seriler) - len(hatalar)}/{len(seriler)} seri yazıldı")
    for seri_id, mesaj in hatalar:
        print(f"  - {seri_id}: {mesaj}")
    return 1 if hatalar else 0


if __name__ == "__main__":
    raise SystemExit(main())
