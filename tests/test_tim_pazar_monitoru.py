"""TİM İhracat Pazar Monitörü aylık PDF bülteni istemcisi
(`ingest/tim.py::pazar_monitoru_*`) testleri.

Ayrı dosyada: `tests/test_tim.py` sektörel/il/ülke XLSX bültenlerinin
sahibi; bu dosya yalnızca İPM eklemesini kapsar, mevcut dosyalara dokunmaz.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ingest.tim import (
    PM_SEKTORLER,
    PM_ULKELER,
    _pm_milli_degerlerini_ayikla,
    _pm_satirlari_ayikla,
    _pm_sayfa_tipi,
    pazar_monitoru_bulten_baglantilari,
    pazar_monitoru_seri_cek,
    pm_bultenini_ayristir,
)


def pm_seri(**kwargs):
    varsayilan = dict(
        id="ihracat-pazar-monitoru/test", tim_pm_endeks="talep",
        tim_pm_sektor=None, tim_pm_ulke=None, start_date=None,
    )
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


# --- _pm_sayfa_tipi: başlık metnine göre sayfa sınıflandırma ---


def test_pm_sayfa_tipi_sektor_talep():
    metin = "TEMMUZ 2026\nTİM SEKTÖR SINIFLANDIRMASINA GÖRE İHRACAT TALEP ENDEKSİ\n..."
    assert _pm_sayfa_tipi(metin) == "sektor-talep"


def test_pm_sayfa_tipi_sektor_dayaniklilik():
    metin = "TEMMUZ 2026\nTİM SEKTÖR SINIFLANDIRMASINA GÖRE PAZAR DAYANIKLILIK ENDEKSİ\n..."
    assert _pm_sayfa_tipi(metin) == "sektor-dayaniklilik"


def test_pm_sayfa_tipi_ulke_talep():
    metin = "SEÇİLMİŞ ÜLKELER İÇİN İHRACAT TALEP ENDEKSİ\n..."
    assert _pm_sayfa_tipi(metin) == "ulke-talep"


def test_pm_sayfa_tipi_ulke_dayaniklilik():
    metin = "SEÇİLMİŞ ÜLKELER İÇİN PAZAR DAYANIKLILIK ENDEKSİ\n..."
    assert _pm_sayfa_tipi(metin) == "ulke-dayaniklilik"


def test_pm_sayfa_tipi_milli():
    metin = "TİM İHRACAT TALEP ENDEKSİ\n...\nTİM PAZAR DAYANIKLILIK ENDEKSİ\n..."
    assert _pm_sayfa_tipi(metin) == "milli"


def test_pm_sayfa_tipi_metodoloji_sayfasinda_none():
    assert _pm_sayfa_tipi("MET ODOLOJİ\nİhracat Talep Endeksi ...") is None


# --- _pm_satirlari_ayikla: sektör/ülke tablosu satırları ---


def test_pm_satirlari_ayikla_gecerli_satiri_okur():
    """Ölçülen gerçek satır (Temmuz 2026 bülteni, sektör Talep tablosu)."""
    metin = "Çelik 101,4 0,5 0,8 1,7"
    sonuc = _pm_satirlari_ayikla(metin, PM_SEKTORLER)
    assert sonuc == {"Çelik": 101.4}


def test_pm_satirlari_ayikla_negatif_degisimli_satiri_okur():
    metin = "Gemi, Yat ve Hizmetleri 101,3 -5,1 1,8 4,0"
    sonuc = _pm_satirlari_ayikla(metin, PM_SEKTORLER)
    assert sonuc == {"Gemi, Yat ve Hizmetleri": 101.3}


def test_pm_satirlari_ayikla_bilinmeyen_adi_atlar():
    metin = "Bilinmeyen Sektör 101,4 0,5 0,8 1,7"
    assert _pm_satirlari_ayikla(metin, PM_SEKTORLER) == {}


def test_pm_satirlari_ayikla_footer_satirini_atlar():
    assert _pm_satirlari_ayikla("Sektörler alfabetik olarak sıralanmıştır.", PM_SEKTORLER) == {}


def test_pm_satirlari_ayikla_ulke_listesiyle_calisir():
    metin = "Danimarka 102,9 2,1 2,4 3,6"
    assert _pm_satirlari_ayikla(metin, PM_ULKELER) == {"Danimarka": 102.9}


# --- _pm_milli_degerlerini_ayikla ---


def test_pm_milli_degerlerini_ayikla_iki_satiri_da_okur():
    metin = (
        "İhracat Talep Endeksi 100,4 0,1 0,3 0,5\n"
        "Pazar Dayanıklılık Endeksi 99,8 0,6 0,2 0,7\n"
    )
    assert _pm_milli_degerlerini_ayikla(metin) == {"talep": 100.4, "dayaniklilik": 99.8}


def test_pm_milli_degerlerini_ayikla_eksikse_kismi_doner():
    """Aralık 2025 gibi bazı aylarda haber metninde yalnızca Talep var —
    ama bu fonksiyon PDF bülten metnini işler; kısmi eksiklik olağan."""
    metin = "İhracat Talep Endeksi 99,4 -0,5 -0,3 -0,5\n"
    assert _pm_milli_degerlerini_ayikla(metin) == {"talep": 99.4}


# --- pm_bultenini_ayristir: tam bülten şablon doğrulaması ---

def _deger(v: float) -> str:
    return f"{v:.1f}".replace(".", ",")



def _tam_bulten_sayfalari() -> list[str]:
    milli = (
        "TİM İHRACAT TALEP ENDEKSİ\nİhracat Talep Endeksi 100,4 0,1 0,3 0,5\n"
        "TİM PAZAR DAYANIKLILIK ENDEKSİ\nPazar Dayanıklılık Endeksi 99,8 0,6 0,2 0,7\n"
    )
    sektor_talep = "TİM SEKTÖR SINIFLANDIRMASINA GÖRE İHRACAT TALEP ENDEKSİ\n" + "\n".join(
        f"{ad} {_deger(101.0 + i * 0.1)} 0,5 0,8 1,7"
        for i, ad in enumerate(PM_SEKTORLER)
    )
    sektor_day = "TİM SEKTÖR SINIFLANDIRMASINA GÖRE PAZAR DAYANIKLILIK ENDEKSİ\n" + "\n".join(
        f"{ad} 100,0 0,5 0,8 1,7" for ad in PM_SEKTORLER
    )
    ulke_talep = "SEÇİLMİŞ ÜLKELER İÇİN İHRACAT TALEP ENDEKSİ\n" + "\n".join(
        f"{ad} 101,0 0,5 0,8 1,7" for ad in PM_ULKELER
    )
    ulke_day = "SEÇİLMİŞ ÜLKELER İÇİN PAZAR DAYANIKLILIK ENDEKSİ\n" + "\n".join(
        f"{ad} 99,0 0,5 0,8 1,7" for ad in PM_ULKELER
    )
    return [milli, sektor_talep, sektor_day, ulke_talep, ulke_day]


class _SahteSayfa:
    def __init__(self, metin):
        self._metin = metin

    def extract_text(self):
        return self._metin


class _SahtePdf:
    def __init__(self, sayfalar):
        self.pages = [_SahteSayfa(m) for m in sayfalar]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_pm_bultenini_ayristir_tam_sablonda_gecer(monkeypatch):
    import ingest.tim as tim_mod

    monkeypatch.setattr(tim_mod.pdfplumber, "open", lambda _b: _SahtePdf(_tam_bulten_sayfalari()))
    sonuc = pm_bultenini_ayristir(b"x")
    assert sonuc["milli"] == {"talep": 100.4, "dayaniklilik": 99.8}
    assert sonuc["sektor-talep"]["Çelik"] == pytest.approx(101.0)
    assert set(sonuc["sektor-talep"]) == set(PM_SEKTORLER)
    assert set(sonuc["ulke-talep"]) == set(PM_ULKELER)


def test_pm_bultenini_ayristir_eksik_sektorde_hata(monkeypatch):
    import ingest.tim as tim_mod

    sayfalar = _tam_bulten_sayfalari()
    # sektör-talep sayfasından bir sektörü çıkar (şablon kayması simülasyonu)
    sayfalar[1] = sayfalar[1].replace("Çelik 101,0 0,5 0,8 1,7\n", "")
    monkeypatch.setattr(tim_mod.pdfplumber, "open", lambda _b: _SahtePdf(sayfalar))
    with pytest.raises(RuntimeError, match="şablonu değişmiş olabilir"):
        pm_bultenini_ayristir(b"x")


def test_pm_bultenini_ayristir_milli_eksikse_hata(monkeypatch):
    import ingest.tim as tim_mod

    sayfalar = _tam_bulten_sayfalari()
    sayfalar[0] = "TİM İHRACAT TALEP ENDEKSİ\nİhracat Talep Endeksi 100,4 0,1 0,3 0,5\n"  # Dayanıklılık kelimesi yok -> "milli" tipi tanınmaz
    monkeypatch.setattr(tim_mod.pdfplumber, "open", lambda _b: _SahtePdf(sayfalar))
    with pytest.raises(RuntimeError, match="şablonu değişmiş olabilir"):
        pm_bultenini_ayristir(b"x")


# --- pazar_monitoru_bulten_baglantilari: yıl arşivi -> aylık PDF ---


class SahteYanit:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class SahteOturum:
    def __init__(self, yanitlar):
        self.yanitlar = yanitlar

    def get(self, url, timeout=None):
        return self.yanitlar.get(url, SahteYanit(status_code=404))


def test_bulten_baglantilari_yil_sayfalarindan_pdf_toplar():
    ana_html = (
        '<a href="raporlar-yayinlar-bultenler-tim-ihracat-pazar-monitoru-2026">2026</a>'
    )
    yil_html = (
        '<a href="/files/downloads/T%C4%B0M%20%C4%B0hracat%20Pazar%20Monit%C3%B6r%C3%BC/'
        'TIMIhracatPazarMonitoru202607.pdf">Temmuz</a>'
    )
    oturum = SahteOturum({
        "https://tim.org.tr/tr/raporlar-yayinlar-tim-ihracat-pazar-monitoru": SahteYanit(text=ana_html),
        "https://tim.org.tr/tr/raporlar-yayinlar-bultenler-tim-ihracat-pazar-monitoru-2026": SahteYanit(text=yil_html),
    })
    baglantilar = pazar_monitoru_bulten_baglantilari(session=oturum)
    assert (2026, 7) in baglantilar
    assert baglantilar[(2026, 7)].endswith("TIMIhracatPazarMonitoru202607.pdf")


def test_bulten_baglantilari_bozuk_dosya_adini_da_bulur():
    """Ölçülen gerçek anomali: Nisan 2026 dosyasında 'İ' eklenip tire
    kullanılmış (`TİMIhracatPazarMonitoru-202604.pdf`)."""
    ana_html = '<a href="raporlar-yayinlar-bultenler-tim-ihracat-pazar-monitoru-2026">2026</a>'
    yil_html = (
        '<a href="/files/downloads/x/T%C4%B0MIhracatPazarMonitoru-202604.pdf">Nisan</a>'
    )
    oturum = SahteOturum({
        "https://tim.org.tr/tr/raporlar-yayinlar-tim-ihracat-pazar-monitoru": SahteYanit(text=ana_html),
        "https://tim.org.tr/tr/raporlar-yayinlar-bultenler-tim-ihracat-pazar-monitoru-2026": SahteYanit(text=yil_html),
    })
    baglantilar = pazar_monitoru_bulten_baglantilari(session=oturum)
    assert (2026, 4) in baglantilar


def test_bulten_baglantilari_yil_baglantisi_yoksa_hata():
    oturum = SahteOturum({
        "https://tim.org.tr/tr/raporlar-yayinlar-tim-ihracat-pazar-monitoru": SahteYanit(text="<html>boş</html>"),
    })
    with pytest.raises(RuntimeError, match="yıl bağlantısı bulunamadı"):
        pazar_monitoru_bulten_baglantilari(session=oturum)


# --- pazar_monitoru_seri_cek: dispatcher ---


def _onbellek():
    return {
        "pm_veri": {
            "milli-talep": {"2026-06-01": 98.9, "2026-07-01": 100.4},
            "milli-dayaniklilik": {"2026-06-01": 98.8, "2026-07-01": 99.8},
            "sektor-talep": {"Çelik": {"2026-07-01": 101.4}, "Tütün": {"2026-07-01": 100.7}},
            "sektor-dayaniklilik": {"Çelik": {"2026-07-01": 100.5}},
            "ulke-talep": {"Danimarka": {"2026-07-01": 102.9}, "İspanya": {"2026-07-01": 96.7}},
            "ulke-dayaniklilik": {"Danimarka": {"2026-07-01": 101.6}},
        }
    }


def test_seri_cek_milli_talep_dogru_deger_dondurur():
    df = pazar_monitoru_seri_cek(pm_seri(tim_pm_endeks="talep"), onbellek=_onbellek())
    assert df["value"].iloc[-1] == pytest.approx(100.4)


def test_seri_cek_milli_dayaniklilik_dogru_deger_dondurur():
    df = pazar_monitoru_seri_cek(pm_seri(tim_pm_endeks="dayaniklilik"), onbellek=_onbellek())
    assert df["value"].iloc[-1] == pytest.approx(99.8)


def test_seri_cek_sektor_talep_dogru_deger_dondurur():
    df = pazar_monitoru_seri_cek(
        pm_seri(tim_pm_endeks="talep", tim_pm_sektor="Çelik"), onbellek=_onbellek(),
    )
    assert df["value"].iloc[-1] == pytest.approx(101.4)


def test_seri_cek_ulke_talep_dogru_deger_dondurur():
    df = pazar_monitoru_seri_cek(
        pm_seri(tim_pm_endeks="talep", tim_pm_ulke="Danimarka"), onbellek=_onbellek(),
    )
    assert df["value"].iloc[-1] == pytest.approx(102.9)


def test_seri_cek_sektor_dayaniklilik_ayri_eksenden_okur():
    df = pazar_monitoru_seri_cek(
        pm_seri(tim_pm_endeks="dayaniklilik", tim_pm_sektor="Çelik"), onbellek=_onbellek(),
    )
    assert df["value"].iloc[-1] == pytest.approx(100.5)


def test_seri_cek_bilinmeyen_sektorde_hata():
    with pytest.raises(RuntimeError, match="sektörü İPM bültenlerinde bulunamadı"):
        pazar_monitoru_seri_cek(
            pm_seri(tim_pm_endeks="talep", tim_pm_sektor="Olmayan Sektör"), onbellek=_onbellek(),
        )


def test_seri_cek_bilinmeyen_ulkede_hata():
    with pytest.raises(RuntimeError, match="ülkesi İPM bültenlerinde bulunamadı"):
        pazar_monitoru_seri_cek(
            pm_seri(tim_pm_endeks="talep", tim_pm_ulke="Olmayan Ülke"), onbellek=_onbellek(),
        )


def test_seri_cek_start_date_oncesini_kirpar():
    df = pazar_monitoru_seri_cek(
        pm_seri(tim_pm_endeks="talep", start_date="2026-07-01"), onbellek=_onbellek(),
    )
    assert list(df["date"]) == ["2026-07-01"]
