"""Kategori sayfası üreticisi.

Sayfalar bildirimseldir: katalogdaki her kategori için bir kapanış
üretilir, içerik katalogdan okunur.
"""

from __future__ import annotations

from typing import Callable

import streamlit as st

from core.catalog import Kategori, SIKLIK_ETIKETLERI, seri_listele
from core.components import grafik_karti, kpi_satiri
from core.stats import GORUNUMLER, VARSAYILAN
from core.takvim import GUNCEL, OKUNAMADI, tablo_df, takvim


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
        kaynaklar = sorted({s.kaynak.name for s in seri_listele()})
        st.caption(
            "Türkiye ekonomisi ve küresel emtia için veri ve grafikler · "
            f"Kaynak: {', '.join(kaynaklar)}"
        )
        sutunlar = st.columns(2)
        for sira, (kategori, hedef) in enumerate(eslesmeler):
            with sutunlar[sira % 2], st.container(border=True):
                st.page_link(hedef, label=f"**{kategori.title}**")
                st.caption(f"{len(seri_listele(kategori.slug))} seri")

    return sayfa


def veri_takvimi_sayfasi() -> None:
    satirlar = takvim()
    sorunlular = [s for s in satirlar if s.durum != GUNCEL]

    st.title("Veri Takvimi")
    st.caption(
        f"{len(satirlar)} seri · {len(satirlar) - len(sorunlular)} güncel · "
        f"{len(sorunlular)} dikkat gerektiriyor"
    )
    st.caption(
        "Bir seri geciktiğinde ya kaynak geç kalmıştır ya da ingest kırılmıştır."
    )

    if sorunlular:
        with st.container(border=True):
            st.markdown(f"**⚠ {len(sorunlular)} seri dikkat gerektiriyor**")
            for s in sorunlular:
                if s.durum == OKUNAMADI:
                    sure = "veri dosyası okunamıyor"
                elif s.bekleme_gunu is None:
                    sure = "hiç veri yok"
                else:
                    sure = f"{s.bekleme_gunu} gündür yeni veri yok"
                st.markdown(
                    f"- **{s.seri.title}** — {sure} "
                    f"({SIKLIK_ETIKETLERI[s.seri.freq].lower()})"
                )
        st.divider()

    st.dataframe(tablo_df(satirlar), width="stretch", hide_index=True)
