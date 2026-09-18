"""Ingest orchestrator.

Bir serinin başarısızlığı diğerlerini düşürmez: başarılı seriler yine
yazılır, hatalar toplanıp raporlanır, en az bir hata varsa exit kodu 1
olur ki Actions kırmızıya dönsün.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from core.catalog import Seri, seri_listele
from core.data import seri_yolu
from ingest import bddk, ebebek, epdk, epias, eurocontrol, evds, fred, osd, pgsus, tav, tefas, thy, tim, yahoo

# Koşu başına tek oturum tüm adaptörlere geçiyor; retry politikası bu yüzden
# tek yerde tanımlanabiliyor (devredilen iş #1). Ölçüm: 111 serilik bir tam
# koşuda EPİAŞ'tan okuma zaman aşımı ve EVDS'ten "Remote end closed
# connection" geldi ve iki seri o gün için düştü; all-or-nothing commit
# politikasıyla tek geçici hata günün tamamını götürüyordu.
# POST'lar da yeniden denenir: hepsi salt-okuma sorgusu, yan etkisi yok.
RETRY = Retry(
    total=3,
    backoff_factor=1.5,  # 0 → 1,5 → 3 sn
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset({"GET", "POST"}),
    raise_on_status=False,
)


def olcekle(df, olcek: float | None):
    """Katalog `olcek`ini uygular. **Tek ölçekleme noktası burasıdır.**

    `None` = ölçekleme yok; katalog `olcek` vermediyse seri olduğu gibi
    kalır. `date` dışındaki tüm sütunlar çarpılır, böylece bileşenli
    (geniş) seriler de tek çağrıda kapsanır ve sütun-başına dolambaç
    gerekmez.

    Ölçekleme adaptörden SONRA uygulanır: saatlik veriyi günlüğe indirgeyen
    adaptörler (EPİAŞ) indirgemeyi kendi içinde bitirir, dolayısıyla buraya
    gelen çerçeve zaten indirgenmiştir. Bir adaptör kendi içinde de
    ölçeklerse çift ölçekleme olur — ölçeklemeyi adaptöre geri koymayın.
    """
    if olcek is None:
        return df
    df = df.copy()
    for sutun in df.columns:
        if sutun != "date":
            df[sutun] = df[sutun] * olcek
    return df


def _cek(seri: Seri, api_key: str | None, tgt: str | None, oturum,
         epias_onbellek: dict | None = None,
         osd_onbellek: dict | None = None,
         tim_onbellek: dict | None = None,
         bddk_onbellek: dict | None = None,
         tefas_onbellek: dict | None = None,
         ec_onbellek: dict | None = None,
         tim_il_onbellek: dict | None = None,
         tim_ulke_onbellek: dict | None = None,
         thy_onbellek: dict | None = None,
         pgsus_onbellek: dict | None = None,
         tav_onbellek: dict | None = None,
         ebebek_onbellek: dict | None = None,
         epdk_onbellek: dict | None = None):
    """Seriyi kaynak tipine göre doğru istemciye yönlendirir ve ölçekler."""
    if seri.kaynak_tipi == "evds":
        df = evds.seri_cek(seri, api_key, session=oturum)
    elif seri.kaynak_tipi == "yahoo":
        df = yahoo.seri_cek(seri, session=oturum)
    elif seri.kaynak_tipi == "epias":
        df = epias.seri_cek(seri, tgt, session=oturum, onbellek=epias_onbellek)
    elif seri.kaynak_tipi == "osd":
        df = osd.seri_cek(seri, onbellek=osd_onbellek, session=oturum)
    elif seri.kaynak_tipi == "tim":
        df = tim.seri_cek(seri, onbellek=tim_onbellek, session=oturum)
    elif seri.kaynak_tipi == "tim_il":
        df = tim.il_seri_cek(seri, onbellek=tim_il_onbellek, session=oturum)
    elif seri.kaynak_tipi == "tim_ulke":
        df = tim.ulke_seri_cek(seri, onbellek=tim_ulke_onbellek, session=oturum)
    elif seri.kaynak_tipi == "bddk":
        df = bddk.seri_cek(seri, onbellek=bddk_onbellek, session=oturum)
    elif seri.kaynak_tipi == "tefas":
        df = tefas.seri_cek(seri, onbellek=tefas_onbellek, session=oturum)
    elif seri.kaynak_tipi == "tefas_fon":
        df = tefas.fon_tam_gecmisi(
            seri.tefas_kod, seri.start_date, date.today().isoformat(),
            session=oturum, tip=seri.tefas_tip,
        )
    elif seri.kaynak_tipi == "eurocontrol":
        df = eurocontrol.seri_cek(seri, onbellek=ec_onbellek, session=oturum)
    elif seri.kaynak_tipi == "fred":
        df = fred.seri_cek(seri, session=oturum)
    elif seri.kaynak_tipi == "pgsus":
        df = pgsus.seri_cek(seri, onbellek=pgsus_onbellek, session=oturum)
    elif seri.kaynak_tipi == "thy":
        df = thy.seri_cek(seri, onbellek=thy_onbellek, session=oturum)
    elif seri.kaynak_tipi == "tav":
        df = tav.seri_cek(seri, onbellek=tav_onbellek, session=oturum)
    elif seri.kaynak_tipi == "ebebek":
        df = ebebek.seri_cek(seri, onbellek=ebebek_onbellek, session=oturum)
    elif seri.kaynak_tipi == "epdk":
        df = epdk.seri_cek(seri, onbellek=epdk_onbellek, session=oturum)
    else:
        raise ValueError(f"Bilinmeyen kaynak tipi: {seri.kaynak_tipi}")
    return olcekle(df, seri.olcek)


def seriyi_yaz(seri: Seri, df) -> int:
    yol = seri_yolu(seri.id)
    yol.parent.mkdir(parents=True, exist_ok=True)
    if seri.kaynak_tipi == "tefas_fon":
        df.to_csv(yol, index=False)
    else:
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
    # Aynı EPİAŞ ucunu paylaşan seriler (uretim + uretim-kompozisyon) yanıtı
    # bir kez çeksin diye koşu başına tek önbellek (bkz. epias.seri_cek).
    epias_onbellek: dict = {}
    # 13 OSD serisi aynı beş bülteni paylaşır (bkz. osd.seri_cek).
    osd_onbellek: dict = {}
    # 13 TİM serisi aynı sekiz yıllık XLSX bültenini paylaşır
    # (bkz. tim.seri_cek); önbelleksiz 104 indirme olurdu.
    tim_onbellek: dict = {}
    # BDDK serileri (kalem, taraf) çiftine göre önbelleklenir; aynı kalemi
    # iki tarafta göstermek istersek yanıt bir kez çekilir.
    bddk_onbellek: dict = {}
    # TEFAS: ay sonu anlık görüntüsü (tip, ay) başına tek istek; dört ölçüt
    # aynı yanıttan üretilir (bkz. tefas.seri_cek).
    tefas_onbellek: dict = {}
    # EUROCONTROL'ün üç JSON dosyası (2–5 MB) koşu başına bir kez inilir.
    ec_onbellek: dict = {}
    # İl×sektör bülteni AYLIKTIR (yıllık değil): 741 seri aynı ~40 aylık
    # dosyayı paylaşır, önbelleksiz her seri kendi ayını yeniden indirir.
    tim_il_onbellek: dict = {}
    # Ülke×sektör bülteni de AYLIKTIR; 674 seri aynı ~44 aylık dosyayı
    # paylaşır (bkz. `ingest.tim.ulke_seri_cek`).
    tim_ulke_onbellek: dict = {}
    # Pegasus tek dosyada 2019'dan bugüne tüm geçmişi taşır; 18 seri (3
    # segment × 6 ölçüt) aynı dosyayı paylaşır (bkz. `ingest.pgsus.seri_cek`).
    pgsus_onbellek: dict = {}
    # THY 15 seri (3 segment × 5 ölçüt) aynı ~5 dosyalık kümeyi paylaşır
    # (bkz. `ingest.thy.seri_cek`).
    thy_onbellek: dict = {}
    # TAV tek dosyada Ocak 2020'den bugüne tüm geçmişi taşır (yıl başına
    # değil, kümülatif pencere); 28 seri (12 varlık × ≤3 segment) aynı
    # dosyayı paylaşır (bkz. `ingest.tav.seri_cek`).
    tav_onbellek: dict = {}
    # ebebek 3 kategoriyi (satış/ziyaretçi/mağaza) paylaşır; 6 seri aynı
    # ~100 duyuru PDF'ini önbellekler (bkz. `ingest.ebebek.seri_cek`).
    ebebek_onbellek: dict = {}
    # EPDK 20 seri (4 ölçüt × 5 ürün) aynı ~8 aylık EK dosyası kümesini
    # paylaşır (bkz. `ingest.epdk.seri_cek`).
    epdk_onbellek: dict = {}

    with requests.Session() as oturum:
        oturum.mount("https://", HTTPAdapter(max_retries=RETRY))
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
                df = _cek(
                    seri, api_key, tgt, oturum,
                    epias_onbellek, osd_onbellek, tim_onbellek, bddk_onbellek,
                    tefas_onbellek, ec_onbellek, tim_il_onbellek, tim_ulke_onbellek,
                    thy_onbellek, pgsus_onbellek, tav_onbellek, ebebek_onbellek,
                    epdk_onbellek,
                )
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
