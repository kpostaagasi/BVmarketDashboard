"""Veri Takvimi: serilerin tazelik durumu.

Saf hesaplama — bu modül doğrudan Streamlit import etmez. Sayfa render'ı
core/page.py'dedir.

Tazelik, dönem etiketinden değil DÖNEM SONUNDAN ölçülür (bkz. `donem_sonu`).

Eşikler SEZGİSELDİR: bir periyot artı tipik yayın gecikmesi. Tek yerde
tutulurlar ki gürültü görüldüğünde ayarlanabilsinler. Seri bazında geçersiz
kılma bilinçli olarak eklenmedi — hangi serinin gürültü çıkaracağı henüz
bilinmiyor.

Bu sayfanın asıl işi ileriye bakan bir yayın takvimi değil, geriye bakan bir
tazelik monitörü olmaktır: bir seri geciktiğinde ya kaynak geç kalmıştır ya da
bizim ingest'imiz sessizce kırılmıştır. İkincisi başka hiçbir yerde görünmez.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from core.catalog import SIKLIK_ETIKETLERI, Seri, seri_listele
from core.data import VeriYokHatasi, seri_csv_oku, seri_yolu

ESIKLER = {"daily": 5, "weekly": 14, "monthly": 50}

GUNCEL = "güncel"
BEKLENIYOR = "bekleniyor"
GECIKMIS = "gecikmiş"
VERI_YOK = "veri yok"
OKUNAMADI = "okunamadı"

# Sıralama ciddiyeti: okunamayan dosya, hiç olmayan dosyadan da gürültülüdür.
_CIDDIYET = {OKUNAMADI: 0, VERI_YOK: 1, GECIKMIS: 2, BEKLENIYOR: 3, GUNCEL: 4}


@dataclass(frozen=True)
class TakvimSatiri:
    seri: Seri
    son_donem: date | None
    bekleme_gunu: int | None
    durum: str


def donem_sonu(etiket: date, freq: str) -> date:
    """Dönem etiketini, o dönemin bittiği güne çevirir.

    Etiket bir aralığın adıdır, anı değil: aylık seride `2026-07-01` "temmuz
    ayı" demektir, "1 temmuz" değil. Tazeliği etiketten ölçmek aylık serilere
    bir aylık sahte gecikme ekliyordu.
    """
    if freq == "monthly":
        return etiket.replace(day=monthrange(etiket.year, etiket.month)[1])
    if freq == "weekly":
        return etiket + timedelta(days=6)
    return etiket


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
    # Dönem henüz bitmediyse fark negatif olur; bitmemiş dönem tanımı gereği güncel.
    bekleme = max((bugun - donem_sonu(son_donem, seri.freq)).days, 0)
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


SUTUNLAR = [
    "Veri",
    "Kategori",
    "Son Dönem",
    "Durum",
    "Sıklık",
    "Kaynak",
    "Yayın notu",
]


def tablo_df(satirlar: list[TakvimSatiri]) -> pd.DataFrame:
    kayitlar = [
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
    return pd.DataFrame(kayitlar, columns=SUTUNLAR)


def takvim(bugun: date | None = None) -> list[TakvimSatiri]:
    """Katalogdaki her seri için satır üretir. Tek I/O yapan fonksiyon."""
    bugun = bugun or date.today()
    satirlar = []
    for seri in seri_listele():
        try:
            df = seri_csv_oku(seri_yolu(seri.id))
            son = df.index.max().date()
        except VeriYokHatasi:
            satirlar.append(satir_uret(seri, None, bugun))
            continue
        except Exception:  # noqa: BLE001 — bozuk CSV bir satırı düşürür, sayfayı değil
            satirlar.append(
                TakvimSatiri(
                    seri=seri, son_donem=None, bekleme_gunu=None, durum=OKUNAMADI
                )
            )
            continue
        satirlar.append(satir_uret(seri, son, bugun))
    return sirala(satirlar)
