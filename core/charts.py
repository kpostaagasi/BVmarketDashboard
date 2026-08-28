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


def son_ay_tamamlanmamissa_dus(
    aylik: pd.DataFrame, ham_son: pd.Timestamp
) -> pd.DataFrame:
    """Ay-başlangıcına indirgenmiş bir seride tamamlanmamış son ayı düşürür.

    Kural: ham verinin son tarihi, indirgenmiş son ayın son gününden ÖNCEYSE
    (`ham_son < aylik.index[-1] + MonthEnd(0)`) o ay henüz tamamlanmamıştır —
    düşürülür. Ayın 1'i (`aylik.index[-1]`) ile ayın son günü (`+ MonthEnd(0)`)
    farklı çapalardır; bu ikisini `ham_son`'la ters karşılaştırmak (ham_son'u
    ay-başlangıcıyla kıyaslamak) ay tamamlanmış olsa bile hemen hemen her
    zaman True verir — bu kural tek yerde uygulanır ki bir daha ayrışmasın.
    Boş `aylik` için no-op.
    """
    if aylik.empty:
        return aylik
    son_ay_sonu = aylik.index[-1] + pd.offsets.MonthEnd(0)
    if ham_son < son_ay_sonu:
        return aylik.iloc[:-1]
    return aylik


def aylige_cevir(
    df: pd.DataFrame, agg: str = "mean", freq: str = "monthly"
) -> pd.DataFrame:
    """Günlük/haftalık seriyi ay başlangıcına indirger.

    `sum` için boş aylar 0.0 değil NaN üretir (min_count=1), yoksa
    `.dropna()` onları temizleyemez. Ayrıca haftalık/günlük `sum`
    serilerinde henüz tamamlanmamış son ay, sahte bir düşüş gibi
    görünmemesi için atılır — aylık serilerde bu sorun yoktur.
    """
    if agg not in _AGG_FONKSIYONLARI:
        raise ValueError(f"Bilinmeyen toplama: {agg}")
    if agg == "sum":
        seri = df["value"].resample("MS").sum(min_count=1)
    else:
        seri = df["value"].resample("MS").agg(_AGG_FONKSIYONLARI[agg])
    seri = seri.dropna().to_frame("value")

    if agg == "sum" and freq != "monthly":
        seri = son_ay_tamamlanmamissa_dus(seri, df.index.max())

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


def paylara_cevir(df: pd.DataFrame) -> pd.DataFrame:
    """Her satırı kendi toplamının yüzdesine çevirir.

    Payda yalnızca sütunlardaki üretim gruplarıdır; `importExport` zaten
    ingest tarafında dışlandığı için paylar %100'e toplanır. Toplamı sıfır
    olan satır NaN üretir — sessizce 0 pay göstermek, veri yokluğunu
    "hiç üretim yok"muş gibi gösterirdi.
    """
    toplam = df.sum(axis=1)
    return df.div(toplam.where(toplam != 0), axis=0) * 100


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
            )
        )
    return _temayi_uygula(fig, birim)


def seviye_figuru(df: pd.DataFrame, birim: str) -> go.Figure:
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
    fig.update_layout(showlegend=False)
    return fig
