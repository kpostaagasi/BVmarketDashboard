import dataclasses

import pytest

from core.catalog import (
    Kaynak,
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
        "enflasyon",
        "sanayi",
        "dis-ticaret",
        "ihracat",
        "bankacilik",
        "para-banka",
        "insaat",
        "kredi-karti",
        "emtia-enerji",
        "emtia-metaller",
        "elektrik",
        "otomotiv",
    ]


def test_seri_sayisi():
    assert len(serileri_yukle()) == 94


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
        "insaat/konut-satis-ilk-el",
        "insaat/konut-satis-ikinci-el",
        "insaat/konut-fiyat-istanbul",
        "insaat/kira-endeksi",
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
        assert set(seri.charts) <= {"seasonality", "level", "composition"}, seri.id
        if seri.kaynak_tipi == "evds":
            assert seri.evds_frequency in {"1", "2", "5"}, seri.id
            assert seri.evds_code, seri.id
        if seri.kaynak_tipi == "yahoo":
            assert seri.yahoo_symbol, seri.id


def _sluglar():
    return {k.slug for k in kategorileri_yukle()}


def test_her_serinin_kaynak_tipi_gecerli():
    for seri in serileri_yukle():
        assert seri.kaynak_tipi in {"evds", "yahoo", "epias", "osd", "tim", "bddk"}, seri.id


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
    with pytest.raises(KatalogHatasi, match="evds_code"):
        _dogrula(seri, _sluglar(), set())


def test_bilinmeyen_kaynak_tipi_reddedilir():
    seri = dataclasses.replace(seri_getir("enflasyon/tufe-genel"), kaynak_tipi="bloomberg")
    with pytest.raises(KatalogHatasi, match="kaynak_tipi"):
        _dogrula(seri, _sluglar(), set())


def test_her_kategori_panosunu_acik_tanimlar():
    """Devredilen iş #3: KPI seçimi artık konumsal değil.

    `pano` boş bırakılırsa `kpi_satiri` katalogdaki ilk dördü gösterir;
    o zaman `series.yaml`'daki sıra değişince sayfanın KPI'ları sessizce
    değişir. Her kategori panosunu açıkça yazar.
    """
    for kategori in kategorileri_yukle():
        assert kategori.pano, kategori.slug


def test_pano_idleri_kendi_kategorisinde_ve_tek_degerli():
    """Pano id'si var olmalı, kategorisine ait olmalı, geniş seri olmamalı.

    (`pano_serileri` bunları çalışma anında da reddediyor; bu test hatayı
    sayfayı açmadan yakalar.)
    """
    for kategori in kategorileri_yukle():
        kategorinin_idleri = {s.id: s for s in seri_listele(kategori.slug)}
        for seri_id in kategori.pano:
            assert seri_id in kategorinin_idleri, seri_id
            assert not kategorinin_idleri[seri_id].epias_bilesenler, seri_id


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


def test_olcek_verilmemisse_none():
    """Varsayılan None; 1.0'a ingest tarafında düşülür.

    Sebep: "verilmiş mi" sorusunun tek bir cevabı olsun. Varsayılan 1.0
    olsaydı, katalogda açıkça yazılmış `olcek: 1.0` ile hiç yazılmamış olan
    ayırt edilemezdi ve yasak-alan kontrolü o değerde delik kalırdı.
    """
    assert seri_getir("enflasyon/tufe-genel").olcek is None


def test_olcek_verilmemisse_ingest_olceklemez():
    """Sözleşmenin diğer yarısı: None ölçeklememek demek, sıfırlamak değil."""
    import pandas as pd

    from ingest.run import olcekle

    df = pd.DataFrame({"value": [10.0, 20.0]})
    assert list(olcekle(df, None)["value"]) == [10.0, 20.0]
    assert list(olcekle(df, 0.001)["value"]) == [0.01, 0.02]


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


def test_epias_serisinde_monthly_agg_last_reddedilir():
    # M6: GECERLI_AYLIK_AGG "last"i kabul ediyor ama epias.seri_cek'in
    # else dalı bunu sessizce ortalamaya çeviriyordu. Bugün böyle bir seri
    # yok ama şablon tuzağa yerleşmesin: epias serisi last alamaz.
    seri = dataclasses.replace(seri_getir("elektrik/ptf"), monthly_agg="last")
    with pytest.raises(KatalogHatasi, match="monthly_agg"):
        _dogrula(seri, _sluglar(), set())


def test_tek_alanli_epias_serileri_epias_alani_tasir_bilesen_tasimaz():
    from core.catalog import serileri_yukle

    serileri_yukle.cache_clear()
    seriler = serileri_yukle()
    tek_alanlilar = [
        s for s in seriler if s.kaynak_tipi == "epias" and s.epias_bilesenler is None
    ]
    assert tek_alanlilar, "katalogda tek alanlı epias serisi yok"
    for s in tek_alanlilar:
        assert s.epias_ucu, f"{s.id}: epias_ucu boş"
        assert s.epias_alani, f"{s.id}: epias_alani boş"
        assert s.epias_bilesenler is None, f"{s.id}: epias_bilesenler dolu olmamalı"


def test_bilesenli_epias_serileri_epias_bilesenler_tasir_alan_tasimaz():
    from core.catalog import serileri_yukle

    serileri_yukle.cache_clear()
    seriler = serileri_yukle()
    bilesenliler = [
        s for s in seriler if s.kaynak_tipi == "epias" and s.epias_bilesenler is not None
    ]
    assert bilesenliler, "katalogda bileşenli epias serisi yok"
    for s in bilesenliler:
        assert s.epias_ucu, f"{s.id}: epias_ucu boş"
        assert s.epias_bilesenler, f"{s.id}: epias_bilesenler boş"
        assert s.epias_alani is None, f"{s.id}: epias_alani dolu olmamalı"


# --- Alan sahipliği tablosu ---


def _ham_seri(**degisiklikler):
    """Geçerli bir evds seri sözlüğü; testler tek alanı değiştirip bozar."""
    ham = {
        "id": "enflasyon/deneme",
        "title": "Deneme",
        "category": "enflasyon",
        "kaynak": {"name": "TCMB EVDS", "url": "https://evds3.tcmb.gov.tr"},
        "kaynak_tipi": "evds",
        "unit": "%",
        "freq": "monthly",
        "charts": ["level"],
        "evds_code": "TP.X",
        "evds_frequency": "5",
    }
    ham.update(degisiklikler)
    return ham


def _dogrula_ham(ham):
    from core.catalog import Seri, _dogrula

    alanlar = {a: ham[a] for a in ham if a != "kaynak"}
    seri = Seri(kaynak=Kaynak(**ham["kaynak"]), **alanlar)
    _dogrula(seri, {"enflasyon"}, set())


def test_kaynak_alanlari_tablosu_her_kaynak_tipini_kapsar():
    from core.catalog import GECERLI_KAYNAK_TIPLERI, KAYNAK_ALANLARI

    assert set(KAYNAK_ALANLARI) == GECERLI_KAYNAK_TIPLERI


def test_evds_serisi_olcek_tasiyabilir():
    """Faz 3f: `olcek` tipe değil kataloğa ait — her kaynak onurlandırır.

    EVDS kredi/mevduat serilerini "Bin TL" cinsinden döndürüyor; ölçek
    olmadan KPI kartında 26.351.644.811 gibi okunamaz bir sayı çıkar.
    """
    _dogrula_ham(_ham_seri(olcek=0.000001))



def test_tim_serisi_sektor_ve_eski_adlar_tasiyabilir():
    _dogrula_ham(
        _ham_seri(
            kaynak_tipi="tim", tim_sektor="Otomotiv Endüstrisi",
            tim_eski_adlar=("Otomotiv",), evds_code=None, evds_frequency=None,
            olcek=0.001,
        )
    )


def test_tim_serisi_sektor_zorunlu():
    with pytest.raises(KatalogHatasi, match="tim_sektor"):
        _dogrula_ham(
            _ham_seri(kaynak_tipi="tim", evds_code=None, evds_frequency=None)
        )


def test_evds_serisi_tim_alani_tasiyamaz():
    with pytest.raises(KatalogHatasi, match="tim_sektor"):
        _dogrula_ham(_ham_seri(tim_sektor="Çelik"))


def test_evds_serisi_epias_alani_tasiyamaz():
    with pytest.raises(KatalogHatasi, match="epias_ucu"):
        _dogrula_ham(_ham_seri(epias_ucu="ptf"))


def test_epias_serisi_evds_alani_tasiyamaz():
    with pytest.raises(KatalogHatasi, match="evds_code"):
        _dogrula_ham(
            _ham_seri(
                kaynak_tipi="epias", epias_ucu="ptf", epias_alani="price",
                evds_frequency=None,
            )
        )


def test_epias_serisi_olcek_ve_start_date_tasiyabilir():
    _dogrula_ham(
        _ham_seri(
            kaynak_tipi="epias", epias_ucu="ptf", epias_alani="price",
            evds_code=None, evds_frequency=None,
            olcek=0.001, start_date="2021-01-01",
        )
    )


def test_yahoo_serisi_start_date_tasiyamaz():
    """Mevcut davranış korunmalı: yahoo range=15y sabit."""
    with pytest.raises(KatalogHatasi, match="start_date"):
        _dogrula_ham(
            _ham_seri(
                kaynak_tipi="yahoo", yahoo_symbol="BZ=F",
                evds_code=None, evds_frequency=None, start_date="2021-01-01",
            )
        )


def test_eksik_zorunlu_alan_reddedilir():
    with pytest.raises(KatalogHatasi, match="evds_code"):
        _dogrula_ham(_ham_seri(evds_code=None))


def test_gercek_katalog_alan_sahipligini_gecer():
    """Regresyon kalkanı: tablo mevcut 94 seriyi reddetmemeli."""
    from core.catalog import serileri_yukle

    serileri_yukle.cache_clear()
    try:
        assert len(serileri_yukle()) == 94
    finally:
        serileri_yukle.cache_clear()


def test_bos_string_zorunlu_alani_karsilamaz():
    """`evds_code: ""` katalogda kod yazmakla aynı şey değildir."""
    with pytest.raises(KatalogHatasi, match="evds_code"):
        _dogrula_ham(_ham_seri(evds_code=""))


def test_bos_string_yahoo_sembolunu_karsilamaz():
    with pytest.raises(KatalogHatasi, match="yahoo_symbol"):
        _dogrula_ham(
            _ham_seri(
                kaynak_tipi="yahoo", yahoo_symbol="",
                evds_code=None, evds_frequency=None,
            )
        )


def test_ortak_alan_tipe_ozgu_yasaklari_gevsetmez():
    """`olcek` ortak alana çıktı; bu, tip tablosunu delik bırakmamalı.

    Aynı red kuralı yolundan geçen tipe özgü bir alan (yahoo serisinde
    `evds_code`) hâlâ reddedilmeli — aksi halde ORTAK_ALANLAR çıkarması
    tabloyu tümden etkisizleştirmiş olurdu.
    """
    from core.catalog import ORTAK_ALANLAR, TIPE_OZGU_ALANLAR

    assert "olcek" in ORTAK_ALANLAR
    assert "olcek" not in TIPE_OZGU_ALANLAR
    with pytest.raises(KatalogHatasi, match="evds_code"):
        _dogrula_ham(
            _ham_seri(kaynak_tipi="yahoo", yahoo_symbol="BZ=F", evds_frequency=None)
        )


def test_gecikme_gunu_sifir_veya_negatif_reddedilir():
    """0 alanı gereksiz yazmak, negatif eşiği daraltıp sahte alarm üretmek."""
    for gecersiz in (0, -5):
        with pytest.raises(KatalogHatasi, match="gecikme_gunu"):
            _dogrula_ham(_ham_seri(gecikme_gunu=gecersiz))


def test_gecikme_gunu_katalogda_yalnizca_gecikmeli_serilerde():
    """Faz 3f: yalnızca kaynağı ~42 gün gecikmeli iki seri taşır.

    Alanın her seriye yayılması eşiği anlamsızlaştırır; bu test yayılmayı
    fark ettirir.
    """
    tasiyanlar = {s.id for s in seri_listele() if s.gecikme_gunu is not None}
    assert tasiyanlar == {"sanayi/uretim-endeksi", "dis-ticaret/cari-denge"}


def test_olcek_sifir_veya_negatif_reddedilir():
    """olcek=0 seriyi sessizce sıfırlar; grafik boş değil, YANLIŞ çizilir."""
    for gecersiz in (0.0, -1.0):
        with pytest.raises(KatalogHatasi, match="olcek"):
            _dogrula_ham(
                _ham_seri(
                    kaynak_tipi="epias", epias_ucu="ptf", epias_alani="price",
                    evds_code=None, evds_frequency=None, olcek=gecersiz,
                )
            )


def test_composition_gecerli_grafik_turu():
    from core.catalog import GECERLI_GRAFIKLER

    assert "composition" in GECERLI_GRAFIKLER


def test_epias_serisi_alan_ve_bilesenleri_birlikte_tasiyamaz():
    with pytest.raises(KatalogHatasi, match="epias_bilesenler"):
        _dogrula_ham(
            _ham_seri(
                kaynak_tipi="epias", epias_ucu="uretim", epias_alani="total",
                epias_bilesenler={"Kömür": ["lignite"]},
                evds_code=None, evds_frequency=None,
            )
        )


def test_epias_serisi_ikisinden_birini_tasimali():
    with pytest.raises(KatalogHatasi, match="epias_alani"):
        _dogrula_ham(
            _ham_seri(
                kaynak_tipi="epias", epias_ucu="uretim",
                evds_code=None, evds_frequency=None,
            )
        )


def test_bilesenli_seri_composition_grafigi_ister():
    with pytest.raises(KatalogHatasi, match="composition"):
        _dogrula_ham(
            _ham_seri(
                kaynak_tipi="epias", epias_ucu="uretim",
                epias_bilesenler={"Kömür": ["lignite"]},
                charts=["level"],
                evds_code=None, evds_frequency=None,
            )
        )


def test_composition_grafigi_bilesen_ister():
    with pytest.raises(KatalogHatasi, match="composition"):
        _dogrula_ham(
            _ham_seri(
                kaynak_tipi="epias", epias_ucu="ptf", epias_alani="price",
                charts=["composition"],
                evds_code=None, evds_frequency=None,
            )
        )


def test_composition_baska_grafikle_birlikte_reddedilir():
    """[composition, level] katalogca kabul edilirse page.py level'i sessizce

    yutar (bkz. M1) — composition her zaman TEK BAŞINA olmalı."""
    with pytest.raises(KatalogHatasi, match="composition"):
        _dogrula_ham(
            _ham_seri(
                kaynak_tipi="epias", epias_ucu="uretim",
                epias_bilesenler={"Kömür": ["lignite"]},
                charts=["composition", "level"],
                evds_code=None, evds_frequency=None,
            )
        )


def test_bilesenler_tuple_olarak_okunur():
    from core.catalog import seri_getir, serileri_yukle

    serileri_yukle.cache_clear()
    try:
        seri = seri_getir("elektrik/uretim-kompozisyon")
        assert seri.epias_bilesenler["Hidroelektrik"] == ("dammedHydro", "river")
        assert "importExport" not in {
            alan for alanlar in seri.epias_bilesenler.values() for alan in alanlar
        }
    finally:
        serileri_yukle.cache_clear()


def test_uretim_serisi_basligi_net_ithalati_belirtir():
    """total = üretim + net ithalat; başlık bunu saklamamalı."""
    from core.catalog import seri_getir

    assert "ithalat" in seri_getir("elektrik/uretim").title.lower()


def test_otomobil_satin_alma_niyeti_serisi_tanimli():
    """TP.TG2.Y17, mevcut tüketici güven serisiyle (TP.TG2.Y01) aynı
    TÜİK/TCMB tüketici eğilim anketinden gelir — aynı kategoriye girer."""
    from core.catalog import seri_getir

    seri = seri_getir("ekonomi-makro/otomobil-satin-alma-niyeti")
    assert seri.evds_code == "TP.TG2.Y17"
    assert seri.evds_frequency == "5"
    assert seri.freq == "monthly"
    assert seri.category == "ekonomi-makro"


def test_osd_gecerli_kaynak_tipi():
    from core.catalog import GECERLI_KAYNAK_TIPLERI, KAYNAK_ALANLARI

    assert "osd" in GECERLI_KAYNAK_TIPLERI
    assert "osd" in KAYNAK_ALANLARI


def test_osd_serisi_firma_ister():
    with pytest.raises(KatalogHatasi, match="osd_firma"):
        _dogrula_ham(
            _ham_seri(kaynak_tipi="osd", evds_code=None, evds_frequency=None)
        )


def test_osd_serisi_evds_alani_tasiyamaz():
    with pytest.raises(KatalogHatasi, match="evds_code"):
        _dogrula_ham(
            _ham_seri(kaynak_tipi="osd", osd_firma="FORD OTOSAN", evds_frequency=None)
        )


def test_evds_serisi_osd_firma_tasiyamaz():
    with pytest.raises(KatalogHatasi, match="osd_firma"):
        _dogrula_ham(_ham_seri(osd_firma="FORD OTOSAN"))


def test_otomotiv_kategorisi_on_uc_seri_icerir():
    from core.catalog import seri_listele

    seriler = seri_listele("otomotiv")
    assert len(seriler) == 13
    assert all(s.kaynak_tipi == "osd" for s in seriler)
    assert all(s.osd_firma for s in seriler)


def test_otomotiv_panosu_portfoy_firmalarini_gosterir():
    from core.catalog import kategorileri_yukle

    (kategori,) = [k for k in kategorileri_yukle() if k.slug == "otomotiv"]
    assert kategori.pano == (
        "otomotiv/ford-otosan", "otomotiv/tofas",
        "otomotiv/turk-traktor", "otomotiv/karsan",
    )
