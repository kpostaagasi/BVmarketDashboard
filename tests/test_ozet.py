import dataclasses
from datetime import date

import pandas as pd
import pytest

from core.catalog import seri_getir
from core.ozet import OzetSatiri, one_cikanlar, ozet_uret, son_yayimlananlar

BUGUN = date(2026, 9, 23)


def seri(seri_id="enflasyon/tufe-genel", **alanlar):
    return dataclasses.replace(seri_getir(seri_id), **alanlar)


def aylik(degerler, bitis="2026-08-01"):
    indeks = pd.date_range(end=bitis, periods=len(degerler), freq="MS")
    return pd.DataFrame({"value": degerler}, index=indeks)


def satir(baslik, yoy, guncel=True, birim="Endeks", freq="monthly",
          tarih="2026-08-01"):
    return OzetSatiri(
        seri=seri(title=baslik, unit=birim, freq=freq),
        son_tarih=pd.Timestamp(tarih), son_deger=1.0, yoy=yoy,
        degisim=None, guncel=guncel,
    )


def test_ozet_bos_seride_none_doner():
    assert ozet_uret(seri(), aylik([]), BUGUN) is None


def test_ozet_yoy_ve_mom_hesaplar():
    ozet = ozet_uret(seri(), aylik([100.0] * 12 + [110.0]), BUGUN)
    assert ozet.yoy == pytest.approx(10.0)
    assert ozet.degisim == pytest.approx(10.0)
    assert ozet.son_deger == 110.0


def test_ozet_guncelligi_takvim_esigini_kullanir():
    assert ozet_uret(seri(), aylik([1.0, 2.0]), BUGUN).guncel
    bayat = aylik([1.0, 2.0], bitis="2026-01-01")
    assert not ozet_uret(seri(), bayat, BUGUN).guncel


def test_yuzde_biriminde_yillik_puan_farki():
    ozet = ozet_uret(seri(unit="%"), aylik([45.0] * 12 + [40.0]), BUGUN)
    assert ozet.yoy_puan == pytest.approx(-5.0)


def test_yuzde_olmayan_birimde_puan_farki_yok():
    assert ozet_uret(seri(), aylik([1.0] * 13), BUGUN).yoy_puan is None


def test_one_cikanlar_artan_ve_duseni_ayirir_ve_siralar():
    satirlar = [satir("a", 5.0), satir("b", 50.0), satir("c", -3.0),
                satir("d", -30.0)]
    artan, dusen = one_cikanlar(satirlar)
    assert [s.seri.title for s in artan] == ["b", "a"]
    assert [s.seri.title for s in dusen] == ["d", "c"]


def test_one_cikanlar_yuzde_birimli_seriyi_dislar():
    artan, _ = one_cikanlar([satir("faiz", 80.0, birim="%")])
    assert artan == []


def test_one_cikanlar_bayat_seriyi_dislar():
    artan, _ = one_cikanlar([satir("eski", 80.0, guncel=False)])
    assert artan == []


def test_one_cikanlar_adet_sinirina_uyar():
    artan, _ = one_cikanlar([satir(str(i), float(i + 1)) for i in range(10)], adet=3)
    assert len(artan) == 3


def test_son_yayimlananlar_gunluk_ve_haftaligi_dislar():
    satirlar = [satir("g", 1.0, freq="daily", tarih="2026-09-22"),
                satir("h", 1.0, freq="weekly", tarih="2026-09-14"),
                satir("a", 1.0)]
    assert [s.seri.title for s in son_yayimlananlar(satirlar)] == ["a"]


def test_son_yayimlananlar_donem_sonuna_gore_siralar():
    # Ç2 etiketi 2026-04-01 ama 30 Haziran'da biter; Mayıs aylığından yeni.
    satirlar = [satir("mayis", 1.0, tarih="2026-05-01"),
                satir("c2", 1.0, freq="quarterly", tarih="2026-04-01")]
    assert [s.seri.title for s in son_yayimlananlar(satirlar)] == ["c2", "mayis"]
