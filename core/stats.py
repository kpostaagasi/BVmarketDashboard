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
GORUNUMLER = (VARSAYILAN, YOY, MOM)


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
    if onceki is None or onceki == 0:
        return None
    # _asof, hedeften önce hiç nokta yoksa None döner; ama hedef ilk
    # noktadan sonraysa ve seri kısaysa aynı noktayı döndürebilir.
    if df.index.min() > hedef:
        return None
    return (son_deger(df) / onceki - 1) * 100


def mom(df: pd.DataFrame) -> float | None:
    return _degisim(df, pd.DateOffset(months=1))


def yoy(df: pd.DataFrame) -> float | None:
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
        yuzde = (df["value"].to_numpy() / np.where(onceki == 0, np.nan, onceki) - 1) * 100
    return pd.DataFrame({"value": yuzde}, index=df.index)


def seri_yoy(df: pd.DataFrame) -> pd.DataFrame:
    return _seri_degisim(df, pd.DateOffset(years=1))


def seri_mom(df: pd.DataFrame) -> pd.DataFrame:
    return _seri_degisim(df, pd.DateOffset(months=1))


def gorunum_uygula(df: pd.DataFrame, gorunum: str) -> pd.DataFrame:
    if gorunum == VARSAYILAN:
        return df
    if gorunum == YOY:
        return seri_yoy(df)
    if gorunum == MOM:
        return seri_mom(df)
    raise ValueError(f"Bilinmeyen görünüm: {gorunum}")
