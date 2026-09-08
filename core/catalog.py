"""Katalog: serilerin ve kategorilerin tek doğruluk kaynağı.

Metadata burada yaşar; veri dosyaları yalnızca `date,value` içerir.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

KOK = Path(__file__).resolve().parent.parent
KATALOG_DIZINI = KOK / "catalog"

GECERLI_FREKANSLAR = {"daily", "weekly", "monthly"}
GECERLI_EVDS_FREKANSLARI = {"1", "2", "5"}
GECERLI_GRAFIKLER = {"seasonality", "level", "composition"}
GECERLI_AYLIK_AGG = {"mean", "last", "sum"}
GECERLI_KAYNAK_TIPLERI = {"evds", "yahoo", "epias", "osd", "tim"}
SIKLIK_ETIKETLERI = {"daily": "GÜNLÜK", "weekly": "HAFTALIK", "monthly": "AYLIK"}

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
        "istege_bagli": ("epias_alani", "epias_bilesenler", "start_date"),
    },
    "osd": {
        "zorunlu": ("osd_firma",),
        "istege_bagli": ("start_date", "osd_eski_adlar"),
    },
    "tim": {
        "zorunlu": ("tim_sektor",),
        "istege_bagli": ("start_date", "tim_eski_adlar"),
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
    osd_firma: str | None = None
    osd_eski_adlar: tuple[str, ...] | None = None
    tim_sektor: str | None = None
    tim_eski_adlar: tuple[str, ...] | None = None
    monthly_agg: str = "mean"
    start_date: str | None = None
    yayin_notu: str | None = None
    olcek: float | None = None
    gecikme_gunu: int | None = None


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
            osd_firma=ham.get("osd_firma"),
            osd_eski_adlar=(
                tuple(ham["osd_eski_adlar"]) if "osd_eski_adlar" in ham else None
            ),
            tim_sektor=ham.get("tim_sektor"),
            tim_eski_adlar=(
                tuple(ham["tim_eski_adlar"]) if "tim_eski_adlar" in ham else None
            ),
            monthly_agg=ham.get("monthly_agg", "mean"),
            start_date=ham.get("start_date"),
            yayin_notu=ham.get("yayin_notu"),
            olcek=float(ham["olcek"]) if "olcek" in ham else None,
            gecikme_gunu=(
                int(ham["gecikme_gunu"]) if "gecikme_gunu" in ham else None
            ),
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
    if seri.kaynak_tipi not in GECERLI_KAYNAK_TIPLERI:
        raise KatalogHatasi(f"{seri.id}: geçersiz kaynak_tipi '{seri.kaynak_tipi}'")
    _alan_sahipligini_dogrula(seri)
    if seri.kaynak_tipi == "epias":
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
