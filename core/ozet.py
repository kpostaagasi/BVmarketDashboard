"""Ana sayfa özeti: öne çıkan hareketler ve son yayımlanan veriler.

Saf hesaplama — `core/takvim.py` gibi Streamlit import etmez; render
`core/page.py::genel_bakis_yap` içindedir. Veri parametre olarak gelir,
bu yüzden dosyasız test edilir.

Aday küme bilinçli olarak dardır: kategori panoları + hisse sayfalarının
"kendi" serileri (~200 seri). 3.700 serinin tamamı (976 fon, 1.400 il/ülke
× sektör kırılımı) sıralamayı küçük tabanlı kırılımların %900'lük
sıçramalarıyla doldururdu — "dikkat çeken" değil gürültü olurdu.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from core.catalog import Seri
from core.stats import mom, qoq, son_deger, son_tarih, yoy
from core.takvim import GUNCEL, donem_sonu, satir_uret


@dataclass(frozen=True)
class OzetSatiri:
    seri: Seri
    son_tarih: pd.Timestamp
    son_deger: float
    yoy: float | None
    degisim: float | None  # aylık seride MoM, çeyreklikte QoQ
    guncel: bool
    # Birimi yüzde olan seride yıllık PUAN farkı; diğerlerinde None.
    # %45→%40 "%11 düştü" değil "5 puan düştü" diye gösterilmeli.
    yoy_puan: float | None = None


def ozet_uret(seri: Seri, df: pd.DataFrame, bugun: date) -> OzetSatiri | None:
    """Boş seri için None — özet satırı uydurulmaz."""
    if df.empty:
        return None
    son = son_tarih(df)
    yoy_puan = None
    if "%" in seri.unit:
        onceki = df["value"][: son - pd.DateOffset(years=1)]
        if not onceki.empty:
            yoy_puan = float(df["value"].iloc[-1] - onceki.iloc[-1])
    return OzetSatiri(
        seri=seri,
        son_tarih=son,
        son_deger=son_deger(df),
        yoy=yoy(df, seri.freq),
        degisim=qoq(df) if seri.freq == "quarterly" else mom(df),
        guncel=satir_uret(seri, son.date(), bugun).durum == GUNCEL,
        yoy_puan=yoy_puan,
    )


def _siralanabilir(satir: OzetSatiri) -> bool:
    """Yıllık % değişim sıralamasına girebilir mi?

    Birimi zaten yüzde olan seriler (faiz, işsizlik, oranlar) dışarıda:
    %45'ten %40'a inen faiz "-%11" diye listelenirse okuyucu bunu 11 puan
    sanır. Bayat seriler de dışarıda — "dikkat çeken" bugünün haberidir.
    """
    return satir.guncel and satir.yoy is not None and "%" not in satir.seri.unit


def one_cikanlar(
    satirlar: list[OzetSatiri], adet: int = 6
) -> tuple[list[OzetSatiri], list[OzetSatiri]]:
    """(yıllık en çok artan, yıllık en çok düşen) — her biri en çok `adet`.

    Artan listesinde yalnızca pozitif, düşende yalnızca negatif YoY olur;
    düşen seri azsa liste kısa kalır, pozitif seriyle doldurulmaz.
    """
    adaylar = [s for s in satirlar if _siralanabilir(s)]
    artan = sorted(
        (s for s in adaylar if s.yoy > 0), key=lambda s: s.yoy, reverse=True
    )
    dusen = sorted((s for s in adaylar if s.yoy < 0), key=lambda s: s.yoy)
    return artan[:adet], dusen[:adet]


def son_yayimlananlar(satirlar: list[OzetSatiri], adet: int = 8) -> list[OzetSatiri]:
    """Aylık ve daha seyrek serilerde dönem sonu en yeni olanlar.

    Günlük ve haftalık seriler her gün/hafta "yeni" olduğu için listeyi
    tek başına doldururdu; bu liste ayda bir gelen makro yayınları
    (TÜFE, sanayi üretimi, dış ticaret) öne çıkarmak içindir. Sıralama
    dönem ETİKETİNE değil dönem SONUNA göredir (bkz. `takvim.donem_sonu`):
    2026-Ç2 etiketi 1 Nisan'dır ama çeyrek 30 Haziran'da biter.
    Eşitlikte başlık sırası kararlılık sağlar.
    """
    adaylar = [s for s in satirlar if s.seri.freq not in {"daily", "weekly"}]
    return sorted(
        adaylar,
        key=lambda s: (
            -pd.Timestamp(donem_sonu(s.son_tarih.date(), s.seri.freq)).value,
            s.seri.title,
        ),
    )[:adet]
