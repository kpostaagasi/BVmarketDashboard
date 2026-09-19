"""EPDK "Petrol ve LPG Piyasası Fiyatlandırma Raporu" (motorin/benzin fiyat
bileşenleri) istemcisi testleri.

`tests/test_epdk.py` (sektör raporu — üretim/satış hacmi) bu dosyayla
KARIŞTIRILMAMALI: ayrı bir rapor, ayrı bir kaynak_tipi (`epdk_fiyat`).
"""

from types import SimpleNamespace

import pytest

from ingest.epdk import (
    fiyat_cekilecek_dosyalar,
    fiyat_dosyalarini_ayikla,
    fiyat_seri_cek,
    fiyat_tablosunu_cikar,
)


def epdk_fiyat_seri(**kwargs):
    varsayilan = dict(
        id="petrol-piyasasi/motorin-nihai-satis-fiyati",
        kaynak_tipi="epdk_fiyat",
        epdk_fiyat_urun="motorin",
        epdk_fiyat_kalem="nihai-satis-fiyati",
    )
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


def _link(url, title):
    return f'<a href="{url}" title="{title}">x</a>'


# --- fiyat_dosyalarini_ayikla / fiyat_cekilecek_dosyalar ---


def test_fiyat_dosyalarini_ayikla_yil_ve_ayi_cikarir():
    html = _link("/Detay/DownloadDocument?id=A", "2026 Ağustos Ayı Petrol ve LPG Piyasası Fiyatlandırma Raporu")
    assert fiyat_dosyalarini_ayikla(html) == [{"yil": 2026, "ay": 8, "url": "/Detay/DownloadDocument?id=A"}]


def test_fiyat_dosyalarini_ayikla_baslik_kirintisini_tolere_eder():
    """Ölçülen gerçek anomali: title sonunda fazladan boşluk/`&quot;` artığı var."""
    html = _link("/Detay/DownloadDocument?id=A", "2024 Mayıs Ayı Petrol ve LPG Piyasası Fiyatlandırma Raporu&quot; ")
    assert fiyat_dosyalarini_ayikla(html) == [{"yil": 2024, "ay": 5, "url": "/Detay/DownloadDocument?id=A"}]


def test_fiyat_dosyalarini_ayikla_dotless_i_varyantini_tolere_eder():
    """Ölçülen gerçek anomali: bazı yıllarda title 'Fiyatlandirma Raporu' (dotless I)."""
    html = _link("/Detay/DownloadDocument?id=A", "2025 Ocak Ayi Petrol ve LPG Piyasasi Fiyatlandirma Raporu")
    assert fiyat_dosyalarini_ayikla(html) == [{"yil": 2025, "ay": 1, "url": "/Detay/DownloadDocument?id=A"}]


def test_fiyat_dosyalarini_ayikla_alakasiz_linki_atlar():
    html = _link("/Detay/DownloadDocument?id=A", "Bir Başka Belge")
    assert fiyat_dosyalarini_ayikla(html) == []


def test_fiyat_cekilecek_dosyalar_ilk_yil_oncesini_eler():
    dosyalar = [{"yil": 2023, "ay": 12, "url": "u1"}, {"yil": 2024, "ay": 1, "url": "u2"}]
    assert fiyat_cekilecek_dosyalar(dosyalar) == [{"yil": 2024, "ay": 1, "url": "u2"}]


def test_fiyat_cekilecek_dosyalar_ayni_donemin_ikinci_linkini_atar():
    """Ölçülen gerçek anomali: liste sayfasında aynı (yıl, ay) için iki farklı
    `id` görülüyor (2026 Temmuz) — yalnızca ilki tutulmalı, gereksiz ikinci
    indirme önlenmeli."""
    dosyalar = [
        {"yil": 2026, "ay": 7, "url": "u_ilk"},
        {"yil": 2026, "ay": 7, "url": "u_ikinci"},
    ]
    assert fiyat_cekilecek_dosyalar(dosyalar) == [{"yil": 2026, "ay": 7, "url": "u_ilk"}]


def test_fiyat_cekilecek_dosyalar_eskiden_yeniye_siralar():
    dosyalar = [{"yil": 2025, "ay": 3, "url": "u2"}, {"yil": 2024, "ay": 6, "url": "u1"}]
    assert [d["url"] for d in fiyat_cekilecek_dosyalar(dosyalar)] == ["u1", "u2"]


# --- fiyat_tablosunu_cikar ---


def _pdf_metni(motorin_satiri, benzin_satiri):
    return (
        f"Tablo-1: Benzin Fiyat Oluşumu (TL/lt)\n{benzin_satiri}\n"
        f"Tablo-2: Yurt İçi Motorin Fiyat Oluşumu (TL/lt)\n{motorin_satiri}\n"
    )


def test_fiyat_tablosunu_cikar_yilli_satiri_okur():
    """2025+ formatı: '<Ay> <Yıl> <Ürün> ...' (yıl yazılı)."""
    metin = _pdf_metni(
        "Ağustos 2026 Motorin 53,890 0,932 0,04568 9,713 15,187 79,768",
        "Ağustos 2026 K.Benzin 95 Oktan 41,009 1,369 0,04568 10,200 18,063 70,686",
    )
    sonuc = fiyat_tablosunu_cikar(metin, "Ağustos", 2026)
    assert sonuc[("motorin", "nihai-satis-fiyati")] == pytest.approx(79.768)
    assert sonuc[("benzin", "urun-fiyati")] == pytest.approx(41.009)
    assert ("motorin", "gelir-payi") not in {(u, k) for (u, k) in sonuc}  # Gelir Payı kapsam dışı


def test_fiyat_tablosunu_cikar_yilsiz_satiri_okur():
    """Ölçülen gerçek anomali: 2024 formatında satırda YIL YOK — yalnızca
    '<Ay> <Ürün> ...'."""
    metin = _pdf_metni(
        "Haziran Motorin 21,244 0,000 0,02529 3,779 15,621 40,670",
        "Haziran K.Benzin 95 Oktan 20,363 0,385 0,02529 3,858 16,271 40,903",
    )
    sonuc = fiyat_tablosunu_cikar(metin, "Haziran", 2024)
    assert sonuc[("motorin", "nihai-satis-fiyati")] == pytest.approx(40.670)
    assert sonuc[("benzin", "nihai-satis-fiyati")] == pytest.approx(40.903)


def test_fiyat_tablosunu_cikar_onceki_ayi_almaz():
    """Her PDF hedef ay + bir önceki ayı taşır; yalnızca hedef ay okunmalı
    (revizyon riski — bkz. modül docstring'i)."""
    metin = (
        "Ağustos 2026 Motorin 53,890 0,932 0,04568 9,713 15,187 79,768\n"
        "Temmuz 2026 Motorin 46,405 0,118 0,04568 9,361 15,479 71,408\n"
    )
    sonuc = fiyat_tablosunu_cikar(metin, "Ağustos", 2026)
    assert sonuc[("motorin", "nihai-satis-fiyati")] == pytest.approx(79.768)


def test_fiyat_tablosunu_cikar_eslesmeyen_ayda_bos_doner():
    metin = "Ağustos 2026 Motorin 53,890 0,932 0,04568 9,713 15,187 79,768\n"
    assert fiyat_tablosunu_cikar(metin, "Eylül", 2026) == {}


def test_fiyat_tablosunu_cikar_bes_kalemi_kapsar():
    metin = _pdf_metni(
        "Ağustos 2026 Motorin 53,890 0,932 0,04568 9,713 15,187 79,768",
        "Ağustos 2026 K.Benzin 95 Oktan 41,009 1,369 0,04568 10,200 18,063 70,686",
    )
    sonuc = fiyat_tablosunu_cikar(metin, "Ağustos", 2026)
    kalemler = {k for (_, k) in sonuc}
    assert kalemler == {"urun-fiyati", "toptanci-marji", "dagitici-bayi-marji", "toplam-vergi", "nihai-satis-fiyati"}


# --- fiyat_seri_cek: ağ kabuğu ---


class SahteOturum:
    def __init__(self, liste_html, pdf_metni_haritasi):
        self.liste_html = liste_html
        self.pdf_metni_haritasi = pdf_metni_haritasi
        self.indirilen_urller = []

    def get(self, url, timeout=None):
        if "Icerik/3-0-143" in url:
            return SimpleNamespace(status_code=200, text=self.liste_html)
        self.indirilen_urller.append(url)
        # url'deki id parametresine göre sahte PDF baytı üret
        return SimpleNamespace(status_code=200, content=self.pdf_metni_haritasi[url])


def test_fiyat_seri_cek_dogru_deger_dondurur(monkeypatch):
    import ingest.epdk as epdk_modul

    liste_html = _link("/Detay/DownloadDocument?id=A", "2026 Ağustos Ayı Petrol ve LPG Piyasası Fiyatlandırma Raporu")
    pdf_metni = _pdf_metni(
        "Ağustos 2026 Motorin 53,890 0,932 0,04568 9,713 15,187 79,768",
        "Ağustos 2026 K.Benzin 95 Oktan 41,009 1,369 0,04568 10,200 18,063 70,686",
    )


    class SahtePdf:
        def __init__(self, veri):
            self.pages = [SimpleNamespace(extract_text=lambda: pdf_metni)]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(epdk_modul.pdfplumber, "open", lambda buf: SahtePdf(buf))

    oturum = SahteOturum(liste_html, {f"{epdk_modul.TABAN}/Detay/DownloadDocument?id=A": b"sahte-pdf-baytlari"})
    df = fiyat_seri_cek(epdk_fiyat_seri(), onbellek={}, session=oturum)
    assert list(df["date"]) == ["2026-08-01"]
    assert df["value"].iloc[0] == pytest.approx(79.768)


def test_fiyat_seri_cek_bilinmeyen_kombinasyonda_hata(monkeypatch):
    import ingest.epdk as epdk_modul

    class SahtePdf:
        def __init__(self, veri):
            self.pages = []

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(epdk_modul.pdfplumber, "open", lambda buf: SahtePdf(buf))
    oturum = SahteOturum("", {})
    with pytest.raises(RuntimeError, match="veri bulunamadı"):
        fiyat_seri_cek(epdk_fiyat_seri(), onbellek={}, session=oturum)
