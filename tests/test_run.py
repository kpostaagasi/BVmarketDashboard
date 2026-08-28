import dataclasses
import sys

import pandas as pd
import pytest

from core.catalog import seri_getir, seri_listele
from ingest.run import _cek


def sahte_df():
    return pd.DataFrame({"date": ["2026-01-01"], "value": [1.0]})


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


def test_cek_epias_serisini_epias_modulune_yonlendirir(monkeypatch):
    import dataclasses

    from core.catalog import seri_getir
    from ingest import run

    cagrildi = {}

    def sahte_seri_cek(seri, tgt, session=None):
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

    def patlayan_epias_cek(seri, tgt, session=None):
        raise AssertionError("tgt yokken epias.seri_cek çağrılmamalı")

    yazilanlar: list[str] = []

    def sahte_seriyi_yaz(seri, df):
        yazilanlar.append(seri.id)
        return len(df)

    monkeypatch.setattr(run.epias, "tgt_al", patlayan_tgt_al)
    monkeypatch.setattr(run.epias, "seri_cek", patlayan_epias_cek)
    monkeypatch.setattr(run.evds, "seri_cek", lambda seri, api_key, session=None, bugun=None: sahte_df())
    monkeypatch.setattr(run.yahoo, "seri_cek", lambda seri, session=None: sahte_df())
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
