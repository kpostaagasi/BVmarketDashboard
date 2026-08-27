"""Veri Takvimi: serilerin tazelik durumu.

Saf hesaplama — bu modül doğrudan Streamlit import etmez. Sayfa render'ı
core/page.py'dedir.

Eşikler SEZGİSELDİR: bir periyot artı tipik yayın gecikmesi. Tek yerde
tutulurlar ki gürültü görüldüğünde ayarlanabilsinler. Seri bazında geçersiz
kılma bilinçli olarak eklenmedi — hangi serinin gürültü çıkaracağı henüz
bilinmiyor.

Bu sayfanın asıl işi ileriye bakan bir yayın takvimi değil, geriye bakan bir
tazelik monitörü olmaktır: bir seri geciktiğinde ya kaynak geç kalmıştır ya da
bizim ingest'imiz sessizce kırılmıştır. İkincisi başka hiçbir yerde görünmez.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from core.catalog import SIKLIK_ETIKETLERI, Seri, seri_listele
from core.data import VeriYokHatasi, seri_csv_oku, seri_yolu

ESIKLER = {"daily": 5, "weekly": 14, "monthly": 50}

GUNCEL = "güncel"
BEKLENIYOR = "bekleniyor"
GECIKMIS = "gecikmiş"
VERI_YOK = "veri yok"

# Sıralama ciddiyeti: verisi hiç olmayan en gürültülü sorundur.
_CIDDIYET = {VERI_YOK: 0, GECIKMIS: 1, BEKLENIYOR: 2, GUNCEL: 3}


@dataclass(frozen=True)
class TakvimSatiri:
    seri: Seri
    son_donem: date | None
    bekleme_gunu: int | None
    durum: str


def durum_hesapla(freq: str, bekleme_gunu: int) -> str:
    esik = ESIKLER[freq]
    if bekleme_gunu <= esik:
        return GUNCEL
    if bekleme_gunu <= esik * 2:
        return BEKLENIYOR
    return GECIKMIS


def satir_uret(seri: Seri, son_donem: date | None, bugun: date) -> TakvimSatiri:
    """Veriyi parametre alır — I/O yapmaz, bu yüzden dosyasız test edilebilir."""
    if son_donem is None:
        return TakvimSatiri(
            seri=seri, son_donem=None, bekleme_gunu=None, durum=VERI_YOK
        )
    bekleme = (bugun - son_donem).days
    return TakvimSatiri(
        seri=seri,
        son_donem=son_donem,
        bekleme_gunu=bekleme,
        durum=durum_hesapla(seri.freq, bekleme),
    )


def sirala(satirlar: list[TakvimSatiri]) -> list[TakvimSatiri]:
    """Önce durum ciddiyeti, sonra bekleme süresi azalan."""
    return sorted(
        satirlar,
        key=lambda s: (_CIDDIYET[s.durum], -(s.bekleme_gunu or 0)),
    )


def _durum_metni(satir: TakvimSatiri) -> str:
    if satir.bekleme_gunu is None:
        return satir.durum
    if satir.durum == GUNCEL:
        return satir.durum
    return f"{satir.durum} ({satir.bekleme_gunu} gün)"


def tablo_df(satirlar: list[TakvimSatiri]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Veri": s.seri.title,
                "Kategori": s.seri.category,
                "Son Dönem": "—" if s.son_donem is None else s.son_donem.isoformat(),
                "Durum": _durum_metni(s),
                "Sıklık": SIKLIK_ETIKETLERI[s.seri.freq],
                "Kaynak": s.seri.kaynak.name,
                "Yayın notu": s.seri.yayin_notu or "",
            }
            for s in satirlar
        ]
    )


def takvim(bugun: date | None = None) -> list[TakvimSatiri]:
    """Katalogdaki her seri için satır üretir. Tek I/O yapan fonksiyon."""
    bugun = bugun or date.today()
    satirlar = []
    for seri in seri_listele():
        try:
            df = seri_csv_oku(seri_yolu(seri.id))
            son = df.index.max().date()
        except VeriYokHatasi:
            son = None
        satirlar.append(satir_uret(seri, son, bugun))
    return sirala(satirlar)
