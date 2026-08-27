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


def test_kategori_sirasi():
    kategoriler = kategorileri_yukle()
    assert [k.slug for k in kategoriler] == [
        "ekonomi-makro",
        "emtia-enerji",
        "emtia-metaller",
        "enflasyon",
        "insaat",
        "kredi-karti",
    ]


def test_seri_sayisi():
    assert len(serileri_yukle()) == 23


def test_seri_alanlari_dogru_tiplerde():
    seri = seri_getir("enflasyon/tufe-genel")
    assert isinstance(seri, Seri)
    assert seri.title == "TÜFE Genel Endeks"
    assert seri.category == "enflasyon"
    assert seri.kaynak.name == "TCMB EVDS"
    assert seri.kaynak_tipi == "evds"
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
        assert seri.monthly_agg in {"mean", "last", "sum"}, seri.id
        assert seri.charts, seri.id
        assert set(seri.charts) <= {"seasonality", "level"}, seri.id
        if seri.kaynak_tipi == "evds":
            assert seri.evds_frequency in {"1", "2", "5"}, seri.id
            assert seri.evds_code, seri.id
        if seri.kaynak_tipi == "yahoo":
            assert seri.yahoo_symbol, seri.id


def _sluglar():
    return {k.slug for k in kategorileri_yukle()}


def test_her_serinin_kaynak_tipi_gecerli():
    for seri in serileri_yukle():
        assert seri.kaynak_tipi in {"evds", "yahoo"}, seri.id


def test_evds_serisi_sayisi_on_uc():
    # Göç kontrolü: 13 EVDS serisinin hepsi kaynak_tipi kazanmış olmalı.
    # Yahoo serileri Task 3'te ekleneceği için "hepsi evds" demiyoruz.
    assert sum(1 for s in serileri_yukle() if s.kaynak_tipi == "evds") == 13


def test_evds_serisinde_evds_code_zorunlu():
    seri = dataclasses.replace(seri_getir("enflasyon/tufe-genel"), evds_code=None)
    with pytest.raises(KatalogHatasi, match="evds_code"):
        _dogrula(seri, _sluglar(), set())


def test_evds_serisinde_gecersiz_frekans_reddedilir():
    seri = dataclasses.replace(seri_getir("enflasyon/tufe-genel"), evds_frequency="9")
    with pytest.raises(KatalogHatasi, match="evds_frequency"):
        _dogrula(seri, _sluglar(), set())


def test_yahoo_serisinde_yahoo_symbol_zorunlu():
    seri = dataclasses.replace(
        seri_getir("enflasyon/tufe-genel"),
        kaynak_tipi="yahoo",
        yahoo_symbol=None,
    )
    with pytest.raises(KatalogHatasi, match="yahoo_symbol"):
        _dogrula(seri, _sluglar(), set())


def test_yahoo_serisi_evds_code_gerektirmez():
    seri = dataclasses.replace(
        seri_getir("enflasyon/tufe-genel"),
        kaynak_tipi="yahoo",
        yahoo_symbol="BZ=F",
        evds_code=None,
        evds_frequency=None,
    )
    _dogrula(seri, _sluglar(), set())  # hata atmamalı


def test_bilinmeyen_kaynak_tipi_reddedilir():
    seri = dataclasses.replace(seri_getir("enflasyon/tufe-genel"), kaynak_tipi="bloomberg")
    with pytest.raises(KatalogHatasi, match="kaynak_tipi"):
        _dogrula(seri, _sluglar(), set())


def test_kategori_notu_okunur():
    kategoriler = {k.slug: k for k in kategorileri_yukle()}
    assert kategoriler["emtia-enerji"].note is not None
    assert "front-month" in kategoriler["emtia-enerji"].note
    assert kategoriler["enflasyon"].note is None
