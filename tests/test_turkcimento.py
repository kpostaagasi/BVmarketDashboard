"""TürkÇimento istemcisinin kabul testleri.

`aylik_toplam`/`_yil_dosyalari` gerçek `.xls` dosyası olmadan DÜZ PYTHON
YAPILARI (xlrd'nin `Book`/`Sheet` arayüzünü taklit eden sahte sınıflar) ile
test edilir — tıpkı `tests/test_otomotiv_marka.py`'nin openpyxl/pdfplumber
çıktısını taklit etmesi gibi (xlrd yalnızca OKUMA yapar, test dosyası
yazacak bir kütüphane projede yok). `seri_cek` ağ kabuğu testleri
`monkeypatch` ile HTTP/XLS katmanını atlar. Sayısal değerler 2026-09-18'de
canlı ölçülen gerçek TürkÇimento verisiyle birebir doğrulandı (bkz. yield
raporu); burada yalnızca ayrıştırma/önbellekleme mantığı pinlenir.
"""

from __future__ import annotations

import pytest

from ingest import turkcimento as tc


class SahteSayfa:
    def __init__(self, satirlar: list[list]):
        self._satirlar = satirlar
        self.nrows = len(satirlar)
        self.ncols = len(satirlar[0]) if satirlar else 0

    def cell_value(self, satir: int, sutun: int):
        deger = self._satirlar[satir][sutun]
        return deger if deger is not None else ""


class SahteKitap:
    def __init__(self, sayfalar: dict[str, SahteSayfa]):
        self._sayfalar = sayfalar

    def sheet_by_name(self, ad: str) -> SahteSayfa:
        return self._sayfalar[ad]


def _ay_sayfasi(uretim_2025=6957759.81, uretim_2026=8107646.6, ic_satis_2026=6778235.43) -> SahteSayfa:
    """Gerçek dosyanın Nisan 2026 sayfasının (2026-09-18 ölçümü) küçültülmüş
    biçimi: ÇİMENTO/Üretim ve ÇİMENTO/İç Satış blokları, TOPLAM son sütunda."""
    satirlar = [
        [None, "2026 Yılı Nisan Ayı Verileri"] + [None] * 8,
        [None] * 10,
        [None, None, None, None, "Marmara", "Ege", "Akdeniz", "Karadeniz", "İç Anadolu", "TOPLAM"],
        [None, "ÇİMENTO", "Üretim", "2025 Aylık", 1, 1, 1, 1, 1, uretim_2025],
        [None, None, None, "2026 Aylık", 1, 1, 1, 1, 1, uretim_2026],
        [None, None, None, "%", 1, 1, 1, 1, 1, 1],
        [None, None, None, "2025 Devre", 1, 1, 1, 1, 1, 1],
        [None, None, None, "2026 Devre", 1, 1, 1, 1, 1, 1],
        [None, None, None, "%", 1, 1, 1, 1, 1, 1],
        [None, None, "İç Satış", "2025 Aylık", 1, 1, 1, 1, 1, 1],
        [None, None, None, "2026 Aylık", 1, 1, 1, 1, 1, ic_satis_2026],
    ]
    return SahteSayfa(satirlar)


def _bos_ay_sayfasi() -> SahteSayfa:
    """Henüz yayımlanmamış ay: blok var ama TOPLAM = 0.0 (Eylül 2026 gibi)."""
    satirlar = [
        [None, "2026 Yılı Eylül Ayı Verileri"] + [None] * 8,
        [None] * 10,
        [None, None, None, None, "Marmara", "Ege", "Akdeniz", "Karadeniz", "İç Anadolu", "TOPLAM"],
        [None, "ÇİMENTO", "Üretim", "2025 Aylık", 1, 1, 1, 1, 1, 1000.0],
        [None, None, None, "2026 Aylık", 0, 0, 0, 0, 0, 0.0],
    ]
    return SahteSayfa(satirlar)


def test_aylik_toplam_dogru_urun_alt_ve_yili_bulur():
    kitap = SahteKitap({"nisan": _ay_sayfasi()})
    assert tc.aylik_toplam(kitap, "nisan", 2026, "ÇİMENTO", "Üretim") == 8107646.6
    assert tc.aylik_toplam(kitap, "nisan", 2026, "ÇİMENTO", "İç Satış") == 6778235.43


def test_aylik_toplam_gecen_yili_karistirmaz():
    kitap = SahteKitap({"nisan": _ay_sayfasi()})
    assert tc.aylik_toplam(kitap, "nisan", 2025, "ÇİMENTO", "Üretim") == 6957759.81


def test_aylik_toplam_olmayan_blok_none_doner():
    kitap = SahteKitap({"nisan": _ay_sayfasi()})
    assert tc.aylik_toplam(kitap, "nisan", 2026, "KLİNKER", "Üretim") is None


def test_seri_cek_henuz_yayimlanmamis_ayi_atlar(monkeypatch):
    """TOPLAM = 0.0 olan ay (henüz yayımlanmamış) noktalara girmez."""
    kitap = SahteKitap({"nisan": _ay_sayfasi(), "eylul": _bos_ay_sayfasi()})
    monkeypatch.setattr(tc, "_yil_dosyalari", lambda session=None: {2026: "https://example.test/2026.xls"})
    monkeypatch.setattr(tc, "_xls_indir", lambda url, session=None: b"sahte")
    monkeypatch.setattr(tc.xlrd, "open_workbook", lambda file_contents: kitap)

    seri = type("S", (), {
        "turkcimento_metrik": "cimento-uretim", "start_date": None, "id": "cimento/test",
    })()
    df = tc.seri_cek(seri, onbellek={})
    assert list(df["date"]) == ["2026-04-01"]
    assert df["value"].iloc[0] == pytest.approx(8107.6466)  # ton -> bin ton


def test_seri_cek_onbellegi_paylasir(monkeypatch):
    indirilenler = []

    def sahte_indir(url, session=None):
        indirilenler.append(url)
        return b"sahte"

    kitap = SahteKitap({"nisan": _ay_sayfasi()})
    monkeypatch.setattr(tc, "_yil_dosyalari", lambda session=None: {2026: "https://example.test/2026.xls"})
    monkeypatch.setattr(tc, "_xls_indir", sahte_indir)
    monkeypatch.setattr(tc.xlrd, "open_workbook", lambda file_contents: kitap)

    seri1 = type("S", (), {"turkcimento_metrik": "cimento-uretim", "start_date": None, "id": "a"})()
    seri2 = type("S", (), {"turkcimento_metrik": "cimento-ic-satis", "start_date": None, "id": "b"})()
    onbellek: dict = {}
    tc.seri_cek(seri1, onbellek=onbellek)
    tc.seri_cek(seri2, onbellek=onbellek)
    assert indirilenler == ["https://example.test/2026.xls"]  # bir kez indirildi


def test_seri_cek_blok_hic_bulunamazsa_yukselir(monkeypatch):
    kitap = SahteKitap({"nisan": _ay_sayfasi()})
    monkeypatch.setattr(tc, "_yil_dosyalari", lambda session=None: {2026: "https://example.test/2026.xls"})
    monkeypatch.setattr(tc, "_xls_indir", lambda url, session=None: b"sahte")
    monkeypatch.setattr(tc.xlrd, "open_workbook", lambda file_contents: kitap)
    # "nisan" dışındaki tüm ay sayfaları da isteniyor ama SahteKitap'ta yok —
    # KeyError yerine RuntimeError'a dönüşmeli mi diye değil, "hiç bulunamadı"
    # yoluna düşüp düşmediğine bakılıyor; bunun için tüm ay sayfalarını ekle.
    tum_aylar = {ay: _ay_sayfasi() if ay == "nisan" else SahteSayfa([[None] * 10]) for ay in tc.AY_SAYFALARI}
    monkeypatch.setattr(tc.xlrd, "open_workbook", lambda file_contents: SahteKitap(tum_aylar))

    seri = type("S", (), {"turkcimento_metrik": "klinker-uretim", "start_date": None, "id": "cimento/x"})()
    with pytest.raises(RuntimeError, match="hiçbir sayfada bulunamadı"):
        tc.seri_cek(seri, onbellek={})


def test_yil_dosyalari_desenle_eslesen_linkleri_cikarir():
    html = (
        '<a href="https://www.turkcimento.org.tr/uploads/pdf/Yeni-2026_Aylik-rev2.xls">İNDİR</a>'
        '<a href="https://www.turkcimento.org.tr/uploads/pdf/Yeni-2025_Aylik-rev4.xls">İNDİR</a>'
        '<a href="https://example.test/alakasiz.xls">İNDİR</a>'
    )

    class SahteYanit:
        status_code = 200
        text = html

    class SahteOturum:
        def get(self, url, timeout=None):
            return SahteYanit()

    eslesme = tc._yil_dosyalari(session=SahteOturum())
    assert eslesme == {
        2026: "https://www.turkcimento.org.tr/uploads/pdf/Yeni-2026_Aylik-rev2.xls",
        2025: "https://www.turkcimento.org.tr/uploads/pdf/Yeni-2025_Aylik-rev4.xls",
    }
