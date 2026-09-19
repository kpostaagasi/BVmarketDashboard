"""Grafik kartlarındaki hazır istatistikler ve görünüm dönüşümleri.

Tüm fonksiyonlar DatetimeIndex'li, tek `value` sütunlu DataFrame alır.
Değişim hesapları konumsal kaydırma (`shift`) değil tarih tabanlı `asof`
mantığı kullanır: aylık, haftalık ve günlük seriler aynı kodla doğru
sonuç verir.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

VARSAYILAN = "Varsayılan"
YOY = "YoY %"
MOM = "MoM %"
CEYREKLIK = "Çeyreklik"
GORUNUMLER = (VARSAYILAN, YOY, MOM, CEYREKLIK)


def son_tarih(df: pd.DataFrame) -> pd.Timestamp:
    return df.index.max()


def son_deger(df: pd.DataFrame) -> float:
    return float(df.loc[son_tarih(df), "value"])


def _asof(df: pd.DataFrame, hedef: pd.Timestamp) -> float | None:
    """`hedef` tarihinde ya da ondan önceki en son değer."""
    uygun = df.index[df.index <= hedef]
    if len(uygun) == 0:
        return None
    return float(df.loc[uygun.max(), "value"])


def _degisim(df: pd.DataFrame, offset: pd.DateOffset) -> float | None:
    if df.empty:
        return None
    simdi = son_tarih(df)
    hedef = simdi - offset
    onceki = _asof(df, hedef)
    if onceki is None or onceki <= 0:
        return None
    # _asof, hedeften önce hiç nokta yoksa None döner; ama hedef ilk
    # noktadan sonraysa ve seri kısaysa aynı noktayı döndürebilir.
    if df.index.min() > hedef:
        return None
    return (son_deger(df) / onceki - 1) * 100


def mom(df: pd.DataFrame) -> float | None:
    return _degisim(df, pd.DateOffset(months=1))


def yoy(df: pd.DataFrame, freq: str = "monthly") -> float | None:
    if freq == "quarterly":
        return _son_ceyrek_degisim(df, 4)
    return _degisim(df, pd.DateOffset(years=1))


def aralik_12a(df: pd.DataFrame) -> tuple[float, float] | None:
    if df.empty:
        return None
    pencere = df[df.index > son_tarih(df) - pd.DateOffset(months=12)]
    if len(pencere) < 2:
        return None
    return (float(pencere["value"].min()), float(pencere["value"].max()))


def _onceki_degerler(df: pd.DataFrame, offset: pd.DateOffset) -> np.ndarray:
    """Her nokta için `offset` kadar önceki (ya da ondan önceki en son) değer."""
    hedefler = df.index - offset
    konum = df.index.searchsorted(hedefler, side="right") - 1
    degerler = df["value"].to_numpy()
    sonuc = np.where(konum >= 0, degerler[konum.clip(min=0)], np.nan)
    # Hedef, serinin ilk noktasından öndeyse karşılaştırma yapılamaz.
    return np.where(hedefler < df.index.min(), np.nan, sonuc)


def _seri_degisim(df: pd.DataFrame, offset: pd.DateOffset) -> pd.DataFrame:
    onceki = _onceki_degerler(df, offset)
    with np.errstate(divide="ignore", invalid="ignore"):
        yuzde = (df["value"].to_numpy() / np.where(onceki <= 0, np.nan, onceki) - 1) * 100
    return pd.DataFrame({"value": yuzde}, index=df.index)


def _seri_ceyrek_degisim(df: pd.DataFrame, donem: int) -> pd.DataFrame:
    ceyrekler = df.index.to_period("Q")
    degerler = pd.Series(df["value"].to_numpy(), index=ceyrekler)
    onceki = degerler.reindex(ceyrekler - donem).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        yuzde = (df["value"].to_numpy() / np.where(onceki <= 0, np.nan, onceki) - 1) * 100
    return pd.DataFrame({"value": yuzde}, index=df.index)


def _son_ceyrek_degisim(df: pd.DataFrame, donem: int) -> float | None:
    if df.empty:
        return None
    deger = _seri_ceyrek_degisim(df, donem).loc[son_tarih(df), "value"]
    return None if pd.isna(deger) else float(deger)


def qoq(df: pd.DataFrame) -> float | None:
    """Önceki takvim çeyreği eksikse daha eski gözleme geri düşmez."""
    return _son_ceyrek_degisim(df, 1)


def seri_yoy(df: pd.DataFrame) -> pd.DataFrame:
    return _seri_degisim(df, pd.DateOffset(years=1))


def seri_mom(df: pd.DataFrame) -> pd.DataFrame:
    return _seri_degisim(df, pd.DateOffset(months=1))


def ceyreklige_cevir(df: pd.DataFrame, agg: str = "mean") -> pd.DataFrame:
    """Seriyi çeyreklik toplulaştırır; her nokta çeyreğin İLK ayına damgalanır.

    Referans panolardaki "Çeyreksel - X" kartları ayrı bir seri değil, aynı
    serinin çeyreklik görünümüdür. `agg` serinin `monthly_agg`ıyla aynı
    anlamda: stok serisi "last", akım serisi "sum", oran/endeks "mean".

    Son çeyrek HENÜZ BİTMEMİŞSE düşürülür: eksik aylarla toplanan bir "sum"
    çeyreği olduğundan küçük görünür ve sahte bir düşüş çizer.
    """
    if df.empty:
        return df
    donem = df.index.to_period("Q")
    gruplu = df.groupby(donem)["value"]
    deger = {"sum": gruplu.sum(), "last": gruplu.last()}.get(agg, gruplu.mean())
    son_gozlem = df.index.max().to_period("M")
    tam = deger[[d.end_time.to_period("M") <= son_gozlem for d in deger.index]]
    return pd.DataFrame(
        {"value": tam.to_numpy()},
        index=pd.PeriodIndex(tam.index, freq="Q").to_timestamp(how="start"),
    )


def gorunum_uygula(
    df: pd.DataFrame, gorunum: str, freq: str = "monthly", agg: str = "mean"
) -> pd.DataFrame:
    if gorunum == VARSAYILAN:
        return df
    if gorunum == YOY:
        if freq == "quarterly":
            return _seri_ceyrek_degisim(df, 4)
        return seri_yoy(df)
    if gorunum == MOM:
        if freq == "quarterly":
            return _seri_ceyrek_degisim(df, 1)
        if freq == "yearly":
            # Yıllık seride aylık değişim TANIMSIZ. `_onceki_degerler` bir ay
            # geriye bakıp en yakın eski noktayı bulduğu için sessizce bir
            # önceki YILI döndürür, yani MoM görünümü YoY ile aynı sayıyı
            # gösterir — yanıltıcı. Boş seri döndürmek dürüst davranış.
            return pd.DataFrame({"value": np.nan}, index=df.index)
        return seri_mom(df)
    if gorunum == CEYREKLIK:
        # Zaten çeyreklik/yıllık seride toplulaştırmanın anlamı yok.
        if freq in {"quarterly", "yearly"}:
            return df
        return ceyreklige_cevir(df, agg)
    raise ValueError(f"Bilinmeyen görünüm: {gorunum}")
