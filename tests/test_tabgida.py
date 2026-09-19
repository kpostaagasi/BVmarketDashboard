"""TAB Gıda çeyreklik "Finansal Bülten" PDF ayrıştırma testleri.

Şebeke: `tabgida.com.tr` TLS/WAF düzeyinde `requests` istemcisini
reddediyor (bkz. modül docstring'i ve görev raporu) — bu yüzden bu adaptör
katalogda KAYITLI DEĞİL. Testler yalnızca ayrıştırma mantığının doğruluğunu
kanıtlıyor (ileride erişim çözülürse ya da farklı bir istemci kullanılırsa
hazır olsun diye)."""

from types import SimpleNamespace

import pytest

from ingest.tabgida import (
    GECERLI_METRIKLER,
    fis_sayisini_ayikla,
    restoran_sayisini_ayikla,
    seri_cek,
)


def tabgd_seri(**kwargs):
    varsayilan = dict(id="restoran/tabgd-restoran-sayisi", tabgida_metrik="restoran-sayisi")
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


def test_restoran_sayisini_ayikla_toplam_ulastirdik_kalibi():
    metin = "30 Haziran 2026 itibarıyla toplam restoran sayımızı 2.100'e ulaştırdık."
    assert restoran_sayisini_ayikla(metin) == 2100.0


def test_restoran_sayisini_ayikla_yili_kapatti_kalibi():
    """FY bültenlerinde farklı ifade biçimi: 'yılı N lokasyonla kapattık'."""
    metin = "restoran sayımızda 2.000'i aştık ve yılı 2.030 lokasyonla kapattık."
    assert restoran_sayisini_ayikla(metin) == 2030.0


def test_restoran_sayisini_ayikla_eslesme_yoksa_none():
    assert restoran_sayisini_ayikla("ilgisiz içerik") is None


def test_fis_sayisini_ayikla_ikinci_sayiyi_alir_cari_donem():
    """TAB Gıda tablo sırası BigChefs'in TERSİ: önceki yıl önce, cari sonra."""
    metin = "Fiş sayısı ('000) 207.648 247.196 %19,0 207.648 247.196 %19,0\n"
    assert fis_sayisini_ayikla(metin) == 247196.0


def test_fis_sayisini_ayikla_bin_adet_olceginde_kalir():
    """Değer zaten bin adet cinsinden — ayrıca 1000 ile çarpılmamalı."""
    metin = "Fiş sayısı ('000) 100.000 150.000 %50,0 100.000 150.000 %50,0\n"
    assert fis_sayisini_ayikla(metin) == 150000.0  # 150 milyon fiş değil


def test_seri_cek_bilinmeyen_metrik_hata_verir():
    with pytest.raises(RuntimeError, match="Bilinmeyen tabgida_metrik"):
        seri_cek(tabgd_seri(tabgida_metrik="olmayan"))


def test_seri_cek_fis_sayisi_yalniz_4_ceyrek_bultenlerini_kullanir(monkeypatch):
    import ingest.tabgida as tabgida_modul

    monkeypatch.setattr(
        tabgida_modul, "_bulten_listesi",
        lambda session=None: [
            {"yil": 2025, "ceyrek": 4, "url": "http://x/fy.pdf"},
            {"yil": 2025, "ceyrek": 2, "url": "http://x/2c.pdf"},
        ],
    )
    icerikler = {"http://x/fy.pdf": "Fiş sayısı ('000) 207.648 247.196 %19,0 207.648 247.196 %19,0\n"}
    monkeypatch.setattr(
        tabgida_modul, "_belge_metnini_getir",
        lambda url, onbellek, session=None: icerikler[url],
    )
    df = seri_cek(tabgd_seri(tabgida_metrik="fis-sayisi"))
    assert list(df["date"]) == ["2025-10-01"]
    assert list(df["value"]) == [247196.0]


def test_gecerli_metrikler_iki_seriyi_kapsar():
    assert GECERLI_METRIKLER == {"restoran-sayisi", "fis-sayisi"}
