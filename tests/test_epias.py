from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from ingest.epias import noktalari_ayikla, pencereleri_bol, seri_cek, tgt_al


def yanit(kayitlar):
    return {"items": kayitlar}


def _gun(tarih: str, alan: str, deger) -> list[dict]:
    """24 saatlik TAM bir günün kayıtlarını üretir.

    `deger` tek sayıysa tüm saatler aynı değeri taşır; sözlükse
    (saat -> değer) yalnızca verilen saatler üretilir — kesik gün
    simüle etmek için `_gun(...)[:12]` gibi dilimlemek de mümkün
    (liste saat 0..23 sırasında döner).
    """
    if isinstance(deger, dict):
        saatler = sorted(deger.items())
    else:
        saatler = [(saat, deger) for saat in range(24)]
    return [
        {"date": f"{tarih}T{saat:02d}:00:00+03:00", alan: v}
        for saat, v in saatler
    ]


def test_noktalari_ayikla_tarih_ve_degeri_cikarir():
    ham = yanit([
        {"date": "2026-08-01T00:00:00+03:00", "price": 2500.0},
        {"date": "2026-08-01T01:00:00+03:00", "price": 2450.5},
    ])
    assert noktalari_ayikla(ham, "price") == [
        ("2026-08-01", 2500.0),
        ("2026-08-01", 2450.5),
    ]


def test_noktalari_ayikla_bos_degeri_atlar():
    ham = yanit([
        {"date": "2026-08-01T00:00:00+03:00", "price": None},
        {"date": "2026-08-02T00:00:00+03:00", "price": 2450.5},
    ])
    assert noktalari_ayikla(ham, "price") == [("2026-08-02", 2450.5)]


def test_noktalari_ayikla_bos_listede_bos_doner():
    assert noktalari_ayikla(yanit([]), "price") == []


def test_noktalari_ayikla_eksik_alanda_hata_verir():
    ham = yanit([{"date": "2026-08-01T00:00:00+03:00"}])
    with pytest.raises(KeyError):
        noktalari_ayikla(ham, "price")


def test_noktalari_ayikla_uretim_alaninda_total_okur():
    # Gerçek üretim gövdesi: date + hour + total + kaynak bazlı alanlar
    ham = yanit([
        {"date": "2026-08-01T00:00:00+03:00", "hour": "00:00",
         "total": 45231.61, "naturalGas": 2575.4, "dammedHydro": 12419.11,
         "wind": 10148.79},
    ])
    assert noktalari_ayikla(ham, "total") == [("2026-08-01", 45231.61)]


class SahteYanit:
    def __init__(self, status_code, govde=None, metin=""):
        self.status_code = status_code
        self._govde = govde or {}
        self.text = metin

    def json(self):
        return self._govde


class SahteOturum:
    """Her `post` çağrısını kaydeder.

    `yanit` tek bir SahteYanit ise her çağrıda aynısı döner (çoğu test için
    yeterli — kaç dilime bölündüğü umursanmıyor). Liste verilirse çağrı
    sırasına göre tüketilir (parçalı çekimi birebir test etmek için).

    `cagrilan_url` / `gonderilen_govde` / `gonderilen_basliklar` SON
    çağrıyı yansıtır (eski testlerle uyumluluk); `cagrilar` TÜM çağrıları
    sırasıyla tutar (yeni parçalı-çekim testleri için).
    """

    def __init__(self, yanit):
        self._yanitlar = yanit if isinstance(yanit, list) else None
        self._sabit_yanit = None if self._yanitlar is not None else yanit
        self.cagrilar: list[dict] = []

    def post(self, url, headers=None, data=None, json=None, timeout=None):
        govde = json if json is not None else data
        self.cagrilar.append({"url": url, "headers": headers, "govde": govde})
        if self._yanitlar is not None:
            return self._yanitlar[len(self.cagrilar) - 1]
        return self._sabit_yanit

    @property
    def cagrilan_url(self):
        return self.cagrilar[-1]["url"] if self.cagrilar else None

    @property
    def gonderilen_govde(self):
        return self.cagrilar[-1]["govde"] if self.cagrilar else None

    @property
    def gonderilen_basliklar(self):
        return self.cagrilar[-1]["headers"] if self.cagrilar else None


# --- tgt_al ---


def test_tgt_al_basarili_ticketi_doner():
    oturum = SahteOturum(SahteYanit(200, metin="TGT-123-abc-cas"))
    assert tgt_al("kullanici", "parola", session=oturum) == "TGT-123-abc-cas"


def test_tgt_al_kullanici_ve_parolayi_form_ile_gonderir():
    oturum = SahteOturum(SahteYanit(200, metin="TGT-xyz"))
    tgt_al("kullanici@example.com", "gizli-parola", session=oturum)
    assert oturum.gonderilen_govde == {
        "username": "kullanici@example.com",
        "password": "gizli-parola",
    }


def test_tgt_al_http_hatasinda_yukselir():
    oturum = SahteOturum(SahteYanit(401, metin="Unauthorized"))
    with pytest.raises(RuntimeError, match="401"):
        tgt_al("kullanici", "parola", session=oturum)


def test_tgt_al_beklenmeyen_govdede_yukselir():
    oturum = SahteOturum(SahteYanit(200, metin="<html>hata</html>"))
    with pytest.raises(RuntimeError, match="TGT"):
        tgt_al("kullanici", "parola", session=oturum)


# --- pencereleri_bol (saf, ağsız) ---


def test_pencereleri_bol_tam_bolunen_araligi_esit_parcalara_ayirir():
    pencereler = pencereleri_bol(date(2024, 1, 1), date(2024, 1, 22), azami_gun=10)
    assert pencereler == [
        (date(2024, 1, 1), date(2024, 1, 11)),
        (date(2024, 1, 12), date(2024, 1, 22)),
    ]


def test_pencereleri_bol_kalan_kisa_dilimi_ayri_dondurur():
    pencereler = pencereleri_bol(date(2024, 1, 1), date(2024, 1, 26), azami_gun=10)
    assert pencereler == [
        (date(2024, 1, 1), date(2024, 1, 11)),
        (date(2024, 1, 12), date(2024, 1, 22)),
        (date(2024, 1, 23), date(2024, 1, 26)),
    ]


def test_pencereleri_bol_kisa_aralik_tek_dilim_doner():
    pencereler = pencereleri_bol(date(2024, 1, 1), date(2024, 1, 6), azami_gun=10)
    assert pencereler == [(date(2024, 1, 1), date(2024, 1, 6))]


def test_pencereleri_bol_sinir_durumu_tam_azami_gun_tek_dilim_doner():
    bitis = date(2024, 1, 1) + timedelta(days=89)
    pencereler = pencereleri_bol(date(2024, 1, 1), bitis, azami_gun=89)
    assert pencereler == [(date(2024, 1, 1), bitis)]


def test_pencereleri_bol_bir_gun_asinca_iki_dilime_boler():
    bitis = date(2024, 1, 1) + timedelta(days=90)
    pencereler = pencereleri_bol(date(2024, 1, 1), bitis, azami_gun=89)
    assert len(pencereler) == 2


def test_pencereleri_bol_ardisik_dilimler_arasinda_bosluk_ve_cakisma_olmaz():
    pencereler = pencereleri_bol(date(2020, 1, 1), date(2026, 8, 27), azami_gun=89)
    assert pencereler[0][0] == date(2020, 1, 1)
    assert pencereler[-1][1] == date(2026, 8, 27)
    for onceki, sonraki in zip(pencereler, pencereler[1:]):
        assert sonraki[0] == onceki[1] + timedelta(days=1), "boşluk ya da çakışma var"
    for baslangic, bitis in pencereler:
        assert (bitis - baslangic).days <= 89


def test_pencereleri_bol_baslangic_bitisten_sonraysa_hata():
    with pytest.raises(ValueError):
        pencereleri_bol(date(2024, 1, 10), date(2024, 1, 1))


# --- seri_cek ---


def _epias_seri(**kwargs):
    varsayilan = dict(
        id="elektrik/ptf",
        epias_ucu="ptf",
        epias_alani="price",
        monthly_agg="mean",
        start_date=None,
        olcek=1.0,
    )
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


def test_seri_cek_http_hatasinda_yukselir():
    oturum = SahteOturum(SahteYanit(500))
    with pytest.raises(RuntimeError, match="500"):
        seri_cek(_epias_seri(), "TGT-abc", session=oturum)


def test_seri_cek_bos_seride_yukselir():
    oturum = SahteOturum(SahteYanit(200, yanit([])))
    with pytest.raises(RuntimeError, match="boş"):
        seri_cek(_epias_seri(), "TGT-abc", session=oturum)


def test_seri_cek_tgt_basligini_gonderir():
    oturum = SahteOturum(SahteYanit(200, yanit([
        {"date": "2026-08-01T00:00:00+03:00", "price": 2500.0},
    ])))
    seri_cek(_epias_seri(), "TGT-abc", session=oturum)
    assert oturum.gonderilen_basliklar["TGT"] == "TGT-abc"


def test_seri_cek_mean_serisi_gunluk_ortalama_alir():
    # PTF gibi monthly_agg="mean" seriler: aynı günün saatlik değerleri
    # ORTALAMASI alınmalı, toplamı değil. Gün TAM 24 saat içeriyor (C1
    # kuralı: eksik saatli günler atılır) — 12 saat 100, 12 saat 300.
    oturum = SahteOturum(SahteYanit(200, yanit(
        _gun("2026-08-01", "price", {**{s: 100.0 for s in range(12)},
                                      **{s: 300.0 for s in range(12, 24)}})
    )))
    df = seri_cek(_epias_seri(monthly_agg="mean", start_date="2026-07-25"),
                  "TGT-abc", session=oturum, bugun=date(2026, 8, 1))
    assert list(df.columns) == ["date", "value"]
    assert len(df) == 1
    assert df.iloc[0]["value"] == pytest.approx(200.0)


def test_seri_cek_sum_serisi_gunluk_toplam_alir():
    # Üretim gibi monthly_agg="sum" seriler: saatlik MWh'lerin günlük
    # TOPLAMI alınmalı — ortalaması alınırsa değer 1/24'üne düşer. Gün
    # TAM 24 saat içeriyor (C1 kuralı); burada dar bir pencere (tek
    # dilim) kullanılıyor ki toplam dilim tekrarından etkilenmesin.
    oturum = SahteOturum(SahteYanit(200, yanit(
        _gun("2026-08-01", "total", 2000.0)  # 24 saat x 2000 = 48000
    )))
    seri = _epias_seri(id="elektrik/uretim", epias_ucu="uretim",
                        epias_alani="total", monthly_agg="sum",
                        start_date="2026-07-25")
    df = seri_cek(seri, "TGT-abc", session=oturum, bugun=date(2026, 8, 1))
    assert len(oturum.cagrilar) == 1
    assert df.iloc[0]["value"] == pytest.approx(48000.0)


def test_seri_cek_olceklendirmeyi_indirgemeden_sonra_uygular():
    # Üretim MWh döner, GWh olarak gösterilecek: olcek=0.001.
    # Ölçekleme günlük TOPLAMDAN sonra uygulanmalı (48000 * 0.001 = 48.0),
    # tek tek saatlik değerlere değil.
    oturum = SahteOturum(SahteYanit(200, yanit(
        _gun("2026-08-01", "total", 2000.0)
    )))
    seri = _epias_seri(id="elektrik/uretim", epias_ucu="uretim",
                        epias_alani="total", monthly_agg="sum", olcek=0.001,
                        start_date="2026-07-25")
    df = seri_cek(seri, "TGT-abc", session=oturum, bugun=date(2026, 8, 1))
    assert df.iloc[0]["value"] == pytest.approx(48.0)


# --- C1: eksik saatli günler günlük indirgemeden önce düşülmeli ---
# (bkz. ingest/epias.py seri_cek docstring'i — son dilimin endDate'i bugün
# olduğu için EPİAŞ o gün yalnızca yayınlanmış saatleri döner; groupby(...)
# bunu günün bir kesri olan, ama günlük toplam/ortalama gibi görünen bir
# sayıya indirger. Kural yalnızca son güne özel değil, genel: "24 saatlik
# kaydı olmayan gün atılır".)


def test_seri_cek_eksik_saatli_son_gun_mean_serisinde_atilir():
    # 2026-08-01 tam (24 saat, 100.0); 2026-08-02 kesik (yalnızca ilk 12
    # saat yayınlanmış, henüz tamamlanmamış son gün senaryosu).
    kayitlar = (
        _gun("2026-08-01", "price", 100.0)
        + _gun("2026-08-02", "price", 300.0)[:12]
    )
    oturum = SahteOturum(SahteYanit(200, yanit(kayitlar)))
    seri = _epias_seri(monthly_agg="mean", start_date="2026-07-25")
    df = seri_cek(seri, "TGT-abc", session=oturum, bugun=date(2026, 8, 2))
    assert list(df["date"]) == ["2026-08-01"]
    assert df.iloc[0]["value"] == pytest.approx(100.0)


def test_seri_cek_eksik_saatli_son_gun_sum_serisinde_atilir():
    kayitlar = (
        _gun("2026-08-01", "total", 1000.0)
        + _gun("2026-08-02", "total", 2000.0)[:12]
    )
    oturum = SahteOturum(SahteYanit(200, yanit(kayitlar)))
    seri = _epias_seri(id="elektrik/uretim", epias_ucu="uretim",
                        epias_alani="total", monthly_agg="sum",
                        start_date="2026-07-25")
    df = seri_cek(seri, "TGT-abc", session=oturum, bugun=date(2026, 8, 2))
    assert list(df["date"]) == ["2026-08-01"]
    assert df.iloc[0]["value"] == pytest.approx(24000.0)


def test_seri_cek_ilk_gun_de_eksikse_atilir():
    # Kural son güne özel değil: start_date gün ortasına denk gelirse ilk
    # gün de eksik olabilir.
    kayitlar = (
        _gun("2026-07-25", "price", 500.0)[12:]  # ilk gün kesik (12 saat)
        + _gun("2026-07-26", "price", 100.0)  # tam gün
    )
    oturum = SahteOturum(SahteYanit(200, yanit(kayitlar)))
    seri = _epias_seri(monthly_agg="mean", start_date="2026-07-25")
    df = seri_cek(seri, "TGT-abc", session=oturum, bugun=date(2026, 7, 26))
    assert list(df["date"]) == ["2026-07-26"]


def test_seri_cek_ptf_ucunu_dogru_yola_ister():
    oturum = SahteOturum(SahteYanit(200, yanit([
        {"date": "2026-08-01T00:00:00+03:00", "price": 2500.0},
    ])))
    seri_cek(_epias_seri(), "TGT-abc", session=oturum)
    assert oturum.cagrilan_url.endswith(
        "/electricity-service/v1/markets/dam/data/mcp"
    )


def test_seri_cek_uretim_ucunu_dogru_yola_ister():
    oturum = SahteOturum(SahteYanit(200, yanit([
        {"date": "2026-08-01T00:00:00+03:00", "total": 45000.0},
    ])))
    seri = _epias_seri(id="elektrik/uretim", epias_ucu="uretim",
                        epias_alani="total")
    seri_cek(seri, "TGT-abc", session=oturum)
    assert oturum.cagrilan_url.endswith(
        "/electricity-service/v1/generation/data/realtime-generation"
    )


def test_seri_cek_start_date_varsa_ilk_dilim_ondan_baslar_son_dilim_bugunde_biter():
    oturum = SahteOturum(SahteYanit(200, yanit([
        {"date": "2026-08-01T00:00:00+03:00", "price": 2500.0},
    ])))
    seri = _epias_seri(start_date="2020-01-01")
    seri_cek(seri, "TGT-abc", session=oturum, bugun=date(2026, 8, 27))
    ilk_govde = oturum.cagrilar[0]["govde"]
    son_govde = oturum.cagrilar[-1]["govde"]
    assert ilk_govde["startDate"] == "2020-01-01T00:00:00+03:00"
    assert son_govde["endDate"] == "2026-08-27T00:00:00+03:00"
    # 2020-01-01 → 2026-08-27 ~6.5 yıl; 89 günlük sınıra tek istekte sığmaz.
    assert len(oturum.cagrilar) > 1


def test_seri_cek_start_date_yoksa_varsayilan_pencere_coklu_yil_ve_parcali():
    # Varsayılan pencere artık 89 gün değil (o zaman mevsimsellik grafiği
    # tek yarım yıllık çizgi kalıyordu); EVDS/Yahoo ile tutarlı biçimde
    # birden çok yıl olmalı. Ama EPİAŞ tek istekte 3 aydan fazlasını kabul
    # etmiyor, o yüzden bu çok-yıllık pencere PARÇALI istenmeli — her
    # tekil dilim 89 günü aşmamalı.
    oturum = SahteOturum(SahteYanit(200, yanit([
        {"date": "2026-08-01T00:00:00+03:00", "price": 2500.0},
    ])))
    seri = _epias_seri(start_date=None)
    bugun = date(2026, 8, 27)
    seri_cek(seri, "TGT-abc", session=oturum, bugun=bugun)

    ilk_baslangic = date.fromisoformat(oturum.cagrilar[0]["govde"]["startDate"][:10])
    assert (bugun - ilk_baslangic).days >= 365 * 4, "varsayılan pencere en az ~4-5 yıl olmalı"
    assert len(oturum.cagrilar) > 1, "çok yıllık pencere tek istekte gönderilemez"
    for cagri in oturum.cagrilar:
        b = date.fromisoformat(cagri["govde"]["startDate"][:10])
        e = date.fromisoformat(cagri["govde"]["endDate"][:10])
        assert (e - b).days <= 89, "her dilim EPİAŞ'ın 3 aylık sınırını aşmamalı"


def test_seri_cek_parcali_yanitlari_birlestirir_tarih_artan_ve_tekil():
    # Her dilim TAM 24 saatlik bir gün döndürüyor (C1 kuralı: eksik saatli
    # günler düşülür — burada dilim birleştirme davranışı test ediliyor,
    # gün tamlığı değil).
    oturum = SahteOturum([
        SahteYanit(200, yanit(_gun("2024-01-01", "price", 100.0))),
        SahteYanit(200, yanit(_gun("2024-04-01", "price", 200.0))),
    ])
    seri = _epias_seri(start_date="2024-01-01")
    df = seri_cek(seri, "TGT-abc", session=oturum, bugun=date(2024, 4, 1))
    assert len(oturum.cagrilar) == 2
    assert list(df["date"]) == ["2024-01-01", "2024-04-01"]
    assert df["date"].is_unique
    assert list(df["date"]) == sorted(df["date"])
    assert list(df["value"]) == pytest.approx([100.0, 200.0])


# --- I3: dilim başına boşluk kontrolü ---


def test_seri_cek_orta_dilim_bos_donerse_hangi_dilim_oldugunu_belirtir():
    # Parçalı çekimde bir dilim HTTP 200 ile boş items dönerse (regresyon:
    # tek istekli eski hâlde bu senaryo zaten hataydı), o dilimin kapsadığı
    # günler sessizce kaybolmamalı — hangi dilim olduğu hataya yazılmalı.
    baslangic = date(2024, 1, 1)
    ilk_dilim_bitis = baslangic + timedelta(days=89)
    ikinci_dilim_baslangic = ilk_dilim_bitis + timedelta(days=1)
    bugun = baslangic + timedelta(days=100)  # 89 günü aşar -> 2 dilim
    oturum = SahteOturum([
        SahteYanit(200, yanit(_gun("2024-01-01", "price", 100.0))),
        SahteYanit(200, yanit([])),  # ikinci dilim boş
    ])
    seri = _epias_seri(start_date=baslangic.isoformat())
    with pytest.raises(RuntimeError) as hata:
        seri_cek(seri, "TGT-abc", session=oturum, bugun=bugun)
    mesaj = str(hata.value)
    assert "boş" in mesaj
    assert ikinci_dilim_baslangic.isoformat() in mesaj
