"""Trabzon Ticaret Borsası (TTB) günlük bülten istemcisinin kabul testleri
(stub oturum/monkeypatch, canlı istek yok)."""

from __future__ import annotations

from datetime import date

import pytest

from core.catalog import Kaynak, Seri
from ingest import trabzontb as ttb


def _ornek_seri(urun: str) -> Seri:
    return Seri(
        id=f"emtia-tarim/{urun}",
        title="Test Serisi",
        category="emtia-tarim",
        kaynak=Kaynak(name="Trabzon TB", url="https://www.tb.org.tr"),
        kaynak_tipi="trabzontb",
        unit="TL/kg",
        freq="daily",
        charts=("level",),
        trabzontb_urun=urun,
    )


# --- agirlikli_ortalama ---


def test_agirlikli_ortalama_tek_satirda_kendi_ortalamasini_doner():
    assert ttb.agirlikli_ortalama([(189.659, 9855.0)]) == pytest.approx(189.659)


def test_agirlikli_ortalama_coklu_satirda_miktar_agirlikli_ortalama():
    # 18.09.2026 bülteninden ölçülen gerçek FINDIK(YAĞLI) satırları.
    satirlar = [(186.545, 6419.0), (210.116, 870.0), (204.930, 6554.0)]
    assert ttb.agirlikli_ortalama(satirlar) == pytest.approx(196.7308, abs=1e-3)


def test_agirlikli_ortalama_sifir_miktarda_hata():
    with pytest.raises(RuntimeError, match="sıfır miktarlı"):
        ttb.agirlikli_ortalama([(100.0, 0.0)])


# --- bulten_satirlarini_cikar ---


_ORNEK_METIN = """Trabzon Ticaret Borsası
GÜNLÜK BÜLTEN
KABUKLU TOMBUL FINDIK(YAĞLI) 2026 186.545 186.545 186.545 6.419 Kg 1,197,341.85 HMS 1
KABUKLU TOMBUL FINDIK(YAĞLI) 2026 210.116 210.116 210.116 870 Kg 182,801.33 KP.AL. 1
KABUKLU TOMBUL FINDIK(YAĞLI) 2026 204.930 204.930 204.930 6.554 Kg 1,343,111.22 TS 1
MISIR UNU(FIRINLANMIŞ) 2026 99.575 99.575 99.575 321 Kg 31,923.68 HMS 1
"""


def test_bulten_satirlarini_cikar_dogru_urunu_bulur():
    sonuc = ttb.bulten_satirlarini_cikar(_ORNEK_METIN)
    assert set(sonuc) == {"KABUKLU TOMBUL FINDIK(YAĞLI)"}
    assert sonuc["KABUKLU TOMBUL FINDIK(YAĞLI)"] == [
        (186.545, 6419.0), (210.116, 870.0), (204.930, 6554.0),
    ]


def test_bulten_satirlarini_cikar_tek_satirli_levant():
    metin = "KABUKLU TOMBUL FINDIK(LEVANT) 2026 189.659 189.659 189.659 9.855 Kg 1,869,089.67 KP,SAT, 1"
    sonuc = ttb.bulten_satirlarini_cikar(metin)
    assert sonuc == {"KABUKLU TOMBUL FINDIK(LEVANT)": [(189.659, 9855.0)]}


def test_bulten_satirlarini_cikar_esleşmeyen_urunleri_atlar():
    assert ttb.bulten_satirlarini_cikar("YAŞ ÇAY YAPRAĞI 2026 35.000 35.000 35.000 42 Kg 1,470.00 HMS 1") == {}


# --- gunleri_uret ---


def test_gunleri_uret_artan_siralidir_ve_bugunu_icerir():
    gunler = ttb.gunleri_uret(date(2026, 9, 18), adet=5)
    assert gunler == sorted(gunler)
    assert gunler[-1] == date(2026, 9, 18)
    assert gunler[0] == date(2026, 9, 14)


# --- bulten_cek: HTTP durum kodları (pdfplumber'a hiç girmeyen yollar) ---


class SahteYanit:
    def __init__(self, durum: int):
        self.status_code = durum


class SahteOturum:
    def __init__(self, durum_haritasi: dict[str, int]):
        self.durum_haritasi = durum_haritasi
        self.cagrilar: list[str] = []

    def get(self, url: str, timeout=None):
        self.cagrilar.append(url)
        return SahteYanit(self.durum_haritasi[url])


def test_bulten_cek_404_none_doner():
    url = "https://www.tb.org.tr/uploads/files/970-19.09.2026.pdf"
    oturum = SahteOturum({url: 404})
    assert ttb.bulten_cek(date(2026, 9, 19), session=oturum) is None


def test_bulten_cek_http_hatasi_yukselir():
    url = "https://www.tb.org.tr/uploads/files/970-19.09.2026.pdf"
    oturum = SahteOturum({url: 500})
    with pytest.raises(RuntimeError, match="500"):
        ttb.bulten_cek(date(2026, 9, 19), session=oturum)


# --- seri_cek: onbellek paylaşımı (bulten_cek monkeypatch'lenir) ---


def test_seri_cek_onbellegi_paylasir_ve_dogru_urunu_secer(monkeypatch):
    """2 ürün aynı günlük bültenleri paylaşır: her gün bir kez çekilmeli."""
    cagrilar: list[date] = []

    def sahte_bulten_cek(gun, session=None):
        cagrilar.append(gun)
        if gun == date(2026, 9, 18):
            return _ORNEK_METIN + "\nKABUKLU TOMBUL FINDIK(LEVANT) 2026 189.659 189.659 189.659 9.855 Kg 1,869,089.67 KP,SAT, 1"
        return None  # diğer tüm günler bülten yok (hafta sonu vb.)

    monkeypatch.setattr(ttb, "bulten_cek", sahte_bulten_cek)

    onbellek: dict = {}
    df_yaglik = ttb.seri_cek(_ornek_seri("findik-yaglik"), onbellek=onbellek, bugun=date(2026, 9, 18))
    df_levant = ttb.seri_cek(_ornek_seri("findik-levant"), onbellek=onbellek, bugun=date(2026, 9, 18))

    assert df_yaglik["date"].tolist() == ["2026-09-18"]
    assert df_yaglik["value"].iloc[0] == pytest.approx(196.7308, abs=1e-3)
    assert df_levant["date"].tolist() == ["2026-09-18"]
    assert df_levant["value"].iloc[0] == pytest.approx(189.659)
    # AZAMI_GERI_GUN gün taranır ama onbellek İKİ seri arasında paylaşılır:
    # ikinci seri_cek çağrısı yeniden taramamalı.
    assert len(cagrilar) == ttb.AZAMI_GERI_GUN


def test_seri_cek_veri_yoksa_hata(monkeypatch):
    monkeypatch.setattr(ttb, "bulten_cek", lambda gun, session=None: None)
    with pytest.raises(RuntimeError, match="hiç veri yok"):
        ttb.seri_cek(_ornek_seri("findik-yaglik"), onbellek={}, bugun=date(2026, 9, 18))
