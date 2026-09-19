"""TAİD (Ağır Ticari Araçlar Derneği) "Perakende Satışlar Yerli/İthal
Dağılımı" bülteni istemcisi testleri.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

import ingest.taid as taid_mod
from ingest.taid import (
    _TABLO_BASLIGI,
    _tek_ay_bolumunu_ayikla,
    bulten_listesini_cek,
    marka_toplamlarini_ayikla,
    seri_cek,
)


class _SahteSayfa:
    def __init__(self, metin: str):
        self._metin = metin

    def extract_text(self):
        return self._metin


class _SahtePdf:
    def __init__(self, sayfalar):
        self.pages = sayfalar

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# Gerçek Ağustos 2026 bülteninden birebir alınan tek-aylık tablo metni
# (bkz. modül docstring'i, canlı ölçüm: FORD TRUCKS TOPLAM=464).
_AGUSTOS_2026_SAYFASI = (
    "Ağır Ticari Araç Pazarı\n"
    + _TABLO_BASLIGI
    + " AĞUSTOS 2026)\n"
    "MARKA YERLİ İTHAL TOPLAM\n"
    "464 0 464\nFORD TRUCKS\n"
    "177 0 177\nISUZU\n"
    "0 204 204\nIVECO\n"
    "0 81 81\nMAN\n"
    "908 184 1092\nMERCEDES\n"
    "71 0 71\nOTOKAR\n"
    "0 99 99\nRENAULT\n"
    "0 184 184\nSCANIA\n"
    "0 58 58\nVOLVO\n"
    "1620 810 2430\nTOPLAM\n"
    + _TABLO_BASLIGI
    + " (OCAK-AĞUSTOS 2026)\n"
    "MARKA YERLİ İTHAL TOPLAM\n"
    "3982 0 3982\nFORD TRUCKS\n"
    "13357 7053 20588\nTOPLAM\n"
)

# OCAK bültenlerinde kümülatif tablo yok (tek ay = Ocak-Ocak); başlık bir
# kez geçer (bkz. `_tek_ay_bolumunu_ayikla` docstring'i).
_OCAK_2026_SAYFASI = (
    "Ağır Ticari Araç Pazarı\n"
    + _TABLO_BASLIGI
    + " OCAK 2026)\n"
    "MARKA YERLİ İTHAL TOPLAM\n"
    "351 0 351\nFORD TRUCKS\n"
    "351 0 351\nTOPLAM\n"
    "Semi-Treyler Araç Pazarı\n"
)


def _tek_sayfali_pdf(monkeypatch, metin: str) -> bytes:
    monkeypatch.setattr(
        taid_mod.pdfplumber, "open",
        lambda _baytlar: _SahtePdf([_SahteSayfa(metin)]),
    )
    return b"herhangi"


def _bulten_govdesi(kayitlar):
    return {"bultenler": kayitlar, "totalPage": 1}


def _kayit(baslik, pdf_yolu):
    return {
        "baslik": baslik,
        "icerik": f'<p><a href="{pdf_yolu}">Raporu görüntülemek için buraya tıklayınız.</a></p>',
    }


class SahteYanit:
    def __init__(self, status_code=200, govde=None, content=b""):
        self.status_code = status_code
        self._govde = govde
        self.content = content

    def json(self):
        return self._govde


class SahteOturum:
    def __init__(self, sayfalar=None, pdfler=None):
        self.sayfalar = sayfalar or {}
        self.pdfler = pdfler or {}
        self.pdf_istekleri = 0

    def get(self, url, params=None, timeout=None):
        if url == taid_mod.LISTE_URL:
            return SahteYanit(govde=self.sayfalar[params["page"]])
        self.pdf_istekleri += 1
        return self.pdfler.get(url, SahteYanit(404))


# --- bulten_listesini_cek ---


def test_bulten_listesini_cek_baslik_ve_pdf_cikarir():
    govde = _bulten_govdesi([
        _kayit("BASIN BÜLTENİ (AĞUSTOS 2026)", "/belgeler/agu.pdf"),
        _kayit("BASIN BÜLTENİ (TEMMUZ 2026)", "/belgeler/tem.pdf"),
    ])
    oturum = SahteOturum(sayfalar={1: govde})
    sonuc = bulten_listesini_cek(date(2026, 9, 20), session=oturum)
    assert sonuc["2026-08-01"] == taid_mod.TABAN + "/belgeler/agu.pdf"
    assert sonuc["2026-07-01"] == taid_mod.TABAN + "/belgeler/tem.pdf"


def test_bulten_listesini_cek_pencere_disini_atlar():
    govde = _bulten_govdesi([
        _kayit("BASIN BÜLTENİ (AĞUSTOS 2026)", "/belgeler/agu.pdf"),
        _kayit("BASIN BÜLTENİ (OCAK 2015)", "/belgeler/eski.pdf"),
    ])
    oturum = SahteOturum(sayfalar={1: govde})
    sonuc = bulten_listesini_cek(date(2026, 9, 20), session=oturum)
    assert "2015-01-01" not in sonuc


def test_bulten_listesini_cek_ilgisiz_baslik_atlanir():
    govde = _bulten_govdesi([{"baslik": "İlgisiz Duyuru", "icerik": "<p>yok</p>"}])
    oturum = SahteOturum(sayfalar={1: govde})
    with pytest.raises(RuntimeError, match="hiç bülten"):
        bulten_listesini_cek(date(2026, 9, 20), session=oturum)


# --- _tek_ay_bolumunu_ayikla ---


def test_tek_ay_bolumunu_ayikla_kumulatif_tablodan_once_durur(monkeypatch):
    baytlar = _tek_sayfali_pdf(monkeypatch, _AGUSTOS_2026_SAYFASI)
    bolum = _tek_ay_bolumunu_ayikla(baytlar)
    assert "FORD TRUCKS" in bolum
    assert "3982" not in bolum  # kümülatif tablonun FORD TRUCKS satırı sızmamalı


def test_tek_ay_bolumunu_ayikla_ocak_kumulatifsiz_calisir(monkeypatch):
    """OCAK bülteninde ikinci (kümülatif) başlık yok; yine de TOPLAM'da durmalı."""
    baytlar = _tek_sayfali_pdf(monkeypatch, _OCAK_2026_SAYFASI)
    bolum = _tek_ay_bolumunu_ayikla(baytlar)
    assert "FORD TRUCKS" in bolum
    assert "Semi-Treyler" not in bolum


def test_tek_ay_bolumunu_ayikla_baslik_yoksa_hata(monkeypatch):
    baytlar = _tek_sayfali_pdf(monkeypatch, "ilgisiz sayfa içeriği")
    with pytest.raises(RuntimeError, match="bulunamadı"):
        _tek_ay_bolumunu_ayikla(baytlar)


# --- marka_toplamlarini_ayikla ---


def test_marka_toplamlarini_ayikla_ford_trucks_dogru(monkeypatch):
    bolum = _tek_ay_bolumunu_ayikla(_tek_sayfali_pdf(monkeypatch, _AGUSTOS_2026_SAYFASI))
    sonuc = marka_toplamlarini_ayikla(bolum)
    assert sonuc["FORD TRUCKS"] == 464.0
    assert sonuc["MERCEDES"] == 1092.0


def test_marka_toplamlarini_ayikla_yerli_ithal_tutmazsa_hata():
    bolum = (
        " AĞUSTOS 2026)\nMARKA YERLİ İTHAL TOPLAM\n464 0 999\nFORD TRUCKS\n999 0 999\nTOPLAM\n"
    )
    with pytest.raises(RuntimeError, match="öz-doğrulama"):
        marka_toplamlarini_ayikla(bolum)


def test_marka_toplamlarini_ayikla_marka_toplami_genel_toplamla_tutmazsa_hata():
    bolum = (
        " AĞUSTOS 2026)\nMARKA YERLİ İTHAL TOPLAM\n464 0 464\nFORD TRUCKS\n999 0 999\nTOPLAM\n"
    )
    with pytest.raises(RuntimeError, match="öz-doğrulama"):
        marka_toplamlarini_ayikla(bolum)


# --- seri_cek ---


def _seri(marka="FORD TRUCKS", start_date=None):
    return SimpleNamespace(taid_marka=marka, start_date=start_date)


def test_seri_cek_gecersiz_marka_hata_verir():
    with pytest.raises(RuntimeError, match="Geçersiz taid_marka"):
        seri_cek(_seri("YOK MARKA"), onbellek={}, session=SahteOturum())


def test_seri_cek_iki_aydan_dogru_deger_uretir(monkeypatch):
    liste_govde = _bulten_govdesi([
        _kayit("BASIN BÜLTENİ (AĞUSTOS 2026)", "/belgeler/agu.pdf"),
        _kayit("BASIN BÜLTENİ (OCAK 2026)", "/belgeler/ocak.pdf"),
    ])
    monkeypatch.setattr(
        taid_mod.pdfplumber, "open",
        lambda baytlar: _SahtePdf([_SahteSayfa(
            _AGUSTOS_2026_SAYFASI if baytlar.getvalue() == b"agu" else _OCAK_2026_SAYFASI
        )]),
    )
    oturum = SahteOturum(
        sayfalar={1: liste_govde},
        pdfler={
            taid_mod.TABAN + "/belgeler/agu.pdf": SahteYanit(content=b"agu"),
            taid_mod.TABAN + "/belgeler/ocak.pdf": SahteYanit(content=b"ocak"),
        },
    )
    df = seri_cek(_seri("FORD TRUCKS"), onbellek={}, session=oturum, bugun=date(2026, 9, 20))
    satirlar = dict(zip(df["date"], df["value"]))
    assert satirlar == {"2026-08-01": 464.0, "2026-01-01": 351.0}


def test_seri_cek_onbellek_pdf_yeniden_indirmez(monkeypatch):
    liste_govde = _bulten_govdesi([_kayit("BASIN BÜLTENİ (AĞUSTOS 2026)", "/belgeler/agu.pdf")])
    monkeypatch.setattr(
        taid_mod.pdfplumber, "open",
        lambda baytlar: _SahtePdf([_SahteSayfa(_AGUSTOS_2026_SAYFASI)]),
    )
    oturum = SahteOturum(
        sayfalar={1: liste_govde},
        pdfler={taid_mod.TABAN + "/belgeler/agu.pdf": SahteYanit(content=b"agu")},
    )
    onbellek: dict = {}
    seri_cek(_seri("FORD TRUCKS"), onbellek=onbellek, session=oturum, bugun=date(2026, 9, 20))
    ilk = oturum.pdf_istekleri
    seri_cek(_seri("MERCEDES"), onbellek=onbellek, session=oturum, bugun=date(2026, 9, 20))
    assert oturum.pdf_istekleri == ilk, "ikinci marka aynı PDF'i yeniden indirmemeli"


def test_seri_cek_start_date_oncesindeki_eski_formati_atlar(monkeypatch):
    """Ocak 2025 öncesi bültenler farklı bir tablo düzeni kullanıyor ve
    ayrıştırma hata veriyor (bkz. modül docstring'i) — `start_date` bu
    ayları hiç İNDİRMEDEN atlamalı, PDF'i açmaya çalışmamalı."""
    liste_govde = _bulten_govdesi([
        _kayit("BASIN BÜLTENİ (AĞUSTOS 2026)", "/belgeler/agu.pdf"),
        _kayit("BASIN BÜLTENİ ARALIK 2024", "/belgeler/eski.pdf"),
    ])
    monkeypatch.setattr(
        taid_mod.pdfplumber, "open",
        lambda baytlar: _SahtePdf([_SahteSayfa(_AGUSTOS_2026_SAYFASI)]),
    )
    oturum = SahteOturum(
        sayfalar={1: liste_govde},
        pdfler={taid_mod.TABAN + "/belgeler/agu.pdf": SahteYanit(content=b"agu")},
    )
    df = seri_cek(
        _seri("FORD TRUCKS", start_date="2025-01-01"),
        onbellek={}, session=oturum, bugun=date(2026, 9, 20),
    )
    assert list(df["date"]) == ["2026-08-01"]
    assert oturum.pdf_istekleri == 1, "start_date öncesi PDF hiç indirilmemeli"
