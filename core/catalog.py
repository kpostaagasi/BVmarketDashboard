"""Katalog: serilerin ve kategorilerin tek doğruluk kaynağı.

Metadata burada yaşar; veri dosyaları yalnızca `date,value` içerir.
"""

from __future__ import annotations

import re

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

KOK = Path(__file__).resolve().parent.parent
KATALOG_DIZINI = KOK / "catalog"

GECERLI_FREKANSLAR = {"daily", "weekly", "monthly", "quarterly"}
GECERLI_EVDS_FREKANSLARI = {"1", "2", "5"}
GECERLI_GRAFIKLER = {"seasonality", "daily_seasonality", "level", "composition", "fon"}
GECERLI_AYLIK_AGG = {"mean", "last", "sum"}
GECERLI_KAYNAK_TIPLERI = {
    "evds", "yahoo", "epias", "osd", "tim", "tim_il", "tim_ulke", "bddk",
    "tefas", "eurocontrol", "fred", "tefas_fon", "pgsus", "thy",
    "tav", "ebebek",
    "epdk",
    "turkcell", "ttkom",
    "odmd",
    "eib", "usk",
}
SIKLIK_ETIKETLERI = {"daily": "GÜNLÜK", "weekly": "HAFTALIK", "monthly": "AYLIK", "quarterly": "ÇEYREKLİK"}
# TEFAS'ın iki ekseni katalogda doğrulanır (core, ingest'i import etmez):
# fon tipi ve hangi toplulaştırmanın istendiği.
GECERLI_TEFAS_TIPLERI = {"YAT", "EMK"}
GECERLI_TEFAS_OLCUTLERI = {"buyukluk", "hesap", "fon-sayisi", "ortalama-buyukluk"}
# EUROCONTROL'ün üç dosyası: ülke, hava yolu, havalimanı.
GECERLI_EC_KAYNAKLARI = {"ulke", "havayolu", "havalimani"}
# Pegasus trafik bülteninin iki ekseni: yolcu segmenti ve ölçüt.
GECERLI_PGSUS_SEGMENTLERI = {"Toplam", "İç Hat", "Dış Hat"}
GECERLI_PGSUS_OLCUTLERI = {
    "misafir", "konma", "koltuk", "doluluk", "ask", "konma-basina-misafir",
}
# THY trafik bülteninin iki ekseni: yolcu segmenti ve ölçüt.
GECERLI_THY_SEGMENTLERI = {"Toplam", "Yurt İçi", "Yurt Dışı"}
GECERLI_THY_OLCUTLERI = {"konma", "ask", "doluluk", "yolcu", "kargo"}
# TAV Havalimanları trafik bülteninin üç ekseni: havalimanı (ya da TAV
# TOPLAM), yolcu segmenti ve hangi ölçütün (yolcu sayısı mı uçuş sayısı mı)
# okunacağı. Bkz. ingest/tav.py docstring'i.
GECERLI_TAV_SEGMENTLERI = {"toplam", "dis-hat", "ic-hat"}
GECERLI_TAV_OLCUTLERI = {"yolcu", "ucus"}
# ebebek Mağazacılık'ın aylık KAP Özel Durum Açıklamalarından çekilen altı
# operasyonel ölçüt. Bkz. ingest/ebebek.py docstring'i.
GECERLI_EBEBEK_METRIKLERI = {
    "satis_adedi", "magaza_ziyaretci", "web_ziyaret",
    "toplam_magaza", "standart_magaza", "mega_magaza",
}
# EPDK petrol piyasası aylık sektör raporunun iki ekseni: ölçüt (üretim/
# satış/dış ticaret yönü) ve ürün grubu. Bkz. ingest/epdk.py docstring'i.
GECERLI_EPDK_OLCUTLERI = {"rafineri-uretimi", "yurtici-satis", "ithalat", "ihracat"}
GECERLI_EPDK_URUNLERI = {"benzin", "motorin", "fuel-oil", "havacilik", "denizcilik"}
# EPİAŞ Şeffaflık baraj doluluk servisinin (dams-data/active-fullness) canlı
# döndürdüğü 17 havza (bkz. GET /v1/dams/data/basin-list, ölçüldü 2026-09-18).
# Bu uç tarih parametresini yok sayar — her zaman bugünün anlık görüntüsünü
# döner, geriye dönük veri yoktur (bkz. ingest/epias.py baraj_doluluk_cek).
GECERLI_EPIAS_HAVZALARI = {
    "Doğu Akdeniz", "Ceyhan", "Batı Karadeniz", "Antalya", "Van Gölü",
    "Seyhan", "Marmara", "Batı Akdeniz", "Yeşilırmak", "Asi", "Susurluk",
    "Kuzey Ege", "Doğu Karadeniz", "Sakarya", "Kızılırmak", "Büyük Menderes",
    "Gediz",
}
# Turkcell Yatırımcı İlişkileri'nin çeyreklik "Financial and Operational
# Data" Excel'inden çekilen 27 operasyonel/finansal ölçüt. Bkz.
# ingest/turkcell.py docstring'i.
GECERLI_TURKCELL_METRIKLERI = {
    "mobil-postpaid-abone", "fiber-abone", "superbox-abone",
    "mobil-prepaid-abone", "mobil-m2m-abone", "iptv-abone",
    "resell-sabit-genisbant-abone", "mobil-churn", "sabit-churn",
    "mobil-arpu-m2m-haric", "residential-fiber-arpu", "mobil-arpu-blended",
    "postpaid-arpu-m2m-haric", "prepaid-arpu",
    "turkiye-segment-geliri", "techfin-segment-geliri",
    "turkiye-segment-favok", "techfin-segment-favok",
    "tuketici-geliri", "kurumsal-geliri", "toptan-geliri",
    "paycell-geliri", "financell-geliri",
    "kktc-geliri", "kktc-abone", "best-geliri", "best-abone",
}
# Türk Telekom Yatırımcı İlişkileri'nin çeyreklik "Özet Finansal ve
# Operasyonel Veriler" Excel'inden çekilen 6 ölçüt. Bkz. ingest/ttkom.py
# docstring'i.
GECERLI_TTKOM_METRIKLERI = {
    "mobil-toplam-abone", "sabit-genisbant-abone", "tv-abone", "sabit-ses-abone",
    "sabit-genisbant-arpu-buyume", "mobil-karma-arpu-buyume",
}
# ODMD (Otomotiv Distribütörleri ve Mobilite Derneği) aylık marka bazında
# perakende satış dosyasının okunan üç sütunu. Bkz. ingest/odmd.py.
GECERLI_ODMD_KATEGORILERI = {"otomobil", "hafif_ticari", "toplam"}
# OSD kaynağının hangi belgeden okunacağı: "uretim" (Aylık Üretim Bülteni,
# varsayılan) ya da "ihracat" (Aylık Değerlendirme Raporu'nun "Dış
# Satışlar" bölümü). Bkz. ingest/osd.py.
GECERLI_OSD_VERI_TIPLERI = {"uretim", "ihracat"}
# EİB (Ege İhracatçı Birlikleri) ESÜHMİB aylık ihracat istatistiğinin iki
# ekseni: kalem (ürün grubu/alt grup ya da hesaplanan toplam) ve ölçüt
# (dolar değeri ya da ton hacmi). Bkz. ingest/eib.py docstring'i.
GECERLI_EIB_KALEMLERI = {
    "SU ÜRÜNLERİ", "LEVREK", "ÇİPURA", "TÜRK SOMONU", "ALABALIK",
    "KAYA LEVREĞİ", "DİĞER SU ÜRÜNLERİ",
    "HAYVANSAL_TOPLAM", "KANATLI", "YUMURTA", "SÜT VE SÜT ÜRÜNLERİ",
    "SOSİS VE BENZERİ ÜRÜNLER (KIRMIZI ET VE KANATLI)", "BAL", "DİĞER",
    "CANLI HAYVAN", "KIRMIZI ET VE SAKATAT",
}
GECERLI_EIB_OLCUTLERI = {"fobusd", "agirlik"}
# USK (Ulusal Süt Konseyi) çiğ süt tavsiye fiyatı + üretim maliyeti
# hesabının kalemleri (maliyet PDF'inin granüler alanları yalnızca yeni
# formatta var). Bkz. ingest/usk.py docstring'i.
GECERLI_USK_KALEMLERI = {
    "tavsiye-fiyati", "uretim-maliyeti", "canli-agirlik", "sut-verimi",
    "buzagi-fiyati", "karma-yem-fiyati", "misir-silaji-fiyati",
    "yonca-fiyati", "saman-fiyati", "yem-maliyeti-toplam", "diger-giderler",
    "buzagi-geliri", "net-maliyet-baz",
}


# Hangi kaynak tipi hangi TİPE ÖZGÜ alanı taşıyabilir. Bir alan burada
# listelenmemişse o kaynak için YASAKTIR: sessizce yok sayılan bir alan
# (ör. yalnızca yahoo'nun onurlandırdığı `yahoo_symbol`) seriyi yanlış
# kaynaktan çektirir ya da fark edilmeden yok sayılır.
# Yeni bir kaynak tipi eklemek, mevcut tiplere ayrı ayrı red kuralı yazmak
# değil, buraya bir satır eklemektir.
KAYNAK_ALANLARI = {
    "evds": {
        "zorunlu": ("evds_code", "evds_frequency"),
        "istege_bagli": ("start_date",),
    },
    "yahoo": {
        # start_date yok: yahoo istemcisi range=15y sabitiyle çalışıyor.
        "zorunlu": ("yahoo_symbol",),
        "istege_bagli": (),
    },
    "epias": {
        "zorunlu": ("epias_ucu",),
        "istege_bagli": ("epias_alani", "epias_bilesenler", "epias_havza", "start_date"),
    },
    "osd": {
        "zorunlu": ("osd_firma",),
        "istege_bagli": (
            "start_date", "osd_eski_adlar", "osd_arac_tipi", "osd_veri_tipi",
        ),
    },
    "tim": {
        "zorunlu": ("tim_sektor",),
        "istege_bagli": ("start_date", "tim_eski_adlar"),
    },
    "tim_il": {
        "zorunlu": ("tim_il", "tim_sektor"),
        "istege_bagli": ("start_date",),
    },
    "tim_ulke": {
        "zorunlu": ("tim_ulke", "tim_sektor"),
        "istege_bagli": ("start_date",),
    },
    "bddk": {
        "zorunlu": ("bddk_kalem",),
        "istege_bagli": ("bddk_taraf", "bddk_kumulatif", "start_date"),
    },
    "tefas": {
        "zorunlu": ("tefas_tip", "tefas_olcut"),
        "istege_bagli": ("start_date",),
    },
    "tefas_fon": {
        "zorunlu": ("tefas_tip", "tefas_kod", "start_date"),
        "istege_bagli": (),
    },
    "eurocontrol": {
        "zorunlu": ("ec_kaynak", "ec_varlik"),
        "istege_bagli": ("start_date",),
    },
    "fred": {
        "zorunlu": ("fred_code",),
        "istege_bagli": ("start_date",),
    },
    "pgsus": {
        "zorunlu": ("pgsus_segment", "pgsus_olcut"),
        "istege_bagli": ("start_date",),
    },
    "thy": {
        "zorunlu": ("thy_segment", "thy_olcut"),
        "istege_bagli": ("start_date",),
    },
    "tav": {
        "zorunlu": ("tav_varlik", "tav_segment"),
        "istege_bagli": ("start_date", "tav_olcut"),
    },
    "ebebek": {
        "zorunlu": ("ebebek_metrik",),
        "istege_bagli": ("start_date",),
    },
    "epdk": {
        "zorunlu": ("epdk_olcut", "epdk_urun"),
        "istege_bagli": ("start_date",),
    },
    "turkcell": {
        "zorunlu": ("turkcell_metrik",),
        "istege_bagli": ("start_date",),
    },
    "ttkom": {
        "zorunlu": ("ttkom_metrik",),
        "istege_bagli": ("start_date",),
    },
    "odmd": {
        "zorunlu": ("odmd_marka", "odmd_kategori"),
        "istege_bagli": ("odmd_yarim_marka", "start_date"),
    },
    "eib": {
        "zorunlu": ("eib_kalem", "eib_olcut"),
        "istege_bagli": ("start_date",),
    },
    "usk": {
        "zorunlu": ("usk_kalem",),
        "istege_bagli": ("start_date",),
    },
}

# Tipe değil, kataloğa ait alanlar: kaynak tipi ne olursa olsun
# onurlandırılırlar (`olcek` → `ingest.run.olcekle`, `gecikme_gunu` →
# `core.takvim`), dolayısıyla hiçbir tip için yasak değildir. Faz 3f'te
# `olcek` buraya taşındı: EVDS serilerinin bir kısmı "Bin TL"/"Bin USD"
# cinsinden gelir ve ölçeklenmeden KPI kartında okunamaz.
ORTAK_ALANLAR = frozenset({"olcek", "gecikme_gunu"})

TIPE_OZGU_ALANLAR = (
    frozenset(
        alan
        for tanim in KAYNAK_ALANLARI.values()
        for alan in tanim["zorunlu"] + tanim["istege_bagli"]
    )
    - ORTAK_ALANLAR
)


@dataclass(frozen=True)
class Hisse:
    """Bir BIST tickerının sayfası: kendi verisi + bağlam serileri.

    `kendi` şirketin yayımlanan verisi (üretim adedi, uçuş sayısı),
    `baglam` sektör/girdi serileri (sektör ihracatı, kur, hammadde).
    Ayrım sayfada görünür: iki liste iki ayrı başlık altında çizilir.
    """

    kod: str
    title: str
    sektor: str
    kendi: tuple[str, ...]
    baglam: tuple[str, ...] = ()
    note: str | None = None


class KatalogHatasi(Exception):
    """Katalog dosyaları tutarsız ya da eksik."""


@dataclass(frozen=True)
class Kaynak:
    name: str
    url: str


@dataclass(frozen=True)
class Kategori:
    slug: str
    title: str
    note: str | None = None
    pano: tuple[str, ...] = ()


@dataclass(frozen=True)
class Seri:
    id: str
    title: str
    category: str
    kaynak: Kaynak
    kaynak_tipi: str
    unit: str
    freq: str
    charts: tuple[str, ...]
    evds_code: str | None = None
    evds_frequency: str | None = None
    yahoo_symbol: str | None = None
    epias_ucu: str | None = None
    epias_alani: str | None = None
    epias_bilesenler: dict[str, tuple[str, ...]] | None = None
    epias_havza: str | None = None
    osd_firma: str | None = None
    osd_eski_adlar: tuple[str, ...] | None = None
    osd_arac_tipi: str | None = None
    osd_veri_tipi: str | None = None
    tim_sektor: str | None = None
    tim_eski_adlar: tuple[str, ...] | None = None
    tim_il: str | None = None
    tim_ulke: str | None = None
    monthly_agg: str = "mean"
    start_date: str | None = None
    bddk_kalem: str | None = None
    bddk_taraf: str | None = None
    bddk_kumulatif: bool | None = None
    tefas_tip: str | None = None
    tefas_olcut: str | None = None
    tefas_kod: str | None = None
    ec_kaynak: str | None = None
    ec_varlik: str | None = None
    fred_code: str | None = None
    pgsus_segment: str | None = None
    pgsus_olcut: str | None = None
    thy_segment: str | None = None
    thy_olcut: str | None = None
    tav_varlik: str | None = None
    tav_segment: str | None = None
    tav_olcut: str | None = None
    ebebek_metrik: str | None = None
    epdk_olcut: str | None = None
    epdk_urun: str | None = None
    turkcell_metrik: str | None = None
    ttkom_metrik: str | None = None
    odmd_marka: tuple[str, ...] | None = None
    odmd_yarim_marka: tuple[str, ...] | None = None
    odmd_kategori: str | None = None
    eib_kalem: str | None = None
    eib_olcut: str | None = None
    usk_kalem: str | None = None
    yayin_notu: str | None = None
    olcek: float | None = None
    gecikme_gunu: int | None = None
    hareketli_ortalama_gun: int | None = None


def _alan_verilmis(seri: Seri, alan: str) -> bool:
    """Tipe özgü alanların tamamı None varsayılanlıdır: verilmiş = None değil.

    `olcek` de bu kurala uyar (varsayılanı None; 1.0'a `ingest` tarafında
    düşülür), böylece katalogda açıkça yazılmış etkisiz bir `olcek: 1.0` da
    yakalanır — onurlandırılmayan bir alan, değeri ne olursa olsun yanıltıcıdır.
    """
    return getattr(seri, alan) is not None


def _alan_sahipligini_dogrula(seri: Seri) -> None:
    tanim = KAYNAK_ALANLARI[seri.kaynak_tipi]
    izinli = set(tanim["zorunlu"]) | set(tanim["istege_bagli"])

    for alan in tanim["zorunlu"]:
        # Boş string alanı doldurmaz: `evds_code: ""` kod yazmakla aynı değil.
        # Not: zorunlu alanlar bugün yalnızca string. Sayısal bir zorunlu alan
        # eklenirse bu falsy kontrolü 0'ı da reddeder — o gün ayrılması gerekir.
        if not getattr(seri, alan):
            raise KatalogHatasi(
                f"{seri.id}: {seri.kaynak_tipi} kaynağı için {alan} zorunlu"
            )

    for alan in sorted(TIPE_OZGU_ALANLAR - izinli):
        if _alan_verilmis(seri, alan):
            raise KatalogHatasi(
                f"{seri.id}: {seri.kaynak_tipi} kaynağı {alan} taşıyamaz"
            )


def _yaml_oku(ad: str) -> list[dict]:
    yol = KATALOG_DIZINI / ad
    if not yol.exists():
        raise KatalogHatasi(f"Katalog dosyası bulunamadı: {yol}")
    icerik = yaml.safe_load(yol.read_text(encoding="utf-8"))
    if not isinstance(icerik, list) or not icerik:
        raise KatalogHatasi(f"{ad} boş ya da liste değil")
    return icerik


@lru_cache(maxsize=1)
def kategorileri_yukle() -> tuple[Kategori, ...]:
    kategoriler = []
    gorulen: set[str] = set()
    for ham in _yaml_oku("categories.yaml"):
        slug = ham["slug"]
        if slug in gorulen:
            raise KatalogHatasi(f"Kategori slug'ı tekrar ediyor: {slug}")
        gorulen.add(slug)
        kategoriler.append(
            Kategori(
                slug=slug,
                title=ham["title"],
                note=ham.get("note"),
                pano=tuple(ham.get("pano", ())),
            )
        )
    return tuple(kategoriler)


@lru_cache(maxsize=1)
def hisseleri_yukle() -> tuple[Hisse, ...]:
    """Ticker tanımlarını okur ve seri referanslarını doğrular.

    Bilinmeyen bir seri id'si sessizce yutulmaz: `pano_serileri` ile aynı
    gerekçe — yazım hatası, kartın sayfada sessizce kaybolmasından ucuza
    yakalanmalı. `kendi` boş olamaz: şirketin kendi verisi olmayan bir
    ticker sayfası yalnızca makro grafik yığınıdır, sayfanın var oluş
    nedeni ortadan kalkar.
    """
    id_kumesi = {s.id for s in serileri_yukle()}
    hisseler: list[Hisse] = []
    gorulen: set[str] = set()
    for ham in _yaml_oku("hisseler.yaml"):
        kod = str(ham["kod"])
        if kod in gorulen:
            raise KatalogHatasi(f"Hisse kodu tekrar ediyor: {kod}")
        if not re.fullmatch(r"[A-Z]{4,6}", kod):
            raise KatalogHatasi(
                f"{kod}: hisse kodu 4–6 büyük harf olmalı (BIST kodu)"
            )
        gorulen.add(kod)
        kendi = tuple(ham.get("kendi", ()))
        baglam = tuple(ham.get("baglam", ()))
        if not kendi:
            raise KatalogHatasi(f"{kod}: en az bir 'kendi' serisi olmalı")
        eksik = [i for i in kendi + baglam if i not in id_kumesi]
        if eksik:
            raise KatalogHatasi(
                f"{kod}: katalogda olmayan seri: {', '.join(eksik)}"
            )
        cakisan = sorted(set(kendi) & set(baglam))
        if cakisan:
            raise KatalogHatasi(
                f"{kod}: aynı seri hem kendi hem baglam listesinde: "
                f"{', '.join(cakisan)} — sayfada iki kez çizilirdi"
            )
        hisseler.append(
            Hisse(
                kod=kod,
                title=ham["title"],
                sektor=ham["sektor"],
                kendi=kendi,
                baglam=baglam,
                note=ham.get("note"),
            )
        )
    return tuple(hisseler)


@lru_cache(maxsize=1)
def serileri_yukle() -> tuple[Seri, ...]:
    sluglar = {k.slug for k in kategorileri_yukle()}
    seriler = []
    gorulen: set[str] = set()

    for ham in _yaml_oku("series.yaml"):
        evds_frekans = ham.get("evds_frequency")
        seri = Seri(
            id=ham["id"],
            title=ham["title"],
            category=ham["category"],
            kaynak=Kaynak(**ham["kaynak"]),
            kaynak_tipi=ham["kaynak_tipi"],
            unit=ham["unit"],
            freq=ham["freq"],
            charts=tuple(ham["charts"]),
            evds_code=ham.get("evds_code"),
            evds_frequency=None if evds_frekans is None else str(evds_frekans),
            yahoo_symbol=ham.get("yahoo_symbol"),
            epias_ucu=ham.get("epias_ucu"),
            epias_alani=ham.get("epias_alani"),
            epias_bilesenler=(
                {ad: tuple(alanlar) for ad, alanlar in ham["epias_bilesenler"].items()}
                if "epias_bilesenler" in ham
                else None
            ),
            epias_havza=ham.get("epias_havza"),
            osd_firma=ham.get("osd_firma"),
            osd_eski_adlar=(
                tuple(ham["osd_eski_adlar"]) if "osd_eski_adlar" in ham else None
            ),
            osd_arac_tipi=ham.get("osd_arac_tipi"),
            osd_veri_tipi=ham.get("osd_veri_tipi"),
            tim_sektor=ham.get("tim_sektor"),
            tim_eski_adlar=(
                tuple(ham["tim_eski_adlar"]) if "tim_eski_adlar" in ham else None
            ),
            tim_il=ham.get("tim_il"),
            tim_ulke=ham.get("tim_ulke"),
            bddk_kalem=ham.get("bddk_kalem"),
            bddk_taraf=(
                str(ham["bddk_taraf"]) if "bddk_taraf" in ham else None
            ),
            bddk_kumulatif=ham.get("bddk_kumulatif"),
            tefas_tip=ham.get("tefas_tip"),
            tefas_olcut=ham.get("tefas_olcut"),
            tefas_kod=ham.get("tefas_kod"),
            ec_kaynak=ham.get("ec_kaynak"),
            ec_varlik=ham.get("ec_varlik"),
            fred_code=ham.get("fred_code"),
            pgsus_segment=ham.get("pgsus_segment"),
            pgsus_olcut=ham.get("pgsus_olcut"),
            thy_segment=ham.get("thy_segment"),
            thy_olcut=ham.get("thy_olcut"),
            tav_varlik=ham.get("tav_varlik"),
            tav_segment=ham.get("tav_segment"),
            tav_olcut=ham.get("tav_olcut"),
            epdk_olcut=ham.get("epdk_olcut"),
            epdk_urun=ham.get("epdk_urun"),
            turkcell_metrik=ham.get("turkcell_metrik"),
            ttkom_metrik=ham.get("ttkom_metrik"),
            odmd_marka=(
                tuple(ham["odmd_marka"]) if "odmd_marka" in ham else None
            ),
            odmd_yarim_marka=(
                tuple(ham["odmd_yarim_marka"]) if "odmd_yarim_marka" in ham else None
            ),
            odmd_kategori=ham.get("odmd_kategori"),
            ebebek_metrik=ham.get("ebebek_metrik"),
            eib_kalem=ham.get("eib_kalem"),
            eib_olcut=ham.get("eib_olcut"),
            usk_kalem=ham.get("usk_kalem"),
            monthly_agg=ham.get("monthly_agg", "mean"),
            start_date=ham.get("start_date"),
            yayin_notu=ham.get("yayin_notu"),
            olcek=float(ham["olcek"]) if "olcek" in ham else None,
            gecikme_gunu=(
                int(ham["gecikme_gunu"]) if "gecikme_gunu" in ham else None
            ),
            hareketli_ortalama_gun=ham.get("hareketli_ortalama_gun"),
        )
        _dogrula(seri, sluglar, gorulen)
        gorulen.add(seri.id)
        seriler.append(seri)

    return tuple(seriler)


def _dogrula(seri: Seri, kategori_sluglari: set[str], gorulen: set[str]) -> None:
    if seri.id in gorulen:
        raise KatalogHatasi(f"Seri id'si tekrar ediyor: {seri.id}")
    if seri.category not in kategori_sluglari:
        raise KatalogHatasi(
            f"{seri.id}: '{seri.category}' kategorisi categories.yaml'da yok"
        )
    if not seri.id.startswith(f"{seri.category}/"):
        raise KatalogHatasi(
            f"{seri.id}: id, kategori adıyla başlamalı ('{seri.category}/')"
        )
    if seri.freq not in GECERLI_FREKANSLAR:
        raise KatalogHatasi(f"{seri.id}: geçersiz freq '{seri.freq}'")
    if seri.monthly_agg not in GECERLI_AYLIK_AGG:
        raise KatalogHatasi(f"{seri.id}: geçersiz monthly_agg '{seri.monthly_agg}'")
    if not seri.charts:
        raise KatalogHatasi(f"{seri.id}: en az bir grafik tanımlı olmalı")
    if not set(seri.charts) <= GECERLI_GRAFIKLER:
        raise KatalogHatasi(f"{seri.id}: bilinmeyen grafik türü {seri.charts}")
    if len(set(seri.charts)) != len(seri.charts):
        raise KatalogHatasi(f"{seri.id}: charts listesinde tekrar var {seri.charts}")
    if "daily_seasonality" in seri.charts and seri.freq != "daily":
        raise KatalogHatasi(f"{seri.id}: daily_seasonality günlük seri gerektirir")
    if "fon" in seri.charts and seri.freq != "daily":
        raise KatalogHatasi(f"{seri.id}: fon grafiği günlük seri gerektirir")
    if seri.freq == "quarterly" and set(seri.charts) != {"level"}:
        raise KatalogHatasi(f"{seri.id}: çeyreklik seri yalnızca level grafiği destekler")
    if seri.hareketli_ortalama_gun is not None:
        if type(seri.hareketli_ortalama_gun) is not int or seri.hareketli_ortalama_gun <= 0:
            raise KatalogHatasi(
                f"{seri.id}: hareketli_ortalama_gun pozitif tam sayı olmalı"
            )
        if seri.freq != "daily" or set(seri.charts) & {"composition", "fon"}:
            raise KatalogHatasi(
                f"{seri.id}: hareketli_ortalama_gun günlük tek değerli seri gerektirir"
            )
    if seri.kaynak_tipi not in GECERLI_KAYNAK_TIPLERI:
        raise KatalogHatasi(f"{seri.id}: geçersiz kaynak_tipi '{seri.kaynak_tipi}'")
    _alan_sahipligini_dogrula(seri)
    if (seri.kaynak_tipi == "tefas_fon") != ("fon" in seri.charts):
        raise KatalogHatasi(f"{seri.id}: tefas_fon kaynağı ile fon grafiği birlikte kullanılmalı")
    if "fon" in seri.charts and seri.charts != ("fon",):
        raise KatalogHatasi(f"{seri.id}: fon tek başına olmalı, başka grafikle birleştirilemez")
    if seri.kaynak_tipi == "epias":
        if seri.epias_ucu == "baraj-doluluk":
            # EPİAŞ'ın baraj doluluk ucu (dams-data/active-fullness +
            # active-volume + dam-volume) saatlik alan/bileşen değil,
            # havza/ülke bazında kapasite ağırlıklı tek bir günlük değerdir
            # (bkz. ingest/epias.py baraj_doluluk_cek) — epias_alani ve
            # epias_bilesenler bu uçta anlamsızdır.
            if seri.epias_alani or seri.epias_bilesenler:
                raise KatalogHatasi(
                    f"{seri.id}: baraj-doluluk serisi epias_alani/"
                    "epias_bilesenler taşıyamaz"
                )
            if (
                seri.epias_havza is not None
                and seri.epias_havza not in GECERLI_EPIAS_HAVZALARI
            ):
                raise KatalogHatasi(
                    f"{seri.id}: geçersiz epias_havza '{seri.epias_havza}' "
                    f"(geçerli: {', '.join(sorted(GECERLI_EPIAS_HAVZALARI))})"
                )
        else:
            if seri.epias_havza is not None:
                raise KatalogHatasi(
                    f"{seri.id}: epias_havza yalnızca baraj-doluluk "
                    "serisinde kullanılır"
                )
            # Tek alan mı, bileşen grubu mu: biri ya da diğeri, ikisi birden değil.
            if bool(seri.epias_alani) == bool(seri.epias_bilesenler):
                raise KatalogHatasi(
                    f"{seri.id}: epias serisi ya epias_alani ya epias_bilesenler "
                    "taşımalı (ikisi birden ya da hiçbiri değil)"
                )
    if bool(seri.epias_bilesenler) != ("composition" in seri.charts):
        raise KatalogHatasi(
            f"{seri.id}: epias_bilesenler ile composition grafiği birlikte "
            "kullanılır; biri varsa diğeri de olmalı"
        )
    if "composition" in seri.charts and set(seri.charts) != {"composition"}:
        # `page.py` bileşenli seri için yalnızca kompozisyon grafiğini çizer;
        # composition başka bir grafikle (ör. level) birlikte listelenirse
        # o ikinci grafik sessizce hiç çizilmez — KAYNAK_ALANLARI tablosunun
        # var oluş gerekçesiyle aynı ilke: sessizce yok sayılan bir alan
        # yanıltıcıdır.
        raise KatalogHatasi(
            f"{seri.id}: composition tek başına olmalı, başka grafikle "
            f"birleştirilemez (charts={list(seri.charts)})"
        )
    if seri.kaynak_tipi == "epias" and seri.monthly_agg == "last":
        # epias.seri_cek yalnızca sum/mean günlük indirgemesi biliyor;
        # "last" verilirse else dalı bunu sessizce ortalamaya çeviriyordu.
        raise KatalogHatasi(
            f"{seri.id}: epias kaynağı monthly_agg='last' alamaz "
            "(yalnızca 'sum' ya da 'mean' desteklenir)"
        )
    if seri.kaynak_tipi == "eurocontrol" and seri.ec_kaynak not in GECERLI_EC_KAYNAKLARI:
        raise KatalogHatasi(
            f"{seri.id}: geçersiz ec_kaynak '{seri.ec_kaynak}' "
            f"(geçerli: {', '.join(sorted(GECERLI_EC_KAYNAKLARI))})"
        )
    if seri.kaynak_tipi == "pgsus":
        if seri.pgsus_segment not in GECERLI_PGSUS_SEGMENTLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz pgsus_segment '{seri.pgsus_segment}' "
                f"(geçerli: {', '.join(sorted(GECERLI_PGSUS_SEGMENTLERI))})"
            )
        if seri.pgsus_olcut not in GECERLI_PGSUS_OLCUTLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz pgsus_olcut '{seri.pgsus_olcut}' "
                f"(geçerli: {', '.join(sorted(GECERLI_PGSUS_OLCUTLERI))})"
            )
    if seri.kaynak_tipi == "thy":
        if seri.thy_segment not in GECERLI_THY_SEGMENTLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz thy_segment '{seri.thy_segment}' "
                f"(geçerli: {', '.join(sorted(GECERLI_THY_SEGMENTLERI))})"
            )
        if seri.thy_olcut not in GECERLI_THY_OLCUTLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz thy_olcut '{seri.thy_olcut}' "
                f"(geçerli: {', '.join(sorted(GECERLI_THY_OLCUTLERI))})"
            )
    if seri.kaynak_tipi == "tav":
        if seri.tav_segment not in GECERLI_TAV_SEGMENTLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz tav_segment '{seri.tav_segment}' "
                f"(geçerli: {', '.join(sorted(GECERLI_TAV_SEGMENTLERI))})"
            )
        # Verilmemişse "yolcu" kabul edilir (ingest/tav.py:seri_cek ile aynı
        # varsayılan) — mevcut 28 yolcu serisi tav_olcut hiç taşımıyor.
        if seri.tav_olcut is not None and seri.tav_olcut not in GECERLI_TAV_OLCUTLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz tav_olcut '{seri.tav_olcut}' "
                f"(geçerli: {', '.join(sorted(GECERLI_TAV_OLCUTLERI))})"
            )
    if seri.kaynak_tipi == "ebebek" and seri.ebebek_metrik not in GECERLI_EBEBEK_METRIKLERI:
        raise KatalogHatasi(
            f"{seri.id}: geçersiz ebebek_metrik '{seri.ebebek_metrik}' "
            f"(geçerli: {', '.join(sorted(GECERLI_EBEBEK_METRIKLERI))})"
        )
    if seri.kaynak_tipi == "epdk":
        if seri.epdk_olcut not in GECERLI_EPDK_OLCUTLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz epdk_olcut '{seri.epdk_olcut}' "
                f"(geçerli: {', '.join(sorted(GECERLI_EPDK_OLCUTLERI))})"
            )
        if seri.epdk_urun not in GECERLI_EPDK_URUNLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz epdk_urun '{seri.epdk_urun}' "
                f"(geçerli: {', '.join(sorted(GECERLI_EPDK_URUNLERI))})"
            )
    if seri.kaynak_tipi == "turkcell" and seri.turkcell_metrik not in GECERLI_TURKCELL_METRIKLERI:
        raise KatalogHatasi(
            f"{seri.id}: geçersiz turkcell_metrik '{seri.turkcell_metrik}' "
            f"(geçerli: {', '.join(sorted(GECERLI_TURKCELL_METRIKLERI))})"
        )
    if seri.kaynak_tipi == "ttkom" and seri.ttkom_metrik not in GECERLI_TTKOM_METRIKLERI:
        raise KatalogHatasi(
            f"{seri.id}: geçersiz ttkom_metrik '{seri.ttkom_metrik}' "
            f"(geçerli: {', '.join(sorted(GECERLI_TTKOM_METRIKLERI))})"
        )
    if (
        seri.kaynak_tipi == "osd"
        and seri.osd_veri_tipi is not None
        and seri.osd_veri_tipi not in GECERLI_OSD_VERI_TIPLERI
    ):
        raise KatalogHatasi(
            f"{seri.id}: geçersiz osd_veri_tipi '{seri.osd_veri_tipi}' "
            f"(geçerli: {', '.join(sorted(GECERLI_OSD_VERI_TIPLERI))})"
        )
    if seri.kaynak_tipi == "odmd":
        if seri.odmd_kategori not in GECERLI_ODMD_KATEGORILERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz odmd_kategori '{seri.odmd_kategori}' "
                f"(geçerli: {', '.join(sorted(GECERLI_ODMD_KATEGORILERI))})"
            )
        if not seri.odmd_marka:
            raise KatalogHatasi(f"{seri.id}: odmd_marka en az bir marka içermeli")
        cakisan = set(seri.odmd_marka) & set(seri.odmd_yarim_marka or ())
        if cakisan:
            raise KatalogHatasi(
                f"{seri.id}: {', '.join(sorted(cakisan))} hem odmd_marka hem "
                "odmd_yarim_marka içinde olamaz"
            )
    if seri.kaynak_tipi in {"tefas", "tefas_fon"}:
        # Yazım hatası adaptörün derinliklerinde KeyError'a dönüşmesin.
        if seri.tefas_tip not in GECERLI_TEFAS_TIPLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz tefas_tip '{seri.tefas_tip}' "
                f"(geçerli: {', '.join(sorted(GECERLI_TEFAS_TIPLERI))})"
            )
        if seri.kaynak_tipi == "tefas" and seri.tefas_olcut not in GECERLI_TEFAS_OLCUTLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz tefas_olcut '{seri.tefas_olcut}' "
                f"(geçerli: {', '.join(sorted(GECERLI_TEFAS_OLCUTLERI))})"
            )
    if seri.kaynak_tipi == "tefas_fon":
        if not isinstance(seri.tefas_kod, str) or not re.fullmatch(r"[A-Z0-9]+", seri.tefas_kod):
            raise KatalogHatasi(f"{seri.id}: geçersiz tefas_kod '{seri.tefas_kod}'")
        try:
            baslangic = date.fromisoformat(seri.start_date)
        except (TypeError, ValueError) as hata:
            raise KatalogHatasi(f"{seri.id}: start_date YYYY-MM-DD biçiminde geçerli tarih olmalı") from hata
        if baslangic.isoformat() != seri.start_date or baslangic > date.today():
            raise KatalogHatasi(f"{seri.id}: start_date YYYY-MM-DD biçiminde ve bugün veya öncesinde olmalı")
    # Alan varlığı tabloda; burada yalnızca değer geçerliliği kalıyor.
    if seri.olcek is not None and seri.olcek <= 0:
        raise KatalogHatasi(
            f"{seri.id}: olcek pozitif olmalı (verilen: {seri.olcek})"
        )
    if seri.gecikme_gunu is not None and seri.gecikme_gunu <= 0:
        # 0 "gecikme yok" demek değil, alanı gereksiz yazmak demek: eşik
        # zaten tipik gecikmeyi içeriyor. Negatif değer eşiği daraltarak
        # sahte "gecikmiş" üretir.
        raise KatalogHatasi(
            f"{seri.id}: gecikme_gunu pozitif olmalı (verilen: {seri.gecikme_gunu})"
        )
    if seri.kaynak_tipi == "evds" and seri.evds_frequency not in GECERLI_EVDS_FREKANSLARI:
        raise KatalogHatasi(
            f"{seri.id}: geçersiz evds_frequency '{seri.evds_frequency}'"
        )


def seri_listele(kategori: str | None = None) -> list[Seri]:
    seriler = serileri_yukle()
    if kategori is None:
        return list(seriler)
    return [s for s in seriler if s.category == kategori]


def seri_getir(seri_id: str) -> Seri:
    for seri in serileri_yukle():
        if seri.id == seri_id:
            return seri
    raise KatalogHatasi(f"Katalogda böyle bir seri yok: {seri_id}")
