"""Kategori sayfası üreticisi.

Sayfalar bildirimseldir: katalogdaki her kategori için bir kapanış
üretilir, içerik katalogdan okunur.
"""

from __future__ import annotations

from typing import Callable

import pandas as pd
import streamlit as st

from core.catalog import Kategori, KatalogHatasi, SIKLIK_ETIKETLERI, Seri, seri_listele
from core.components import grafik_karti, kompozisyon_karti, kpi_satiri
from core.stats import GORUNUMLER, VARSAYILAN
from core.takvim import GUNCEL, OKUNAMADI, tablo_df, takvim


# Yalnızca "Durum" ayarlanır: "bekleniyor (59 gün)" otomatik genişliğe
# sığmıyor. Diğer sütunlarda otomatik boyutlandırma zaten doğru sonuç
# veriyor; genişlik dayatmak onları kesiyordu.
TAKVIM_SUTUN_AYARI = {
    "Durum": st.column_config.TextColumn("Durum", width="medium"),
}


def takvim_sutun_sirasi(df: pd.DataFrame) -> list[str]:
    """Tamamen boş sütunları çıkarır.

    "Yayın notu" bugün her seride boş; yer kaplayıp bilgi taşımıyor ve
    kalan sütunları daraltıyor. Not girildiğinde sütun kendiliğinden döner.
    """
    return [ad for ad in df.columns if df[ad].astype(str).str.strip().any()]


def pano_serileri(kategori: Kategori, seriler: list[Seri]) -> list[Seri]:
    """Panoda gösterilecek serileri, kategorinin belirlediği sırada döndürür.

    Pano tanımlı değilse mevcut davranış korunur: kpi_satiri zaten ilk dördü
    alır (ve çok bileşenli serileri kendi içinde sessizce atlar — bkz.
    `core.components._kpi_uygun_seriler`). Bilinmeyen bir id sessizce
    yutulmaz — yazım hatası, kartın sessizce kaybolmasından daha ucuza
    yakalanmalı. Aynı gerekçeyle, `pano`da AÇIKÇA çok bileşenli (geniş) bir
    seri istenmişse de hata verilir: KPI kartı tek bir sayı gösterir, böyle
    bir serinin tek sayısı yoktur — bunu açıkça istemek de bir yazım/tasarım
    hatasıdır ve sessizce kaybolmamalı (bkz. I3).
    """
    if not kategori.pano:
        return seriler
    indeks = {s.id: s for s in seriler}
    eksik = [i for i in kategori.pano if i not in indeks]
    if eksik:
        raise KatalogHatasi(
            f"{kategori.slug} panosunda bilinmeyen seri: {', '.join(eksik)}"
        )
    genis = [i for i in kategori.pano if indeks[i].epias_bilesenler]
    if genis:
        raise KatalogHatasi(
            f"{kategori.slug} panosunda çok bileşenli (geniş) seri: "
            f"{', '.join(genis)} — KPI kartı tek sayı gösterir, bu serilerin "
            "tek sayısı yoktur"
        )
    return [indeks[i] for i in kategori.pano]


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

    kpi_satiri(pano_serileri(kategori, seriler))

    with st.expander("Veri Takvimi", expanded=False):
        takvim_df = tablo_df(takvim(kategori=kategori.slug))
        st.dataframe(
            takvim_df,
            width="stretch",
            hide_index=True,
            column_config=TAKVIM_SUTUN_AYARI,
            column_order=takvim_sutun_sirasi(takvim_df),
        )
    st.divider()

    sutunlar = st.columns(2)
    for sira, seri in enumerate(seriler):
        with sutunlar[sira % 2]:
            if "composition" in seri.charts:
                kompozisyon_karti(seri)
            else:
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

    df = tablo_df(satirlar)
    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        column_config=TAKVIM_SUTUN_AYARI,
        column_order=takvim_sutun_sirasi(df),
    )
