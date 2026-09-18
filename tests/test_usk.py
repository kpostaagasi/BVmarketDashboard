"""USK (Ulusal Süt Konseyi) çiğ süt tavsiye fiyatı ve üretim maliyeti
istemcisi testleri."""

from datetime import date
from types import SimpleNamespace

import pytest

from ingest.usk import (
    _eski_format_ayikla,
    _format_tespit_et,
    _yeni_format_ayikla,
    aylik_seriye_yay,
    cekilecek_maliyet_dosyalari,
    maliyet_dosyalarini_ayikla,
    maliyet_pdf_ayikla,
    seri_cek,
    tavsiye_tablosunu_ayikla,
)


def usk_seri(**kwargs):
    varsayilan = dict(id="test/tavsiye-fiyati", usk_kalem="tavsiye-fiyati", start_date=None)
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


# --- tavsiye_tablosunu_ayikla: TablePress HTML ---


def _tavsiye_tablosu_html(satirlar):
    """`satirlar`: [(yıl_ya_da_None, col1, col2)] — yıl verilmişse başlık satırı."""
    icerik = []
    for yil, col1, col2 in satirlar:
        if yil is not None:
            icerik.append(f'<tr><td class="column-1"><strong>{yil} YILI</strong></td><td class="column-2"><strong>TL/litre</strong></td></tr>')
        else:
            icerik.append(f'<tr><td class="column-1">{col1}</td><td class="column-2">{col2}</td></tr>')
    return '<table id="tablepress-27"><tbody>' + "".join(icerik) + "</tbody></table>"


def test_tavsiye_tablosunu_ayikla_gun_ay_ayiklar():
    html = _tavsiye_tablosu_html([(2026, None, None), (None, "1 Mayıs -", "24,30")])
    sonuc = tavsiye_tablosunu_ayikla(html)
    assert sonuc == [("2026-05-01", 24.30)]


def test_tavsiye_tablosunu_ayikla_gun_araligini_ilk_gune_indirger():
    """'1-31 Ocak' → gün 1, Ocak (31 değil — bkz. modül testinin amacı)."""
    html = _tavsiye_tablosu_html([(2024, None, None), (None, "1-31 Ocak", "1,40")])
    assert tavsiye_tablosunu_ayikla(html) == [("2024-01-01", 1.40)]


def test_tavsiye_tablosunu_ayikla_dipnot_yildizlarini_yok_sayar():
    html = _tavsiye_tablosu_html([(2017, None, None), (None, "1 Ocak-31 Temmuz", "1,21**")])
    assert tavsiye_tablosunu_ayikla(html) == [("2017-01-01", 1.21)]


def test_tavsiye_tablosunu_ayikla_coklu_yili_sirali_dondurur():
    html = _tavsiye_tablosu_html([
        (2025, None, None), (None, "1 Ocak - 31 Temmuz", "17,15"),
        (2026, None, None), (None, "1 Ocak - 21 Ocak", "19,60"),
        (None, "22 Ocak - 30 Nisan", "22,22"),
        (None, "1 Mayıs -", "24,30"),
    ])
    assert tavsiye_tablosunu_ayikla(html) == [
        ("2025-01-01", 17.15), ("2026-01-01", 19.60), ("2026-01-22", 22.22), ("2026-05-01", 24.30),
    ]


def test_tavsiye_tablosunu_ayikla_tablo_yoksa_hata():
    with pytest.raises(RuntimeError, match="tablosu bulunamadı"):
        tavsiye_tablosunu_ayikla("<html><body>yok</body></html>")


# --- aylik_seriye_yay: kırık noktaları aylık ızgaraya ileri-doldurma ---


def test_aylik_seriye_yay_degisim_oncesi_sonrasi_dogru_deger_tasir():
    kirilmalar = [("2026-01-22", 22.22), ("2026-05-01", 24.30)]
    sonuc = aylik_seriye_yay(kirilmalar, date(2026, 6, 15))
    assert sonuc["2026-01-01"] == 22.22  # başlangıç noktası ocak ayı değeri
    assert sonuc["2026-04-01"] == 22.22  # mayıs öncesi hâlâ eski değer
    assert sonuc["2026-05-01"] == 24.30
    assert sonuc["2026-06-01"] == 24.30  # son değer bugüne kadar taşınır


def test_aylik_seriye_yay_bos_listede_bos_doner():
    assert aylik_seriye_yay([], date(2026, 1, 1)) == {}


# --- maliyet_dosyalarini_ayikla: yalnızca temiz "Ay, YYYY" bağlantıları ---


def test_maliyet_dosyalarini_ayikla_temiz_baglantilari_alir():
    html = '<a href="https://x/MALIYET-AGUSTOS-2026.pdf">Ağustos, 2026</a>'
    assert maliyet_dosyalarini_ayikla(html) == {(2026, 8): "https://x/MALIYET-AGUSTOS-2026.pdf"}


def test_maliyet_dosyalarini_ayikla_coklu_ay_araligini_atlar():
    """'Ocak-Mart, 2019' gibi çok-aylık aralıklar ay adı eşleşmediği için elenir."""
    html = '<a href="https://x/OCAK-MART-2019.pdf">Ocak-Mart, 2019</a>'
    assert maliyet_dosyalarini_ayikla(html) == {}


def test_maliyet_dosyalarini_ayikla_pdf_disi_baglantilari_yok_sayar():
    html = '<a href="https://x/sayfa.html">Ağustos, 2026</a>'
    assert maliyet_dosyalarini_ayikla(html) == {}


def test_cekilecek_maliyet_dosyalari_pencereyi_daraltir():
    dosyalar = {(2019, 1): "eski", (2021, 1): "gecerli", (2026, 12): "gelecek"}
    sonuc = cekilecek_maliyet_dosyalari(dosyalar, date(2026, 9, 18))
    assert sonuc == {(2021, 1): "gecerli"}


# --- format tespiti + ayıklama: gerçek belgelerden alınmış (kısaltılmış) metinler ---

_ESKI_FORMAT_METNI = (
    "ÇİĞ SÜT MALİYET HESAPLAMA KRİTERLERİ\n"
    "MARMARA BÖLGESİ 1 LİTRE ÇİĞ SÜT MALİYETİ\n"
    "FARK 296,72 FARK 296,72\nMALİYET 14,84 MALİYET 14,84\n"
    "BÖLGELER MALİYET(TL/LT)\nMARMARA 14,84\nEGE 14,84\n"
    "İÇ ANADOLU 14,84\nAKDENİZ 14,84 * ÇİĞ SÜT DESTEKLEME PRİMİ.\n"
    "TÜRKİYE ORTALAMASI 14,84"
)

_YENI_FORMAT_METNI = (
    "AĞUSTOS - 2026 DÖNEMİ\nTÜM BÖLGELERE GÖRE 1 LİTRE ÇİĞ SÜT ÜRETİM MALİYETİ\n"
    "TEMEL KABULLER\nIRKI HOLSTEİN\nCANLI AĞIRLIK (KG) 600\n"
    "SÜT VERİMİ (LT/GÜN ) 20\nBUZAĞI FİYATI (TL/BAŞ) 38.000\n"
    "RASYON (Sağılan İnek)\nYEM MİKTARI BİRİM FİYAT YEM MALİYETİ\nYEMİN ADI\n"
    "(Kg/Gün) (TL/Kg) (TL/Gün)\nKarma Yem 8 19,07 152,56\n"
    "Mısır Silajı 20 4,75 95,00\nYonca 4 12,24 48,96\nSaman 2 4,13 8,26\n"
    "Fire (%3) 9,14\nTOPLAM 313,92\nGİDERLER\n% TL/GÜN\n"
    "Yem Gideri (Sağılan İnek) 62,1 313,92\nDiğer Giderler\n37,9 191,59\n"
    "(İşçilik, Yakıt, Su, Elektrik, Sağlık, Tohum,\nSigorta, Faiz, Amortisman vb.)\n"
    "TOPLAM 100,0 505,51\nGELİRLER\n"
    "Buzağı Geliri (Buzağı Fiyatı/450) *0,9 76,00\nGELİR TOPLAM 76,00\n"
    "FARK 429,51\nÇİĞ SÜT ÜRETİM MALİYETİ 21,48 TL/Litre\nNotlar"
)


def test_format_tespit_et_eski_ve_yeniyi_ayirir():
    assert _format_tespit_et(_ESKI_FORMAT_METNI) == "eski"
    assert _format_tespit_et(_YENI_FORMAT_METNI) == "yeni"


def test_format_tespit_et_bilinmeyen_sablonda_hata():
    with pytest.raises(RuntimeError, match="tanınmayan"):
        _format_tespit_et("alakasız içerik")


def test_eski_format_ayikla_turkiye_ortalamasini_okur():
    assert _eski_format_ayikla(_ESKI_FORMAT_METNI) == pytest.approx(14.84)


def test_yeni_format_ayikla_gercek_deger_agustos_2026():
    """CANLI ölçülen referans (2026-09-18): 21,48 TL/Litre."""
    sonuc = _yeni_format_ayikla(_YENI_FORMAT_METNI)
    assert sonuc["maliyet"] == pytest.approx(21.48)
    assert sonuc["buzagi_fiyati"] == pytest.approx(38000.0)
    assert sonuc["karma_yem_fiyati"] == pytest.approx(19.07)
    assert sonuc["yem_maliyeti_toplam"] == pytest.approx(313.92)
    assert sonuc["diger_giderler"] == pytest.approx(191.59)
    assert sonuc["fark"] == pytest.approx(429.51)


def test_yeni_format_ayikla_alan_eksikse_hata():
    with pytest.raises(RuntimeError, match="canli_agirlik"):
        _yeni_format_ayikla("RASYON (Sağılan İnek)\nÇİĞ SÜT ÜRETİM MALİYETİ 21,48 TL")


class _SahteSayfa:
    def __init__(self, metin):
        self._metin = metin

    def extract_text(self):
        return self._metin


class _SahtePdf:
    def __init__(self, metin):
        self.pages = [_SahteSayfa(metin)]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_maliyet_pdf_ayikla_eski_formatta_yalnizca_maliyet_doner(monkeypatch):
    import ingest.usk as usk_mod
    monkeypatch.setattr(usk_mod.pdfplumber, "open", lambda _b: _SahtePdf(_ESKI_FORMAT_METNI))
    assert maliyet_pdf_ayikla(b"pdf") == {"uretim-maliyeti": pytest.approx(14.84)}


def test_maliyet_pdf_ayikla_yeni_formatta_tum_kalemleri_doner(monkeypatch):
    import ingest.usk as usk_mod
    monkeypatch.setattr(usk_mod.pdfplumber, "open", lambda _b: _SahtePdf(_YENI_FORMAT_METNI))
    sonuc = maliyet_pdf_ayikla(b"pdf")
    assert sonuc["uretim-maliyeti"] == pytest.approx(21.48)
    assert sonuc["buzagi-fiyati"] == pytest.approx(38000.0)
    assert len(sonuc) == 12  # uretim-maliyeti + 11 granüler kalem


# --- seri_cek: ağ kabuğu ---


class SahteYanit:
    def __init__(self, status_code=200, text="", content=b""):
        self.status_code = status_code
        self.text = text
        self.content = content


class SahteOturum:
    def __init__(self, tavsiye_html, maliyet_liste_html, pdf_metni=_YENI_FORMAT_METNI):
        self.tavsiye_html = tavsiye_html
        self.maliyet_liste_html = maliyet_liste_html
        self.pdf_metni = pdf_metni
        self.cagrilar = []

    def get(self, url, timeout=None, headers=None):
        # UA başlığı zorunlu: USK sunucusu varsayılan requests UA'sını 403'lüyor.
        assert headers and "User-Agent" in headers, "USK isteği UA başlığı taşımalı"
        self.cagrilar.append(url)
        if "yillara-gore" in url:
            return SahteYanit(text=self.tavsiye_html)
        if "bolgelere-gore" in url:
            return SahteYanit(text=self.maliyet_liste_html)
        return SahteYanit(content=b"pdf-bytes")


def _basit_tavsiye_html():
    return _tavsiye_tablosu_html([(2026, None, None), (None, "1 Ocak -", "20,00")])


def _basit_maliyet_liste_html():
    return '<a href="https://x/MALIYET-AGUSTOS-2026.pdf">Ağustos, 2026</a>'


def test_seri_cek_uretim_maliyeti_dogru_deger_dondurur(monkeypatch):
    import ingest.usk as usk_mod
    monkeypatch.setattr(usk_mod.pdfplumber, "open", lambda _b: _SahtePdf(_YENI_FORMAT_METNI))
    oturum = SahteOturum(_basit_tavsiye_html(), _basit_maliyet_liste_html())
    df = seri_cek(usk_seri(usk_kalem="uretim-maliyeti"), onbellek={}, session=oturum, bugun=date(2026, 9, 18))
    assert df["value"].iloc[0] == pytest.approx(21.48)
    assert df["date"].iloc[0] == "2026-08-01"


def test_seri_cek_tavsiye_fiyati_aylik_izgaraya_yayilir(monkeypatch):
    import ingest.usk as usk_mod
    monkeypatch.setattr(usk_mod.pdfplumber, "open", lambda _b: _SahtePdf(_YENI_FORMAT_METNI))
    oturum = SahteOturum(_basit_tavsiye_html(), _basit_maliyet_liste_html())
    df = seri_cek(usk_seri(usk_kalem="tavsiye-fiyati"), onbellek={}, session=oturum, bugun=date(2026, 8, 18))
    assert list(df["date"]) == [
        "2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01",
        "2026-05-01", "2026-06-01", "2026-07-01", "2026-08-01",
    ]
    assert (df["value"] == 20.0).all()


def test_seri_cek_onbellegi_paylasir(monkeypatch):
    import ingest.usk as usk_mod
    monkeypatch.setattr(usk_mod.pdfplumber, "open", lambda _b: _SahtePdf(_YENI_FORMAT_METNI))
    oturum = SahteOturum(_basit_tavsiye_html(), _basit_maliyet_liste_html())
    onbellek = {}
    seri_cek(usk_seri(usk_kalem="uretim-maliyeti"), onbellek=onbellek, session=oturum, bugun=date(2026, 9, 18))
    cagri_sayisi = len(oturum.cagrilar)
    seri_cek(usk_seri(usk_kalem="buzagi-fiyati"), onbellek=onbellek, session=oturum, bugun=date(2026, 9, 18))
    assert len(oturum.cagrilar) == cagri_sayisi


def test_seri_cek_bilinmeyen_kalemde_hata(monkeypatch):
    import ingest.usk as usk_mod
    monkeypatch.setattr(usk_mod.pdfplumber, "open", lambda _b: _SahtePdf(_YENI_FORMAT_METNI))
    oturum = SahteOturum(_basit_tavsiye_html(), _basit_maliyet_liste_html())
    with pytest.raises(RuntimeError, match="bulunamadı"):
        seri_cek(usk_seri(usk_kalem="yok-olan-kalem"), onbellek={}, session=oturum, bugun=date(2026, 9, 18))


def test_seri_cek_maliyet_listesi_bosken_hata():
    oturum = SahteOturum(_basit_tavsiye_html(), "<html>hiç bağlantı yok</html>")
    with pytest.raises(RuntimeError, match="maliyet PDF"):
        seri_cek(usk_seri(usk_kalem="uretim-maliyeti"), onbellek={}, session=oturum, bugun=date(2026, 9, 18))
