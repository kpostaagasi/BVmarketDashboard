"""Streamlit bileşenleri: KPI satırı ve grafik kartı.

grafik_karti() tek fonksiyondur; sitedeki tüm kartlar onun bir örneğidir.
"""

from __future__ import annotations

from base64 import b64encode
from html import escape

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
from core.theme import RENKLER, STIL_CSS


def stil_uygula() -> None:
    """Uygulama geneli CSS'i enjekte eder; her sayfa çalışmasında bir kez."""
    st.html(f"<style>{STIL_CSS}</style>")


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


def kisa_sayi(deger: float | None) -> str:
    """KPI için: büyük sayıda kuruş gürültüdür, küçük sayıda bilgidir.

    |x| ≥ 1.000 ya da tam sayıysa (uçuş, adet) ondalıksız, değilse iki
    basamak. `sayi_bicimle`den ayrı tutulur; grafik kartı ve tablo tam
    hassasiyeti göstermeye devam eder.
    """
    if deger is None:
        return "—"
    tam = abs(deger) >= 1000 or float(deger).is_integer()
    return _tr_sayi(deger, 0 if tam else 2).removesuffix(",")


def degisim_rozeti(deger: float | None, etiket: str, puan: bool = False) -> str:
    """Hap biçimli değişim rozeti. Renk yalnızca ▲/▼ ile birlikte gelir.

    `puan=True` birimi zaten yüzde olan seriler içindir (faiz): %45→%40
    "%11 düştü" değil "5 puan düştü" yazılır; değer burada FARKTIR.
    """
    if deger is None:
        return f"<span class='bv-rozet bv-rozet-notr'><small>{etiket}</small> —</span>"
    if round(deger, 2) == 0:
        return f"<span class='bv-rozet bv-rozet-notr'><small>{etiket}</small> 0</span>"
    sinif = "artis" if deger >= 0 else "dusus"
    isaret = "▲" if deger >= 0 else "▼"
    metin = (
        f"{_tr_sayi(abs(deger), 2)} puan" if puan else f"%{_tr_sayi(abs(deger), 1)}"
    )
    return (
        f"<span class='bv-rozet bv-rozet-{sinif}'><small>{etiket}</small> "
        f"{isaret} {metin}</span>"
    )


def kivilcim_svg(
    degerler: list[float], renk: str, en: int = 96, boy: int = 30
) -> str:
    """Eksensiz mini çizgi (sparkline) — data-URI'li <img> içinde SVG.

    `preserveAspectRatio='none'`: telefonda CSS resmi kart genişliğine
    yayar; çizgi esner, kalınlığı `non-scaling-stroke` ile sabit kalır.

    Plotly figürü değil: bir KPI satırında dört ek iframe/figür sayfayı
    ağırlaştırırdı, 40 noktalık bir polyline yeterli. Satır içi <svg>
    değil: `st.html`in temizleyicisi <svg>'yi siliyor, <img> data-URI'sini
    geçiriyor (ölçüldü, Streamlit 1.62). Sabit seride (min=max) çizgi
    ortada düz durur; ikiden az nokta boş döner.
    """
    temiz = [d for d in degerler if d == d]  # NaN'ları at
    if len(temiz) < 2:
        return ""
    alt, ust = min(temiz), max(temiz)
    aralik = (ust - alt) or 1.0
    adim = en / (len(temiz) - 1)
    noktalar = " ".join(
        f"{i * adim:.1f},{boy - 2 - (d - alt) / aralik * (boy - 4):.1f}"
        for i, d in enumerate(temiz)
    )
    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{en}' height='{boy}' "
        f"viewBox='0 0 {en} {boy}' preserveAspectRatio='none'>"
        f"<polyline points='{noktalar}' fill='none' stroke='{renk}' "
        f"stroke-width='1.6' stroke-linejoin='round' stroke-linecap='round' "
        f"vector-effect='non-scaling-stroke'/></svg>"
    )
    kodlu = b64encode(svg.encode()).decode()
    return (
        f"<img class='bv-kivilcim' width='{en}' height='{boy}' alt='' "
        f"src='data:image/svg+xml;base64,{kodlu}'/>"
    )


def kivilcim_verisi(df: pd.DataFrame, freq: str, adet: int = 40) -> list[float]:
    """Mini grafiğin noktaları: aylık ve seyrek serilerde son 24 dönem,
    günlük/haftalık seride son ~1 yılın haftalık kapanışları."""
    if freq in {"daily", "weekly"}:
        return list(df["value"].resample("W").last().dropna().tail(52))
    return list(df["value"].dropna().tail(min(adet, 24)))


def kpi_karti_html(
    baslik: str, deger: str, birim: str, rozetler: list[str],
    alt_metin: str, kivilcim: str = "",
) -> str:
    # Katalog başlıkları kesme işareti taşıyor ("TİM'in") — escape'siz
    # title='…' özniteliği kırılır.
    baslik, birim = escape(baslik), escape(birim)
    return (
        "<div class='bv-kpi'>"
        f"<div class='bv-kpi-etiket' title='{baslik}'>{baslik}</div>"
        "<div class='bv-kpi-govde'><div>"
        f"<div class='bv-kpi-deger'>{deger}</div>"
        f"<div class='bv-kpi-birim' title='{birim}'>{birim}</div>"
        f"</div>{kivilcim}</div>"
        f"<div class='bv-kpi-alt'>{''.join(rozetler)}<span>{alt_metin}</span></div>"
        "</div>"
    )


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

    Kart saf HTML'dir: birim sayının altında ayrı satırda durur. Eski
    `st.markdown("### 5.781,74 Endeks (2025=100)")` dar sütunda üç satıra
    kırılıyordu.
    """
    gosterilecek = _kpi_uygun_seriler(seriler)[:sutun_sayisi]
    if not gosterilecek:
        return
    sutunlar = st.columns(sutun_sayisi)
    for sutun, seri in zip(sutunlar, gosterilecek):
        with sutun:
            st.html(kpi_html(seri))


def piyasa_karti_html(seri: Seri) -> str:
    """Ana sayfa piyasa şeridi: günlük seri, son gözleme göre 1G değişim.

    Birimi yüzde olan seride (politika faizi) değişimler puan farkıdır.
    """
    try:
        df = load_series(seri.id)
    except VeriYokHatasi:
        return kpi_karti_html(seri.title, "—", seri.unit, [], "veri yok")
    if len(df) < 2:
        return kpi_karti_html(seri.title, "—", seri.unit, [], "veri yetersiz")
    degerler = df["value"]
    puan = "%" in seri.unit
    if puan:
        gunluk = degerler.iloc[-1] - degerler.iloc[-2]
        yillik_onceki = degerler[: son_tarih(df) - pd.DateOffset(years=1)]
        yillik = (
            degerler.iloc[-1] - yillik_onceki.iloc[-1]
            if not yillik_onceki.empty else None
        )
    else:
        gunluk = (degerler.iloc[-1] / degerler.iloc[-2] - 1) * 100
        yillik = yoy(df, seri.freq)
    renk = RENKLER["artis"] if (yillik or 0) >= 0 else RENKLER["dusus"]
    return kpi_karti_html(
        seri.title,
        kisa_sayi(son_deger(df)),
        seri.unit,
        [degisim_rozeti(gunluk, "1G", puan), degisim_rozeti(yillik, "YoY", puan)],
        f"{son_tarih(df):%d.%m.%Y}",
        kivilcim_svg(kivilcim_verisi(df, seri.freq), renk),
    )


def kpi_html(seri: Seri) -> str:
    """Tek serinin KPI kartı. Veri yoksa kart düşmez, "veri yok" der."""
    try:
        df = load_series(seri.id)
    except VeriYokHatasi:
        return kpi_karti_html(seri.title, "—", seri.unit, [], "veri yok")
    if df.empty:
        return kpi_karti_html(seri.title, "—", seri.unit, [], "veri dosyası boş")
    degisim = qoq(df) if seri.freq == "quarterly" else mom(df)
    degisim_etiketi = "QoQ" if seri.freq == "quarterly" else "MoM"
    renk = RENKLER["artis"] if (yoy(df, seri.freq) or 0) >= 0 else RENKLER["dusus"]
    return kpi_karti_html(
        seri.title,
        kisa_sayi(son_deger(df)),
        seri.unit,
        [degisim_rozeti(yoy(df, seri.freq), "YoY"),
         degisim_rozeti(degisim, degisim_etiketi)],
        donem_etiketi(son_tarih(df), seri.freq),
        kivilcim_svg(kivilcim_verisi(df, seri.freq), renk),
    )


# `SIKLIK_ETIKETLERI` BÜYÜK harf; `.capitalize()` Türkçe İ'yi "i̇" (birleşik
# nokta) yapıyor, bu yüzden ayrı ve açık bir tablo.
SIKLIK_METNI = {
    "daily": "Günlük", "weekly": "Haftalık", "monthly": "Aylık",
    "quarterly": "Çeyreklik", "yearly": "Yıllık",
}


def kart_basligi_html(seri: Seri) -> str:
    return (
        "<div class='bv-kart-bas'>"
        f"<span class='bv-kart-baslik'>{escape(seri.title)}</span>"
        f"<span class='bv-kart-kaynak'><a href='{escape(seri.kaynak.url)}' "
        f"target='_blank'>{escape(seri.kaynak.name)} ↗</a></span></div>"
    )


def _kart_anahtari(seri: Seri) -> str:
    """`st-key-kart-*` CSS sınıfının kaynağı (bkz. theme.STIL_CSS)."""
    return f"kart-{seri.id.replace('/', '-')}"


def istatistik_html(df, seri: Seri) -> str:
    """Değer · YoY · MoM rozetleri, altında dönem ve 12A aralık.

    Eski iki sütunlu markdown düzeni dar kartta dört satıra dağılıyordu;
    tek esnek satır sığmadığında kendiliğinden kırılır.
    """
    aralik = aralik_12a(df)
    aralik_metni = (
        f"12A aralık {sayi_bicimle(aralik[0])} – {sayi_bicimle(aralik[1])}"
        if aralik else ""
    )
    degisim_etiketi = "QoQ" if seri.freq == "quarterly" else "MoM"
    degisim = qoq(df) if seri.freq == "quarterly" else mom(df)
    meta = " · ".join(
        parca for parca in (
            f"Son dönem {donem_etiketi(son_tarih(df), seri.freq)}",
            SIKLIK_METNI[seri.freq],
            aralik_metni,
        ) if parca
    )
    return (
        "<div class='bv-kart-ist'>"
        f"<span class='bv-kart-deger'>{sayi_bicimle(son_deger(df))}"
        f"<small>{escape(seri.unit)}</small></span>"
        f"{degisim_rozeti(yoy(df, seri.freq), 'YoY')}"
        f"{degisim_rozeti(degisim, degisim_etiketi)}"
        "</div>"
        f"<div class='bv-kart-meta'>{meta}</div>"
    )


def grafik_karti(seri: Seri, gorunum: str) -> None:
    if "fon" in seri.charts:
        fon_karti(seri)
        return
    with st.container(key=_kart_anahtari(seri)):
        st.html(kart_basligi_html(seri))

        try:
            df = load_series(seri.id)
        except VeriYokHatasi as hata:
            st.warning(str(hata))
            return

        if df.empty:
            # Başlığı olup satırı olmayan CSV: son_tarih NaT döner, sayfa düşer.
            st.warning(f"{seri.title}: veri dosyası boş")
            return

        st.html(istatistik_html(df, seri))

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
    with st.container(key=_kart_anahtari(seri)):
        st.html(kart_basligi_html(seri))

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
