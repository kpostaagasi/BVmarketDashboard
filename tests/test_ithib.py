"""İTHİB (Tekstil İhracat Değerlendirme Notu) PDF istemcisi testleri.

`pdfplumber.open` monkeypatch'lenip sahte `Sayfa`/`Pdf` nesneleri
beslenir (bkz. `tests/test_tmsd.py`'deki aynı desen) — gerçek PDF
üretilmez; `extract_words()`/`extract_text()` çıktısı elle inşa edilir.
Bu, modülün asıl kırılganlığını (konum tabanlı kategori/değer
eşleştirmesi, tek aylık sayfa seçimi, çeyrek sonu kümülatif sayfa
tuzağı) gerçek PDF üretmeden pinler.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import ingest.ithib as ithib_mod
from ingest.ithib import (
    KALEM_IPLIK,
    KALEM_TEKNIK_TEKSTIL,
    _bulteni_getir,
    _degerleri_ayikla,
    _kategorileri_bul,
    _urun_grubu_sayfasini_bul,
    bulteni_ayikla,
    liste_baglantilarini_cek,
    seri_cek,
)


def ithib_seri(**kwargs):
    varsayilan = {"id": "test/iplik", "ithib_kalem": KALEM_IPLIK, "start_date": None}
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


def _kelime(x0, top, metin):
    return {"x0": x0, "x1": x0 + len(metin) * 9.0, "top": top, "text": metin}


class _SahteSayfa:
    def __init__(self, metin, kelimeler):
        self._metin = metin
        self._kelimeler = kelimeler

    def extract_text(self):
        return self._metin

    def extract_words(self):
        return self._kelimeler


class _SahtePdf:
    def __init__(self, sayfalar):
        self.pages = sayfalar

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


# Gerçek 2026 Ağustos bültenindeki değerlerle birebir eşleşen, elle
# inşa edilmiş tek-aylık karşılaştırma sayfası (bkz. modül docstring'i).
_KATEGORI_ETIKET_KELIMELERI = [
    _kelime(130.4, 401.0, "İPLİK"),
    _kelime(211.5, 401.0, "TEKNİK"),
    _kelime(266.8, 401.0, "TEKSTİL"),
    _kelime(354.7, 401.0, "DOKUMA"),
    _kelime(361.5, 420.6, "KUMAŞ"),
    _kelime(466.2, 401.0, "EV"),
    _kelime(487.9, 401.0, "TEKSTİLİ"),
    _kelime(578.1, 401.0, "ÖRME"),
    _kelime(624.4, 401.0, "KUMAŞ"),
    _kelime(725.1, 401.0, "ELYAF"),
    _kelime(815.3, 401.0, "KONFEKSİYON"),
    _kelime(823.5, 420.6, "YAN"),
    _kelime(857.6, 420.6, "SANAYİ"),
]

_DEGER_KELIMELERI = [
    _kelime(110.3, 150.0, "179"), _kelime(136.0, 130.0, "199"),  # İPLİK: önceki, bu yıl
    _kelime(230.0, 168.0, "183"), _kelime(256.2, 169.0, "182"),  # TEKNİK TEKSTİL
    _kelime(349.3, 166.0, "184"), _kelime(376.8, 175.0, "176"),  # DOKUMA KUMAŞ
    _kelime(470.1, 202.0, "151"), _kelime(496.1, 194.0, "159"),  # EV TEKSTİLİ
    _kelime(590.1, 219.0, "135"), _kelime(616.2, 241.0, "116"),  # ÖRME KUMAŞ
    _kelime(713.3, 281.0, "79"), _kelime(735.8, 248.0, "108"),   # ELYAF
    _kelime(833.1, 312.0, "50"), _kelime(859.0, 311.0, "51"),    # KONFEKSİYON YAN SANAYİ
]


def _iyi_sayfa(onceki_yil=2025, bu_yil=2026, ay="Ağustos"):
    metin = (
        "ÜRÜN GRUBU BAZINDA TEKSTİL SEKTÖRÜ İHRACATI\n"
        f"{ay} Ayında Ürün Grupları Bazında Türkiye Tekstil Sektörü İhracatı\n"
        f"{onceki_yil} {ay} {bu_yil} {ay}"
    )
    return _SahteSayfa(metin, _KATEGORI_ETIKET_KELIMELERI + _DEGER_KELIMELERI)


def _ceyrek_sonu_kumulatif_sayfa():
    """Çeyrek sonu (Mart/Haziran/Eylül/Aralık) bültenlerindeki, AYNI
    başlığı taşıyan ama kümülatif olan tuzak sayfa (bkz. modül
    docstring'i: '2025 Ocak-Mart 2026 Ocak-Mart' lejantı — ay adı
    tireli aralık olduğu için tek-ay deseniyle eşleşmemeli)."""
    metin = (
        "ÜRÜN GRUBU BAZINDA TEKSTİL SEKTÖRÜ İHRACATI\n"
        "2025 Ocak-Mart 2026 Ocak-Mart"
    )
    return _SahteSayfa(metin, [])


# --- liste_baglantilarini_cek ---


def test_liste_baglantilarini_cek_baglanti_ve_ay_cikarir():
    html = (
        '<a href="https://x/Tekstil-İhracat-Değerlendirme-Notu---2026-Ağustos-Ayı.pdf" '
        'target="_blank" class="stretched-link">'
        '<h3 class="title">Tekstil İhracat Değerlendirme Notu - 2026 Ağustos Ayı</h3></a>'
        '<a href="https://x/2025-eylul.pdf"><h3>Tekstil İhracat Değerlendirme Notu - 2025 Eylül Ayı</h3></a>'
    )
    sonuc = liste_baglantilarini_cek(html)
    assert sonuc[(2026, 8)] == "https://x/Tekstil-İhracat-Değerlendirme-Notu---2026-Ağustos-Ayı.pdf"
    assert sonuc[(2025, 9)] == "https://x/2025-eylul.pdf"


def test_liste_baglantilarini_cek_bos_sayfa_hata_verir():
    with pytest.raises(RuntimeError, match="hiç rapor bağlantısı"):
        liste_baglantilarini_cek("<html>boş</html>")


def test_liste_baglantilarini_cek_bilinmeyen_ay_hata_verir():
    html = '<a href="https://x/y.pdf"><h3>Tekstil İhracat Değerlendirme Notu - 2026 Zulüs Ayı</h3></a>'
    with pytest.raises(RuntimeError, match="bilinmeyen ay adı"):
        liste_baglantilarini_cek(html)


# --- _urun_grubu_sayfasini_bul ---


def test_urun_grubu_sayfasini_bul_ceyrek_kumulatif_tuzagini_atlar():
    """Çeyrek sonu bültenindeki kümülatif tuzak sayfa (boş kelime
    listesi) değil, gerçek tek-aylık sayfa (7 kategori kelimesi)
    seçilmeli."""
    pdf = _SahtePdf([_ceyrek_sonu_kumulatif_sayfa(), _iyi_sayfa(ay="Mart")])
    sayfa = _urun_grubu_sayfasini_bul(pdf, "Mart")
    assert sayfa.extract_words() != []
    assert len(_kategorileri_bul(sayfa)) == 7


def test_urun_grubu_sayfasini_bul_baska_ay_lejanti_reddedilir():
    """Beklenen aydan farklı bir tek-ay lejantı eşleşmemeli."""
    pdf = _SahtePdf([_iyi_sayfa(ay="Temmuz")])
    with pytest.raises(RuntimeError, match="bulunamadı"):
        _urun_grubu_sayfasini_bul(pdf, "Ağustos")


def test_urun_grubu_sayfasini_bul_hicbir_sayfa_yoksa_hata_verir():
    pdf = _SahtePdf([_SahteSayfa("ilgisiz içerik", [])])
    with pytest.raises(RuntimeError, match="bulunamadı"):
        _urun_grubu_sayfasini_bul(pdf, "Ağustos")


# --- _kategorileri_bul ---


def test_kategorileri_bul_yedi_kategoriyi_dogru_birlestirir():
    sayfa = _iyi_sayfa()
    kategoriler = _kategorileri_bul(sayfa)
    etiketler = sorted(ad for ad, _, _ in kategoriler)
    assert etiketler == sorted([
        "İPLİK", "TEKNİK TEKSTİL", "DOKUMA KUMAŞ", "EV TEKSTİLİ",
        "ÖRME KUMAŞ", "ELYAF", "KONFEKSİYON YAN SANAYİ",
    ])


def test_kategorileri_bul_eksik_kategori_hata_verir():
    eksik = [k for k in _KATEGORI_ETIKET_KELIMELERI if k["text"] != "ELYAF"]
    sayfa = _SahteSayfa("", eksik)
    with pytest.raises(RuntimeError, match="beklenenle uyuşmuyor"):
        _kategorileri_bul(sayfa)


def test_kategorileri_bul_dusey_konum_kaymasina_dayanikli():
    """Çubuk yüksekliğine göre etiket satırının 'top' konumu ay
    bağımsız kayabilir (bkz. modül docstring'i) — sabit bant değil,
    en kalabalık satır (mod) kullanılmalı."""
    kaydirilmis = [dict(k, top=k["top"] + 50) for k in _KATEGORI_ETIKET_KELIMELERI]
    sayfa = _SahteSayfa("", kaydirilmis)
    kategoriler = _kategorileri_bul(sayfa)
    assert len(kategoriler) == 7


# --- _degerleri_ayikla ---


def test_degerleri_ayikla_kucuk_x0_onceki_buyuk_x0_bu_yil():
    sayfa = _iyi_sayfa()
    kategoriler = _kategorileri_bul(sayfa)
    degerler = _degerleri_ayikla(sayfa, kategoriler, "test")
    assert degerler["İPLİK"] == (179.0, 199.0)
    assert degerler["KONFEKSİYON YAN SANAYİ"] == (50.0, 51.0)


def test_degerleri_ayikla_yanlis_sayida_deger_hata_verir():
    kategoriler = _kategorileri_bul(_iyi_sayfa())
    sadece_iplik_degerleri = [k for k in _DEGER_KELIMELERI if k["x0"] < 200]
    sayfa = _SahteSayfa("", sadece_iplik_degerleri)
    with pytest.raises(RuntimeError, match="2 değer bekleniyor"):
        _degerleri_ayikla(sayfa, kategoriler, "test")


def test_degerleri_ayikla_ondalikli_deger_de_okunur():
    """Bazı baskılar değerleri nokta ayraçlı ondalıkla basıyor (bkz.
    modül docstring'i ve `_degerleri_ayikla`)."""
    kategoriler = _kategorileri_bul(_iyi_sayfa())
    ondalikli = [
        dict(k, text=str(round(float(k["text"]) + 0.5, 3))) if k["text"].lstrip("-").isdigit() else k
        for k in _DEGER_KELIMELERI
    ]
    sayfa = _SahteSayfa("", ondalikli)
    degerler = _degerleri_ayikla(sayfa, kategoriler, "test")
    assert degerler["İPLİK"] == (179.5, 199.5)


# --- bulteni_ayikla ---


def test_bulteni_ayikla_kalem_eslemesi_dogru(monkeypatch):
    def sahte_pdfplumber_open(_baytlar):
        return _SahtePdf([_iyi_sayfa()])

    monkeypatch.setattr(ithib_mod.pdfplumber, "open", sahte_pdfplumber_open)
    sonuc = bulteni_ayikla(b"pdf", 2026, 8)
    assert sonuc[KALEM_IPLIK] == (179.0, 199.0)
    assert sonuc[KALEM_TEKNIK_TEKSTIL] == (183.0, 182.0)
    assert len(sonuc) == 7


# --- seri_cek ---


class SahteYanit:
    def __init__(self, status_code, content=b"", text=""):
        self.status_code = status_code
        self.content = content
        self.text = text


class SahteOturum:
    def __init__(self, yanitlar):
        self.yanitlar = yanitlar

    def get(self, url, timeout=None):
        return self.yanitlar.get(url, SahteYanit(404))


_LISTE_HTML = (
    '<a href="https://x/agu26.pdf"><h3>Tekstil İhracat Değerlendirme Notu - 2026 Ağustos Ayı</h3></a>'
)


def _sahte_pdf_kurulumu(monkeypatch):
    def sahte_pdfplumber_open(_baytlar):
        return _SahtePdf([_iyi_sayfa()])

    monkeypatch.setattr(ithib_mod.pdfplumber, "open", sahte_pdfplumber_open)


def test_seri_cek_bilinmeyen_kalem_hata_verir():
    with pytest.raises(RuntimeError, match="bilinmeyen kalem"):
        seri_cek(ithib_seri(ithib_kalem="yok-olan-kalem"), session=SahteOturum({}))


def test_seri_cek_iki_nokta_uretir_bu_ay_ve_gecen_yil(monkeypatch):
    """Her bülten İKİ noktaya katkı yapmalı: bu ay + aynı ay bir önceki
    yıl (bkz. modül docstring'i)."""
    _sahte_pdf_kurulumu(monkeypatch)
    oturum = SahteOturum({
        ithib_mod.LISTE_URL: SahteYanit(200, text=_LISTE_HTML),
        "https://x/agu26.pdf": SahteYanit(200, b"pdf-baytlari"),
    })
    df = seri_cek(ithib_seri(), onbellek={}, session=oturum)
    satirlar = dict(zip(df["date"], df["value"]))
    assert satirlar["2026-08-01"] == 199.0
    assert satirlar["2025-08-01"] == 179.0
    assert len(df) == 2


def test_seri_cek_liste_sayfasi_404_hata_verir():
    oturum = SahteOturum({ithib_mod.LISTE_URL: SahteYanit(404)})
    with pytest.raises(RuntimeError, match="HTTP 404"):
        seri_cek(ithib_seri(), session=oturum)


def test_seri_cek_onbellek_paylasilir_iki_kalem_icin_yeniden_indirmez(monkeypatch):
    _sahte_pdf_kurulumu(monkeypatch)
    cagri_sayisi = SimpleNamespace(n=0)

    class SayanOturum(SahteOturum):
        def get(self, url, timeout=None):
            cagri_sayisi.n += 1
            return super().get(url, timeout)

    oturum = SayanOturum({
        ithib_mod.LISTE_URL: SahteYanit(200, text=_LISTE_HTML),
        "https://x/agu26.pdf": SahteYanit(200, b"pdf-baytlari"),
    })
    onbellek: dict = {}
    seri_cek(ithib_seri(ithib_kalem=KALEM_IPLIK), onbellek=onbellek, session=oturum)
    ilk_cagri = cagri_sayisi.n
    seri_cek(ithib_seri(ithib_kalem=KALEM_TEKNIK_TEKSTIL), onbellek=onbellek, session=oturum)
    assert cagri_sayisi.n == ilk_cagri  # liste + pdf zaten önbellekte, yeni istek yok


def test_seri_cek_start_date_oncesini_kirpar(monkeypatch):
    _sahte_pdf_kurulumu(monkeypatch)
    oturum = SahteOturum({
        ithib_mod.LISTE_URL: SahteYanit(200, text=_LISTE_HTML),
        "https://x/agu26.pdf": SahteYanit(200, b"pdf-baytlari"),
    })
    df = seri_cek(ithib_seri(start_date="2026-01-01"), onbellek={}, session=oturum)
    assert list(df["date"]) == ["2026-08-01"]


def test_bulteni_getir_pdf_404_hata_verir():
    oturum = SahteOturum({})
    with pytest.raises(RuntimeError, match="HTTP 404"):
        _bulteni_getir(2026, 8, "https://x/yok.pdf", {}, oturum)
