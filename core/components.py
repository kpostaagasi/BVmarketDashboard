"""Streamlit bileşenleri: KPI satırı ve grafik kartı.

grafik_karti() tek fonksiyondur; sitedeki tüm kartlar onun bir örneğidir.
"""

from __future__ import annotations

import streamlit as st

from core.catalog import Seri
from core.charts import mevsimsellik_figuru, seviye_figuru
from core.data import VeriYokHatasi, load_series
from core.stats import (
    VARSAYILAN,
    aralik_12a,
    gorunum_uygula,
    mom,
    son_deger,
    son_tarih,
    yoy,
)
from core.theme import RENKLER

_SIKLIK_ETIKETLERI = {"daily": "GÜNLÜK", "weekly": "HAFTALIK", "monthly": "AYLIK"}


def _tr_sayi(deger: float, basamak: int = 2) -> str:
    """1234.56 -> '1.234,56' (Türkçe: binlik nokta, ondalık virgül)."""
    tam, _, ondalik = f"{deger:,.{basamak}f}".partition(".")
    return f"{tam.replace(',', '.')},{ondalik}"


def sayi_bicimle(deger: float | None, birim: str = "") -> str:
    if deger is None:
        return "—"
    metin = _tr_sayi(deger)
    return f"{metin} {birim}".strip()


def yuzde_rozeti(deger: float | None) -> str:
    """Durum rengi yalnızca ▲/▼ işaretiyle birlikte kullanılır."""
    if deger is None:
        return ":gray[—]"
    isaret = "▲" if deger >= 0 else "▼"
    renk = RENKLER["artis"] if deger >= 0 else RENKLER["dusus"]
    return f"<span style='color:{renk}'>{isaret} %{_tr_sayi(deger, 1)}</span>"


def kpi_satiri(seriler: list[Seri]) -> None:
    gosterilecek = seriler[:4]
    if not gosterilecek:
        return
    sutunlar = st.columns(len(gosterilecek))
    for sutun, seri in zip(sutunlar, gosterilecek):
        with sutun, st.container(border=True):
            st.caption(seri.title)
            try:
                df = load_series(seri.id)
            except VeriYokHatasi:
                st.markdown("**—**")
                st.caption("veri yok")
                continue
            st.markdown(f"### {sayi_bicimle(son_deger(df), seri.unit)}")
            st.markdown(
                f"YoY {yuzde_rozeti(yoy(df))} · {son_tarih(df):%Y-%m}",
                unsafe_allow_html=True,
            )


def _istatistik_satiri(df, seri: Seri) -> None:
    aralik = aralik_12a(df)
    aralik_metni = (
        f"{sayi_bicimle(aralik[0])} – {sayi_bicimle(aralik[1])}" if aralik else "—"
    )
    sol, sag = st.columns(2)
    with sol:
        st.markdown(
            f"**{sayi_bicimle(son_deger(df), seri.unit)}**  \n"
            f"MoM {yuzde_rozeti(mom(df))}",
            unsafe_allow_html=True,
        )
    with sag:
        st.markdown(
            f"YoY {yuzde_rozeti(yoy(df))}  \n"
            f"<span style='color:{RENKLER['metin_soluk']}'>12A aralık "
            f"{aralik_metni}</span>",
            unsafe_allow_html=True,
        )


def grafik_karti(seri: Seri, gorunum: str) -> None:
    with st.container(border=True):
        baslik, kaynak = st.columns([4, 1])
        baslik.markdown(f"**{seri.title}**")
        kaynak.markdown(
            f"<div style='text-align:right;color:{RENKLER['metin_soluk']};"
            f"font-size:0.8em'>"
            f"<a href='{seri.kaynak.url}' style='color:inherit'>"
            f"{seri.kaynak.name}</a></div>",
            unsafe_allow_html=True,
        )

        try:
            df = load_series(seri.id)
        except VeriYokHatasi as hata:
            st.warning(str(hata))
            return

        etiket = _SIKLIK_ETIKETLERI[seri.freq]
        st.caption(f"Son Dönem: {son_tarih(df):%Y-%m} · {etiket}")
        _istatistik_satiri(df, seri)

        gosterilecek = gorunum_uygula(df, gorunum)
        birim = seri.unit if gorunum == VARSAYILAN else "%"

        for grafik in seri.charts:
            if grafik == "seasonality":
                fig = mevsimsellik_figuru(gosterilecek, birim, agg=seri.monthly_agg)
            else:
                fig = seviye_figuru(gosterilecek, birim)
            st.plotly_chart(fig, use_container_width=True, key=f"{seri.id}-{grafik}")

        with st.expander("Veri tablosu"):
            st.dataframe(
                gosterilecek.rename(columns={"value": birim}),
                use_container_width=True,
            )
