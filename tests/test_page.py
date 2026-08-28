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
