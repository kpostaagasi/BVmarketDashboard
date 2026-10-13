import dataclasses

import pandas as pd

from core.catalog import hisseleri_yukle, seri_getir
from core.ozet import OzetSatiri
from core.rapor import UYARI, gozlem_cumlesi, hisse_raporu, piyasa_raporu


def satir(**alanlar):
    seri = dataclasses.replace(
        seri_getir("enflasyon/tufe-genel"),
        title=alanlar.pop("title", "TÜFE"),
        unit=alanlar.pop("unit", "Endeks"),
        freq=alanlar.pop("freq", "monthly"),
    )
    return OzetSatiri(
        seri=seri,
        son_tarih=pd.Timestamp(alanlar.pop("tarih", "2026-08-01")),
        son_deger=alanlar.pop("son_deger", 110.0),
        yoy=alanlar.pop("yoy", 10.0),
        degisim=alanlar.pop("degisim", 1.5),
        guncel=alanlar.pop("guncel", True),
        yoy_puan=alanlar.pop("yoy_puan", None),
    )


def test_yoy_yoksa_uydurulmaz():
    metin = gozlem_cumlesi(satir(yoy=None, degisim=None))
    assert "Yıllık" not in metin
    assert "Aylık" not in metin


def test_yuzde_birimde_puan_yazar_yuzde_degil():
    metin = gozlem_cumlesi(satir(unit="%", yoy=-11.0, yoy_puan=-5.0, degisim=-11.0))
    assert "5,00 puan düştü" in metin
    assert "%11" not in metin
    assert "Önceki döneme göre" not in metin


def test_bayat_veri_soylenir():
    assert "Veri güncel değil." in gozlem_cumlesi(satir(guncel=False))


def test_hisse_raporu_uyari_ve_vekil_ayrimi():
    hisse = hisseleri_yukle()[0]
    metin = hisse_raporu(hisse, [satir(title="Üretim")], [satir(title="Kur")], ["Eksik seri"])
    assert metin.endswith(UYARI)
    assert "şirkete ait değil" in metin
    assert "Verisi yok: Eksik seri." in metin
    assert "Üretim:" in metin


def test_piyasa_raporu_bos_adayda_susmaz():
    metin = piyasa_raporu([], [])
    assert "Sıralamaya girecek güncel seri yok." in metin
    assert metin.endswith(UYARI)
