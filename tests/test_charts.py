import pandas as pd
import pytest

from core.charts import aylige_cevir, mevsimsellik_figuru, seviye_figuru
from core.theme import RENKLER, TR_AYLAR


def gunluk_df(baslangic, periyot, deger=1.0):
    idx = pd.date_range(baslangic, periods=periyot, freq="D", name="date")
    return pd.DataFrame({"value": [deger] * periyot}, index=idx)


def aylik_df(baslangic, periyot):
    idx = pd.date_range(baslangic, periods=periyot, freq="MS", name="date")
    return pd.DataFrame({"value": [float(i) for i in range(periyot)]}, index=idx)


def test_aylige_cevir_ortalama_alir():
    idx = pd.date_range("2026-01-01", periods=31, freq="D", name="date")
    df = pd.DataFrame({"value": [10.0] * 30 + [41.0]}, index=idx)
    sonuc = aylige_cevir(df, "mean")
    assert len(sonuc) == 1
    assert sonuc.iloc[0]["value"] == pytest.approx(11.0)


def test_aylige_cevir_son_degeri_alir():
    idx = pd.date_range("2026-01-01", periods=3, freq="D", name="date")
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0]}, index=idx)
    assert aylige_cevir(df, "last").iloc[0]["value"] == 3.0


def test_aylige_cevir_toplar():
    idx = pd.date_range("2026-01-01", periods=3, freq="D", name="date")
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0]}, index=idx)
    assert aylige_cevir(df, "sum").iloc[0]["value"] == 6.0


def test_mevsimsellik_uc_yil_icin_uc_iz_uretir():
    df = aylik_df("2022-01-01", 60)  # 2022-01 .. 2026-12
    fig = mevsimsellik_figuru(df, "Adet")
    assert len(fig.data) == 3


def test_mevsimsellik_ilk_iz_cari_yil_ve_kalin():
    df = aylik_df("2022-01-01", 60)
    fig = mevsimsellik_figuru(df, "Adet")
    ilk = fig.data[0]
    assert ilk.name == "2026"
    assert ilk.line.color == RENKLER["seri"][0]
    assert ilk.line.width == 3
    assert fig.data[1].line.width == 2


def test_mevsimsellik_x_ekseni_ay_numaralari():
    df = aylik_df("2022-01-01", 60)
    fig = mevsimsellik_figuru(df, "Adet")
    assert list(fig.data[0].x) == list(range(1, 13))
    assert list(fig.layout.xaxis.ticktext) == TR_AYLAR


def test_mevsimsellik_kisa_seride_mevcut_yillari_verir():
    df = aylik_df("2026-01-01", 6)
    fig = mevsimsellik_figuru(df, "Adet")
    assert len(fig.data) == 1
    assert fig.data[0].name == "2026"


def test_mevsimsellik_eksik_ayi_cizgiyle_baglamaz():
    df = pd.DataFrame(
        {"value": [10.0, 30.0]},
        index=pd.to_datetime(["2026-01-01", "2026-03-01"]),
    )
    iz = mevsimsellik_figuru(df, "Adet").data[0]
    assert list(iz.x) == [1, 2, 3]
    assert iz.y[0] == 10.0 and pd.isna(iz.y[1]) and iz.y[2] == 30.0
    assert not iz.connectgaps


def test_seviye_tek_iz_ve_legendsiz():
    df = aylik_df("2024-01-01", 24)
    fig = seviye_figuru(df, "TL")
    assert len(fig.data) == 1
    assert fig.layout.showlegend is False
    assert fig.data[0].line.color == RENKLER["seri"][0]


def test_seviye_y_ekseni_birimi_gosterir():
    df = aylik_df("2024-01-01", 24)
    fig = seviye_figuru(df, "TL")
    assert fig.layout.yaxis.title.text == "TL"


def test_mevsimsellik_tek_yilda_legend_kapali():
    df = aylik_df("2026-01-01", 6)
    assert mevsimsellik_figuru(df, "Adet").layout.showlegend is False


def test_mevsimsellik_cok_yilda_legend_acik():
    df = aylik_df("2022-01-01", 60)
    assert mevsimsellik_figuru(df, "Adet").layout.showlegend is True


def test_mevsimsellik_paletten_fazla_yil_istenirse_hata():
    df = aylik_df("2016-01-01", 120)
    with pytest.raises(ValueError, match="yil_sayisi"):
        mevsimsellik_figuru(df, "Adet", yil_sayisi=4)


def test_aylige_cevir_sum_bos_ayi_sifir_yapmaz():
    # Şubat'ta hiç veri yok — 0.0 değil, boşluk olmalı
    idx = pd.DatetimeIndex(
        ["2026-01-05", "2026-01-19", "2026-03-02", "2026-03-16"], name="date"
    )
    df = pd.DataFrame({"value": [10.0, 10.0, 20.0, 20.0]}, index=idx)
    sonuc = aylige_cevir(df, "sum")
    assert list(sonuc.index.month) == [1, 3]


def test_aylige_cevir_sum_tamamlanmamis_son_ayi_atar():
    idx = pd.date_range("2026-01-05", "2026-04-10", freq="W-MON", name="date")
    df = pd.DataFrame({"value": [100.0] * len(idx)}, index=idx)
    sonuc = aylige_cevir(df, "sum", freq="weekly")
    assert sonuc.index.max() == pd.Timestamp("2026-03-01")


def test_aylige_cevir_aylik_seride_son_ay_korunur():
    idx = pd.date_range("2026-01-01", periods=4, freq="MS", name="date")
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0, 4.0]}, index=idx)
    sonuc = aylige_cevir(df, "sum", freq="monthly")
    assert sonuc.index.max() == pd.Timestamp("2026-04-01")


def test_aylige_cevir_mean_tamamlanmamis_son_ayi_korur():
    idx = pd.date_range("2026-01-05", "2026-04-10", freq="W-MON", name="date")
    df = pd.DataFrame({"value": [100.0] * len(idx)}, index=idx)
    sonuc = aylige_cevir(df, "mean", freq="weekly")
    assert sonuc.index.max() == pd.Timestamp("2026-04-01")


def test_paylara_cevir_yuzdeye_normalize_eder():
    from core.charts import paylara_cevir

    df = pd.DataFrame(
        {"Kömür": [60.0, 30.0], "Rüzgar": [40.0, 10.0]},
        index=pd.to_datetime(["2026-07-01", "2026-08-01"]),
    )
    paylar = paylara_cevir(df)
    assert list(paylar["Kömür"]) == [60.0, 75.0]
    assert list(paylar["Rüzgar"]) == [40.0, 25.0]


def test_paylara_cevir_her_satir_yuze_toplanir():
    from core.charts import paylara_cevir

    df = pd.DataFrame(
        {"A": [1.0, 2.0], "B": [3.0, 5.0], "C": [6.0, 3.0]},
        index=pd.to_datetime(["2026-07-01", "2026-08-01"]),
    )
    toplamlar = paylara_cevir(df).sum(axis=1)
    assert all(abs(t - 100.0) < 1e-9 for t in toplamlar)


def test_paylara_cevir_sifir_toplamli_satirda_nan_uretir():
    """Sıfıra bölme sessizce 0 pay üretmemeli — veri yokluğu görünür kalsın."""
    from core.charts import paylara_cevir

    df = pd.DataFrame(
        {"A": [0.0, 2.0], "B": [0.0, 2.0]},
        index=pd.to_datetime(["2026-07-01", "2026-08-01"]),
    )
    paylar = paylara_cevir(df)
    assert paylar.iloc[0].isna().all()
    assert list(paylar.iloc[1]) == [50.0, 50.0]


def test_kompozisyon_figuru_her_gruba_bir_iz_ekler():
    from core.charts import kompozisyon_figuru

    df = pd.DataFrame(
        {"Kömür": [60.0, 30.0], "Rüzgar": [40.0, 10.0]},
        index=pd.to_datetime(["2026-07-01", "2026-08-01"]),
    )
    fig = kompozisyon_figuru(df, "GWh")
    assert len(fig.data) == 2
    assert {iz.name for iz in fig.data} == {"Kömür", "Rüzgar"}


def test_kompozisyon_figuru_kategorik_paleti_sutun_adina_gore_kullanir():
    """Renk sütun ADINA göre seçilmeli — pozisyona göre `zip` semantiği bozar.

    RENKLER["kategorik"] artık grup adıyla anahtarlanmış bir dict (liste
    değil); df'teki sütun sırası paletin doğrulayıcıya verilen sırasından
    farklı olsa da her iz kendi grubunun rengini almalı.
    """
    from core.charts import kompozisyon_figuru

    df = pd.DataFrame(
        {"Rüzgar": [1.0], "Kömür": [2.0], "Güneş": [3.0]},
        index=pd.to_datetime(["2026-07-01"]),
    )
    fig = kompozisyon_figuru(df, "GWh")
    renkler = {iz.name: iz.line.color for iz in fig.data}
    assert renkler == {
        "Rüzgar": RENKLER["kategorik"]["Rüzgar"],
        "Kömür": RENKLER["kategorik"]["Kömür"],
        "Güneş": RENKLER["kategorik"]["Güneş"],
    }


def test_kompozisyon_figuru_bilinmeyen_sutun_key_error_firlatir():
    """Katalogla palet ayrışırsa sessiz varsayılana düşmek yerine patlamalı."""
    from core.charts import kompozisyon_figuru

    df = pd.DataFrame(
        {"Bilinmeyen-Grup": [1.0]},
        index=pd.to_datetime(["2026-07-01"]),
    )
    with pytest.raises(KeyError):
        kompozisyon_figuru(df, "GWh")


def test_kompozisyon_figuru_desen_sutun_adina_gore_uygular():
    """Çizgi deseni de CIZGI_DESENLERI'nden sütun adına göre gelmeli."""
    from core.charts import kompozisyon_figuru
    from core.theme import CIZGI_DESENLERI

    df = pd.DataFrame(
        {"Rüzgar": [1.0], "Kömür": [2.0], "Doğalgaz": [3.0]},
        index=pd.to_datetime(["2026-07-01"]),
    )
    fig = kompozisyon_figuru(df, "GWh")
    desenler = {iz.name: iz.line.dash for iz in fig.data}
    assert desenler == {
        "Rüzgar": CIZGI_DESENLERI["Rüzgar"],
        "Kömür": CIZGI_DESENLERI["Kömür"],
        "Doğalgaz": CIZGI_DESENLERI["Doğalgaz"],
    }


def _aylik(*aylar):
    return pd.DataFrame(
        {"value": [float(i) for i in range(len(aylar))]},
        index=pd.to_datetime(list(aylar)),
    )


def test_kismi_aylari_dus_tam_aylari_korur():
    from core.charts import kismi_aylari_dus

    aylik = _aylik("2026-07-01", "2026-08-01")
    ham = pd.date_range("2026-07-01", "2026-08-31", freq="D")
    assert len(kismi_aylari_dus(aylik, ham, "daily")) == 2


def test_kismi_aylari_dus_eksik_son_ayi_dusurur():
    from core.charts import kismi_aylari_dus

    aylik = _aylik("2026-07-01", "2026-08-01")
    ham = pd.date_range("2026-07-01", "2026-08-15", freq="D")
    assert list(kismi_aylari_dus(aylik, ham, "daily").index) == [
        pd.Timestamp("2026-07-01")
    ]


def test_kismi_aylari_dus_eksik_ilk_ayi_dusurur():
    """Veri ayın ortasında başlıyorsa ilk ay sahte bir dip üretir (M5)."""
    from core.charts import kismi_aylari_dus

    aylik = _aylik("2026-06-01", "2026-07-01", "2026-08-01")
    ham = pd.date_range("2026-06-28", "2026-08-31", freq="D")
    assert list(kismi_aylari_dus(aylik, ham, "daily").index) == [
        pd.Timestamp("2026-07-01"), pd.Timestamp("2026-08-01")
    ]


def test_kismi_aylari_dus_icteki_kismi_ayi_da_dusurur():
    """EUROCONTROL: önceki yıl verisi cari günde bitiyor, yani seride İÇ
    kısmi ay var (2025-09, 8 gün). Uçlara özel eski kural bunu kaçırıyordu.
    """
    from core.charts import kismi_aylari_dus

    aylik = _aylik("2025-08-01", "2025-09-01", "2026-01-01")
    ham = pd.DatetimeIndex(
        list(pd.date_range("2025-08-01", "2025-09-08", freq="D"))
        + list(pd.date_range("2026-01-01", "2026-01-31", freq="D"))
    )
    assert list(kismi_aylari_dus(aylik, ham, "daily").index) == [
        pd.Timestamp("2025-08-01"), pd.Timestamp("2026-01-01")
    ]


def test_kismi_aylari_dus_haftalik_seride_son_haftayi_tam_sayar():
    """Haftalık seride ayın son noktası son yedi güne düşer; ay tamdır."""
    from core.charts import kismi_aylari_dus

    aylik = _aylik("2026-07-01")
    ham = pd.date_range("2026-07-03", "2026-07-31", freq="7D")
    assert len(kismi_aylari_dus(aylik, ham, "daily")) == 0
    assert len(kismi_aylari_dus(aylik, ham, "weekly")) == 1


def test_kismi_aylari_dus_iki_uc_da_eksikse_ikisi_de_duser():
    from core.charts import kismi_aylari_dus

    aylik = _aylik("2026-06-01", "2026-07-01", "2026-08-01")
    ham = pd.date_range("2026-06-28", "2026-08-15", freq="D")
    assert list(kismi_aylari_dus(aylik, ham, "daily").index) == [
        pd.Timestamp("2026-07-01")
    ]


def test_kismi_aylari_dus_bos_df_hata_vermez():
    from core.charts import kismi_aylari_dus

    aylik = pd.DataFrame({"value": []}, index=pd.DatetimeIndex([]))
    sonuc = kismi_aylari_dus(
        aylik, pd.date_range("2026-08-01", "2026-08-15", freq="D"), "daily"
    )
    assert sonuc.empty


def test_aylige_cevir_sum_kismi_ilk_ayi_da_atar():
    """4 günlük 2021-08, 7 kat sahte dip olarak çiziliyordu (M5)."""
    gunler = pd.date_range("2026-06-28", "2026-08-15", freq="D")
    df = pd.DataFrame({"value": [1.0] * len(gunler)}, index=gunler)
    sonuc = aylige_cevir(df, agg="sum", freq="daily")
    assert list(sonuc.index) == [pd.Timestamp("2026-07-01")]


def test_kompozisyon_verisi_hazirla_mutlakta_kismi_ilk_ayi_atar():
    from core.charts import kompozisyon_verisi_hazirla

    gunler = pd.date_range("2026-06-28", "2026-08-15", freq="D")
    df = pd.DataFrame(
        {"A": [1.0] * len(gunler), "B": [2.0] * len(gunler)}, index=gunler
    )
    sonuc = kompozisyon_verisi_hazirla(df, gorunum_mutlak=True, freq="daily")
    assert list(sonuc.index) == [pd.Timestamp("2026-07-01")]


def test_kompozisyon_verisi_hazirla_yuzdede_kismi_uclar_korunur():
    from core.charts import kompozisyon_verisi_hazirla

    gunler = pd.date_range("2026-06-28", "2026-08-15", freq="D")
    df = pd.DataFrame(
        {"A": [1.0] * len(gunler), "B": [3.0] * len(gunler)}, index=gunler
    )
    sonuc = kompozisyon_verisi_hazirla(df, gorunum_mutlak=False, freq="daily")
    assert len(sonuc) == 3  # Haz, Tem, Ağu — kısmi uçlar pay görünümünde geçerli
    assert sonuc.iloc[0]["A"] == pytest.approx(25.0)


def test_kompozisyon_verisi_hazirla_bos_girdide_bos_doner():
    from core.charts import kompozisyon_verisi_hazirla

    df = pd.DataFrame({"A": []}, index=pd.DatetimeIndex([]))
    sonuc = kompozisyon_verisi_hazirla(df, gorunum_mutlak=True, freq="daily")
    assert sonuc.empty


def test_kompozisyon_figuru_hovertemplate_birim_icerir():
    """Unified hover'daki sekiz satır birimsiz çıkıyordu (M4)."""
    from core.charts import kompozisyon_figuru

    df = pd.DataFrame(
        {"Kömür": [1.0], "Rüzgar": [2.0]},
        index=pd.to_datetime(["2026-07-01"]),
    )
    fig = kompozisyon_figuru(df, "GWh")
    for iz in fig.data:
        assert iz.hovertemplate and "GWh" in iz.hovertemplate


def _gunluk_kompozisyon_df(gun_sayisi_haziran=30, gun_sayisi_temmuz=5):
    """Haziran'ı tam, Temmuz'u (Ay tamamlanmamış) kısmi doldurur."""
    idx_haziran = pd.date_range("2026-06-01", periods=gun_sayisi_haziran, freq="D")
    idx_temmuz = pd.date_range("2026-07-01", periods=gun_sayisi_temmuz, freq="D")
    idx = idx_haziran.append(idx_temmuz)
    idx.name = "date"
    return pd.DataFrame({"A": [10.0] * len(idx), "B": [30.0] * len(idx)}, index=idx)


def test_kompozisyon_verisi_hazirla_yuzdede_kismi_son_ay_korunur():
    """Pay % ölçekten bağımsızdır: kısmi ayın kaynak karışımı geçerli bir gözlemdir."""
    from core.charts import kompozisyon_verisi_hazirla

    df = _gunluk_kompozisyon_df()
    sonuc = kompozisyon_verisi_hazirla(df, gorunum_mutlak=False, freq="daily")
    assert list(sonuc.index) == [pd.Timestamp("2026-06-01"), pd.Timestamp("2026-07-01")]
    assert sonuc.loc["2026-07-01", "A"] == pytest.approx(25.0)
    assert sonuc.loc["2026-07-01", "B"] == pytest.approx(75.0)


def test_kompozisyon_verisi_hazirla_mutlakta_kismi_son_ay_dusurulur():
    """GWh (mutlak) görünüm bir ölçektir: kısmi ayın TOPLAMI sahte düşüş gösterir."""
    from core.charts import kompozisyon_verisi_hazirla

    df = _gunluk_kompozisyon_df()
    sonuc = kompozisyon_verisi_hazirla(df, gorunum_mutlak=True, freq="daily")
    assert list(sonuc.index) == [pd.Timestamp("2026-06-01")]
    assert sonuc.loc["2026-06-01", "A"] == pytest.approx(300.0)


def test_kompozisyon_verisi_hazirla_aylik_freqde_dusurulmez():
    """`aylige_cevir`'deki freq != "monthly" koruması burada da geçerli olmalı (M2)."""
    from core.charts import kompozisyon_verisi_hazirla

    idx = pd.date_range("2026-06-01", periods=2, freq="MS", name="date")
    df = pd.DataFrame({"A": [10.0, 10.0], "B": [30.0, 30.0]}, index=idx)
    sonuc = kompozisyon_verisi_hazirla(df, gorunum_mutlak=True, freq="monthly")
    assert list(sonuc.index) == list(idx)


def test_seviye_figuru_x_ekseni_dilden_bagimsiz_bicim_kullanir():
    """Plotly varsayılanı "Jan 2022" derdi; kart içinde mevsimsellik grafiği
    Türkçe ay adları kullanıyor ve ikisi yan yana duruyor.
    """
    df = pd.DataFrame(
        {"value": [1.0, 2.0]}, index=pd.to_datetime(["2026-01-01", "2026-02-01"])
    )
    fig = seviye_figuru(df, "adet")
    assert fig.layout.xaxis.tickformat == "%m.%Y"


def test_hareketli_ortalama_takvim_boslugunu_atlamaz():
    from core.charts import hareketli_ortalama_uygula

    ham = gunluk_df("2026-01-01", 16, 14.0).drop(pd.Timestamp("2026-01-09"))
    sonuc = hareketli_ortalama_uygula(ham, 7)
    assert sonuc.loc[:"2026-01-06", "value"].isna().all()
    assert sonuc.loc["2026-01-07", "value"] == 14.0
    assert sonuc.loc["2026-01-09":"2026-01-15", "value"].isna().all()
    assert sonuc.loc["2026-01-16", "value"] == 14.0
    assert pd.Timestamp("2026-01-09") not in ham.index
    assert ham["value"].eq(14.0).all()
    assert hareketli_ortalama_uygula(ham, None) is ham


def test_gunluk_mevsimsellik_artik_gunu_hizalar_boslugu_korur():
    from core.charts import gunluk_mevsimsellik_figuru

    df = pd.DataFrame(
        {"value": [10.0, 20.0, 30.0, 50.0, 60.0, 70.0]},
        index=pd.to_datetime([
            "2024-02-28", "2024-02-29", "2024-03-01", "2024-03-03",
            "2025-02-28", "2025-03-01",
        ]),
    )
    izler = {iz.name: iz for iz in gunluk_mevsimsellik_figuru(df, "Uçuş").data}
    artik = izler["2024"]
    normal = izler["2025"]
    assert pd.Timestamp(artik.x[1]) == pd.Timestamp("2000-02-29")
    assert artik.y[1] == 20.0
    assert pd.Timestamp(artik.x[2]) == pd.Timestamp(normal.x[1]) == pd.Timestamp("2000-03-01")
    assert pd.Timestamp(artik.x[3]) == pd.Timestamp("2000-03-02")
    assert pd.isna(artik.y[3]) and not artik.connectgaps
    assert list(artik.customdata)[1] == "29.02.2024"
