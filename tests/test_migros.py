"""Migros Ticaret A.Ş. (BIST: MGROS) "Ara Dönem Faaliyet Raporu" PDF
istemcisi testleri."""

from types import SimpleNamespace

import pytest

from ingest.migros import (
    GECERLI_METRIKLER,
    _belge_metnini_getir,
    magaza_sayisini_ayikla,
    seri_cek,
)


class SahteYanit:
    def __init__(self, status_code=200, content=b""):
        self.status_code = status_code
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class SahteOturum:
    def __init__(self, status_code=404):
        self.status_code = status_code

    def get(self, url, headers=None, timeout=None):
        return SahteYanit(status_code=self.status_code)


def test_belge_metnini_getir_404_link_curumesinde_none_doner():
    """Ölçülen gerçek anomali: 2012 dönemine ait bazı rapor bağlantıları
    artık 404 veriyor — dönem atlanır, seri PATLAMAZ."""
    onbellek = {}
    sonuc = _belge_metnini_getir("http://x/eski-2012.pdf", onbellek, session=SahteOturum(404))
    assert sonuc is None
    assert onbellek["http://x/eski-2012.pdf"] is None  # önbelleklenir, tekrar denenmez


def test_seri_cek_404lu_donemi_atlar_digerlerini_kullanir(monkeypatch):
    import ingest.migros as migros_modul

    monkeypatch.setattr(
        migros_modul, "_rapor_listesi",
        lambda session=None: [
            {"tarih": "2012-09-01", "url": "http://x/eski.pdf"},
            {"tarih": "2026-06-01", "url": "http://x/haz.pdf"},
        ],
    )

    def sahte_getir(url, onbellek, session=None):
        return None if url == "http://x/eski.pdf" else "30 Haziran 2026 itibarıyla toplam\nmağaza sayısı 3.830 oldu."

    monkeypatch.setattr(migros_modul, "_belge_metnini_getir", sahte_getir)
    df = seri_cek(mgros_seri())
    assert list(df["date"]) == ["2026-06-01"]
    assert list(df["value"]) == [3830.0]


def mgros_seri(**kwargs):
    varsayilan = dict(id="perakende/mgros-toplam-magaza-sayisi", migros_metrik="toplam-magaza-sayisi")
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


def test_magaza_sayisini_ayikla_detayli_dokum_kalibi():
    metin = (
        "Şirketimiz, 30 Haziran 2026 itibarıyla yurt içinde 7 coğrafi bölgede 2.220 Migros, "
        "1.186 Migros Jet, 157 Macrocenter, 109 Macrokiosk, 50 hipermarket, 24 Toptan, 80 Mion "
        "ve 4 Petimo mağazası olmak üzere toplam\n3.830 mağazaya ulaştı."
    )
    assert magaza_sayisini_ayikla(metin) == 3830.0


def test_magaza_sayisini_ayikla_ozet_cumle_kalibi():
    """Bazı çeyreklerde yalnızca kısa özet cümlesi var (ölçülen ikinci biçim)."""
    metin = "30 Eylül 2025 itibarıyla toplam\nmağaza sayısı 3.730 oldu."
    assert magaza_sayisini_ayikla(metin) == 3730.0


def test_magaza_sayisini_ayikla_eslesme_yoksa_none():
    assert magaza_sayisini_ayikla("ilgisiz içerik") is None


def test_seri_cek_bilinmeyen_metrik_hata_verir():
    with pytest.raises(RuntimeError, match="Bilinmeyen migros_metrik"):
        seri_cek(mgros_seri(migros_metrik="olmayan"))


def test_seri_cek_hicbir_raporda_deger_yoksa_patlar(monkeypatch):
    import ingest.migros as migros_modul

    monkeypatch.setattr(
        migros_modul, "_rapor_listesi",
        lambda session=None: [{"tarih": "2026-06-01", "url": "http://x/haz.pdf"}],
    )
    monkeypatch.setattr(
        migros_modul, "_belge_metnini_getir",
        lambda url, onbellek, session=None: "ilgisiz içerik",
    )
    with pytest.raises(RuntimeError, match="mağaza sayısı bulunamadı"):
        seri_cek(mgros_seri())


def test_seri_cek_dogru_seriyi_uretir(monkeypatch):
    import ingest.migros as migros_modul

    monkeypatch.setattr(
        migros_modul, "_rapor_listesi",
        lambda session=None: [
            {"tarih": "2026-06-01", "url": "http://x/haz.pdf"},
            {"tarih": "2026-03-01", "url": "http://x/mar.pdf"},
        ],
    )
    icerikler = {
        "http://x/haz.pdf": "30 Haziran 2026 itibarıyla toplam\nmağaza sayısı 3.830 oldu.",
        "http://x/mar.pdf": "31 Mart 2026 itibarıyla toplam\nmağaza sayısı 3.812 oldu.",
    }
    monkeypatch.setattr(
        migros_modul, "_belge_metnini_getir",
        lambda url, onbellek, session=None: icerikler[url],
    )
    df = seri_cek(mgros_seri())
    assert list(df["date"]) == ["2026-03-01", "2026-06-01"]
    assert list(df["value"]) == [3812.0, 3830.0]


def test_gecerli_metrikler_tek_seriyi_kapsar():
    assert GECERLI_METRIKLER == {"toplam-magaza-sayisi"}
