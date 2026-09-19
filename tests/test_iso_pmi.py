"""İSO Sektörel PMI + Türkiye İmalat PMI istemcisi (`ingest/iso_pmi.py`)
testleri."""

from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace

import pytest

from ingest.iso_pmi import (
    GECERLI_METRIKLER,
    SEKTOR_SIRASI,
    _manset_degerini_ayikla,
    _pdf_dosyalarini_ayikla,
    _satir_degerlerini_ayikla,
    _sayfa_sektoru,
    _zip_baglantisini_bul,
    manset_veriyi_topla,
    seri_cek,
    sektorel_veriyi_topla,
)


def iso_seri(**kwargs):
    varsayilan = dict(
        id="sanayi/iso-pmi-test", iso_pmi_sektor=None, iso_pmi_metrik="pmi",
        start_date=None,
    )
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


# --- _sayfa_sektoru: başlık metniyle eşleme, sayfa indeksine göre değil ---


def test_sayfa_sektoru_ilk_6_satirda_tam_adi_bulur():
    metin = "İstanbul Sanayi\nOdası Türkiye\nSektörel PMI® Anketi\nGıda Ürünleri\nAçıklama metni burada devam eder."
    assert _sayfa_sektoru(metin) == "Gıda Ürünleri"


def test_sayfa_sektoru_kapak_sayfasinda_none_doner():
    """Kapak sayfası içindekiler listesinde sektör adları geçer ama ilk 6
    satırda TEK BAŞINA bir satır olarak yer almaz (ölçüldü)."""
    metin = (
        "AĞUSTOS 2026\nİstanbul Sanayi Odası Türkiye\nSektörel PMI® Anketi\n"
        "Ağustos'ta tüm sektörlerde yeni siparişler yavaşladı\n"
        "İstanbul Sanayi Odası Türkiye Sektörel PMI® endeksleri...\n"
        "İçindekiler Türkiye imalat sektöründe...\n"
        "Genel Bakış\nGıda Ürünleri\n"
    )
    assert _sayfa_sektoru(metin) is None


def test_sayfa_sektoru_bilinmeyen_baslikta_none_doner():
    assert _sayfa_sektoru("Rastgele Başlık\nİkinci satır\n") is None


# --- _satir_degerlerini_ayikla: "Endeks Özeti" tablosu satırları ---


def test_satir_degerlerini_ayikla_gecerli_satiri_okur():
    """Ölçülen gerçek satır (Ağustos 2026, Gıda Ürünleri Endeks Özeti)."""
    metin = "08-26 47,4 44,4 47,5 51,4 47,5 48,1 48,9 64,7 52,2 45,9 49,3 47,8"
    sonuc = _satir_degerlerini_ayikla(metin)
    assert sonuc == {
        "2026-08-01": [47.4, 44.4, 47.5, 51.4, 47.5, 48.1, 48.9, 64.7, 52.2, 45.9, 49.3, 47.8]
    }


def test_satir_degerlerini_ayikla_birden_fazla_ayi_okur():
    metin = (
        "03-26 47,1 46,6 45,6 47,9 47,5 48,1 48,5 62,9 54,7 46,6 51,1 47,7\n"
        "04-26 47,7 44,6 46,2 44,4 48,1 48,8 51,6 66,5 57,0 44,2 46,8 49,6\n"
    )
    sonuc = _satir_degerlerini_ayikla(metin)
    assert sorted(sonuc) == ["2026-03-01", "2026-04-01"]


def test_satir_degerlerini_ayikla_eksik_sutunlu_satiri_atlar():
    """Şablon kayması (sütun sayısı değişmiş) sessizce yanlış eşleşmemeli —
    12'den farklı sayı sayısı olan satır yok sayılır."""
    metin = "08-26 47,4 44,4 47,5"
    assert _satir_degerlerini_ayikla(metin) == {}


def test_satir_degerlerini_ayikla_anlatim_satirini_atlar():
    metin = "Bu Ağustos'ta 47,4 puana geriledi ve 44,4 oldu."
    assert _satir_degerlerini_ayikla(metin) == {}


# --- _manset_degerini_ayikla: değişken başlık cümlesi ---


def test_manset_degeri_haziran_kalibi():
    assert _manset_degerini_ayikla("PMI Haziran'da 47,1 olarak gerçekleşti\n") == 47.1


def test_manset_degeri_temmuz_kalibi():
    assert _manset_degerini_ayikla("PMI Temmuz'da 47,7 olarak gerçekleşti\n") == 47.7


def test_manset_degeri_agustos_farkli_cumle_kalibi():
    """Ay ay değişen cümle şablonu — sabit metin değil, ölçülen gerçek."""
    assert _manset_degerini_ayikla("PMI 48,1 ile son üç ayın en yüksek düzeyine çıktı\n") == 48.1


def test_manset_degeri_bulunamazsa_hata():
    with pytest.raises(RuntimeError, match="manşet değer satırı bulunamadı"):
        _manset_degerini_ayikla("Alakasız bir başlık\nİkinci satır\n")


# --- _pdf_dosyalarini_ayikla: bozuk kodlanmış dosya adlarına dayanıklı ---


def _zip_bayti(dosyalar: dict[str, bytes]) -> bytes:
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as z:
        for ad, icerik in dosyalar.items():
            z.writestr(ad, icerik)
    return tampon.getvalue()


def test_pdf_dosyalarini_ayikla_kronolojik_sirali_doner():
    zip_bayt = _zip_bayti({
        "TRSektörelPMI_2026.03_TUR.pdf": b"mart",
        "TRSektörelPMI_2025.08_TUR.pdf": b"agustos25",
        "TRSektörelPMI_2026.01_TUR.pdf": b"ocak",
    })
    sonuc = _pdf_dosyalarini_ayikla(zip_bayt)
    assert [t for t, _ in sonuc] == [(2025, 8), (2026, 1), (2026, 3)]


def test_pdf_dosyalarini_ayikla_bozuk_kodlanmis_adi_isler():
    """Ölçülen gerçek anomali: manşet PMI ZIP'inde Türkçe büyük İ bozuk
    kodlanıyor ('TRÿmalatPMI_2026.08_TUR_PR.pdf') — sayısal kısım yeterli."""
    zip_bayt = _zip_bayti({"TR\xffmalatPMI_2026.08_TUR_PR.pdf": b"agustos"})
    sonuc = _pdf_dosyalarini_ayikla(zip_bayt)
    assert sonuc == [((2026, 8), b"agustos")]


def test_pdf_dosyalarini_ayikla_pdf_disi_dosyalari_yoksayar():
    zip_bayt = _zip_bayti({"readme.txt": b"x", "TRSektörelPMI_2026.03_TUR.pdf": b"mart"})
    sonuc = _pdf_dosyalarini_ayikla(zip_bayt)
    assert len(sonuc) == 1


# --- _zip_baglantisini_bul ---


def test_zip_baglantisini_bul_bulur():
    html = '<a href="/file/sektorel-PMI-9886.zip">İndir</a>'
    assert _zip_baglantisini_bul(html) == "https://www.iso.org.tr/file/sektorel-PMI-9886.zip"


def test_zip_baglantisini_bul_bulunamazsa_hata():
    with pytest.raises(RuntimeError, match="bulunamadı"):
        _zip_baglantisini_bul("<html>boş</html>")


# --- sektorel_veriyi_topla / manset_veriyi_topla: pdfplumber sahteleme ---


class _SahteSayfa:
    def __init__(self, metin: str):
        self._metin = metin

    def extract_text(self):
        return self._metin


class _SahtePdf:
    def __init__(self, sayfalar: list[str]):
        self.pages = [_SahteSayfa(m) for m in sayfalar]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _gida_sayfasi(deger_satiri: str) -> str:
    return f"İstanbul Sanayi\nOdası Türkiye\nSektörel PMI® Anketi\nGıda Ürünleri\nAçıklama\n{deger_satiri}\n"


def test_sektorel_veriyi_topla_tum_sektorleri_bulamazsa_hata(monkeypatch):
    import ingest.iso_pmi as iso_pmi_mod

    # Yalnızca Gıda Ürünleri sayfası içeren tek dosyalı ZIP — kalan 9 sektör
    # hiçbir dosyada yok, bu bir şablon kayması sinyali olmalı.
    zip_bayt = _zip_bayti({"TRSektörelPMI_2026.08_TUR.pdf": b"x"})
    monkeypatch.setattr(
        iso_pmi_mod.pdfplumber, "open",
        lambda _b: _SahtePdf([_gida_sayfasi("08-26 47,4 44,4 47,5 51,4 47,5 48,1 48,9 64,7 52,2 45,9 49,3 47,8")]),
    )
    with pytest.raises(RuntimeError, match="şablonu değişmiş olabilir"):
        sektorel_veriyi_topla(zip_bayt)


def test_sektorel_veriyi_topla_tum_10_sektor_varsa_gecer(monkeypatch):
    import ingest.iso_pmi as iso_pmi_mod

    satir = "08-26 47,4 44,4 47,5 51,4 47,5 48,1 48,9 64,7 52,2 45,9 49,3 47,8"
    sayfalar = [
        f"İstanbul Sanayi\nOdası Türkiye\nSektörel PMI® Anketi\n{ad}\nAçıklama\n{satir}\n"
        for ad in SEKTOR_SIRASI
    ]
    zip_bayt = _zip_bayti({"TRSektörelPMI_2026.08_TUR.pdf": b"x"})
    monkeypatch.setattr(iso_pmi_mod.pdfplumber, "open", lambda _b: _SahtePdf(sayfalar))
    veri = sektorel_veriyi_topla(zip_bayt)
    assert set(veri) == set(SEKTOR_SIRASI)
    assert veri["Gıda Ürünleri"]["2026-08-01"][0] == 47.4


def test_manset_veriyi_topla_her_dosyanin_tek_degerini_okur(monkeypatch):
    import ingest.iso_pmi as iso_pmi_mod

    zip_bayt = _zip_bayti({
        "TR\xffmalatPMI_2026.07_TUR_PR.pdf": b"x",
        "TR\xffmalatPMI_2026.08_TUR_PR.pdf": b"y",
    })
    metinler = {
        b"x": "PMI Temmuz'da 47,7 olarak gerçekleşti\n",
        b"y": "PMI 48,1 ile son üç ayın en yüksek düzeyine çıktı\n",
    }

    def sahte_ac(baytlar):
        # zipfile üzerinden okunan içerik `bytes` — sözlükte anahtar olarak kullanılabilir
        return _SahtePdf([metinler[bytes(baytlar.getvalue())]])

    monkeypatch.setattr(iso_pmi_mod.pdfplumber, "open", sahte_ac)
    veri = manset_veriyi_topla(zip_bayt)
    assert veri == {"2026-07-01": 47.7, "2026-08-01": 48.1}


# --- seri_cek: dispatcher ---


def _onbellek():
    return {
        "sektorel": {
            "Gıda Ürünleri": {
                "2026-07-01": [45.7, 41.5, 43.1, 50.8, 45.9, 51.5, 45.6, 55.6, 53.0, 45.4, 49.9, 46.1],
                "2026-08-01": [47.4, 44.4, 47.5, 51.4, 47.5, 48.1, 48.9, 64.7, 52.2, 45.9, 49.3, 47.8],
            },
        },
        "manset": {"2026-07-01": 47.7, "2026-08-01": 48.1},
    }


def test_seri_cek_manset_pmi_dogru_deger_dondurur():
    df = seri_cek(iso_seri(), onbellek=_onbellek())
    assert list(df["date"]) == ["2026-07-01", "2026-08-01"]
    assert df["value"].iloc[-1] == pytest.approx(48.1)


def test_seri_cek_manset_pmi_disinda_metrik_isterse_hata():
    with pytest.raises(RuntimeError, match="yalnızca iso_pmi_metrik='pmi'"):
        seri_cek(iso_seri(iso_pmi_metrik="yeni-siparisler"), onbellek=_onbellek())


def test_seri_cek_sektor_pmi_dogru_deger_dondurur():
    df = seri_cek(iso_seri(iso_pmi_sektor="Gıda Ürünleri", iso_pmi_metrik="pmi"), onbellek=_onbellek())
    assert df["value"].iloc[-1] == pytest.approx(47.4)


def test_seri_cek_yeni_siparisler_dogru_sutunu_okur():
    df = seri_cek(iso_seri(iso_pmi_sektor="Gıda Ürünleri", iso_pmi_metrik="yeni-siparisler"), onbellek=_onbellek())
    assert df["value"].iloc[-1] == pytest.approx(47.5)


def test_seri_cek_yeni_ihracat_siparisleri_dogru_sutunu_okur():
    df = seri_cek(
        iso_seri(iso_pmi_sektor="Gıda Ürünleri", iso_pmi_metrik="yeni-ihracat-siparisleri"),
        onbellek=_onbellek(),
    )
    assert df["value"].iloc[-1] == pytest.approx(51.4)


def test_seri_cek_fiyat_farki_urun_eksi_girdi_hesaplar():
    """Ölçülen gerçek (Ağustos 2026 Gıda): Ürün Fiyatları 52,2 − Girdi
    Fiyatları 64,7 = −12,5, referans kart değeriyle birebir."""
    df = seri_cek(iso_seri(iso_pmi_sektor="Gıda Ürünleri", iso_pmi_metrik="fiyat-farki"), onbellek=_onbellek())
    assert df["value"].iloc[-1] == pytest.approx(-12.5)


def test_seri_cek_bilinmeyen_sektorde_hata():
    with pytest.raises(RuntimeError, match="bilinmeyen iso_pmi_sektor"):
        seri_cek(iso_seri(iso_pmi_sektor="Olmayan Sektör", iso_pmi_metrik="pmi"), onbellek=_onbellek())


def test_seri_cek_bilinmeyen_metrikte_hata():
    with pytest.raises(RuntimeError, match="bilinmeyen iso_pmi_metrik"):
        seri_cek(iso_seri(iso_pmi_sektor="Gıda Ürünleri", iso_pmi_metrik="olmayan-metrik"), onbellek=_onbellek())


def test_seri_cek_start_date_oncesini_kirpar():
    df = seri_cek(
        iso_seri(iso_pmi_sektor="Gıda Ürünleri", iso_pmi_metrik="pmi", start_date="2026-08-01"),
        onbellek=_onbellek(),
    )
    assert list(df["date"]) == ["2026-08-01"]


def test_gecerli_metrikler_dort_deger_icerir():
    assert GECERLI_METRIKLER == {"pmi", "yeni-siparisler", "yeni-ihracat-siparisleri", "fiyat-farki"}
