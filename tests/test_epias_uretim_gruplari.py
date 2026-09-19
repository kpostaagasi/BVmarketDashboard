"""`noktalari_ayikla`nın çoklu-alan toplama modu testleri (Faz: enerji
kalan aileler — kaynak bazlı üretim GWh serileri).

`epias_alani` katalogda bir liste verilirse `serileri_yukle` bunu tuple'a
çevirir ve `seri_cek` aynen tek-alanlı yoldaki gibi `noktalari_ayikla`'ya
geçirir — pencere bölme/eksik-saat filtresi DEĞİŞMEZ (bkz. `test_epias.py`,
bu dosya yalnızca alan toplama davranışını hedefler). Ağustos 2026 canlı
ölçümüyle (Doğalgaz=naturalGas+lng, Hidroelektrik=dammedHydro+river,
Kömür=importCoal+lignite+blackCoal+asphaltiteCoal) MarketVisuals'ın
energy_mix.html kartlarıyla BİREBİR (yuvarlama farkı ≤0,1 GWh) eşleşti.
"""

from datetime import date
from types import SimpleNamespace

import pytest

from ingest.epias import noktalari_ayikla, seri_cek


def yanit(kayitlar):
    return {"items": kayitlar}


def _gun(tarih: str, **degerler) -> list[dict]:
    """24 saatlik TAM bir günün kayıtlarını üretir, her saat aynı değerler."""
    return [
        {"date": f"{tarih}T{saat:02d}:00:00+03:00", **degerler}
        for saat in range(24)
    ]


# --- noktalari_ayikla: tekli alan davranışı DEĞİŞMEMELİ (geriye dönük uyum) ---


def test_noktalari_ayikla_tekli_string_alan_eskisi_gibi_calisir():
    ham = yanit([{"date": "2026-08-01T00:00:00+03:00", "total": 45231.61}])
    assert noktalari_ayikla(ham, "total") == [("2026-08-01", 45231.61)]


# --- noktalari_ayikla: çoklu alan toplama (yeni davranış) ---


def test_noktalari_ayikla_coklu_alan_toplar():
    ham = yanit([
        {"date": "2026-08-01T00:00:00+03:00", "naturalGas": 2575.4, "lng": 100.0},
    ])
    assert noktalari_ayikla(ham, ("naturalGas", "lng")) == [("2026-08-01", 2675.4)]


def test_noktalari_ayikla_coklu_alanda_herhangi_biri_none_ise_saat_atlanir():
    """Bir kaynağın üretimini sessizce eksik göstermemek için (bkz.
    `bilesen_noktalari_ayikla`daki aynı ilke) HERHANGİ biri None ise saat
    tamamen düşer — 0 sayılmaz."""
    ham = yanit([
        {"date": "2026-08-01T00:00:00+03:00", "naturalGas": 2575.4, "lng": None},
        {"date": "2026-08-01T01:00:00+03:00", "naturalGas": 100.0, "lng": 50.0},
    ])
    assert noktalari_ayikla(ham, ("naturalGas", "lng")) == [("2026-08-01", 150.0)]


def test_noktalari_ayikla_coklu_alanda_bilinmeyen_alan_hata_verir():
    ham = yanit([{"date": "2026-08-01T00:00:00+03:00", "naturalGas": 100.0}])
    with pytest.raises(KeyError):
        noktalari_ayikla(ham, ("naturalGas", "yokBoyleAlan"))


def test_noktalari_ayikla_dort_alanli_komur_grubu_toplar():
    """Kömür grubu: importCoal+lignite+blackCoal+asphaltiteCoal (bkz.
    `elektrik/uretim-kompozisyon`daki AYNI grup tanımı)."""
    ham = yanit([{
        "date": "2026-08-01T00:00:00+03:00",
        "importCoal": 100.0, "lignite": 50.0, "blackCoal": 10.0, "asphaltiteCoal": 5.0,
    }])
    alan = ("importCoal", "lignite", "blackCoal", "asphaltiteCoal")
    assert noktalari_ayikla(ham, alan) == [("2026-08-01", 165.0)]


# --- seri_cek: uçtan uca, çoklu alanlı seri de pencere/eksik-gün kuralına uyar ---


def _epias_seri(**kwargs):
    varsayilan = dict(
        id="elektrik/uretim-dogalgaz",
        epias_ucu="uretim",
        epias_alani=("naturalGas", "lng"),
        epias_bilesenler=None,
        monthly_agg="sum",
        start_date="2026-07-25",  # dar pencere: tek dilim, tekrar riski yok
        olcek=1.0,
    )
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


class SahteYanit:
    def __init__(self, status_code, govde=None):
        self.status_code = status_code
        self._govde = govde or {}

    def json(self):
        return self._govde


class SahteOturum:
    def __init__(self, yanit):
        self._yanit = yanit
        self.istek_sayisi = 0

    def post(self, url, headers=None, json=None, timeout=None):
        self.istek_sayisi += 1
        return self._yanit


def test_seri_cek_coklu_alanli_seri_gunluk_toplam_doner():
    kayitlar = _gun("2026-08-01", naturalGas=100.0, lng=25.0)
    oturum = SahteOturum(SahteYanit(200, yanit(kayitlar)))
    df = seri_cek(_epias_seri(), "TGT-abc", session=oturum, bugun=date(2026, 8, 1))
    assert oturum.istek_sayisi == 1
    assert df.iloc[0]["value"] == pytest.approx(24 * 125.0)


def test_seri_cek_coklu_alanli_seride_eksik_saatli_gun_atilir():
    """Faz 3b C1 kuralı çoklu-alan yolunda da geçerli: 2026-08-01 tam (24
    saat), 2026-08-02 kesik (yalnızca ilk 12 saat) — kesik gün düşmeli."""
    kayitlar = _gun("2026-08-01", naturalGas=100.0, lng=25.0) + _gun(
        "2026-08-02", naturalGas=100.0, lng=25.0
    )[:12]
    oturum = SahteOturum(SahteYanit(200, yanit(kayitlar)))
    df = seri_cek(_epias_seri(), "TGT-abc", session=oturum, bugun=date(2026, 8, 2))
    assert list(df["date"]) == ["2026-08-01"]


def test_seri_cek_coklu_alanli_seri_value_sutunu_dondurur():
    """Wide (bileşen) formatın AKSİNE `date,value` — level/seasonality
    grafiğiyle doğrudan uyumlu (bkz. modül docstring'i)."""
    kayitlar = _gun("2026-08-01", naturalGas=100.0, lng=25.0)
    oturum = SahteOturum(SahteYanit(200, yanit(kayitlar)))
    df = seri_cek(_epias_seri(), "TGT-abc", session=oturum, bugun=date(2026, 8, 1))
    assert list(df.columns) == ["date", "value"]
