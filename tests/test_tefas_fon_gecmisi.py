"""TEFAS tek-fon günlük geçmiş (fon_gecmisi) testleri.

Ağ tamamen sahte; hız sınırlama beklemeleri monkeypatch'lenir.
Kart semantiği ölçümünden gelen sözleşme:

- Tek fon, 1 ayı aşmayan pencereler; her pencere tek istek.
- Yanıt satırı: {fonKodu, fonUnvan, tarih, fiyat, tedPaySayisi,
  kisiSayisi, portfoyBuyukluk}.
- Pencere boş (hafta sonu/tatil) → satır yok, PENCERE_GUN adımıyla geriye.
- Pencere sınırı: başlangıç 5 yıldan eski olamaz (AZAMI_GECMIS_YIL).
"""

from __future__ import annotations

import json

import pytest

from ingest import tefas

from test_tefas import SahteOturum, SahteYanit, yanit_govdesi


@pytest.fixture(autouse=True)
def _beklemeyi_kapat(monkeypatch):
    monkeypatch.setattr(tefas, "_bekle", lambda: None)
    monkeypatch.setattr(tefas.time, "sleep", lambda saniye: None)


def fon_satiri(tarih, fiyat):
    return {
        "fonKodu": "ADE", "fonUnvan": "ADE FONU", "tarih": tarih,
        "fiyat": fiyat, "tedPaySayisi": 1000000, "kisiSayisi": 1000,
        "portfoyBuyukluk": fiyat * 1000000, "borsaBultenFiyat": None,
        "rn": 1,
    }


def pencere_istegi(bas, bit):
    return json.dumps({
        "fonTipi": "YAT", "fonKodu": "ADE", "aramaMetni": None,
        "fonTurKod": None, "fonGrubu": None, "sfonTurKod": None,
        "basTarih": bas, "bitTarih": bit, "basSira": 1,
        "bitSira": 5000, "fonTurAciklama": None, "dil": "TR",
        "kurucuKod": None,
    })


def test_fon_gecmisi_gunluk_seri_dondurur():
    """Bir aylık pencere: 3 iş günü → 3 satır, tarih artan."""
    oturum = SahteOturum()
    oturum.sirali = [
        SahteYanit(yanit_govdesi([
            fon_satiri("2026-08-28", 0.9), fon_satiri("2026-08-27", 0.89),
        ])),
    ]
    df = tefas.fon_gecmisi("ADE", "2026-08-01", "2026-08-31", session=oturum)
    assert list(df.columns) == ["date", "value"]
    assert df["date"].tolist() == ["2026-08-27", "2026-08-28"]
    assert df["value"].tolist() == [0.89, 0.9]


def test_fon_gecmisi_pencereyi_asar():
    """31 gün üstü pencere ValueError: uç 1 ay sınırı (ölçülmüş)."""
    oturum = SahteOturum()
    with pytest.raises(ValueError, match="1 ay"):
        tefas.fon_gecmisi("ADE", "2026-01-01", "2026-12-31", session=oturum)


def test_fon_gecmisi_bos_gunlerden_geriye_inmez():
    """İstek aralığındaki günler boşsa boş veri döner ama hata vermez:
    fonun o pencerede yayını yok — çağıran pencereyi kaydırır."""
    oturum = SahteOturum()
    oturum.sirali = [SahteYanit({"errorCode": None,
        "errorMessage": "Index 0 out of bounds for length 0",
        "resultList": None, "toplamSayi": None, "toplamSayfa": None})]
    df = tefas.fon_gecmisi("ADE", "2026-08-01", "2026-08-31", session=oturum)
    assert df.empty
