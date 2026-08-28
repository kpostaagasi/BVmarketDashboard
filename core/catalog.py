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
GECERLI_GRAFIKLER = {"seasonality", "level"}
GECERLI_AYLIK_AGG = {"mean", "last", "sum"}
GECERLI_KAYNAK_TIPLERI = {"evds", "yahoo", "epias"}
SIKLIK_ETIKETLERI = {"daily": "GÜNLÜK", "weekly": "HAFTALIK", "monthly": "AYLIK"}


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
    monthly_agg: str = "mean"
    start_date: str | None = None
    yayin_notu: str | None = None
    olcek: float = 1.0


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
            monthly_agg=ham.get("monthly_agg", "mean"),
            start_date=ham.get("start_date"),
            yayin_notu=ham.get("yayin_notu"),
            olcek=float(ham.get("olcek", 1.0)),
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
    if seri.kaynak_tipi == "evds":
        if not seri.evds_code:
            raise KatalogHatasi(f"{seri.id}: evds kaynağı için evds_code zorunlu")
        if seri.evds_frequency not in GECERLI_EVDS_FREKANSLARI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz evds_frequency '{seri.evds_frequency}'"
            )
        if seri.yahoo_symbol:
            raise KatalogHatasi(f"{seri.id}: evds kaynağı yahoo_symbol taşımamalı")
    if seri.kaynak_tipi == "yahoo":
        if not seri.yahoo_symbol:
            raise KatalogHatasi(f"{seri.id}: yahoo kaynağı için yahoo_symbol zorunlu")
        if seri.evds_code or seri.evds_frequency:
            raise KatalogHatasi(
                f"{seri.id}: yahoo kaynağı evds alanları taşımamalı"
            )
        if seri.start_date:
            raise KatalogHatasi(
                f"{seri.id}: yahoo kaynağı start_date desteklemiyor "
                "(range=15y sabit)"
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
