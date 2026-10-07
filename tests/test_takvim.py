import dataclasses
from datetime import date

import pandas as pd

from core.catalog import seri_getir
from core.takvim import (
    ESIKLER,
    BEKLENIYOR,
    GECIKMIS,
    GUNCEL,
    OKUNAMADI,
    SUTUNLAR,
    VERI_YOK,
    TakvimSatiri,
    donem_sonu,
    durum_hesapla,
    satir_uret,
    sirala,
    tablo_df,
    uyari_basligi,
    uyari_govdesi,
)


def seri(freq="monthly"):
    return dataclasses.replace(seri_getir("enflasyon/tufe-genel"), freq=freq)


def test_esik_kurallari_her_siklikta_ayni():
    """Eşik → güncel, eşik+1 → bekleniyor, iki katı → hâlâ bekleniyor.

    Sınırlar `ESIKLER`'den okunur: eşik yeniden ayarlanırsa test kırılmaz,
    ama bandın kendisi bozulursa (bir eşiğin iki katına düşmesi gibi) kırılır.
    """
    for freq, esik in ESIKLER.items():
        assert durum_hesapla(freq, esik) == GUNCEL
        assert durum_hesapla(freq, esik + 1) == BEKLENIYOR
        assert durum_hesapla(freq, esik * 2) == BEKLENIYOR
        assert durum_hesapla(freq, esik * 2 + 1) == GECIKMIS


def test_aylik_esik_normal_yayin_gecikmesini_kapsar():
    """Türkiye'de aylık resmi istatistik dönem sonundan ~2 ay sonra yayımlanır.

    Bu seriler sağlamdır — veri commit'i güncel, CSV'ler boşluksuz. Eşik
    normal gecikmeyi karşılamazsa Veri Takvimi kalıcı sahte alarm üretir
    (2026-09-30'da 326 uyarının 235'i buydu).
    """
    assert durum_hesapla("monthly", 61) == GUNCEL
    assert durum_hesapla("monthly", ESIKLER["monthly"] * 2) == BEKLENIYOR
    assert durum_hesapla("monthly", ESIKLER["monthly"] * 2 + 1) == GECIKMIS


def test_gecikme_gunu_esigi_genisletir():
    """Kaynağın normal yayın gecikmesi sahte alarm üretmemeli."""
    esik = ESIKLER["monthly"]
    assert durum_hesapla("monthly", esik + 1) == BEKLENIYOR
    assert durum_hesapla("monthly", esik + 1, 25) == GUNCEL
    assert durum_hesapla("monthly", esik + 26, 25) == BEKLENIYOR


def test_gecikme_gunu_gercek_gecikmeyi_gizlemez():
    """Sabır sınırsız değil: iki katın üstü hâlâ gecikmiş."""
    esik = ESIKLER["monthly"] + 25
    assert durum_hesapla("monthly", esik * 2 + 1, 25) == GECIKMIS


def test_satir_uret_serinin_gecikme_gunune_uyar():
    """80 gündür yeni veri yok: sabırlı seri güncel, sabırsızı bekleniyor."""
    gecikmeli = dataclasses.replace(seri("monthly"), gecikme_gunu=25)
    satir = satir_uret(gecikmeli, date(2026, 5, 1), date(2026, 8, 19))
    assert satir.bekleme_gunu == 80
    assert satir.durum == GUNCEL
    assert satir_uret(seri("monthly"), date(2026, 5, 1), date(2026, 8, 19)).durum == (
        BEKLENIYOR
    )


def test_satir_uret_beklemeyi_donem_sonundan_olcer():
    """Aylık etiket ayın 1'i; bekleme dönemin bittiği günden sayılmalı.

    Temmuz verisi 3 Ağustos'ta yayınlanır ve 3 Eylül'e kadar en güncel veridir.
    Etiketten ölçmek bu normal aralığı sahte gecikme gibi gösteriyordu.
    """
    satir = satir_uret(seri("monthly"), date(2026, 7, 1), date(2026, 8, 27))
    assert satir.bekleme_gunu == 27
    assert satir.durum == GUNCEL
    assert satir.son_donem == date(2026, 7, 1)


def test_satir_uret_bitmemis_donemde_beklemeyi_sifira_kirpar():
    """Ağustos verisi geldiyse ve ağustos bitmediyse bekleme negatif çıkar."""
    satir = satir_uret(seri("monthly"), date(2026, 8, 1), date(2026, 8, 27))
    assert satir.bekleme_gunu == 0
    assert satir.durum == GUNCEL


def test_satir_uret_gercekten_gecikeni_isaretlemeye_devam_eder():
    """Nisan verisi temmuz başında en güncelse üç dönem geridedir."""
    satir = satir_uret(seri("monthly"), date(2026, 4, 1), date(2026, 7, 5))
    assert satir.bekleme_gunu == 66
    assert satir.durum == BEKLENIYOR


def test_donem_sonu_aylik_etiketi_ay_sonuna_tasir():
    assert donem_sonu(date(2026, 7, 1), "monthly") == date(2026, 7, 31)
    assert donem_sonu(date(2026, 2, 1), "monthly") == date(2026, 2, 28)


def test_ceyreklik_donem_sonu_ve_bekleme():
    assert donem_sonu(date(2024, 2, 29), "quarterly") == date(2024, 3, 31)
    assert donem_sonu(date(2026, 4, 1), "quarterly") == date(2026, 6, 30)
    assert donem_sonu(date(2026, 10, 1), "quarterly") == date(2026, 12, 31)
    satir = satir_uret(seri("quarterly"), date(2026, 4, 1), date(2026, 9, 17))
    assert satir.bekleme_gunu == 79
    assert satir.durum == GUNCEL
    assert tablo_df([satir]).iloc[0]["Son Dönem"] == "2026-Ç2"


def test_donem_sonu_haftalik_etikete_alti_gun_ekler():
    assert donem_sonu(date(2026, 8, 21), "weekly") == date(2026, 8, 27)


def test_donem_sonu_gunluk_etiketi_degistirmez():
    assert donem_sonu(date(2026, 8, 27), "daily") == date(2026, 8, 27)


def test_satir_uret_verisi_olmayan_seriyi_isaretler():
    satir = satir_uret(seri("daily"), None, date(2026, 8, 27))
    assert satir.durum == VERI_YOK
    assert satir.son_donem is None
    assert satir.bekleme_gunu is None


def test_sirala_once_ciddiyeti_sonra_beklemeyi_kullanir():
    s = seri("daily")
    satirlar = [
        TakvimSatiri(s, date(2026, 8, 26), 1, GUNCEL),
        TakvimSatiri(s, date(2026, 8, 1), 26, GECIKMIS),
        TakvimSatiri(s, None, None, VERI_YOK),
        TakvimSatiri(s, date(2026, 8, 20), 7, BEKLENIYOR),
        TakvimSatiri(s, date(2026, 8, 10), 17, GECIKMIS),
    ]
    assert [x.durum for x in sirala(satirlar)] == [
        VERI_YOK,
        GECIKMIS,
        GECIKMIS,
        BEKLENIYOR,
        GUNCEL,
    ]
    # aynı durumda daha uzun bekleyen üstte
    gecikmisler = [x for x in sirala(satirlar) if x.durum == GECIKMIS]
    assert [x.bekleme_gunu for x in gecikmisler] == [26, 17]


def test_tablo_df_sutunlari_ve_sirasi():
    s = seri("monthly")
    satirlar = [TakvimSatiri(s, date(2026, 7, 1), 57, BEKLENIYOR)]
    df = tablo_df(satirlar)
    assert list(df.columns) == [
        "Veri",
        "Kategori",
        "Son Dönem",
        "Durum",
        "Sıklık",
        "Kaynak",
        "Yayın notu",
    ]
    assert df.iloc[0]["Veri"] == s.title
    assert df.iloc[0]["Son Dönem"] == "2026-07-01"
    assert df.iloc[0]["Durum"] == "bekleniyor (57 gün)"
    assert df.iloc[0]["Sıklık"] == "AYLIK"


def test_tablo_df_verisi_olmayan_seride_tire_gosterir():
    s = seri("daily")
    df = tablo_df([TakvimSatiri(s, None, None, VERI_YOK)])
    assert df.iloc[0]["Son Dönem"] == "—"
    assert df.iloc[0]["Durum"] == "veri yok"


def test_tablo_df_yayin_notu_yoksa_bos():
    s = seri("monthly")
    df = tablo_df([TakvimSatiri(s, date(2026, 7, 1), 57, BEKLENIYOR)])
    assert df.iloc[0]["Yayın notu"] == ""


def test_tablo_df_guncel_satirda_gun_sayisi_gostermez():
    s = seri("daily")
    df = tablo_df([TakvimSatiri(s, date(2026, 8, 26), 1, GUNCEL)])
    assert df.iloc[0]["Durum"] == "güncel"


def test_sirala_okunamadi_en_uste_gelir():
    s = seri("daily")
    satirlar = [
        TakvimSatiri(s, None, None, VERI_YOK),
        TakvimSatiri(s, date(2026, 8, 1), 26, GECIKMIS),
        TakvimSatiri(s, None, None, OKUNAMADI),
    ]
    assert [x.durum for x in sirala(satirlar)] == [OKUNAMADI, VERI_YOK, GECIKMIS]


def test_tablo_df_okunamayan_satiri_gosterir():
    s = seri("daily")
    df = tablo_df([TakvimSatiri(s, None, None, OKUNAMADI)])
    assert df.iloc[0]["Durum"] == "okunamadı"
    assert df.iloc[0]["Son Dönem"] == "—"


def test_tablo_df_bos_listede_sutunlari_korur():
    df = tablo_df([])
    assert list(df.columns) == SUTUNLAR
    assert len(df) == 0


def test_takvim_kategoriye_filtreler():
    from core.takvim import takvim

    satirlar = takvim(kategori="enflasyon")
    assert satirlar, "enflasyon kategorisinde seri yok"
    assert {s.seri.category for s in satirlar} == {"enflasyon"}


def test_seriyi_oku_genis_biciminde_kirilmaz():
    """Kompozisyon serisinde `value` sütunu yok; seri_csv_oku KeyError verir."""
    from core.catalog import seri_getir
    from core.takvim import _seriyi_oku

    df = _seriyi_oku(seri_getir("elektrik/uretim-kompozisyon"))
    assert "Kömür" in df.columns
    assert not df.empty


def test_seriyi_oku_tek_degerli_seride_value_dondurur():
    """Dallanma mevcut 25 seriyi etkilememeli."""
    from core.catalog import seri_getir
    from core.takvim import _seriyi_oku

    df = _seriyi_oku(seri_getir("enflasyon/tufe-genel"))
    assert list(df.columns) == ["value"]


def test_takvim_kompozisyon_serisini_okunamadi_saymaz():
    """Geniş CSV bozuk değil; OKUNAMADI'ya düşerse dallanma çalışmıyordur."""
    from core.takvim import OKUNAMADI, takvim

    (satir,) = [
        s for s in takvim(kategori="elektrik")
        if s.seri.id == "elektrik/uretim-kompozisyon"
    ]
    assert satir.durum != OKUNAMADI
    assert satir.son_donem is not None


def test_uyari_govdesi_not_yoksa_yalnizca_sureyi_yazar():
    s = seri("monthly")
    assert s.yayin_notu is None
    satir = TakvimSatiri(s, date(2020, 1, 1), 2400, GECIKMIS)
    assert uyari_govdesi(satir) == "2400 gündür yeni veri yok (Aylık)"


def test_uyari_govdesi_yayin_notunu_sona_ekler():
    s = dataclasses.replace(seri("monthly"), yayin_notu="Eurostat TR 2025-12'de duruyor")
    satir = TakvimSatiri(s, date(2025, 12, 1), 278, GECIKMIS)
    assert uyari_govdesi(satir) == (
        "278 gündür yeni veri yok (Aylık). Eurostat TR 2025-12'de duruyor"
    )


def test_uyari_govdesi_veri_yok_ve_okunamadi():
    s = seri("daily")
    assert uyari_govdesi(TakvimSatiri(s, None, None, VERI_YOK)) == "hiç veri yok (Günlük)"
    assert uyari_govdesi(TakvimSatiri(s, None, None, OKUNAMADI)) == (
        "veri dosyası okunamıyor (Günlük)"
    )


def test_uyari_basligi_notlu_ile_bakilacagi_ayirir():
    notlu = dataclasses.replace(seri("monthly"), yayin_notu="kaynak geride")
    notsuz = seri("monthly")
    baslik = uyari_basligi([
        TakvimSatiri(notlu, date(2025, 12, 1), 278, GECIKMIS),
        TakvimSatiri(notsuz, date(2020, 1, 1), 2400, GECIKMIS),
    ])
    assert baslik == (
        "2 seri dikkat gerektiriyor: 1 kaynak geride (yayın notu var), 1 bakılacak"
    )
