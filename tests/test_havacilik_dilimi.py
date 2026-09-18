"""Havacılık diliminin gerçek veriyle sayfa davranışı regresyonları.

AppTest yerine proje test geleneği: gerçek CSV'ler + çekirdek katman
çağrıları. AppTest Streamlit test API'si bu ortamda güvenilmez dosya-kökü
davranışı gösterdiği için çizim zinciri birebir çağrılır.
"""

from __future__ import annotations

import pandas as pd

from core.catalog import seri_listele
from core.charts import gunluk_mevsimsellik_figuru, hareketli_ortalama_uygula
from core.data import load_series

YENI_HAVALIMANLARI = {
    "havacilik/amsterdam",
    "havacilik/paris-cdg",
    "havacilik/madrid-barajas",
    "havacilik/frankfurt",
    "havacilik/viyana",
    "havacilik/budapeste",
    "havacilik/londra-heathrow",
}


def test_havacilik_kategorisi_14_eurocontrol_serisi_barindirir():
    """Referans aviation_airports.html 9 havalimanı + 3 havayolu + Türkiye
    + SunExpress gösterir; katalogda 14 EUROCONTROL kartı olmalı.

    Kategori sayısı değil KAYNAK sayısı pinlenir: aynı kategoriye sonradan
    THY/Pegasus trafik serileri eklendi ve toplam sayı sözleşmeyi taşımıyor.
    """
    havadaki = [s for s in seri_listele("havacilik") if s.kaynak_tipi == "eurocontrol"]
    assert len(havadaki) == 14


def test_yeni_havalimani_serilerinin_csvsi_gercek_aralikta():
    """7 yeni havalimanı CSV'si gerçek kaynak penceresiyle yazılmalı:
    2025-01-02 (referansın iki yıllık uzatma başlangıcı) → en az
    2026-09-16 (referansın son günü)."""
    for seri in seri_listele("havacilik"):
        if seri.id in YENI_HAVALIMANLARI:
            df = load_series(seri.id)
            assert str(df.index.min().date()) == "2025-01-02", seri.id
            assert str(df.index.max().date()) >= "2026-09-16", seri.id


def test_hareketli_ortalama_tam_pencere_bekler_ve_boslugu_korur():
    """min_periods=pencere: 6 günlük kısmi pencere ortalama üretemez;
    aradaki eksik gün NaN kalır (grafik boşluğu çizer, bağlamaz)."""
    df = load_series("havacilik/amsterdam")
    duzgun = hareketli_ortalama_uygula(df, 7)
    # Takvim günlük genişletildi: tüm günler satır, sıcaklıkta NaN.
    assert len(duzgun) >= len(df)
    assert duzgun["value"].isna().sum() >= 6
    # Tam pencereye düşen ilk gün ham 7 günün ortalamasına eşittir.
    ilk_tam = duzgun["value"].first_valid_index()
    ham_pencere = df.loc[ilk_tam - pd.Timedelta(days=6):ilk_tam, "value"]
    assert ilk_tam in ham_pencere.index
    assert abs(duzgun.loc[ilk_tam, "value"] - ham_pencere.mean()) < 1e-9


def test_gunluk_mevsimsellik_yil_izlerini_kalibre_eder():
    """Referansın 'X ekseninde 12 ay, her yıl bir çizgi' formu: her izin
    x'i 2000 referansına hizalanmalı, hover gerçek tarihi taşımali."""
    df = load_series("havacilik/amsterdam")
    duzgun = hareketli_ortalama_uygula(df, 7)
    fig = gunluk_mevsimsellik_figuru(duzgun, "Uçuş (7g ort.)")
    yillar = {t.name for t in fig.data}
    assert yillar == {"2026", "2025"}
    for iz in fig.data:
        # 29 Şubat güvenli: tüm x değerleri 2000 yılını gösterir.
        assert all(getattr(x, "year", 2000) == 2000 for x in iz.x)
        # Hover gerçek tarihi taşır (customdata ile hizalanır).
        assert len(iz.customdata) == len(iz.x)
