"""Veri raporu: ölçülmüş gözlemden cümle. Model yok, uydurma yok.

Eksik YoY/MoM cümleye girmez. Birimi yüzde olan seride yıllık değişim
puan farkıdır — %45→%40 "%11 düştü" yazılmaz.
"""

from __future__ import annotations

from core.catalog import Hisse
from core.ozet import OzetSatiri

UYARI = (
    "Bu metin katalogdaki serilerin son gözleminden üretilir. "
    "Model yorumu değildir. Alım-satım önerisi değildir."
)


def _tr(deger: float, basamak: int) -> str:
    tam, _, ondalik = f"{deger:,.{basamak}f}".partition(".")
    metin = f"{tam.replace(',', '.')},{ondalik}"
    return metin if basamak else metin.removesuffix(",")


def _tarih(satir: OzetSatiri) -> str:
    tarih = satir.son_tarih
    freq = satir.seri.freq
    if freq == "yearly":
        return str(tarih.year)
    if freq == "quarterly":
        return f"{tarih.year}-Ç{(tarih.month - 1) // 3 + 1}"
    if freq in {"daily", "weekly"}:
        return tarih.strftime("%Y-%m-%d")
    return tarih.strftime("%Y-%m")


def _degisim(deger: float, etiket: str, puan: bool = False) -> str:
    if round(deger, 2) == 0:
        return f"{etiket} değişmedi."
    yon = "arttı" if deger > 0 else "düştü"
    if puan:
        return f"{etiket} {_tr(abs(deger), 2)} puan {yon}."
    return f"{etiket} %{_tr(abs(deger), 1)} {yon}."


def gozlem_cumlesi(satir: OzetSatiri) -> str:
    seri = satir.seri
    deger = _tr(satir.son_deger, 0 if abs(satir.son_deger) >= 1000 or float(satir.son_deger).is_integer() else 2)
    parcalar = [f"{seri.title}: son gözlem {_tarih(satir)}, {deger} {seri.unit}."]
    if "%" in seri.unit:
        if satir.yoy_puan is not None:
            parcalar.append(_degisim(satir.yoy_puan, "Yıllık", puan=True))
    else:
        if satir.yoy is not None:
            parcalar.append(_degisim(satir.yoy, "Yıllık"))
        if satir.degisim is not None:
            etiket = "Çeyreklik" if seri.freq == "quarterly" else "Aylık"
            parcalar.append(_degisim(satir.degisim, etiket))
    parcalar.append("Veri güncel." if satir.guncel else "Veri güncel değil.")
    return " ".join(parcalar)


def _blok(baslik: str, satirlar: list[OzetSatiri]) -> list[str]:
    if not satirlar:
        return []
    return [baslik, *[gozlem_cumlesi(s) for s in satirlar]]


def hisse_raporu(
    hisse: Hisse,
    kendi: list[OzetSatiri],
    baglam: list[OzetSatiri],
    eksik: list[str] | None = None,
) -> str:
    blok = [f"{hisse.title} ({hisse.kod}) · {hisse.sektor}"]
    if hisse.note:
        blok.append(hisse.note.strip())
    if eksik:
        blok.append("Verisi yok: " + ", ".join(eksik) + ".")
    blok.extend(_blok("Şirketin kendi verisi", kendi))
    if baglam:
        blok.append("Aşağıdakiler şirkete ait değil; sektör ve girdi vekilidir.")
        blok.extend(gozlem_cumlesi(s) for s in baglam)
    if not kendi and not baglam and not eksik:
        blok.append("Gösterilecek gözlem yok.")
    blok.append(UYARI)
    return "\n\n".join(blok)


def piyasa_raporu(artan: list[OzetSatiri], dusen: list[OzetSatiri]) -> str:
    blok = [
        "Piyasa özeti",
        (
            "Aday küme: kategori panoları ve hisse sayfalarındaki şirket verileri. "
            "Birimi yüzde olan ve güncel olmayan seriler sıralamaya girmez."
        ),
    ]
    if not artan and not dusen:
        blok.append("Sıralamaya girecek güncel seri yok.")
    blok.extend(_blok("Yıllık en çok artan", artan))
    blok.extend(_blok("Yıllık en çok düşen", dusen))
    blok.append(UYARI)
    return "\n\n".join(blok)
