"""Ingest orchestrator.

Bir serinin başarısızlığı diğerlerini düşürmez: başarılı seriler yine
yazılır, hatalar toplanıp raporlanır, en az bir hata varsa exit kodu 1
olur ki Actions kırmızıya dönsün.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict
from datetime import date, timedelta

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from core.catalog import Seri, seri_listele
from core.data import seri_yolu
from ingest import ayd, bddk, bigchefs, botas, dhmi, ebebek, eia, eib, ecb, epdk, epias, eurocontrol, eurostat, eurostat_insaat, eurostat_turizm, evds, fred, gph, ifo, iso_pmi, istib, ithib, ktb, migros, odmd, orge, osd, pgsus, sgk, taid, tav, tcud, tefas, tepav, thy, tim, tmsd, trabzontb, tsb, tspb, ttkom, tuik, turkbesd, turkcell, turkcimento, turktraktor, uab, usk, worldbank, yahoo

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


# Fon fiyatları geriye dönük revize edilmiyor. 969 fonun tüm geçmişini her
# gün ay ay yeniden çekmek (~24.000 istek) koşuyu 6 saatlik Actions sınırına
# taşıyordu; artık mevcut CSV'nin son tarihinden bu kadar gün geriden devam
# edilir, örtüşen günler yeni değerle güncellenir.
TEFAS_GERI_GUN = 7


def tefas_fon_cek(seri: Seri, oturum, bugun: date | None = None) -> pd.DataFrame:
    """TEFAS fon geçmişini artımlı çeker: CSV yoksa tam geçmiş, varsa ek."""
    bugun = bugun or date.today()
    yol = seri_yolu(seri.id)
    eski = pd.read_csv(yol) if yol.exists() else None
    if eski is None or eski.empty:
        return tefas.fon_tam_gecmisi(
            seri.tefas_kod, seri.start_date, bugun.isoformat(),
            session=oturum, tip=seri.tefas_tip,
        )
    bas = max(
        date.fromisoformat(seri.start_date),
        date.fromisoformat(str(eski["date"].max())) - timedelta(days=TEFAS_GERI_GUN),
    )
    yeni = tefas.fon_tam_gecmisi(
        seri.tefas_kod, bas.isoformat(), bugun.isoformat(),
        session=oturum, tip=seri.tefas_tip, bos_izin=True,
    )
    return (
        pd.concat([eski, yeni], ignore_index=True)
        .drop_duplicates("date", keep="last")
        .sort_values("date")
        .reset_index(drop=True)
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
         epdk_onbellek: dict | None = None,
         turkcell_onbellek: dict | None = None,
         ttkom_onbellek: dict | None = None,
         eib_onbellek: dict | None = None,
         usk_onbellek: dict | None = None,
         odmd_onbellek: dict | None = None,
         turkbesd_onbellek: dict | None = None,
         wb_onbellek: dict | None = None,
         ifo_onbellek: dict | None = None,
         tsb_onbellek: dict | None = None,
         epdk_dogalgaz_onbellek: dict | None = None,
         eurostat_onbellek: dict | None = None,
         turkcimento_onbellek: dict | None = None,
         tim_ulke_grubu_onbellek: dict | None = None,
         tspb_onbellek: dict | None = None,
         sgk_onbellek: dict | None = None,
         ayd_onbellek: dict | None = None,
         gph_onbellek: dict | None = None,
         orge_onbellek: dict | None = None,
         tcud_onbellek: dict | None = None,
         dhmi_onbellek: dict | None = None,
         uab_onbellek: dict | None = None,
         ktb_onbellek: dict | None = None,
         eurostat_turizm_onbellek: dict | None = None,
         iso_pmi_onbellek: dict | None = None,
         tim_pazar_monitoru_onbellek: dict | None = None,
         bigchefs_onbellek: dict | None = None,
         turktraktor_onbellek: dict | None = None,
         migros_onbellek: dict | None = None,
         tepav_onbellek: dict | None = None,
         istib_onbellek: dict | None = None,
         tuik_kanatli_onbellek: dict | None = None,
         botas_onbellek: dict | None = None,
         tmsd_onbellek: dict | None = None,
         ithib_onbellek: dict | None = None,
         trabzontb_onbellek: dict | None = None,
         eurostat_insaat_onbellek: dict | None = None,
         taid_onbellek: dict | None = None,
         thy_ir_onbellek: dict | None = None,
         pgsus_ir_onbellek: dict | None = None):
    """Seriyi kaynak tipine göre doğru istemciye yönlendirir ve ölçekler."""
    if seri.kaynak_tipi == "evds":
        df = evds.seri_cek(seri, api_key, session=oturum)
    elif seri.kaynak_tipi == "yahoo":
        df = yahoo.seri_cek(seri, session=oturum)
    elif seri.kaynak_tipi == "epias":
        if seri.epias_ucu == "baraj-doluluk":
            df = epias.baraj_doluluk_cek(
                seri, tgt, session=oturum, onbellek=epias_onbellek,
            )
        else:
            df = epias.seri_cek(seri, tgt, session=oturum, onbellek=epias_onbellek)
    elif seri.kaynak_tipi == "osd":
        df = osd.seri_cek(seri, onbellek=osd_onbellek, session=oturum)
    elif seri.kaynak_tipi == "tim":
        df = tim.seri_cek(seri, onbellek=tim_onbellek, session=oturum)
    elif seri.kaynak_tipi == "tim_il":
        df = tim.il_seri_cek(seri, onbellek=tim_il_onbellek, session=oturum)
    elif seri.kaynak_tipi == "tim_ulke":
        df = tim.ulke_seri_cek(seri, onbellek=tim_ulke_onbellek, session=oturum)
    elif seri.kaynak_tipi == "tim_ulke_grubu":
        df = tim.ulke_grubu_seri_cek(seri, onbellek=tim_ulke_grubu_onbellek, session=oturum)
    elif seri.kaynak_tipi == "bddk":
        df = bddk.seri_cek(seri, onbellek=bddk_onbellek, session=oturum)
    elif seri.kaynak_tipi == "bddk_haftalik":
        df = bddk.seri_cek_haftalik(seri, onbellek=bddk_onbellek, session=oturum)
    elif seri.kaynak_tipi == "bddk_bdmk":
        df = bddk.seri_cek_bdmk(seri, onbellek=bddk_onbellek, session=oturum)
    elif seri.kaynak_tipi == "tefas":
        df = tefas.seri_cek(seri, onbellek=tefas_onbellek, session=oturum)
    elif seri.kaynak_tipi == "tefas_fon":
        df = tefas_fon_cek(seri, oturum)
    elif seri.kaynak_tipi == "eurocontrol":
        df = eurocontrol.seri_cek(seri, onbellek=ec_onbellek, session=oturum)
    elif seri.kaynak_tipi == "fred":
        df = fred.seri_cek(seri, session=oturum)
    elif seri.kaynak_tipi == "pgsus":
        df = pgsus.seri_cek(seri, onbellek=pgsus_onbellek, session=oturum)
    elif seri.kaynak_tipi == "thy":
        df = thy.seri_cek(seri, onbellek=thy_onbellek, session=oturum)
    elif seri.kaynak_tipi == "thy_ir":
        df = thy.sunum_seri_cek(seri, onbellek=thy_ir_onbellek, session=oturum)
    elif seri.kaynak_tipi == "pgsus_ir":
        df = pgsus.sunum_seri_cek(seri, onbellek=pgsus_ir_onbellek, session=oturum)
    elif seri.kaynak_tipi == "tav":
        df = tav.seri_cek(seri, onbellek=tav_onbellek, session=oturum)
    elif seri.kaynak_tipi == "ebebek":
        df = ebebek.seri_cek(seri, onbellek=ebebek_onbellek, session=oturum)
    elif seri.kaynak_tipi == "epdk":
        df = epdk.seri_cek(seri, onbellek=epdk_onbellek, session=oturum)
    elif seri.kaynak_tipi == "turkcell":
        df = turkcell.seri_cek(seri, onbellek=turkcell_onbellek, session=oturum)
    elif seri.kaynak_tipi == "ttkom":
        df = ttkom.seri_cek(seri, onbellek=ttkom_onbellek, session=oturum)
    elif seri.kaynak_tipi == "eib":
        df = eib.seri_cek(seri, onbellek=eib_onbellek, session=oturum)
    elif seri.kaynak_tipi == "usk":
        df = usk.seri_cek(seri, onbellek=usk_onbellek, session=oturum)
    elif seri.kaynak_tipi == "odmd":
        df = odmd.seri_cek(seri, onbellek=odmd_onbellek, session=oturum)
    elif seri.kaynak_tipi == "turkbesd":
        df = turkbesd.seri_cek(seri, onbellek=turkbesd_onbellek, session=oturum)
    elif seri.kaynak_tipi == "worldbank":
        df = worldbank.seri_cek(seri, onbellek=wb_onbellek, session=oturum)
    elif seri.kaynak_tipi == "ifo":
        df = ifo.seri_cek(seri, onbellek=ifo_onbellek, session=oturum)
    elif seri.kaynak_tipi == "tsb":
        df = tsb.seri_cek(seri, onbellek=tsb_onbellek, session=oturum)
    elif seri.kaynak_tipi == "epdk_dogalgaz":
        df = epdk.dogalgaz_seri_cek(seri, onbellek=epdk_dogalgaz_onbellek, session=oturum)
    elif seri.kaynak_tipi == "eurostat":
        df = eurostat.seri_cek(seri, onbellek=eurostat_onbellek, session=oturum)
    elif seri.kaynak_tipi == "ecb":
        df = ecb.seri_cek(seri, session=oturum)
    elif seri.kaynak_tipi == "turkcimento":
        df = turkcimento.seri_cek(seri, onbellek=turkcimento_onbellek, session=oturum)
    elif seri.kaynak_tipi == "tspb":
        df = tspb.seri_cek(seri, onbellek=tspb_onbellek, session=oturum)
    elif seri.kaynak_tipi == "sgk":
        df = sgk.seri_cek(seri, onbellek=sgk_onbellek, session=oturum)
    elif seri.kaynak_tipi == "ayd":
        df = ayd.seri_cek(seri, onbellek=ayd_onbellek, session=oturum)
    elif seri.kaynak_tipi == "gph":
        df = gph.seri_cek(seri, onbellek=gph_onbellek, session=oturum)
    elif seri.kaynak_tipi == "orge":
        df = orge.seri_cek(seri, onbellek=orge_onbellek, session=oturum)
    elif seri.kaynak_tipi == "tcud":
        df = tcud.seri_cek(seri, onbellek=tcud_onbellek, session=oturum)
    elif seri.kaynak_tipi == "dhmi":
        df = dhmi.seri_cek(seri, onbellek=dhmi_onbellek, session=oturum)
    elif seri.kaynak_tipi == "uab":
        df = uab.seri_cek(seri, onbellek=uab_onbellek, session=oturum)
    elif seri.kaynak_tipi == "ktb":
        df = ktb.seri_cek(seri, onbellek=ktb_onbellek, session=oturum)
    elif seri.kaynak_tipi == "eurostat_turizm":
        df = eurostat_turizm.seri_cek(seri, onbellek=eurostat_turizm_onbellek, session=oturum)
    elif seri.kaynak_tipi == "iso_pmi":
        df = iso_pmi.seri_cek(seri, onbellek=iso_pmi_onbellek, session=oturum)
    elif seri.kaynak_tipi == "tim_pazar_monitoru":
        df = tim.pazar_monitoru_seri_cek(seri, onbellek=tim_pazar_monitoru_onbellek, session=oturum)
    elif seri.kaynak_tipi == "bigchefs":
        df = bigchefs.seri_cek(seri, onbellek=bigchefs_onbellek, session=oturum)
    elif seri.kaynak_tipi == "turktraktor":
        df = turktraktor.seri_cek(seri, onbellek=turktraktor_onbellek, session=oturum)
    elif seri.kaynak_tipi == "migros":
        df = migros.seri_cek(seri, onbellek=migros_onbellek, session=oturum)
    elif seri.kaynak_tipi == "tepav":
        df = tepav.seri_cek(seri, onbellek=tepav_onbellek, session=oturum)
    elif seri.kaynak_tipi == "istib":
        df = istib.seri_cek(seri, onbellek=istib_onbellek, session=oturum)
    elif seri.kaynak_tipi == "tuik_kanatli":
        df = tuik.seri_cek(seri, onbellek=tuik_kanatli_onbellek, session=oturum)
    elif seri.kaynak_tipi == "botas":
        df = botas.seri_cek(seri, onbellek=botas_onbellek, session=oturum)
    elif seri.kaynak_tipi == "epdk_fiyat":
        df = epdk.fiyat_seri_cek(seri, onbellek=epdk_onbellek, session=oturum)
    elif seri.kaynak_tipi == "tmsd":
        df = tmsd.seri_cek(seri, onbellek=tmsd_onbellek, session=oturum)
    elif seri.kaynak_tipi == "ithib":
        df = ithib.seri_cek(seri, onbellek=ithib_onbellek, session=oturum)
    elif seri.kaynak_tipi == "eia":
        df = eia.seri_cek(seri, session=oturum)
    elif seri.kaynak_tipi == "trabzontb":
        df = trabzontb.seri_cek(seri, onbellek=trabzontb_onbellek, session=oturum)
    elif seri.kaynak_tipi == "eurostat_insaat":
        df = eurostat_insaat.seri_cek(seri, onbellek=eurostat_insaat_onbellek, session=oturum)
    elif seri.kaynak_tipi == "taid":
        df = taid.seri_cek(seri, onbellek=taid_onbellek, session=oturum)
    else:
        raise ValueError(f"Bilinmeyen kaynak tipi: {seri.kaynak_tipi}")
    return olcekle(df, seri.olcek)


def seriyi_yaz(seri: Seri, df) -> int:
    """Tam üzerine yazar; yalnızca anlık-görüntü kaynakları BİRİKTİRİR.

    Kural: CSV'ler her koşuda baştan yazılır (revizyonlar yakalanmalı).
    Tek istisna EPİAŞ baraj doluluğu: uç `date` alanını yok sayıp yalnızca
    BUGÜNÜN anlık görüntüsünü döndürüyor (canlı ölçüldü, bkz.
    `epias.baraj_doluluk_cek`), yani geriye dönük çekim mümkün değil.
    Üzerine yazmak her koşuda geçmişi silerdi; bu yüzden mevcut satırlar
    korunur, aynı günün değeri yenisiyle güncellenir.

    TEFAS fonları da geçmişi korur, ama birleştirme burada değil
    `tefas_fon_cek`te yapılır (artımlı çekim); buraya tam seri gelir.
    """
    yol = seri_yolu(seri.id)
    yol.parent.mkdir(parents=True, exist_ok=True)
    if seri.epias_ucu == "baraj-doluluk" and yol.exists():
        df = (
            pd.concat([pd.read_csv(yol), df], ignore_index=True)
            .drop_duplicates("date", keep="last")
            .sort_values("date")
            .reset_index(drop=True)
        )
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
    ayristirici.add_argument(
        "--freq",
        help="Yalnızca bu sıklıklardaki serileri çek (virgülle: daily,weekly)",
    )
    args = ayristirici.parse_args()

    seriler = seri_listele()
    if args.freq:
        sikliklar = {f.strip() for f in args.freq.split(",") if f.strip()}
        seriler = [s for s in seriler if s.freq in sikliklar]
        if not seriler:
            print(f"HATA: bu sıklıkta seri yok: {args.freq}", file=sys.stderr)
            return 2
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
    # Kaynak tipi başına toplam süre: yavaş kaynağı loglardan bulabilmek için.
    sureler: dict[str, float] = defaultdict(float)
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
    # THY 30 seri (çeyreklik Yatırımcı Sunumu metrikleri) aynı tek PDF'i
    # paylaşır — trafik bültenindeki `thy_onbellek`ten AYRI (bkz.
    # `ingest.thy.sunum_seri_cek`).
    thy_ir_onbellek: dict = {}
    # Pegasus 16 seri (çeyreklik Yatırımcı Sunumu metrikleri) aynı tek
    # PDF'i paylaşır — trafik bültenindeki `pgsus_onbellek`ten AYRI (bkz.
    # `ingest.pgsus.sunum_seri_cek`).
    pgsus_ir_onbellek: dict = {}
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
    # Turkcell 27 seri aynı çeyreklik "Financial and Operational Data"
    # Excel'ini paylaşır (bkz. `ingest.turkcell.seri_cek`).
    turkcell_onbellek: dict = {}
    # Türk Telekom 6 seri aynı çeyreklik "Özet Finansal ve Operasyonel
    # Veriler" Excel'ini paylaşır (bkz. `ingest.ttkom.seri_cek`).
    ttkom_onbellek: dict = {}
    # EİB 32 seri (14 su ürünleri + 18 hayvansal) aynı 1-2 yıllık yıllık
    # bülten indirmesini paylaşır (bkz. `ingest.eib.seri_cek`).
    eib_onbellek: dict = {}
    # USK 15 seri aynı tavsiye fiyatı tablosunu ve aynı aylık maliyet PDF
    # kümesini paylaşır (bkz. `ingest.usk.seri_cek`).
    usk_onbellek: dict = {}
    # ODMD 79 seri (TOASO/DOAS marka bazlı perakende) aynı ~60 aylık XLSX
    # kümesini paylaşır (bkz. `ingest.odmd.seri_cek`).
    odmd_onbellek: dict = {}
    # TÜRKBESD 24 seri (6 ürün × 4 ölçüt) aynı 4 yıllık XLSX dosyasını
    # (ölçüt başına 1) paylaşır (bkz. `ingest.turkbesd.seri_cek`).
    turkbesd_onbellek: dict = {}
    # Dünya Bankası Pink Sheet 3 seri (gübre endeksi + urea + DAP) aynı
    # aylık CMO-Historical-Data-Monthly.xlsx'i paylaşır (bkz.
    # `ingest.worldbank.seri_cek`).
    wb_onbellek: dict = {}
    # ifo Institute 3 seri (iklim/durum/beklenti) aynı aylık "ifo Business
    # Climate" Excel'ini paylaşır (bkz. `ingest.ifo.seri_cek`).
    ifo_onbellek: dict = {}
    # TSB "Prim Üretimleri Sıralama" ayda bir yayımlanan workbook'u
    # dosya yolu + sheet başına önbellekler; aynı ayın workbook'unu
    # birden çok şirket serisi paylaşır (bkz. `ingest.tsb.seri_cek`).
    tsb_onbellek: dict = {}
    # TSPB "Veriler" sayfasının iki dosyasını (PYŞ Aylık, Krediler) 13 seri
    # paylaşır — dosya başına ARŞİV+GÜNCEL iki indirme (bkz.
    # `ingest.tspb.seri_cek`).
    tspb_onbellek: dict = {}
    # EPDK doğal gaz sektör raporu 9 seri aynı ~7-8 aylık EK dosyası
    # kümesini paylaşır (petrol `epdk_onbellek`iyle AYNI desen, ayrı
    # anahtar — bkz. `ingest.epdk.dogalgaz_seri_cek`).
    epdk_dogalgaz_onbellek: dict = {}
    # Eurostat 6 seri (2 dataset × 3 geo/currency) dataset başına TEK
    # istekle tüm tarihçeyi paylaşır (bkz. `ingest.eurostat.seri_cek`).
    eurostat_onbellek: dict = {}
    # TürkÇimento 8 seri (5 çimento + 3 klinker ölçütü) aynı ~9 yıllık XLS
    # dosyası kümesini paylaşır (bkz. `ingest.turkcimento.seri_cek`).
    turkcimento_onbellek: dict = {}
    # Ülke grupları bülteni AYLIKTIR (il/ülke ile aynı takvim); 12+ grup
    # serisi aynı ~44 aylık XLSX kümesini paylaşır (bkz.
    # `ingest.tim.ulke_grubu_seri_cek`).
    tim_ulke_grubu_onbellek: dict = {}
    # SGK tek XLSX bülteni (2012'den bugüne aylık) 6 seri (hastane×4,
    # eczane×2) tarafından paylaşılır (bkz. `ingest.sgk.seri_cek`).
    sgk_onbellek: dict = {}
    # AYD tek endeks serisi kendi ay-ay sayfa taramasını önbellekler (bkz.
    # `ingest.ayd.seri_cek`) — burada yalnızca tutarlılık için tutulur.
    ayd_onbellek: dict = {}
    # GPH 3 seri (konsolide yolcu/sefer + konsolide edilmeyen yolcu) aynı
    # aylık XLSX'i paylaşır (bkz. `ingest.gph.seri_cek`).
    gph_onbellek: dict = {}
    # ORGE 2 seri (backlog + YTD yeni iş) aynı çeyreklik PDF sunumunu
    # paylaşır (bkz. `ingest.orge.seri_cek`).
    orge_onbellek: dict = {}
    # TÇÜD 9 seri (üretim/tüketim/ihracat/ithalat + dünya/Çin/Hindistan)
    # aynı aylık basın bülteni kümesini paylaşır (bkz. `ingest.tcud.seri_cek`).
    tcud_onbellek: dict = {}
    # DHMİ 5 seri (yolcu toplam/dış hat, kargo, uçak toplam/ticari) aynı
    # ~8-20 aylık TÜMÜ.xlsx kümesini paylaşır (bkz. `ingest.dhmi.seri_cek`).
    dhmi_onbellek: dict = {}
    # UAB 10 seri (ulusal toplam + 9 liman başkanlığı) yıl başına aynı
    # ~12 aylık .xls kümesini paylaşır (bkz. `ingest.uab.seri_cek`).
    uab_onbellek: dict = {}
    # KTB tek seri (yabancı ziyaretçi sayısı) tek sınır bültenini
    # önbellekler (bkz. `ingest.ktb.seri_cek`).
    ktb_onbellek: dict = {}
    # Eurostat tour_occ_nim 3 seri (toplam/yerli/yabancı geceleme) tek
    # API yanıtını paylaşır (bkz. `ingest.eurostat_turizm.seri_cek`).
    eurostat_turizm_onbellek: dict = {}
    # İSO Sektörel PMI (40 seri) + manşet İmalat PMI (1 seri) ayrı ZIP/PDF
    # kümelerini paylaşır — ikisi de aynı `onbellek` dict altında iki ayrı
    # anahtarla tutulur (bkz. `ingest.iso_pmi._sektorel_onbellegi_getir` /
    # `_manset_onbellegi_getir`).
    iso_pmi_onbellek: dict = {}
    # TİM İhracat Pazar Monitörü 47 seri (2 milli + 26 sektör + 19 ülke)
    # aynı aylık PDF bülten kümesini paylaşır (bkz.
    # `ingest.tim._pazar_monitoru_onbellegi_getir`).
    tim_pazar_monitoru_onbellek: dict = {}
    # BigChefs 20 seri (aylık şube bildirimi + çeyreklik Bilgilendirme
    # Notu) aynı duyurular/YI sayfa taramasını ve belge metni önbelleğini
    # paylaşır (bkz. `ingest.bigchefs.seri_cek`).
    bigchefs_onbellek: dict = {}
    # TürkTraktör 3 seri (fabrika/yurtdışı/toplam satış) aynı aylık OSD
    # bildirim PDF kümesini paylaşır (bkz. `ingest.turktraktor.seri_cek`).
    turktraktor_onbellek: dict = {}
    # Migros tek seri (çeyrek sonu mağaza sayısı) kendi rapor taramasını
    # önbellekler (bkz. `ingest.migros.seri_cek`).
    migros_onbellek: dict = {}
    # TEPAV 3 seri (TEGE aylık/yıllık + KKTC-TEGE aylık) aynı hub+yıl+haber
    # sayfası taramasını paylaşır (bkz. `ingest.tepav.seri_cek`).
    tepav_onbellek: dict = {}
    # TMSD 7 seri (makarna/noodle/irmik + buğday dış ticareti) aynı aylık
    # PDF sektör raporunu paylaşır (bkz. `ingest.tmsd.seri_cek`).
    tmsd_onbellek: dict = {}
    # İTB 4 seri (piliç/hindi eti + kanat) aynı haftalık tescil bültenini
    # (hafta başına tek istek) paylaşır (bkz. `ingest.istib.seri_cek`).
    istib_onbellek: dict = {}
    # TÜİK/Eurostat apro_mt_pwgtm 3 seri (üretim×2 + kesilen tavuk) tek API
    # yanıtını paylaşır (bkz. `ingest.tuik.seri_cek`).
    tuik_kanatli_onbellek: dict = {}
    # BOTAŞ 5 seri (tüketici kategorisi) aynı güncel tarife sayfasını
    # (indeks + detay, koşu başına iki istek) paylaşır (bkz.
    # `ingest.botas.seri_cek`).
    botas_onbellek: dict = {}
    # İTHİB 7 seri (ürün grubu bazında tekstil ihracatı) aynı liste
    # sayfasını (ay→PDF eşlemesi) ve her ay için aynı PDF'i paylaşır
    # (bkz. `ingest.ithib.seri_cek`).
    ithib_onbellek: dict = {}
    # Trabzon TB 2 seri (fındık yağlık + levant) aynı günlük bülten PDF
    # kümesini paylaşır (bkz. `ingest.trabzontb.seri_cek`).
    trabzontb_onbellek: dict = {}
    # Eurostat sts_copr_m (İnşaat Üretim Endeksi) 4 seri (F/F41/F42/F43)
    # aynı API yanıtını paylaşır (bkz. `ingest.eurostat_insaat.seri_cek`).
    eurostat_insaat_onbellek: dict = {}
    # TAİD 1 seri (FROTO perakende kamyon) kendi bülten listesini ve marka
    # tablosu ayrıştırmasını önbellekler (bkz. `ingest.taid.seri_cek`).
    taid_onbellek: dict = {}

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
            baslangic = time.monotonic()
            try:
                df = _cek(
                    seri, api_key, tgt, oturum,
                    epias_onbellek, osd_onbellek, tim_onbellek, bddk_onbellek,
                    tefas_onbellek, ec_onbellek, tim_il_onbellek, tim_ulke_onbellek,
                    thy_onbellek, pgsus_onbellek, tav_onbellek, ebebek_onbellek,
                    epdk_onbellek, turkcell_onbellek, ttkom_onbellek,
                    eib_onbellek, usk_onbellek, odmd_onbellek, turkbesd_onbellek,
                    wb_onbellek, ifo_onbellek, tsb_onbellek,
                    epdk_dogalgaz_onbellek, eurostat_onbellek,
                    turkcimento_onbellek=turkcimento_onbellek,
                    tim_ulke_grubu_onbellek=tim_ulke_grubu_onbellek,
                    tspb_onbellek=tspb_onbellek,
                    sgk_onbellek=sgk_onbellek,
                    ayd_onbellek=ayd_onbellek,
                    gph_onbellek=gph_onbellek,
                    orge_onbellek=orge_onbellek,
                    tcud_onbellek=tcud_onbellek,
                    dhmi_onbellek=dhmi_onbellek,
                    uab_onbellek=uab_onbellek,
                    ktb_onbellek=ktb_onbellek,
                    eurostat_turizm_onbellek=eurostat_turizm_onbellek,
                    iso_pmi_onbellek=iso_pmi_onbellek,
                    tim_pazar_monitoru_onbellek=tim_pazar_monitoru_onbellek,
                    bigchefs_onbellek=bigchefs_onbellek,
                    turktraktor_onbellek=turktraktor_onbellek,
                    migros_onbellek=migros_onbellek,
                    tepav_onbellek=tepav_onbellek,
                    tmsd_onbellek=tmsd_onbellek,
                    istib_onbellek=istib_onbellek,
                    tuik_kanatli_onbellek=tuik_kanatli_onbellek,
                    botas_onbellek=botas_onbellek,
                    ithib_onbellek=ithib_onbellek,
                    trabzontb_onbellek=trabzontb_onbellek,
                    eurostat_insaat_onbellek=eurostat_insaat_onbellek,
                    taid_onbellek=taid_onbellek,
                    thy_ir_onbellek=thy_ir_onbellek,
                    pgsus_ir_onbellek=pgsus_ir_onbellek,
                )
                adet = seriyi_yaz(seri, df)
                basarili.append(f"{seri.id} ({adet} nokta)")
                print(f"  ✓ {seri.id} — {adet} nokta "
                      f"({time.monotonic() - baslangic:.1f} sn)")
            except Exception as hata:  # noqa: BLE001 — modül bazlı izolasyon
                hatalar.append((seri.id, str(hata)))
                print(f"  ✗ {seri.id} — {hata} "
                      f"({time.monotonic() - baslangic:.1f} sn)", file=sys.stderr)
            sureler[seri.kaynak_tipi] += time.monotonic() - baslangic

    print("\nKaynak tipi başına süre (en yavaş 15):")
    for tip, sure in sorted(sureler.items(), key=lambda x: -x[1])[:15]:
        print(f"  {tip:<24} {sure / 60:6.1f} dk")
    print(f"\n{len(basarili)}/{len(seriler)} seri başarılı")
    if hatalar:
        print(f"{len(hatalar)} seri başarısız:", file=sys.stderr)
        for seri_id, mesaj in hatalar:
            print(f"  - {seri_id}: {mesaj}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
