import dataclasses
import sys

import pandas as pd
import pytest

from core.catalog import seri_getir, seri_listele
from ingest.run import _cek, olcekle


def sahte_df():
    return pd.DataFrame({"date": ["2026-01-01"], "value": [1.0]})


def tum_adaptorleri_stubla(monkeypatch, haric=()):
    """`main()` katalogdaki HER seriyi gezer: stub'lanmayan bir kaynak tipi
    testi GERÇEK AĞA çıkarır (süre 1 sn'den 7 dakikaya fırlar, sonuç ağ
    durumuna bağlı olur).

    Elle tutulan liste 35+ kaynak tipinin gerisine düştüğü için stub kümesi
    artık `ingest.run`un içe aktardığı MODÜLLERDEN TÜRETİLİR: her ingest
    modülünde tanımlı `seri_cek`, `*_seri_cek`, `fon_tam_gecmisi`,
    `fon_artimi` ve `baraj_doluluk_cek` otomatik stub'lanır. Yeni adaptör eklemek bu
    yardımcıyı güncellemeyi gerektirmez; liste bayatlayamaz.
    """
    import types

    from ingest import run

    for modul in list(vars(run).values()):
        if not isinstance(modul, types.ModuleType):
            continue
        if not modul.__name__.startswith("ingest."):
            continue
        for ad, nesne in list(vars(modul).items()):
            if not callable(nesne) or getattr(nesne, "__module__", None) != modul.__name__:
                continue
            if not (ad == "seri_cek" or ad.endswith("_seri_cek")
                    or ad in {"fon_tam_gecmisi", "fon_artimi",
                              "baraj_doluluk_cek"}):
                continue
            if (modul, ad) in haric:
                continue
            monkeypatch.setattr(modul, ad, lambda *a, **k: sahte_df())


def test_cek_yahoo_serisini_yahoo_moduline_yonlendirir(monkeypatch):
    gorulen = {}

    def sahte(seri, session=None):
        gorulen["id"] = seri.id
        return sahte_df()

    monkeypatch.setattr("ingest.run.yahoo.seri_cek", sahte)
    _cek(seri_getir("emtia-enerji/brent"), None, None, None)
    assert gorulen["id"] == "emtia-enerji/brent"


def test_cek_evds_serisini_evds_moduline_yonlendirir(monkeypatch):
    gorulen = {}

    def sahte(seri, api_key, session=None, bugun=None):
        gorulen["id"] = seri.id
        gorulen["key"] = api_key
        return sahte_df()

    monkeypatch.setattr("ingest.run.evds.seri_cek", sahte)
    _cek(seri_getir("enflasyon/tufe-genel"), "gizli", None, None)
    assert gorulen["id"] == "enflasyon/tufe-genel"
    assert gorulen["key"] == "gizli"


def test_cek_bilinmeyen_kaynak_tipinde_hata():
    seri = dataclasses.replace(seri_getir("enflasyon/tufe-genel"), kaynak_tipi="bloomberg")
    with pytest.raises(ValueError, match="Bilinmeyen kaynak tipi"):
        _cek(seri, "gizli", None, None)


# --- Faz 3f: ölçekleme tek noktada, orchestrator'da ---


def test_cek_evds_serisinde_olcegi_uygular(monkeypatch):
    """EVDS "Bin TL" döner; katalog `olcek`i olmadan KPI okunamaz."""
    monkeypatch.setattr(
        "ingest.run.evds.seri_cek",
        lambda seri, api_key, session=None, bugun=None: pd.DataFrame(
            {"date": ["2026-01-01"], "value": [26_351_644_811.0]}
        ),
    )
    seri = dataclasses.replace(seri_getir("enflasyon/tufe-genel"), olcek=0.000001)
    df = _cek(seri, "gizli", None, None)
    assert df["value"].iloc[0] == pytest.approx(26_351.644811)


def test_cek_olcek_yoksa_degeri_bozmaz(monkeypatch):
    monkeypatch.setattr(
        "ingest.run.evds.seri_cek",
        lambda seri, api_key, session=None, bugun=None: sahte_df(),
    )
    df = _cek(seri_getir("enflasyon/tufe-genel"), "gizli", None, None)
    assert df["value"].iloc[0] == pytest.approx(1.0)


def test_olcekle_tarih_disindaki_tum_sutunlari_olcekler():
    """Bileşenli (geniş) seri: sütun-başına çağrı gerekmez, `date` korunur."""
    df = pd.DataFrame({"date": ["2026-08-01"], "Kömür": [2400.0], "Rüzgar": [240.0]})
    sonuc = olcekle(df, 0.001)
    assert sonuc["Kömür"].iloc[0] == pytest.approx(2.4)
    assert sonuc["Rüzgar"].iloc[0] == pytest.approx(0.24)
    assert sonuc["date"].iloc[0] == "2026-08-01"
    assert df["Kömür"].iloc[0] == 2400.0  # girdi mutasyona uğramaz


def test_cek_epias_serisini_epias_modulune_yonlendirir(monkeypatch):
    import dataclasses

    from core.catalog import seri_getir
    from ingest import run

    cagrildi = {}

    def sahte_seri_cek(seri, tgt, session=None, onbellek=None):
        cagrildi["tgt"] = tgt
        cagrildi["id"] = seri.id
        return "DF"

    monkeypatch.setattr(run.epias, "seri_cek", sahte_seri_cek)
    seri = dataclasses.replace(
        seri_getir("enflasyon/tufe-genel"),
        kaynak_tipi="epias", epias_ucu="ptf", epias_alani="price",
    )
    assert run._cek(seri, "ANAHTAR", "TGT-123", None) == "DF"
    assert cagrildi == {"tgt": "TGT-123", "id": "enflasyon/tufe-genel"}


# --- I2: EPİAŞ TGT girişi hata izolasyonunun İÇİNDE olmalı ---
# (docstring: "Bir serinin başarısızlığı diğerlerini düşürmez" — ama
# tgt_al try/except'in dışındaydı; giriş başarısız olursa main()
# traceback ile ölüyor, EVDS/Yahoo serileri de o gün güncellenmiyordu.)


def test_main_epias_giris_basarisizsa_diger_kaynaklar_calismaya_devam_eder(
    monkeypatch, tmp_path
):
    from ingest import run

    monkeypatch.setenv("EVDS_API_KEY", "sahte-anahtar")
    monkeypatch.setenv("EPIAS_USERNAME", "sahte-kullanici")
    monkeypatch.setenv("EPIAS_PASSWORD", "sahte-parola")
    monkeypatch.setattr(sys, "argv", ["run.py"])

    def patlayan_tgt_al(kullanici, parola, session=None):
        raise RuntimeError("EPİAŞ giriş başarısız: HTTP 503")

    def patlayan_epias_cek(seri, tgt, session=None, onbellek=None):
        raise AssertionError("tgt yokken epias.seri_cek çağrılmamalı")

    yazilanlar: list[str] = []

    def sahte_seriyi_yaz(seri, df):
        yazilanlar.append(seri.id)
        return len(df)

    monkeypatch.setattr(run.epias, "tgt_al", patlayan_tgt_al)
    monkeypatch.setattr(run.epias, "seri_cek", patlayan_epias_cek)
    tum_adaptorleri_stubla(monkeypatch, haric={(run.epias, "seri_cek")})
    monkeypatch.setattr(run, "seriyi_yaz", sahte_seriyi_yaz)

    kod = run.main()

    tum_seriler = seri_listele()
    epias_idler = {s.id for s in tum_seriler if s.kaynak_tipi == "epias"}
    assert epias_idler, "katalogda epias serisi yok"
    diger_idler = {s.id for s in tum_seriler if s.kaynak_tipi != "epias"}

    assert kod == 1, "en az bir hata varsa exit kodu 1 olmalı"
    assert set(yazilanlar) == diger_idler, (
        "epias dışındaki seriler yine yazılmalı"
    )
    assert not (set(yazilanlar) & epias_idler)


def test_main_epias_serileri_tek_onbellek_paylasir(monkeypatch):
    """Aynı uç iki seri için iki kez tam çekiliyordu (M6) — koşu başına
    tek önbellek dict'i tüm epias çağrılarına aynı nesne olarak gitmeli."""
    from ingest import run

    monkeypatch.setenv("EVDS_API_KEY", "sahte-anahtar")
    monkeypatch.setenv("EPIAS_USERNAME", "sahte-kullanici")
    monkeypatch.setenv("EPIAS_PASSWORD", "sahte-parola")
    monkeypatch.setattr(sys, "argv", ["run.py"])

    gorulen_onbellekler = []

    def sahte_epias_cek(seri, tgt, session=None, onbellek=None):
        gorulen_onbellekler.append(onbellek)
        return sahte_df()

    monkeypatch.setattr(run.epias, "tgt_al", lambda k, p, session=None: "TGT-x")
    monkeypatch.setattr(run.epias, "seri_cek", sahte_epias_cek)
    tum_adaptorleri_stubla(monkeypatch, haric={(run.epias, "seri_cek")})
    monkeypatch.setattr(run, "seriyi_yaz", lambda seri, df: len(df))

    assert run.main() == 0
    assert len(gorulen_onbellekler) >= 3  # üç epias serisi var
    assert all(o is not None for o in gorulen_onbellekler)
    assert all(o is gorulen_onbellekler[0] for o in gorulen_onbellekler)


def test_cek_osd_serisini_osd_modulune_yonlendirir(monkeypatch):
    import dataclasses

    from core.catalog import seri_getir
    from ingest import run

    cagrildi = {}

    def sahte_seri_cek(seri, onbellek=None, session=None):
        cagrildi["id"] = seri.id
        cagrildi["onbellek"] = onbellek
        return "DF"

    monkeypatch.setattr(run.osd, "seri_cek", sahte_seri_cek)
    seri = dataclasses.replace(
        seri_getir("enflasyon/tufe-genel"),
        kaynak_tipi="osd", osd_firma="FORD OTOSAN",
        evds_code=None, evds_frequency=None,
    )
    onbellek: dict = {}
    assert run._cek(seri, "ANAHTAR", None, None, None, onbellek) == "DF"
    assert cagrildi["onbellek"] is onbellek


def test_cek_tim_serisini_tim_modulune_yonlendirir(monkeypatch):
    """13 TİM serisi koşu başına tek önbellek paylaşmalı (8 dosya, 104 değil)."""
    import dataclasses

    from core.catalog import seri_getir
    from ingest import run

    cagrildi = {}

    def sahte_seri_cek(seri, onbellek=None, session=None):
        cagrildi["id"] = seri.id
        cagrildi["onbellek"] = onbellek
        return pd.DataFrame({"date": ["2026-01-01"], "value": [1000.0]})

    monkeypatch.setattr(run.tim, "seri_cek", sahte_seri_cek)
    seri = dataclasses.replace(
        seri_getir("enflasyon/tufe-genel"),
        kaynak_tipi="tim", tim_sektor="Çelik", olcek=0.001,
        evds_code=None, evds_frequency=None,
    )
    onbellek: dict = {}
    df = run._cek(seri, "ANAHTAR", None, None, None, None, onbellek)
    assert cagrildi["id"] == "enflasyon/tufe-genel"
    assert cagrildi["onbellek"] is onbellek
    # Bin USD → Milyon USD çevrimi orchestrator'da (faz 3f)
    assert df["value"].iloc[0] == pytest.approx(1.0)


def test_oturum_retry_politikasi_tasir(monkeypatch):
    """Geçici ağ hatası (okuma zaman aşımı, 5xx) tüm günü götürmemeli.

    Ölçüm: 111 serilik tam koşuda EPİAŞ okuma zaman aşımı ve EVDS bağlantı
    kesilmesi iki seriyi düşürmüştü; retry tek noktada, paylaşılan oturumda.
    """
    from ingest import run

    monkeypatch.setenv("EVDS_API_KEY", "sahte")
    monkeypatch.setenv("EPIAS_USERNAME", "sahte")
    monkeypatch.setenv("EPIAS_PASSWORD", "sahte")
    monkeypatch.setattr(sys, "argv", ["run.py", "--only", "enflasyon/tufe-genel"])

    gorulen = {}

    def sahte_evds(seri, api_key, session=None, bugun=None):
        gorulen["adaptor"] = session.get_adapter("https://x/")
        return sahte_df()

    monkeypatch.setattr(run.evds, "seri_cek", sahte_evds)
    monkeypatch.setattr(run, "seriyi_yaz", lambda seri, df: len(df))
    assert run.main() == 0

    retry = gorulen["adaptor"].max_retries
    assert retry.total == 3
    assert 429 in retry.status_forcelist
    assert "POST" in retry.allowed_methods


def test_tefas_fon_csv_yoksa_tam_gecmis_ceker(monkeypatch, tmp_path):
    from datetime import date

    from ingest import run

    seri = seri_getir("fonlar/ade")
    monkeypatch.setattr(run, "seri_yolu", lambda _id: tmp_path / "yok.csv")
    cagri = {}

    def sahte(kod, bas, bit, session=None, tip="YAT", bos_izin=False):
        cagri.update(bas=bas, bit=bit, bos_izin=bos_izin)
        return pd.DataFrame({"date": ["2026-09-21"], "fiyat": [1.0]})

    monkeypatch.setattr(run.tefas, "fon_tam_gecmisi", sahte)
    run.tefas_fon_cek(seri, None, bugun=date(2026, 9, 22))
    assert cagri == {"bas": seri.start_date, "bit": "2026-09-22", "bos_izin": False}


def test_tefas_fon_csv_varsa_son_tarihten_geriye_birlestirir(monkeypatch, tmp_path):
    """Her gün tam geçmiş ~24.000 istek demekti (6 saatlik Actions sınırı)."""
    from datetime import date

    from ingest import run

    yol = tmp_path / "ade.csv"
    pd.DataFrame({
        "date": ["2026-09-01", "2026-09-15", "2026-09-18"],
        "fiyat": [1.0, 2.0, 3.0],
    }).to_csv(yol, index=False)
    monkeypatch.setattr(run, "seri_yolu", lambda _id: yol)
    cagri = {}

    def sahte(kod, bas, bit, session=None, tip="YAT", onbellek=None):
        cagri.update(bas=bas, onbellek=onbellek)
        return pd.DataFrame({"date": ["2026-09-18", "2026-09-21"], "fiyat": [3.5, 4.0]})

    monkeypatch.setattr(run.tefas, "fon_artimi", sahte)
    df = run.tefas_fon_cek(seri_getir("fonlar/ade"), None, bugun=date(2026, 9, 22))
    assert cagri == {"bas": "2026-09-11", "onbellek": None}
    assert df.to_dict("list") == {
        "date": ["2026-09-01", "2026-09-15", "2026-09-18", "2026-09-21"],
        "fiyat": [1.0, 2.0, 3.5, 4.0],
    }


def test_tefas_fon_artimli_bos_pencere_eski_veriyi_korur(monkeypatch, tmp_path):
    from datetime import date

    from ingest import run

    yol = tmp_path / "ade.csv"
    pd.DataFrame({"date": ["2026-09-18"], "fiyat": [3.0]}).to_csv(yol, index=False)
    monkeypatch.setattr(run, "seri_yolu", lambda _id: yol)
    monkeypatch.setattr(
        run.tefas, "fon_artimi",
        lambda *a, **k: pd.DataFrame(columns=["date", "fiyat"]),
    )
    df = run.tefas_fon_cek(seri_getir("fonlar/ade"), None, bugun=date(2026, 9, 22))
    assert df.to_dict("list") == {"date": ["2026-09-18"], "fiyat": [3.0]}


def test_main_freq_filtresi_yalnizca_secilen_sikliklari_ceker(monkeypatch):
    from ingest import run

    monkeypatch.setenv("EVDS_API_KEY", "sahte")
    monkeypatch.setenv("EPIAS_USERNAME", "sahte")
    monkeypatch.setenv("EPIAS_PASSWORD", "sahte")
    monkeypatch.setattr(sys, "argv", ["run.py", "--freq", "weekly, yearly"])
    monkeypatch.setattr(run.epias, "tgt_al", lambda k, p, session=None: "TGT")
    tum_adaptorleri_stubla(monkeypatch)
    yazilanlar = []
    monkeypatch.setattr(
        run, "seriyi_yaz", lambda seri, df: yazilanlar.append(seri) or len(df),
    )
    assert run.main() == 0
    beklenen = {s.id for s in seri_listele() if s.freq in {"weekly", "yearly"}}
    assert beklenen and {s.id for s in yazilanlar} == beklenen


def test_main_freq_filtresi_bos_kalirsa_hata(monkeypatch):
    from ingest import run

    monkeypatch.setattr(sys, "argv", ["run.py", "--freq", "saatlik"])
    assert run.main() == 2


def test_tefas_fonlari_gun_onbellegini_paylasir(monkeypatch, tmp_path):
    """969 fon aynı günleri paylaşır: istek sayısı fon sayısına değil gün
    sayısına bağlı olmalı (fon başına istek 7 sn ritmiyle ~113 dk ederdi)."""
    from datetime import date

    from ingest import run

    def yol_ver(seri_id):
        yol = tmp_path / f"{seri_id.replace('/', '_')}.csv"
        if not yol.exists():
            pd.DataFrame({"date": ["2026-09-21"], "fiyat": [1.0]}).to_csv(
                yol, index=False)
        return yol

    monkeypatch.setattr(run, "seri_yolu", yol_ver)
    gunler = []

    def sahte_gun_cek(tip, gun, session=None):
        gunler.append((tip, gun))
        return [{"fonKodu": "ADE", "tarih": gun.isoformat(), "fiyat": 1.0,
                 "tedPaySayisi": 1, "kisiSayisi": 1, "portfoyBuyukluk": 1.0}]

    monkeypatch.setattr(run.tefas, "_gun_cek", sahte_gun_cek)
    monkeypatch.setattr(run.tefas, "_bekle", lambda: None)
    onbellek: dict = {}
    for seri_id in ("fonlar/ade", "fonlar/aal", "fonlar/ahl"):
        seri = dataclasses.replace(seri_getir("fonlar/ade"), id=seri_id)
        run.tefas_fon_cek(seri, None, bugun=date(2026, 9, 23),
                          gun_onbellek=onbellek)
    # Pencere: son tarihten TEFAS_GERI_GUN geri (09-14) → bugün (09-23).
    # Üç fon × on gün = 30 istek yerine gün başına tek istek.
    assert gunler == [("YAT", date(2026, 9, gun)) for gun in range(14, 24)]


def test_main_ardisik_hatada_kaynagi_gecer(monkeypatch):
    """Yanıt vermeyen uç seri başına dakikalar yiyip işi zaman sınırına
    taşıyordu (22 Eylül 2026: TEFAS'ta tek seride 85 dk)."""
    from ingest import run

    monkeypatch.setenv("EVDS_API_KEY", "sahte")
    monkeypatch.setenv("EPIAS_USERNAME", "sahte")
    monkeypatch.setenv("EPIAS_PASSWORD", "sahte")
    monkeypatch.setattr(sys, "argv", ["run.py", "--freq", "monthly"])
    monkeypatch.setattr(run.epias, "tgt_al", lambda k, p, session=None: "TGT")
    tum_adaptorleri_stubla(monkeypatch)
    monkeypatch.setattr(run, "seriyi_yaz", lambda seri, df: len(df))

    denemeler = []

    def patlayan(*a, **k):
        denemeler.append(1)
        raise RuntimeError("okuma zaman aşımı")

    monkeypatch.setattr(run.tim, "il_seri_cek", patlayan)
    assert run.main() == 1
    # 741 tim_il serisi var; tavana gelince kalanlar denenmeden geçilir.
    assert len(denemeler) == run.ARDISIK_HATA_TAVANI


def test_main_arada_basari_ardisik_sayaci_sifirlar(monkeypatch):
    from ingest import run

    monkeypatch.setenv("EVDS_API_KEY", "sahte")
    monkeypatch.setattr(sys, "argv", ["run.py", "--freq", "yearly"])
    tum_adaptorleri_stubla(monkeypatch)
    monkeypatch.setattr(run, "seriyi_yaz", lambda seri, df: len(df))
    sira = {"n": 0}

    def bir_atla(*a, **k):
        sira["n"] += 1
        if sira["n"] % 2:
            raise RuntimeError("geçici")
        return sahte_df()

    monkeypatch.setattr(run.turkbesd, "seri_cek", bir_atla)
    assert run.main() == 1
    # 24 yıllık turkbesd serisi: hatalar ardışık olmadığı için hiçbiri geçilmez.
    assert sira["n"] == 24
