import pandas as pd

from core.page import TAKVIM_SUTUN_AYARI, takvim_sutun_sirasi
from core.takvim import SUTUNLAR


def test_takvim_sutun_ayari_yalnizca_gercek_sutunlari_hedefler():
    """Sütun adı yanlış yazılırsa Streamlit ayarı sessizce yok sayar.

    Her sütunun ayarlanması gerekmiyor — otomatik genişlik çoğu sütun için
    doğru. Ayarlananların gerçek sütun olması gerekiyor.
    """
    assert set(TAKVIM_SUTUN_AYARI) <= set(SUTUNLAR)


def test_takvim_durum_sutunu_genisletilir():
    """"bekleniyor (59 gün)" varsayılan genişliğe sığmıyordu."""
    assert "Durum" in TAKVIM_SUTUN_AYARI


def test_bos_sutun_gizlenir():
    """Tamamen boş "Yayın notu" sütunu yer kaplıyor, bilgi taşımıyor."""
    df = pd.DataFrame({"Veri": ["a"], "Durum": ["güncel"], "Yayın notu": [""]})
    assert takvim_sutun_sirasi(df) == ["Veri", "Durum"]


def test_dolu_sutun_gizlenmez():
    """Tek bir not bile girildiyse sütun geri gelmeli."""
    df = pd.DataFrame(
        {"Veri": ["a", "b"], "Durum": ["güncel", "güncel"], "Yayın notu": ["", "3. iş günü"]}
    )
    assert takvim_sutun_sirasi(df) == ["Veri", "Durum", "Yayın notu"]


def test_pano_serileri_pano_sirasini_korur():
    import dataclasses

    from core.catalog import Kategori, seri_getir
    from core.page import pano_serileri

    a = dataclasses.replace(seri_getir("enflasyon/tufe-genel"), id="k/a")
    b = dataclasses.replace(seri_getir("enflasyon/tufe-genel"), id="k/b")
    kategori = Kategori(slug="k", title="K", pano=("k/b", "k/a"))
    assert [s.id for s in pano_serileri(kategori, [a, b])] == ["k/b", "k/a"]


def test_pano_bossa_seri_listesi_degismeden_donuyor():
    """"İlk dördü göster" kırpması burada değil, kpi_satiri içinde olur."""
    import dataclasses

    from core.catalog import Kategori, seri_getir
    from core.page import pano_serileri

    seriler = [
        dataclasses.replace(seri_getir("enflasyon/tufe-genel"), id=f"k/{i}")
        for i in range(6)
    ]
    kategori = Kategori(slug="k", title="K")
    assert pano_serileri(kategori, seriler) == seriler


def test_pano_bilinmeyen_id_hata_verir():
    import pytest

    from core.catalog import Kategori, KatalogHatasi, seri_getir
    from core.page import pano_serileri

    kategori = Kategori(slug="k", title="K", pano=("k/yok",))
    with pytest.raises(KatalogHatasi):
        pano_serileri(kategori, [seri_getir("enflasyon/tufe-genel")])


def test_kategori_takvim_sutun_sirasi_bos_sutunu_disliyor():
    """Kategori takvimi de global takvim gibi tamamen boş sütunu gizlemeli.

    Katalogdaki hiçbir seri yayin_notu taşımıyor, bu yüzden "Yayın notu"
    her kategori df'inde tamamen boş olur — column_order bunu düşürmeli.
    """
    from core.takvim import SUTUNLAR, takvim, tablo_df

    df = tablo_df(takvim(kategori="enflasyon"))
    sira = takvim_sutun_sirasi(df)
    assert "Yayın notu" not in sira
    assert set(sira) == set(SUTUNLAR) - {"Yayın notu"}
