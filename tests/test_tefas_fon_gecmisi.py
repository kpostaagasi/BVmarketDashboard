"""TEFAS tek-fon geçmişi: tam ay kapsamı ve eksik yanıt koruması."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from ingest import tefas
from test_tefas import SahteOturum, SahteYanit, yanit_govdesi


@pytest.fixture(autouse=True)
def _beklemeyi_kapat(monkeypatch):
    monkeypatch.setattr(tefas, "_bekle", lambda: None)


def fon_satiri(tarih, fiyat, kod="ADE"):
    return {
        "fonKodu": kod, "fonUnvan": f"{kod} FONU", "tarih": tarih,
        "fiyat": fiyat, "tedPaySayisi": 1000000, "kisiSayisi": 1000,
        "portfoyBuyukluk": fiyat * 1000000,
    }


def test_fon_gecmisi_gunluk_seri_dondurur():
    oturum = SahteOturum(sirali=[SahteYanit(yanit_govdesi([
        fon_satiri("2026-08-28", 0.905655),
        fon_satiri("2026-08-27", 0.899681),
    ]))])
    df = tefas.fon_gecmisi("ADE", "2026-08-01", "2026-08-31", session=oturum)
    assert df.to_dict("list") == {
        "date": ["2026-08-27", "2026-08-28"],
        "fiyat": [0.899681, 0.905655], "pay": [1000000, 1000000],
        "hesap": [1000, 1000], "buyukluk": [899681.0, 905655.0],
    }


def test_fon_gecmisi_pencereyi_asar():
    with pytest.raises(ValueError, match="1 ay"):
        tefas.fon_gecmisi("ADE", "2026-01-01", "2026-12-31", session=SahteOturum())


def test_fon_gecmisi_bos_gunlerden_geriye_inmez():
    df = tefas.fon_gecmisi("ADE", "2026-08-01", "2026-08-31", session=SahteOturum())
    assert df.empty


def test_tam_gecmis_ekim_aralik_ve_csv_hassasiyetini_korur(tmp_path):
    # 428 sentetik iş günü: canlı kaynak paritesi değil, ay döngüsü kanıtı.
    tarihler = pd.bdate_range("2025-01-02", periods=428)
    tarih_metinleri = tarihler.strftime("%Y-%m-%d").tolist()
    fiyatlar = [0.528498 + sira / 1000000 for sira in range(len(tarihler))]
    satirlar = [fon_satiri(gun.strftime("%Y-%m-%d"), fiyat, "AAJ")
                for gun, fiyat in zip(tarihler, fiyatlar)]

    class AylikOturum:
        def post(self, url, data: str, headers=None, timeout=None):
            govde = json.loads(data)
            if govde["fonTipi"] != "EMK":
                return SahteYanit(yanit_govdesi([]))
            bas = pd.Timestamp(govde["basTarih"]).strftime("%Y-%m-%d")
            bit = pd.Timestamp(govde["bitTarih"]).strftime("%Y-%m-%d")
            secilen = [satir for satir in satirlar if bas <= satir["tarih"] <= bit]
            return SahteYanit(yanit_govdesi(list(reversed(secilen))))

    df = tefas.fon_tam_gecmisi("AAJ", tarih_metinleri[0], tarih_metinleri[-1],
                             AylikOturum(), tip="EMK")
    yol = tmp_path / "aaj.csv"
    df.to_csv(yol, index=False)
    okunan = pd.read_csv(yol)
    assert okunan["date"].tolist() == tarihler.strftime("%Y-%m-%d").tolist()
    assert okunan["fiyat"].tolist() == pytest.approx(fiyatlar, abs=1e-12)
    assert okunan["hesap"].tolist() == [1000] * 428


def test_http_hatasi_tam_gecmisi_kismi_dondurmez():
    oturum = SahteOturum(sirali=[
        SahteYanit(yanit_govdesi([fon_satiri("2026-07-31", 0.8)])),
        SahteYanit({"faultCode": "ERR-224"}, status_code=429),
    ])
    with pytest.raises(RuntimeError, match="HTTP 429"):
        tefas.fon_tam_gecmisi("ADE", "2026-07-01", "2026-08-31", oturum)


def test_uygulama_hatasi_bos_veri_sayilmaz():
    oturum = SahteOturum(sirali=[SahteYanit({
        "errorCode": "ERR-001", "errorMessage": "Geçersiz sorgu", "resultList": None,
    })])
    with pytest.raises(RuntimeError, match="uygulama hatası"):
        tefas.fon_gecmisi("ADE", "2026-08-01", "2026-08-31", oturum)


def test_kirpilmis_pencere_reddedilir():
    govde = yanit_govdesi([fon_satiri("2026-08-31", 0.9)])
    govde["toplamSayi"] = 21
    with pytest.raises(RuntimeError, match="eksik pencere"):
        tefas.fon_gecmisi("ADE", "2026-08-01", "2026-08-31",
                          SahteOturum(sirali=[SahteYanit(govde)]))


def test_baska_fonun_satiri_reddedilir():
    govde = yanit_govdesi([fon_satiri("2026-08-31", 0.9, "AAJ")])
    with pytest.raises(RuntimeError, match="fon/tarih uyuşmazlığı"):
        tefas.fon_gecmisi("ADE", "2026-08-01", "2026-08-31",
                          SahteOturum(sirali=[SahteYanit(govde)]))


def test_tam_gecmis_bos_izinle_bos_cerceve_dondurur():
    df = tefas.fon_tam_gecmisi("ADE", "2026-08-01", "2026-08-31",
                               SahteOturum(), bos_izin=True)
    assert df.empty
    assert "fiyat" in df.columns
