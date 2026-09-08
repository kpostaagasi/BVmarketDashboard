"""Streamlit bileşenleri: KPI satırı ve grafik kartı.

grafik_karti() tek fonksiyondur; sitedeki tüm kartlar onun bir örneğidir.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.catalog import SIKLIK_ETIKETLERI, Seri
from core.charts import (
    kompozisyon_figuru,
    kompozisyon_verisi_hazirla,
    mevsimsellik_figuru,
    seviye_figuru,
)
from core.data import VeriYokHatasi, load_series, load_wide_series
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
    return f"<span style='color:{renk}'>{isaret} %{_tr_sayi(abs(deger), 1)}</span>"


def grafik_agg(seri: Seri, gorunum: str) -> str:
    """Yüzde görünümünde toplama anlamsızdır — yüzdelerin ortalaması alınır."""
    return seri.monthly_agg if gorunum == VARSAYILAN else "mean"


def donem_etiketi(tarih: pd.Timestamp, freq: str) -> str:
    """Günlük ve haftalık serilerde gün gösterilir — bayatlık ancak böyle görülür."""
    return f"{tarih:%Y-%m}" if freq == "monthly" else f"{tarih:%Y-%m-%d}"


def _kpi_uygun_seriler(seriler: list[Seri]) -> list[Seri]:
    """Çok bileşenli (geniş) serileri KPI listesinden atlar.

    KPI kartı tek bir sayı gösterir; çok bileşenli bir serinin tek sayısı
    yoktur — bu bir hata değil, uygulanamazlıktır, bu yüzden burada
    SESSİZCE atlanır. `load_wide_series`'in geniş CSV'sinde `value` sütunu
    olmadığından, atlanmazsa `load_series` KeyError fırlatır ve bu, yalnızca
    `VeriYokHatasi` yakalayan `kpi_satiri` içinde yakalanmadan sayfayı
    düşürür. Bir seri `pano`da AÇIKÇA istenmişse bu sessiz atlama devreye
    girmez — `pano_serileri` (core/page.py) orada KatalogHatasi fırlatır.
    """
    return [s for s in seriler if not s.epias_bilesenler]


def kpi_satiri(seriler: list[Seri], sutun_sayisi: int = 4) -> None:
    """En çok dört KPI; ızgara SABİT dört sütun.

    Sütun sayısını gösterilecek seri sayısına bağlamak tek KPI'lı sayfada
    (hisse sayfaları) kartı tüm satıra yayıyordu — dev sayı, küçük etiket:
    kategori sayfalarındaki ritimden kopan bir "hero metrik" görüntüsü.
    Sabit ızgara kart genişliğini sayfalar arası aynı tutar.
    """
    gosterilecek = _kpi_uygun_seriler(seriler)[:sutun_sayisi]
    if not gosterilecek:
        return
    sutunlar = st.columns(sutun_sayisi)
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
                f"YoY {yuzde_rozeti(yoy(df))} · "
                f"{donem_etiketi(son_tarih(df), seri.freq)}",
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

        if df.empty:
            # Başlığı olup satırı olmayan CSV: son_tarih NaT döner, sayfa düşer.
            st.warning(f"{seri.title}: veri dosyası boş")
            return

        etiket = SIKLIK_ETIKETLERI[seri.freq]
        st.caption(f"Son Dönem: {donem_etiketi(son_tarih(df), seri.freq)} · {etiket}")
        _istatistik_satiri(df, seri)

        gosterilecek = gorunum_uygula(df, gorunum)
        birim = seri.unit if gorunum == VARSAYILAN else "%"

        for grafik in seri.charts:
            if grafik == "seasonality":
                fig = mevsimsellik_figuru(
                    gosterilecek, birim, agg=grafik_agg(seri, gorunum), freq=seri.freq
                )
            else:
                fig = seviye_figuru(gosterilecek, birim)
            st.plotly_chart(fig, width="stretch", key=f"{seri.id}-{grafik}")

        with st.expander("Veri tablosu"):
            st.dataframe(
                gosterilecek.rename(columns={"value": birim}),
                width="stretch",
            )


def kompozisyon_karti(seri: Seri) -> None:
    """Kaynak bazlı üretim kartı: kendi Pay%/GWh seçicisiyle.

    Sayfa düzeyindeki Varsayılan/YoY/MoM seçicisine bağlanmaz —
    kompozisyon grafiğinde YoY'un anlamı yoktur ve iki seçiciyi bağlamak
    anlamsız kombinasyonlar üretir.

    İndirgeme + tamamlanmamış-ay kuralı + görünüm seçimi
    `kompozisyon_verisi_hazirla`de (core/charts.py) yaşar — bu fonksiyon
    yalnızca render yapar. "Son Dönem" altyazısı GERÇEKTEN gösterilen
    aralığın son ayını yansıtır: Pay % ve GWh görünümleri, kısmi son ay
    kuralı yalnızca GWh'de uygulandığı için farklı son ay gösterebilir —
    bu doğru davranıştır (bkz. I2).
    """
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
            df = load_wide_series(seri.id)
        except VeriYokHatasi as hata:
            st.warning(str(hata))
            return

        gorunum = st.segmented_control(
            "Görünüm",
            ["Pay %", seri.unit],
            default="Pay %",
            key=f"kompozisyon_{seri.id}",
            label_visibility="collapsed",
        ) or "Pay %"

        gorunum_mutlak = gorunum != "Pay %"
        gosterilecek = kompozisyon_verisi_hazirla(df, gorunum_mutlak, seri.freq)
        birim = seri.unit if gorunum_mutlak else "%"

        if gosterilecek.empty:
            # Boş/tamamen kısmi veri: NaT üzerinde strftime sayfayı düşürür.
            st.warning(f"{seri.title}: gösterilecek tam ay yok")
            return

        st.caption(
            f"Son Dönem: {donem_etiketi(gosterilecek.index.max(), 'monthly')} · AYLIK"
        )
        st.plotly_chart(
            kompozisyon_figuru(gosterilecek, birim),
            width="stretch",
            key=f"{seri.id}-composition",
        )

        with st.expander("Veri tablosu"):
            st.dataframe(gosterilecek, width="stretch")
