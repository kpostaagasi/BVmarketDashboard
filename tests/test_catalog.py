import dataclasses

import pytest

from core.catalog import (
    KatalogHatasi,
    Seri,
    _dogrula,
    kategorileri_yukle,
    seri_getir,
    seri_listele,
    serileri_yukle,
)


def test_dort_kategori_yuklenir():
    kategoriler = kategorileri_yukle()
    assert [k.slug for k in kategoriler] == [
        "ekonomi-makro",
        "enflasyon",
        "insaat",
        "kredi-karti",
    ]


def test_onuc_seri_yuklenir():
    assert len(serileri_yukle()) == 13


def test_seri_alanlari_dogru_tiplerde():
    seri = seri_getir("enflasyon/tufe-genel")
    assert isinstance(seri, Seri)
    assert seri.title == "TÜFE Genel Endeks"
    assert seri.category == "enflasyon"
    assert seri.kaynak.name == "TCMB EVDS"
    assert seri.evds_code == "TP.TUKFIY2025.GENEL"
    assert seri.evds_frequency == "5"
    assert seri.charts == ("seasonality", "level")
    assert seri.monthly_agg == "mean"
    assert seri.start_date is None


def test_kategoriye_gore_filtreleme():
    idler = [s.id for s in seri_listele("insaat")]
    assert idler == [
        "insaat/konut-fiyat-endeksi",
        "insaat/konut-satis-toplam",
        "insaat/konut-satis-ipotekli",
    ]


def test_bilinmeyen_seri_hata_verir():
    with pytest.raises(KatalogHatasi):
        seri_getir("yok/boyle-bir-seri")


def test_her_seri_id_si_kendi_kategorisiyle_baslar():
    for seri in serileri_yukle():
        assert seri.id.startswith(f"{seri.category}/"), seri.id


def test_her_seri_bilinen_bir_kategoriye_ait():
    sluglar = {k.slug for k in kategorileri_yukle()}
    for seri in serileri_yukle():
        assert seri.category in sluglar, seri.id


def test_idler_tekil():
    idler = [s.id for s in serileri_yukle()]
    assert len(idler) == len(set(idler))


def test_charts_listesinde_tekrar_reddedilir():
    seri = dataclasses.replace(
        seri_getir("enflasyon/tufe-genel"), charts=("level", "level")
    )
    sluglar = {k.slug for k in kategorileri_yukle()}
    with pytest.raises(KatalogHatasi, match="tekrar"):
        _dogrula(seri, sluglar, set())


def test_alan_degerleri_gecerli_kumelerde():
    for seri in serileri_yukle():
        assert seri.freq in {"daily", "weekly", "monthly"}, seri.id
        assert seri.evds_frequency in {"1", "2", "5"}, seri.id
        assert seri.monthly_agg in {"mean", "last", "sum"}, seri.id
        assert seri.charts, seri.id
        assert set(seri.charts) <= {"seasonality", "level"}, seri.id
        assert seri.evds_code, seri.id
