"""Plotly figür üreticileri.

İki form yeterli:
- mevsimsellik: yıl başına bir çizgi, x ekseni Oca→Ara. "Bu ay normal mi?"
- seviye: tüm geçmiş, tek çizgi. "Nereden nereye geldik?"

Çift y-eksenli grafik üretilmez; farklı ölçekteki iki büyüklük iki ayrı
grafiktir.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from core.theme import CIZGI_DESENLERI, RENKLER, TR_AYLAR

_AGG_FONKSIYONLARI = {"mean": "mean", "last": "last", "sum": "sum"}


# Kapsama penceresi: bir ayın "başı" ve "sonu" sayılan gün sayısı, serinin
# frekansına göre. Günlük seride ayın son gününde nokta beklenir; haftalık
# seride son nokta ayın son yedi gününden biri olabilir.
_KAPSAMA_GUNU = {"daily": 1, "weekly": 7}


def kismi_aylari_dus(
    aylik: pd.DataFrame, ham_indeks: pd.DatetimeIndex, freq: str
) -> pd.DataFrame:
    """Ay-başlangıcına indirgenmiş `sum` serisinden KISMİ ayları düşürür.

    Bir ay ancak hem başı hem sonu ham veriyle kapsanıyorsa tamdır: ayın
    ilk `adım` günü içinde ve son `adım` günü içinde en az bir ham nokta
    olmalı (`adım` günlük seride 1, haftalık seride 7). Kısmi ay `sum`
    serisinde sahte bir dip üretir.

    Kural yalnızca UÇ aylara değil, İÇ aylara da uygulanır: EUROCONTROL
    serilerinde 2025 verisi cari günün bir yıl öncesinde bitiyor, yani
    seride 2025-09 (8 günlük) kısmi bir İÇ ay olarak duruyordu ve
    mevsimsellik grafiğinde uçurum gibi görünüyordu. Uçlara özel eski kural
    (Faz 3c'nin `uc_aylar_tamamlanmamissa_dus`) bunu yakalamıyordu; kural
    genelleştirildi, uç davranışı aynı kaldı.

    Boş `aylik` ya da bilinmeyen frekans için no-op.
    """
    if aylik.empty or freq not in _KAPSAMA_GUNU:
        return aylik
    adim = pd.Timedelta(days=_KAPSAMA_GUNU[freq] - 1)
    tutulan = []
    for ay_basi in aylik.index:
        ay_sonu = ay_basi + pd.offsets.MonthEnd(0)
        bas_var = ((ham_indeks >= ay_basi) & (ham_indeks <= ay_basi + adim)).any()
        son_var = ((ham_indeks >= ay_sonu - adim) & (ham_indeks <= ay_sonu)).any()
        tutulan.append(bool(bas_var and son_var))
    return aylik[tutulan]


def aylige_cevir(
    df: pd.DataFrame, agg: str = "mean", freq: str = "monthly"
) -> pd.DataFrame:
    """Günlük/haftalık seriyi ay başlangıcına indirger.

    `sum` için boş aylar 0.0 değil NaN üretir (min_count=1), yoksa
    `.dropna()` onları temizleyemez. Ayrıca haftalık/günlük `sum`
    serilerinde KISMİ aylar (uçtaki ya da içteki) sahte bir düşüş gibi
    görünmemesi için atılır — aylık serilerde bu sorun yoktur.
    """
    if freq == "quarterly":
        raise ValueError("Çeyreklik veri aylık seriye dönüştürülemez")
    if agg not in _AGG_FONKSIYONLARI:
        raise ValueError(f"Bilinmeyen toplama: {agg}")
    if agg == "sum":
        seri = df["value"].resample("MS").sum(min_count=1)
    else:
        seri = df["value"].resample("MS").agg(_AGG_FONKSIYONLARI[agg])
    seri = seri.dropna().to_frame("value")

    if agg == "sum" and freq != "monthly":
        seri = kismi_aylari_dus(seri, df.index, freq)

    return seri


def _temayi_uygula(fig: go.Figure, birim: str) -> go.Figure:
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=RENKLER["metin_soluk"], size=12),
        margin=dict(l=8, r=8, t=8, b=8),
        height=280,
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            bgcolor="rgba(0,0,0,0)",
        ),
    )
    fig.update_xaxes(
        showgrid=False,
        linecolor=RENKLER["izgara"],
        tickfont=dict(color=RENKLER["metin_soluk"]),
    )
    fig.update_yaxes(
        gridcolor=RENKLER["izgara"],
        zeroline=False,
        title=dict(text=birim, font=dict(color=RENKLER["metin_soluk"], size=11)),
        tickfont=dict(color=RENKLER["metin_soluk"]),
    )
    return fig


def mevsimsellik_figuru(
    df: pd.DataFrame,
    birim: str,
    agg: str = "mean",
    freq: str = "monthly",
    yil_sayisi: int = 3,
) -> go.Figure:
    if yil_sayisi > len(RENKLER["seri"]):
        raise ValueError(
            f"yil_sayisi en fazla {len(RENKLER['seri'])} olabilir — palet o kadar "
            "seri için doğrulandı. Daha fazlası için theme.py'deki paletin yeniden "
            "doğrulanması gerekir."
        )
    aylik = aylige_cevir(df, agg, freq)
    fig = go.Figure()

    if aylik.empty:
        return _temayi_uygula(fig, birim)

    son_yil = int(aylik.index.year.max())
    ilk_yil = int(aylik.index.year.min())
    yillar = [y for y in range(son_yil, son_yil - yil_sayisi, -1) if y >= ilk_yil]

    for sira, yil in enumerate(yillar):
        alt = aylik[aylik.index.year == yil]
        if alt.empty:
            continue
        # Eksik ayı atlamak komşu ayları bağlar ve olmayan veriyi ima eder.
        alt = alt.asfreq("MS")
        fig.add_trace(
            go.Scatter(
                x=list(alt.index.month),
                y=list(alt["value"]),
                name=str(yil),
                mode="lines+markers",
                line=dict(color=RENKLER["seri"][sira], width=3 if sira == 0 else 2),
                marker=dict(size=8 if sira == 0 else 6),
                hovertemplate=f"{yil}: %{{y:,.2f}} {birim}<extra></extra>",
            )
        )

    fig.update_xaxes(
        tickmode="array",
        tickvals=list(range(1, 13)),
        ticktext=TR_AYLAR,
        range=[0.5, 12.5],
    )
    _temayi_uygula(fig, birim)
    fig.update_layout(showlegend=len(fig.data) >= 2)
    return fig


def hareketli_ortalama_uygula(
    df: pd.DataFrame, gun: int | None
) -> pd.DataFrame:
    """Ham veriyi değiştirmeden tam takvim penceresinin ortalamasını alır."""
    if gun is None or df.empty:
        return df
    return df.asfreq("D").rolling(f"{gun}D", min_periods=gun).mean()


def gunluk_mevsimsellik_figuru(
    df: pd.DataFrame, birim: str, yil_sayisi: int = 3
) -> go.Figure:
    """Ay/gün hizalı yıllar; 2000 referansı 29 Şubat'ı da korur."""
    if not 1 <= yil_sayisi <= len(RENKLER["seri"]):
        raise ValueError(f"yil_sayisi 1–{len(RENKLER['seri'])} arasında olmalı")
    fig = go.Figure()
    if df.empty:
        return _temayi_uygula(fig, birim)

    son_yil = int(df.index.year.max())
    for sira, yil in enumerate(range(son_yil, son_yil - yil_sayisi, -1)):
        alt = df[df.index.year == yil]
        if alt.empty:
            continue
        alt = alt.asfreq("D")
        fig.add_trace(
            go.Scatter(
                x=[tarih.replace(year=2000) for tarih in alt.index],
                y=list(alt["value"]),
                customdata=alt.index.strftime("%d.%m.%Y"),
                name=str(yil),
                mode="lines",
                connectgaps=False,
                line=dict(color=RENKLER["seri"][sira], width=3 if sira == 0 else 2),
                hovertemplate=f"%{{customdata}}: %{{y:,.2f}} {birim}<extra></extra>",
            )
        )

    fig.update_xaxes(
        tickmode="array",
        tickvals=pd.date_range("2000-01-01", periods=12, freq="MS"),
        ticktext=TR_AYLAR,
        range=[pd.Timestamp("2000-01-01"), pd.Timestamp("2000-12-31")],
    )
    _temayi_uygula(fig, birim)
    fig.update_layout(showlegend=len(fig.data) >= 2)
    return fig


def paylara_cevir(df: pd.DataFrame) -> pd.DataFrame:
    """Her satırı kendi toplamının yüzdesine çevirir.

    Payda yalnızca sütunlardaki üretim gruplarıdır; `importExport` zaten
    ingest tarafında dışlandığı için paylar %100'e toplanır. Toplamı sıfır
    olan satır NaN üretir — sessizce 0 pay göstermek, veri yokluğunu
    "hiç üretim yok"muş gibi gösterirdi.
    """
    toplam = df.sum(axis=1)
    return df.div(toplam.where(toplam != 0), axis=0) * 100


def kompozisyon_verisi_hazirla(
    df: pd.DataFrame, gorunum_mutlak: bool, freq: str
) -> pd.DataFrame:
    """Geniş (bileşenli) günlük/haftalık seriyi kart için aylığa indirger.

    Kısmi ayları (uçtaki ya da içteki) düşürme kuralı yalnızca MUTLAK
    (GWh) görünümde
    uygulanır: bu bir ÖLÇEK düzeltmesidir (kısmi ayın TOPLAMI sahte bir
    düşüş gösterir) — tıpkı `aylige_cevir`'in `agg == "sum"` durumunda
    yaptığı gibi. Pay % görünümü ölçekten BAĞIMSIZDIR: kısmi bir ayın
    kaynak karışımı tamamen geçerli bir gözlemdir, bu yüzden orada kural
    hiç uygulanmaz ve o ayın verisi korunur.

    `aylige_cevir` ile aynı gerekçeyle: `freq == "monthly"` ise kural yine
    uygulanmaz (kaynak zaten aylıksa "tamamlanmamış ay" kavramı yoktur).
    """
    aylik = df.resample("MS").sum(min_count=1).dropna(how="all")
    if gorunum_mutlak and freq != "monthly":
        aylik = kismi_aylari_dus(aylik, df.index, freq)
    return aylik if gorunum_mutlak else paylara_cevir(aylik)


def kompozisyon_figuru(df: pd.DataFrame, birim: str) -> go.Figure:
    """Grup başına bir çizgi.

    Renk ve çizgi deseni sütun ADINA göre seçilir (`RENKLER["kategorik"]`,
    `CIZGI_DESENLERI`) — pozisyona göre değil. Bilinmeyen bir sütun adı
    gelirse `KeyError` doğal olarak fırlar: katalogla palet ayrışmışsa bunu
    sessizce yutmak yerine görmemiz gerekir. Çizgi deseni, rengin tek başına
    ayıramadığı bazı grup çiftleri için ikincil (erişilebilirlik) kodlamadır.
    """
    fig = go.Figure()
    for sutun in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df[sutun],
                name=sutun,
                mode="lines",
                line={
                    "color": RENKLER["kategorik"][sutun],
                    "dash": CIZGI_DESENLERI[sutun],
                    "width": 2,
                },
                hovertemplate=f"{sutun}: %{{y:,.2f}} {birim}<extra></extra>",
            )
        )
    return _temayi_uygula(fig, birim)


def seviye_figuru(df: pd.DataFrame, birim: str, freq: str = "monthly") -> go.Figure:
    fig = go.Figure(
        go.Scatter(
            x=list(df.index),
            y=list(df["value"]),
            mode="lines",
            line=dict(color=RENKLER["seri"][0], width=2),
            hovertemplate=f"%{{y:,.2f}} {birim}<extra></extra>",
        )
    )
    _temayi_uygula(fig, birim)
    # Plotly'nin varsayılan ay adları İngilizce ("Jan 2022") — mevsimsellik
    # grafiği Türkçe ay adları kullanıyor, ikisi aynı kartta yan yana
    # duruyor. Sayısal biçim (01.2022) dilden bağımsız ve Türkçe tarih
    # yazımına uygun; plotly.js için Türkçe locale paketi gerekmiyor.
    fig.update_xaxes(tickformat="%m.%Y")
    if freq == "quarterly":
        fig.update_xaxes(dtick="M3", tickformat="%Y-Ç%q")
        fig.update_traces(
            customdata=[f"{tarih.year}-Ç{tarih.quarter}" for tarih in df.index],
            hovertemplate=f"%{{customdata}}<br>%{{y:,.2f}} {birim}<extra></extra>",
        )
    fig.update_layout(showlegend=False)
    return fig


def fon_donem_figuru(degerler: pd.Series, birim: str) -> go.Figure:
    """Fon dönem sonu stokları ve değişimleri için sıfır tabanlı çubuklar."""
    fig = go.Figure(go.Bar(
        x=list(degerler.index), y=list(degerler),
        marker_color=RENKLER["seri"][0],
        hovertemplate=f"%{{x|%d.%m.%Y}}<br>%{{y:,.2f}} {birim}<extra></extra>",
    ))
    _temayi_uygula(fig, birim)
    fig.update_xaxes(tickformat="%m.%Y")
    fig.update_yaxes(rangemode="tozero")
    return fig
