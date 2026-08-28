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
        "elektrik",
    ]


def test_seri_sayisi():
    assert len(serileri_yukle()) == 25


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
        assert seri.kaynak_tipi in {"evds", "yahoo", "epias"}, seri.id


def test_evds_serilerinin_hepsi_evds_koduna_sahip():
    evds_seriler = [s for s in serileri_yukle() if s.kaynak_tipi == "evds"]
    assert evds_seriler, "en az bir EVDS serisi olmalı"
    assert all(s.evds_code for s in evds_seriler)


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


def test_yahoo_serisi_start_date_reddedilir():
    seri = dataclasses.replace(
        seri_getir("emtia-enerji/brent"), start_date="2020-01-01"
    )
    with pytest.raises(KatalogHatasi, match="start_date"):
        _dogrula(seri, _sluglar(), set())


def test_evds_serisi_yahoo_symbol_tasiyamaz():
    seri = dataclasses.replace(
        seri_getir("enflasyon/tufe-genel"), yahoo_symbol="BZ=F"
    )
    with pytest.raises(KatalogHatasi, match="yahoo_symbol"):
        _dogrula(seri, _sluglar(), set())


def test_yahoo_serisi_evds_alani_tasiyamaz():
    seri = dataclasses.replace(
        seri_getir("emtia-enerji/brent"), evds_code="TP.XXX"
    )
    with pytest.raises(KatalogHatasi, match="evds alanları"):
        _dogrula(seri, _sluglar(), set())


def test_bilinmeyen_kaynak_tipi_reddedilir():
    seri = dataclasses.replace(seri_getir("enflasyon/tufe-genel"), kaynak_tipi="bloomberg")
    with pytest.raises(KatalogHatasi, match="kaynak_tipi"):
        _dogrula(seri, _sluglar(), set())


def test_metaller_kpi_sirasi():
    ilk_dort = [s.id for s in seri_listele("emtia-metaller")][:4]
    assert ilk_dort == [
        "emtia-metaller/altin",
        "emtia-metaller/gumus",
        "emtia-metaller/bakir",
        "emtia-metaller/hrc-celik",
    ]


def test_kategori_notu_okunur():
    kategoriler = {k.slug: k for k in kategorileri_yukle()}
    # Her iki emtia kategorisi de sürekli ön vade uyarısını taşımalı
    for slug in ("emtia-enerji", "emtia-metaller"):
        assert kategoriler[slug].note, slug
        assert "front-month" in kategoriler[slug].note, slug
    assert kategoriler["enflasyon"].note is None


def test_yayin_notu_varsayilan_none():
    assert seri_getir("enflasyon/tufe-genel").yayin_notu is None


def test_siklik_etiketleri_tum_frekanslari_kapsar():
    from core.catalog import GECERLI_FREKANSLAR, SIKLIK_ETIKETLERI

    assert set(SIKLIK_ETIKETLERI) == GECERLI_FREKANSLAR


def test_kategori_pano_alani_tuple_olarak_okunur(tmp_path, monkeypatch):
    # NOT: kategorileri_yukle() @lru_cache'li; dosyadaki önceki testler onu
    # gerçek katalogla doldurmuş oluyor. cache_clear() olmadan bu test
    # gerçek 6 kategoriyi görür ve (kategori,) unpacking'i ValueError verir.
    # Test sonunda da cache'i temizliyoruz ki KATALOG_DIZINI monkeypatch'i
    # geri alındığında sonraki testler yine gerçek katalog verisini görsün.
    from core import catalog

    (tmp_path / "categories.yaml").write_text(
        "- slug: elektrik\n"
        "  title: Elektrik\n"
        "  pano: [elektrik/uretim, elektrik/ptf]\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(catalog, "KATALOG_DIZINI", tmp_path)
    catalog.kategorileri_yukle.cache_clear()
    try:
        (kategori,) = catalog.kategorileri_yukle()
        assert kategori.pano == ("elektrik/uretim", "elektrik/ptf")
    finally:
        catalog.kategorileri_yukle.cache_clear()


def test_kategori_pano_yoksa_bos_tuple(tmp_path, monkeypatch):
    from core import catalog

    (tmp_path / "categories.yaml").write_text(
        "- slug: enflasyon\n  title: Enflasyon\n", encoding="utf-8"
    )
    monkeypatch.setattr(catalog, "KATALOG_DIZINI", tmp_path)
    catalog.kategorileri_yukle.cache_clear()
    try:
        (kategori,) = catalog.kategorileri_yukle()
        assert kategori.pano == ()
    finally:
        catalog.kategorileri_yukle.cache_clear()


def test_epias_gecerli_kaynak_tipi():
    from core.catalog import GECERLI_KAYNAK_TIPLERI

    assert "epias" in GECERLI_KAYNAK_TIPLERI


def test_olcek_varsayilan_bir():
    assert seri_getir("enflasyon/tufe-genel").olcek == 1.0


def test_olcek_yaml_dan_float_olarak_okunur(tmp_path, monkeypatch):
    from core import catalog

    (tmp_path / "categories.yaml").write_text(
        "- slug: elektrik\n  title: Elektrik\n", encoding="utf-8"
    )
    (tmp_path / "series.yaml").write_text(
        "- id: elektrik/uretim\n"
        "  title: Elektrik Üretimi\n"
        "  category: elektrik\n"
        "  kaynak: {name: EPİAŞ, url: https://example.com}\n"
        "  kaynak_tipi: epias\n"
        "  epias_ucu: uretim\n"
        "  epias_alani: total\n"
        "  unit: GWh\n"
        "  freq: daily\n"
        "  charts: [level]\n"
        "  olcek: 0.001\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(catalog, "KATALOG_DIZINI", tmp_path)
    catalog.kategorileri_yukle.cache_clear()
    catalog.serileri_yukle.cache_clear()
    try:
        (seri,) = catalog.serileri_yukle()
        assert seri.olcek == pytest.approx(0.001)
    finally:
        catalog.kategorileri_yukle.cache_clear()
        catalog.serileri_yukle.cache_clear()


def test_epias_serisi_uc_ve_alan_ister():
    from core.catalog import KatalogHatasi, serileri_yukle

    serileri_yukle.cache_clear()
    seriler = serileri_yukle()
    epias = [s for s in seriler if s.kaynak_tipi == "epias"]
    assert epias, "katalogda epias serisi yok"
    for s in epias:
        assert s.epias_ucu, f"{s.id}: epias_ucu boş"
        assert s.epias_alani, f"{s.id}: epias_alani boş"
