"""Kategori sayfası üreticisi.

Sayfalar bildirimseldir: katalogdaki her kategori için bir kapanış
üretilir, içerik katalogdan okunur.
"""

from __future__ import annotations

from typing import Callable

import streamlit as st

from core.catalog import Kategori, seri_listele
from core.components import grafik_karti, kpi_satiri
from core.stats import GORUNUMLER, VARSAYILAN


def _kategoriyi_ciz(kategori: Kategori) -> None:
    seriler = seri_listele(kategori.slug)

    st.title(kategori.title)
    kaynaklar = sorted({s.kaynak.name for s in seriler})
    st.caption(f"{len(seriler)} seri · Kaynak: {', '.join(kaynaklar)}")
    if kategori.note:
        st.caption(kategori.note)

    gorunum = st.segmented_control(
        "Görünüm",
        GORUNUMLER,
        default=VARSAYILAN,
        key=f"gorunum_{kategori.slug}",
        label_visibility="collapsed",
    )
    gorunum = gorunum or VARSAYILAN

    kpi_satiri(seriler)
    st.divider()

    sutunlar = st.columns(2)
    for sira, seri in enumerate(seriler):
        with sutunlar[sira % 2]:
            grafik_karti(seri, gorunum)


def kategori_sayfasi_yap(kategori: Kategori) -> Callable[[], None]:
    def sayfa() -> None:
        _kategoriyi_ciz(kategori)

    sayfa.__name__ = f"sayfa_{kategori.slug.replace('-', '_')}"
    return sayfa


def genel_bakis_yap(
    eslesmeler: list[tuple[Kategori, "st.Page"]],
) -> Callable[[], None]:
    def sayfa() -> None:
        st.title("BV Market Dashboard")
        st.caption("Türkiye ekonomisi için veri ve grafikler · Kaynak: TCMB EVDS")
        sutunlar = st.columns(2)
        for sira, (kategori, hedef) in enumerate(eslesmeler):
            with sutunlar[sira % 2], st.container(border=True):
                st.page_link(hedef, label=f"**{kategori.title}**")
                st.caption(f"{len(seri_listele(kategori.slug))} seri")

    return sayfa
