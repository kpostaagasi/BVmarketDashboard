"""TürkTraktör (BIST: TTRAK) OSD'ye bildirilen üretim/satış PDF istemcisi
testleri."""

from types import SimpleNamespace

import pytest

from ingest.turktraktor import (
    GECERLI_METRIKLER,
    ay_verilerini_ayikla,
    bulten_baglantilari,
    seri_cek,
)


def ttrak_seri(**kwargs):
    varsayilan = dict(id="otomotiv/ttrak-fabrika-satis", turktraktor_metrik="fabrika-satis")
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


_ORNEK_METIN = (
    "AĞUSTOS 2026\nFABRİKA YURTDIŞI\nTİPLER\nSATIŞ SATIŞ\nAylık 592 441\n"
    "TRAKTÖR\nKümülatif 5.160 8.123\n"
    "FABRİKA SATIŞ: FABRİKA TARAFINDAN BAYİYE FATURA EDİLEN ARAÇLAR\n"
    "YURTDIŞI SATIŞ: FABRİKA TARAFINDAN İHRAÇ EDİLEN ARAÇLAR\n"
    "ÜRETİLEN TRAKTÖR\nA B\nTOPLAM 1.023 12.843\n"
    "A: AİT OLDUĞU AY\nB: YILBAŞINDAN İTİBAREN\nKÜMÜLE\n"
)


def test_ay_verilerini_ayikla_aylik_degerleri_dogru_okur():
    fabrika, yurtdisi, uretim = ay_verilerini_ayikla(_ORNEK_METIN)
    assert (fabrika, yurtdisi, uretim) == (592.0, 441.0, 1023.0)


def test_ay_verilerini_ayikla_aylik_satiri_yoksa_patlar():
    with pytest.raises(RuntimeError, match="'Aylık' satırı bulunamadı"):
        ay_verilerini_ayikla("ilgisiz içerik")


def test_ay_verilerini_ayikla_uretim_toplam_satiri_yoksa_patlar():
    yalniz_satis = "Aylık 592 441\n"
    with pytest.raises(RuntimeError, match="TOPLAM satırı bulunamadı"):
        ay_verilerini_ayikla(yalniz_satis)


# --- bulten_baglantilari: indeks HTML'inden GUID bağlantı ayrıştırma ---


def test_bulten_baglantilari_tire_ayracli_dosya_adini_cozer():
    html = (
        '<a href="/getmedia/ef8e8fd4-506c-4173-b9e3-2224d3f7f266/'
        'Agustos-2026-OSD-URETIM-SATIS.pdf">Ağustos</a>'
    )
    sonuc = bulten_baglantilari(html)
    assert sonuc == {
        "2026-08": "https://www.turktraktor.com.tr/getmedia/ef8e8fd4-506c-4173-b9e3-2224d3f7f266/"
        "Agustos-2026-OSD-URETIM-SATIS.pdf"
    }


def test_bulten_baglantilari_alt_cizgi_ayracli_dosya_adini_da_cozer():
    """Ölçülen anomali: bazı yıllar 'Ay_YılOSD_URETIM_SATIS_.pdf' kullanıyor."""
    html = (
        '<a href="/getmedia/5df708e2-8e74-4437-be3f-619202eabfe5/'
        'Nisan_2024OSD_URETIM_SATIS_.pdf">Nisan</a>'
    )
    sonuc = bulten_baglantilari(html)
    assert "2024-04" in sonuc


def test_bulten_baglantilari_yilsiz_dosya_adlarini_atlar():
    """Bazı eski aylar dosya adında yıl taşımıyor (ör. 'Ekim.pdf') — atlanır."""
    html = '<a href="/getmedia/xxx-yyy/Ekim.pdf">Ekim</a>'
    assert bulten_baglantilari(html) == {}


# --- seri_cek: dispatch + toplam-satis türetimi ---


def test_seri_cek_bilinmeyen_metrik_hata_verir():
    with pytest.raises(RuntimeError, match="Bilinmeyen turktraktor_metrik"):
        seri_cek(ttrak_seri(turktraktor_metrik="olmayan"))


def test_seri_cek_toplam_satis_fabrika_ve_yurtdisi_toplamidir(monkeypatch):
    import ingest.turktraktor as tt_modul

    monkeypatch.setattr(tt_modul, "_indeks_cek", lambda session=None: {"2026-08": "http://x/agu.pdf"})
    monkeypatch.setattr(
        tt_modul, "_bulten_verisini_getir",
        lambda anahtar, baglantilar, onbellek, session=None: (592.0, 441.0, 1023.0),
    )
    df = seri_cek(ttrak_seri(turktraktor_metrik="toplam-satis"))
    assert list(df["date"]) == ["2026-08-01"]
    assert list(df["value"]) == [1033.0]


def test_gecerli_metrikler_uc_seriyi_kapsar():
    assert GECERLI_METRIKLER == {"fabrika-satis", "yurtdisi-satis", "toplam-satis"}
