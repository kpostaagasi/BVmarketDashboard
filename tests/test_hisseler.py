"""Hisse (ticker) katalogu testleri.

Ticker sayfası mevcut serileri şirket ekseninde topluyor; katalogdaki her
referans gerçek bir seri olmalı, yoksa sayfa sessizce eksik çizer.
"""

import pytest

from core.catalog import (
    Hisse,
    KatalogHatasi,
    hisseleri_yukle,
    seri_getir,
)


def test_hisseler_yuklenir():
    hisseler = hisseleri_yukle()
    assert len(hisseler) >= 6
    assert all(isinstance(h, Hisse) for h in hisseler)


def test_kabul_olcutundeki_alti_ticker_var():
    kodlar = {h.kod for h in hisseleri_yukle()}
    assert {"FROTO", "TOASO", "TTRAK", "KARSN", "OTKAR", "ASUZU"} <= kodlar


def test_her_hissenin_serileri_katalogda():
    """Yazım hatası sayfada sessizce kaybolmasın (pano_serileri ile aynı ilke)."""
    for hisse in hisseleri_yukle():
        for seri_id in hisse.kendi + hisse.baglam:
            assert seri_getir(seri_id).id == seri_id


def test_her_hissede_en_az_uc_seri():
    """Sayfa başına en az üç grafik kartı: iki seri makro yığını olur."""
    for hisse in hisseleri_yukle():
        assert len(hisse.kendi) + len(hisse.baglam) >= 3, hisse.kod


def test_her_hissede_kendi_verisi_var():
    for hisse in hisseleri_yukle():
        assert hisse.kendi, hisse.kod


def test_kendi_ve_baglam_ayrik():
    """Aynı seri iki listede olursa sayfada iki kez çizilir."""
    for hisse in hisseleri_yukle():
        assert not (set(hisse.kendi) & set(hisse.baglam)), hisse.kod


def test_hisse_kodlari_bist_bicimi():
    for hisse in hisseleri_yukle():
        assert hisse.kod.isupper() and 4 <= len(hisse.kod) <= 6, hisse.kod


def _gecici_katalog(tmp_path, icerik: str):
    """hisseler.yaml'ı geçici dizinden okutur; lru_cache iki uçta temizlenir."""
    from core import catalog

    (tmp_path / "categories.yaml").write_text(
        "- slug: otomotiv\n  title: Otomotiv\n  grup: Sanayi & İnşaat\n  pano: [otomotiv/x]\n",
        encoding="utf-8",
    )
    (tmp_path / "series.yaml").write_text(
        "- id: otomotiv/x\n"
        "  title: X Üretim\n"
        "  category: otomotiv\n"
        "  kaynak: { name: OSD, url: https://example.com }\n"
        "  kaynak_tipi: osd\n"
        "  osd_firma: X\n"
        '  unit: "adet"\n'
        "  freq: monthly\n"
        "  charts: [level]\n",
        encoding="utf-8",
    )
    (tmp_path / "hisseler.yaml").write_text(icerik, encoding="utf-8")
    return catalog


def _yukle(tmp_path, monkeypatch, icerik):
    catalog = _gecici_katalog(tmp_path, icerik)
    monkeypatch.setattr(catalog, "KATALOG_DIZINI", tmp_path)
    for onbellek in (
        catalog.kategorileri_yukle,
        catalog.serileri_yukle,
        catalog.hisseleri_yukle,
    ):
        onbellek.cache_clear()
    try:
        return catalog.hisseleri_yukle()
    finally:
        for onbellek in (
            catalog.kategorileri_yukle,
            catalog.serileri_yukle,
            catalog.hisseleri_yukle,
        ):
            onbellek.cache_clear()


def test_bilinmeyen_seri_reddedilir(tmp_path, monkeypatch):
    icerik = (
        "- kod: XXXX\n  title: X\n  sektor: Otomotiv\n"
        "  kendi: [otomotiv/yok]\n"
    )
    with pytest.raises(KatalogHatasi, match="katalogda olmayan seri"):
        _yukle(tmp_path, monkeypatch, icerik)


def test_kendi_bos_reddedilir(tmp_path, monkeypatch):
    """Kendi verisi olmayan ticker sayfası yalnızca makro grafik yığınıdır."""
    icerik = (
        "- kod: XXXX\n  title: X\n  sektor: Otomotiv\n"
        "  kendi: []\n  baglam: [otomotiv/x]\n"
    )
    with pytest.raises(KatalogHatasi, match="kendi"):
        _yukle(tmp_path, monkeypatch, icerik)


def test_gecersiz_kod_reddedilir(tmp_path, monkeypatch):
    icerik = "- kod: froto\n  title: X\n  sektor: Otomotiv\n  kendi: [otomotiv/x]\n"
    with pytest.raises(KatalogHatasi, match="büyük harf"):
        _yukle(tmp_path, monkeypatch, icerik)


def test_tekrar_eden_kod_reddedilir(tmp_path, monkeypatch):
    icerik = (
        "- kod: XXXX\n  title: X\n  sektor: Otomotiv\n  kendi: [otomotiv/x]\n"
        "- kod: XXXX\n  title: Y\n  sektor: Otomotiv\n  kendi: [otomotiv/x]\n"
    )
    with pytest.raises(KatalogHatasi, match="tekrar ediyor"):
        _yukle(tmp_path, monkeypatch, icerik)


def test_ayni_seri_iki_listede_reddedilir(tmp_path, monkeypatch):
    icerik = (
        "- kod: XXXX\n  title: X\n  sektor: Otomotiv\n"
        "  kendi: [otomotiv/x]\n  baglam: [otomotiv/x]\n"
    )
    with pytest.raises(KatalogHatasi, match="iki kez çizilirdi"):
        _yukle(tmp_path, monkeypatch, icerik)
