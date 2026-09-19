"""Streamlit bileşenleri: KPI satırı ve grafik kartı.

grafik_karti() tek fonksiyondur; sitedeki tüm kartlar onun bir örneğidir.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.catalog import SIKLIK_ETIKETLERI, Seri
from core.charts import (
    fon_donem_figuru,
    karsilastirma_figuru,
    gunluk_mevsimsellik_figuru,
    hareketli_ortalama_uygula,
    kompozisyon_figuru,
    kompozisyon_verisi_hazirla,
    mevsimsellik_figuru,
    seviye_figuru,
)
from core.data import VeriYokHatasi, load_series, load_wide_series
from core.stats import (
    CEYREKLIK,
    MOM,
    VARSAYILAN,
    aralik_12a,
    gorunum_uygula,
    mom,
    qoq,
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
    """Yüzde görünümünde toplama anlamsızdır — yüzdelerin ortalaması alınır.

    Çeyreklik görünümde veri ZATEN toplulaştırılmış gelir; ikinci kez
    toplamak çeyrek değerlerini üst üste bindirir, bu yüzden ortalama."""
    return seri.monthly_agg if gorunum == VARSAYILAN else "mean"


def donem_etiketi(tarih: pd.Timestamp, freq: str) -> str:
    """Günlük ve haftalık serilerde gün gösterilir — bayatlık ancak böyle görülür."""
    if freq == "yearly":
        return f"{tarih.year}"
    if freq == "quarterly":
        return f"{tarih.year}-Ç{tarih.quarter}"
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
    return [s for s in seriler if not s.epias_bilesenler and "fon" not in s.charts]


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
                f"YoY {yuzde_rozeti(yoy(df, seri.freq))} · "
                f"{donem_etiketi(son_tarih(df), seri.freq)}",
                unsafe_allow_html=True,
            )


def _istatistik_satiri(df, seri: Seri) -> None:
    aralik = aralik_12a(df)
    aralik_metni = (
        f"{sayi_bicimle(aralik[0])} – {sayi_bicimle(aralik[1])}" if aralik else "—"
    )
    degisim_etiketi = "QoQ" if seri.freq == "quarterly" else "MoM"
    degisim = qoq(df) if seri.freq == "quarterly" else mom(df)
    sol, sag = st.columns(2)
    with sol:
        st.markdown(
            f"**{sayi_bicimle(son_deger(df), seri.unit)}**  \n"
            f"{degisim_etiketi} {yuzde_rozeti(degisim)}",
            unsafe_allow_html=True,
        )
    with sag:
        st.markdown(
            f"YoY {yuzde_rozeti(yoy(df, seri.freq))}  \n"
            f"<span style='color:{RENKLER['metin_soluk']}'>12A aralık "
            f"{aralik_metni}</span>",
            unsafe_allow_html=True,
        )


def grafik_karti(seri: Seri, gorunum: str) -> None:
    if "fon" in seri.charts:
        fon_karti(seri)
        return
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

        hesaplanacak = hareketli_ortalama_uygula(df, seri.hareketli_ortalama_gun)
        gosterilecek = gorunum_uygula(
            hesaplanacak, gorunum, seri.freq, seri.monthly_agg
        )
        if seri.freq == "quarterly" and gorunum == MOM:
            st.caption("Çeyreklik seri: önceki çeyreğe göre değişim (QoQ %)")
        if gorunum == CEYREKLIK and seri.freq not in {"quarterly", "yearly"}:
            st.caption(
                f"Çeyreklik toplulaştırma ({seri.monthly_agg}); "
                "tamamlanmamış çeyrek gösterilmez"
            )
        if seri.hareketli_ortalama_gun is not None:
            st.caption(
                f"Grafikler: {seri.hareketli_ortalama_gun} günlük hareketli ortalama · "
                "Üstteki istatistikler: ham günlük veri"
            )
        birim = seri.unit if gorunum in (VARSAYILAN, CEYREKLIK) else "%"

        for grafik in seri.charts:
            if grafik == "seasonality":
                fig = mevsimsellik_figuru(
                    gosterilecek, birim, agg=grafik_agg(seri, gorunum), freq=seri.freq
                )
            elif grafik == "daily_seasonality":
                fig = gunluk_mevsimsellik_figuru(gosterilecek, birim)
            else:
                fig = seviye_figuru(gosterilecek, birim, seri.freq)
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


ONS_GRAM = 31.1034768


def _yuze_endeksle(seri: pd.Series) -> pd.Series:
    return seri / seri.iloc[0] * 100


def _fon_karsilastirma(fiyat: pd.Series) -> pd.DataFrame:
    """Fon ile BIST 100, Dolar/TL ve gram altını aynı pencerede endeksler.

    Gram altın katalogda yok: ons altın (USD) × USD/TRY ÷ 31,1035 ile
    türetilir — iki seri de günlük ve katalogda mevcut.
    """
    olcutler = {"Fon": fiyat}
    try:
        bist = load_series("ekonomi-makro/bist100")["value"]
        usd = load_series("ekonomi-makro/usd-try")["value"]
        ons = load_series("emtia-metaller/altin")["value"]
    except VeriYokHatasi:
        return pd.DataFrame(olcutler).pipe(lambda d: d.assign(Fon=_yuze_endeksle(d["Fon"])))
    gram_altin = (ons * usd / ONS_GRAM).dropna()
    for ad, seri in (("BIST 100", bist), ("Dolar/TL", usd), ("Gram Altın", gram_altin)):
        # Fonun yayın günlerine hizala: ölçütün tatil günü fonun gününü silmesin.
        olcutler[ad] = seri.reindex(fiyat.index, method="ffill")
    return pd.DataFrame(olcutler).dropna().apply(_yuze_endeksle)


def fon_karti(seri: Seri) -> None:
    """Fon fiyatı, dönem sonu büyüklüğü ve hesap değişimlerini gösterir."""
    st.subheader(seri.title)
    st.caption(f"Kaynak: {seri.kaynak.name} · Hesap sayısı tekil kişi sayısı değildir.")
    try:
        df = load_wide_series(seri.id)
    except VeriYokHatasi as hata:
        st.warning(str(hata))
        return
    if df.empty:
        st.warning(f"{seri.title}: veri dosyası boş")
        return
    st.caption(f"Son yayın: {df.index.max():%d.%m.%Y} · {len(df)} günlük gözlem")
    st.caption("Cari hafta ve ay tamamlanmamıştır; son yayın günündeki değer gösterilir.")
    baslangic = st.date_input(
        "Fiyat ve düşüş grafikleri başlangıcı",
        value=max(df.index.min().date(), pd.Timestamp(df.index.max().year - 1, 1, 1).date()),
        min_value=df.index.min().date(), max_value=df.index.max().date(),
        key=f"fon_baslangic_{seri.id}",
    )
    fiyat = df.loc[pd.Timestamp(baslangic):, "fiyat"]
    gorunum = st.segmented_control(
        "Fiyat görünümü", ["Fiyat (TL)", "1.000 TL yatırım"],
        default="Fiyat (TL)", key=f"fon_fiyat_{seri.id}",
    )
    gosterilen = fiyat if gorunum != "1.000 TL yatırım" else fiyat / fiyat.iloc[0] * 1000
    st.markdown("**Günlük fiyat**")
    fig = seviye_figuru(gosterilen.to_frame("value"), "TL", "daily")
    fig.update_traces(hovertemplate="%{y:,.6f} TL<extra></extra>")
    st.plotly_chart(fig, width="stretch", key=f"{seri.id}-fiyat")
    for frekans, baslik, adet in (("W-SUN", "Haftalık", 52), ("ME", "Aylık", 24)):
        donem = df.resample(frekans).last()
        olcutler = (
            ("Getiri", donem["fiyat"].pct_change(fill_method=None) * 100, "%"),
            ("Fon büyüklüğü", donem["buyukluk"] / 1e6, "Milyon TL"),
            ("Hesap değişimi", donem["hesap"].diff(), "Hesap"),
            ("Hesap değişimi (%)", donem["hesap"].pct_change(fill_method=None) * 100, "%"),
        )
        sutunlar = st.columns(2)
        for sira, (etiket, degerler, birim) in enumerate(olcutler):
            with sutunlar[sira % 2]:
                st.markdown(f"**{baslik} · {etiket}**")
                st.plotly_chart(
                    fon_donem_figuru(degerler.tail(adet), birim), width="stretch",
                    key=f"{seri.id}-{frekans}-{sira}",
                )
    st.markdown("**Zirveden düşüş**")
    dusus = (fiyat / fiyat.cummax() - 1) * 100
    st.plotly_chart(seviye_figuru(dusus.to_frame("value"), "%", "daily"),
                    width="stretch", key=f"{seri.id}-dusus")
    st.markdown("**Karşılaştırma (100'e endeksli)**")
    st.caption(
        "Gram altın ons altın × USD/TRY ÷ 31,1035 ile türetilir; ölçütler fonun "
        "yayın günlerine ileri doldurma ile hizalanır."
    )
    st.plotly_chart(karsilastirma_figuru(_fon_karsilastirma(fiyat), "Endeks (ilk gün=100)"),
                    width="stretch", key=f"{seri.id}-karsilastirma")
    with st.expander("Fon verisi"):
        st.dataframe(df.rename(columns={"fiyat": "Fiyat (TL)", "pay": "Pay",
                     "hesap": "Hesap", "buyukluk": "Büyüklük (TL)"}), width="stretch")
