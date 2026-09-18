"""Veri Takvimi: serilerin tazelik durumu.

Saf hesaplama — bu modül doğrudan Streamlit import etmez. Sayfa render'ı
core/page.py'dedir.

Tazelik, dönem etiketinden değil DÖNEM SONUNDAN ölçülür (bkz. `donem_sonu`).

Eşikler SEZGİSELDİR: bir periyot artı tipik yayın gecikmesi. Tek yerde
tutulurlar ki gürültü görüldüğünde ayarlanabilsinler. Faz 3f'te seri bazında
geçersiz kılma eklendi (`Seri.gecikme_gunu`): hangi serinin gürültü çıkardığı
artık biliniyor. TÜİK sanayi üretim endeksi ve TCMB ödemeler dengesi dönem
sonundan ~42 gün sonra yayımlanıyor, yani aylık eşiğin (50) altında hiç
kalmıyorlar ve kalıcı sahte alarm üretiyorlardı — kalıcı alarm, "kırmızı satır
bir şeyin bozulduğu anlamına gelir" sözleşmesini yok eder. `gecikme_gunu` o
serinin eşiğine eklenir; kaynağın normal takvimi kadar sabır tanınır.

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
from core.data import VeriYokHatasi, genis_csv_oku, seri_csv_oku, seri_yolu

ESIKLER = {"daily": 5, "weekly": 14, "monthly": 50, "quarterly": 120, "yearly": 430}

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
    if freq == "yearly":
        return etiket.replace(month=12, day=31)
    if freq == "quarterly":
        ay = (etiket.month - 1) // 3 * 3 + 3
        return etiket.replace(month=ay, day=monthrange(etiket.year, ay)[1])
    if freq == "monthly":
        return etiket.replace(day=monthrange(etiket.year, etiket.month)[1])
    if freq == "weekly":
        return etiket + timedelta(days=6)
    return etiket


def durum_hesapla(freq: str, bekleme_gunu: int, gecikme_gunu: int = 0) -> str:
    esik = ESIKLER[freq] + gecikme_gunu
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
        durum=durum_hesapla(seri.freq, bekleme, seri.gecikme_gunu or 0),
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
            "Son Dönem": (
                "—" if s.son_donem is None else
                f"{s.son_donem.year}-Ç{(s.son_donem.month - 1) // 3 + 1}"
                if s.seri.freq == "quarterly" else s.son_donem.isoformat()
            ),
            "Durum": _durum_metni(s),
            "Sıklık": SIKLIK_ETIKETLERI[s.seri.freq],
            "Kaynak": s.seri.kaynak.name,
            "Yayın notu": s.seri.yayin_notu or "",
        }
        for s in satirlar
    ]
    return pd.DataFrame(kayitlar, columns=SUTUNLAR)


def _seriyi_oku(seri: Seri) -> pd.DataFrame:
    """Biçime göre doğru okuyucuyu seçer; hataları yukarı bırakır.

    Kompozisyon serilerinde `value` sütunu yoktur ve `seri_csv_oku`
    gövdesindeki `df[["value"]]` KeyError fırlatır. Hata yakalama
    `takvim()` içinde kalır: VERI_YOK ile OKUNAMADI ayrımı oraya aittir.
    """
    if seri.epias_bilesenler or "fon" in seri.charts:
        return genis_csv_oku(seri_yolu(seri.id))
    return seri_csv_oku(seri_yolu(seri.id))


def takvim(bugun: date | None = None,
           kategori: str | None = None) -> list[TakvimSatiri]:
    """Katalogdaki her seri için satır üretir. Tek I/O yapan fonksiyon."""
    bugun = bugun or date.today()
    seriler = seri_listele(kategori)
    satirlar = []
    for seri in seriler:
        try:
            df = _seriyi_oku(seri)
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
