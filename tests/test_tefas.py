"""TEFAS istemcisi testleri.

Ağ tamamen sahte; hız sınırlama beklemeleri `_bekle`/`time.sleep`
monkeypatch'lenerek sıfırlanır, aksi halde her test 7 saniye beklerdi.
"""

import json
from datetime import date
from types import SimpleNamespace

import pytest

from ingest import tefas
from ingest.tefas import ay_sonlari, seri_cek, toplulastir


@pytest.fixture(autouse=True)
def _beklemeyi_kapat(monkeypatch):
    monkeypatch.setattr(tefas, "_bekle", lambda: None)
    monkeypatch.setattr(tefas.time, "sleep", lambda saniye: None)
    # `seri_cek` 36 ay sonu gezer; testler tek ayı inceler. `ay_sonlari`
    # doğrudan import edildiği için kendi testleri gerçek fonksiyonu görür.
    monkeypatch.setattr(tefas, "ay_sonlari", lambda bugun: [bugun])


def fon_satiri(kod, buyukluk, kisi=100):
    return {
        "fonKodu": kod, "fonUnvan": f"{kod} FONU", "tarih": "2026-08-28",
        "fiyat": 3.5, "tedPaySayisi": 1000, "kisiSayisi": kisi,
        "portfoyBuyukluk": buyukluk, "borsaBultenFiyat": None, "rn": 1,
    }


def yanit_govdesi(satirlar):
    return {"errorCode": None, "errorMessage": None, "resultList": satirlar,
            "toplamSayi": len(satirlar), "toplamSayfa": 1}


VERI_YOK = {"errorCode": None, "errorMessage": "Index 0 out of bounds for length 0",
            "resultList": None, "toplamSayi": None, "toplamSayfa": None}


class SahteYanit:
    def __init__(self, govde, status_code=200):
        self._govde = govde
        self.status_code = status_code

    def json(self):
        return self._govde


class SahteOturum:
    """Tarihe göre yanıt verir; listede olmayan gün "veri yok" döner."""

    def __init__(self, gune_gore=None, sirali=None):
        self.gune_gore = gune_gore or {}
        self.sirali = list(sirali or [])
        self.istekler = []

    def post(self, url, data=None, headers=None, timeout=None):
        govde = json.loads(data)
        self.istekler.append((govde["fonTipi"], govde["basTarih"]))
        if self.sirali:
            return self.sirali.pop(0)
        anahtar = (govde["fonTipi"], govde["basTarih"])
        if anahtar in self.gune_gore:
            return SahteYanit(yanit_govdesi(self.gune_gore[anahtar]))
        return SahteYanit(VERI_YOK)


def tefas_seri(**kwargs):
    varsayilan = dict(
        id="fonlar/yatirim-fonu-buyukluk",
        kaynak_tipi="tefas",
        tefas_tip="YAT",
        tefas_olcut="buyukluk",
        start_date=None,
    )
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


# --- Ay sonu listesi ---


def test_ay_sonlari_bes_yil_sinirinin_icinde_kalir():
    """Uç "başlangıç tarihi 5 yıldan eski olamaz" diyor; pay bırakılır."""
    aylar = ay_sonlari(date(2026, 9, 8), gecmis_yil=3)
    assert len(aylar) == 36
    assert aylar[0] == date(2023, 10, 31)


def test_ay_sonlari_cari_ayda_bugunu_kullanir():
    """Ayın sonu gelmediyse ileri tarih istenmez."""
    assert ay_sonlari(date(2026, 9, 8))[-1] == date(2026, 9, 8)


def test_ay_sonlari_ay_sonlarini_dogru_secer():
    aylar = ay_sonlari(date(2024, 3, 15), gecmis_yil=1)
    assert date(2024, 2, 29) in aylar  # artık yıl
    assert date(2024, 1, 31) in aylar


# --- Toplulaştırma ---


def test_toplulastir_dort_olcutu_uretir():
    toplam = toplulastir([fon_satiri("A", 100.0, 10), fon_satiri("B", 300.0, 30)])
    assert toplam["buyukluk"] == 400.0
    assert toplam["hesap"] == 40.0
    assert toplam["fon-sayisi"] == 2.0
    assert toplam["ortalama-buyukluk"] == 200.0


def test_toplulastir_bos_buyuklugu_sifir_sayar():
    """Yeni fon `portfoyBuyukluk: null` gelebilir; toplam patlamamalı."""
    satir = fon_satiri("C", None, 5)
    assert toplulastir([satir])["buyukluk"] == 0.0


def test_toplulastir_bos_listede_hata():
    with pytest.raises(RuntimeError, match="boş"):
        toplulastir([])


# --- Yayın olmayan gün ve geriye yürüme ---


def test_seri_cek_veri_olmayan_gunden_geriye_yurur():
    """Hafta sonu/tatilde uç "Index 0 out of bounds" döndürüyor."""
    oturum = SahteOturum({("YAT", "20240129"): [fon_satiri("A", 500.0)]})
    df = seri_cek(tefas_seri(), session=oturum, bugun=date(2024, 1, 31))
    # 31 ve 30 Ocak boş, 29'unda veri var
    assert [t for _, t in oturum.istekler][:3] == ["20240131", "20240130", "20240129"]
    assert list(df["value"]) == [500.0]
    assert list(df["date"]) == ["2024-01-01"]


def test_seri_cek_ayin_hic_verisi_yoksa_o_ayi_atlar():
    oturum = SahteOturum({})
    with pytest.raises(RuntimeError, match="hiç nokta döndürmedi"):
        seri_cek(tefas_seri(), session=oturum, bugun=date(2024, 1, 31))


# --- Hız sınırı ---


def test_seri_cek_429da_yeniden_dener():
    oturum = SahteOturum(sirali=[
        SahteYanit({}, status_code=429),
        SahteYanit(yanit_govdesi([fon_satiri("A", 700.0)])),
    ])
    df = seri_cek(tefas_seri(), session=oturum, bugun=date(2024, 1, 31))
    assert list(df["value"]) == [700.0]
    assert len(oturum.istekler) == 2


def test_seri_cek_429_israrliysa_hata():
    oturum = SahteOturum(sirali=[SahteYanit({}, status_code=429)] * 3)
    with pytest.raises(RuntimeError, match="hız sınırı aşılamadı"):
        seri_cek(tefas_seri(), session=oturum, bugun=date(2024, 1, 31))


def test_seri_cek_baglanti_hatasinda_yeniden_dener():
    """Sınıra yaklaşınca uç 429 yerine yanıtı hiç vermiyor (okuma zaman aşımı)."""
    import requests as _requests

    class ZamanAsimiOturumu(SahteOturum):
        def __init__(self):
            super().__init__({})
            self.sayac = 0

        def post(self, url, data=None, headers=None, timeout=None):
            self.sayac += 1
            if self.sayac == 1:
                raise _requests.exceptions.ReadTimeout("read timed out")
            return SahteYanit(yanit_govdesi([fon_satiri("A", 900.0)]))

    oturum = ZamanAsimiOturumu()
    df = seri_cek(tefas_seri(), session=oturum, bugun=date(2024, 1, 31))
    assert list(df["value"]) == [900.0]
    assert oturum.sayac == 2


def test_seri_cek_baglanti_hatasi_israrliysa_hata():
    import requests as _requests

    class HepZamanAsimi(SahteOturum):
        def post(self, url, data=None, headers=None, timeout=None):
            raise _requests.exceptions.ReadTimeout("read timed out")

    with pytest.raises(RuntimeError, match="bağlantı hatası"):
        seri_cek(tefas_seri(), session=HepZamanAsimi(), bugun=date(2024, 1, 31))


# --- Sayfa tavanı ---


def test_seri_cek_sayfa_tavanina_dayanirsa_hata():
    """Kırpılmış sayfa sessiz eksik toplam demektir."""
    cok = [fon_satiri(f"F{i}", 1.0) for i in range(tefas.SAYFA_TAVANI)]
    oturum = SahteOturum(sirali=[SahteYanit(yanit_govdesi(cok))])
    with pytest.raises(RuntimeError, match="sayfa tavanına"):
        seri_cek(tefas_seri(), session=oturum, bugun=date(2024, 1, 31))


# --- Önbellek ve ölçüt seçimi ---


def test_seri_cek_ayni_anlik_goruntuyu_yeniden_cekmez():
    """Dört ölçüt tek yanıttan üretilir; yoksa istek sayısı dörde katlanır."""
    oturum = SahteOturum({("YAT", "20240131"): [fon_satiri("A", 400.0, 8)]})
    onbellek: dict = {}
    seri_cek(tefas_seri(), onbellek=onbellek, session=oturum, bugun=date(2024, 1, 31))
    ilk = len(oturum.istekler)
    df = seri_cek(tefas_seri(tefas_olcut="hesap"), onbellek=onbellek,
                  session=oturum, bugun=date(2024, 1, 31))
    assert len(oturum.istekler) == ilk
    assert list(df["value"]) == [8.0]


def test_seri_cek_emk_tipini_istekte_gonderir():
    oturum = SahteOturum({("EMK", "20240131"): [fon_satiri("E", 50.0)]})
    seri_cek(tefas_seri(tefas_tip="EMK"), session=oturum, bugun=date(2024, 1, 31))
    assert oturum.istekler[0][0] == "EMK"


def test_seri_cek_start_date_oncesini_kirpar(monkeypatch):
    monkeypatch.setattr(
        tefas, "ay_sonlari", lambda bugun: [date(2024, 1, 31), date(2024, 2, 29)]
    )
    oturum = SahteOturum({
        ("YAT", "20240131"): [fon_satiri("A", 100.0)],
        ("YAT", "20240229"): [fon_satiri("A", 200.0)],
    })
    df = seri_cek(tefas_seri(start_date="2024-02-01"), session=oturum,
                  bugun=date(2024, 2, 29))
    assert list(df["date"]) == ["2024-02-01"]
    assert list(df["value"]) == [200.0]
