"""BigChefs (BIST: BIGCH) yatırımcı ilişkileri istemcisi testleri."""

from types import SimpleNamespace

import pytest

from ingest.bigchefs import (
    GECERLI_METRIKLER,
    _metrik_deger,
    _sube_bilgisi,
    seri_cek,
)


def bigch_seri(**kwargs):
    varsayilan = dict(id="restoran/bigch-sube-sayisi", bigchefs_metrik="sube-sayisi")
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


# --- _sube_bilgisi: "Şirket Profili" / "Grup Hakkında" paragrafı ---

_AYLIK_METIN = (
    "Özel Durum Açıklaması (Genel)\n2 Mart 2026\nAylık şube sayısı bildirimi - Mart 2026\n"
    "Türkiye'de 29 şehirde 125 şube, yurt dışında 10 ülkede 13 şube olmak üzere, toplam 138\n"
    "şubeye sahip olan şirketimizin, 2 Mart 2026 tarihi itibarıyla Türkiye'de faaliyet gösterdiği şehir\n"
    "sayısı 30'a yükselmiş olup; şube sayısında değişiklik olmamıştır.\n"
    "Şirket Profili\n2009 yılında Ankara'da kurulan Büyük Şefler; bünyesindeki BigChefs, Numnum ve\n"
    "Buselik markalarıyla; 2 Mart 2026 tarihi itibarıyla Türkiye'de 30 şehirde 125 şube; yurt\n"
    "dışında 10 ülkede 13 şube olmak üzere toplam 138 şube ile hizmet vermektedir."
)

_CEYREKLIK_METIN = (
    "Grup Hakkında\n2009 yılında Ankara'da kurulan Büyük Şefler; bünyesindeki BigChefs, NumNum, "
    "Buselik markalarıyla; 31 Aralık 2025 tarihi itibarıyla Türkiye'de 29 şehirde 127 şube; yurt "
    "dışında 10 ülkede 13 şube olmak üzere toplam 140 şube ve kendi bünyesinde 1.545 çalışan ile "
    "hizmet vermektedir."
)


def test_sube_bilgisi_aylik_bildirimden_toplam_sehir_ulke_cikarir():
    toplam, sehir, ulke, calisan = _sube_bilgisi(_AYLIK_METIN)
    assert (toplam, sehir, ulke) == (138.0, 30.0, 10.0)
    assert calisan is None  # aylık bildirimde çalışan sayısı yok


def test_sube_bilgisi_satir_sonu_kirigina_dayanikli():
    """pdfplumber cümle içi satır sonu ekleyebiliyor (ölçüldü); \\s+ ile eşleşmeli."""
    kirilmis = _AYLIK_METIN.replace("yurt\ndışında", "yurt \n dışında")
    toplam, sehir, ulke, _ = _sube_bilgisi(kirilmis)
    assert (toplam, sehir, ulke) == (138.0, 30.0, 10.0)


def test_sube_bilgisi_ceyreklik_notta_calisan_sayisini_da_cikarir():
    toplam, sehir, ulke, calisan = _sube_bilgisi(_CEYREKLIK_METIN)
    assert (toplam, sehir, ulke, calisan) == (140.0, 29.0, 10.0, 1545.0)


def test_sube_bilgisi_eslesme_yoksa_none_doner():
    assert _sube_bilgisi("ilgisiz metin") is None


# --- _metrik_deger: "Finansal ve Operasyonel Özet" tablosu satırları ---

_OZET_TABLO = (
    "Sistem genelinde net satışlar 2.228.882.651 2.180.722.156 48.160.495 %2,2\n"
    "Net satışlar 1.170.003.689 1.103.785.758 66.217.931 %6,0\n"
    "Brüt kar marjı %15,2 %13,5\n"
    "Net kar (32.229.759) (34.956.607) 2.726.848 %7,8\n"
    "Net kar marjı (%2,8) (%3,2)\n"
)


def test_metrik_deger_ilk_sayiyi_alir_cari_donem():
    assert _metrik_deger(_OZET_TABLO, "Net satışlar") == 1170003689.0


def test_metrik_deger_yuzde_etiketini_parse_eder():
    assert _metrik_deger(_OZET_TABLO, "Brüt kar marjı") == 15.2


def test_metrik_deger_negatif_parantezi_dogru_isaretler():
    assert _metrik_deger(_OZET_TABLO, "Net kar") == -32229759.0
    assert _metrik_deger(_OZET_TABLO, "Net kar marjı") == -2.8


def test_metrik_deger_uzun_etiket_kisa_etikete_yanlislikla_eslemez():
    """'Net kar' etiketi 'Net kar marjı' satırına yanlışlıkla eşleşmemeli."""
    yalniz_marji = "Net kar marjı (%2,8) (%3,2)\n"
    assert _metrik_deger(yalniz_marji, "Net kar") is None


def test_metrik_deger_bulunamayan_etiket_none_doner():
    assert _metrik_deger(_OZET_TABLO, "Olmayan Satır") is None


# --- seri_cek: uçtan uca dispatch (ağ çağrıları monkeypatch'lenir) ---


def test_seri_cek_bilinmeyen_metrik_hata_verir():
    with pytest.raises(RuntimeError, match="Bilinmeyen bigchefs_metrik"):
        seri_cek(bigch_seri(bigchefs_metrik="olmayan-metrik"))


def test_seri_cek_aylik_metrik_belgelerden_deger_bulamazsa_patlar(monkeypatch):
    import ingest.bigchefs as bigchefs_modul

    monkeypatch.setattr(
        bigchefs_modul, "_duyuru_listesi",
        lambda session=None: [
            {"tarih": "2026-01-01", "konu": "Aylık Şube Sayısı Bildirimi", "url": "http://x/1.pdf"},
        ],
    )
    monkeypatch.setattr(
        bigchefs_modul, "_belge_metnini_getir",
        lambda url, onbellek, session=None: "ilgisiz içerik",
    )
    with pytest.raises(RuntimeError, match="değer bulunamadı"):
        seri_cek(bigch_seri(bigchefs_metrik="sube-sayisi"))


def test_seri_cek_aylik_metrik_dogru_seriyi_uretir(monkeypatch):
    import ingest.bigchefs as bigchefs_modul

    monkeypatch.setattr(
        bigchefs_modul, "_duyuru_listesi",
        lambda session=None: [
            {"tarih": "2026-03-01", "konu": "Aylık Şube Sayısı Bildirimi", "url": "http://x/mart.pdf"},
            {"tarih": "2026-02-01", "konu": "Aylık Şube Sayısı Bildirimi", "url": "http://x/subat.pdf"},
            {"tarih": None, "konu": "BuyukSefler 1C2026 Bilgilendirme Notu", "url": "http://x/not.pdf"},
        ],
    )
    icerikler = {"http://x/mart.pdf": _AYLIK_METIN, "http://x/subat.pdf": _AYLIK_METIN}
    monkeypatch.setattr(
        bigchefs_modul, "_belge_metnini_getir",
        lambda url, onbellek, session=None: icerikler[url],
    )
    df = seri_cek(bigch_seri(bigchefs_metrik="sehir-sayisi"))
    assert list(df["date"]) == ["2026-02-01", "2026-03-01"]
    assert list(df["value"]) == [30.0, 30.0]


def test_gecerli_metrikler_tum_dogrudan_etiketleri_kapsar():
    assert "net-kar-marji" in GECERLI_METRIKLER
    assert "fis-ortalamasi-bigchefs" in GECERLI_METRIKLER
    assert "calisan-sayisi" in GECERLI_METRIKLER
