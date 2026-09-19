"""TMSD (Türkiye Makarna Sanayicileri Derneği) aylık PDF sektör raporu
istemcisi testleri.

`pdfplumber.open` monkeypatch'lenip sahte `Sayfa`/`Pdf` nesneleri
beslenir (bkz. `tests/test_usk.py`'deki aynı desen) — gerçek PDF
üretilmez; `extract_words()` çıktısı elle inşa edilir. Bu, modülün asıl
kırılganlığını (konum tabanlı sütun eşleştirmesi, bölünmüş ondalık
birleştirme, sezon→takvim çevrimi) gerçek PDF üretmeden pinler.
"""

from datetime import date
from types import SimpleNamespace

import pytest

import ingest.tmsd as tmsd_mod
from ingest.tmsd import (
    KALEM_DURUM_BUGDAY_ITHALAT,
    KALEM_MAKARNA_EKMEKLIK,
    TAKVIM_SUTUNLARI,
    _sayfayi_bul,
    _tabloyu_ayikla,
    bulten_url,
    bulteni_ayikla,
    seri_cek,
)


def tmsd_seri(**kwargs):
    varsayilan = dict(id="test/makarna-ekmeklik", tmsd_kalem=KALEM_MAKARNA_EKMEKLIK, start_date=None)
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


def _kelime(x0, top, metin):
    return {"x0": x0, "x1": x0 + len(metin) * 6.5, "top": top, "text": metin}


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


# --- bulten_url: kapak adı inşası ---


def test_bulten_url_ay_adini_yila_gore_kodlar():
    assert bulten_url(2026, 7).endswith("Raporu%20Temmuz%202026.pdf")
    assert bulten_url(2026, 1).endswith("Raporu%20Ocak%202026.pdf")


# --- _sayfayi_bul ---


def test_sayfayi_bul_ilk_eslesen_sayfayi_doner():
    sayfalar = [
        _SahteSayfa("BAŞKA SAYFA", []),
        _SahteSayfa("MAKARNA İHRACATI (EKMEKLİK BUĞDAY İÇEREN)\nHAZİRAN 2026", []),
        _SahteSayfa("MAKARNA İHRACATI (EKMEKLİK BUĞDAY İÇEREN)\nOCAK-HAZİRAN 2026", []),
    ]
    sayfa = _sayfayi_bul(_SahtePdf(sayfalar), "MAKARNA İHRACATI (EKMEKLİK BUĞDAY İÇEREN)")
    assert sayfa is sayfalar[1]


def test_sayfayi_bul_bulunamazsa_hata():
    with pytest.raises(RuntimeError, match="bulunamadı"):
        _sayfayi_bul(_SahtePdf([_SahteSayfa("BAŞKA SAYFA", [])]), "YOK OLAN BAŞLIK")


# --- _tabloyu_ayikla: YIL/AY (takvim) ızgarası, konum tabanlı ---


def _yilay_kelimeleri(satirlar, ikinci_tablo_offset=None):
    """satirlar: {yıl: {ay_etiketi: (x0, metin_parcalari)}} — ana YIL/AY
    başlığı top=453 sabit; `ikinci_tablo_offset` verilirse fiyat tablosu
    taklidi eklenir (aynı x0'larda başka bir YIL/AY + yıl etiketleri)."""
    kelimeler = [_kelime(58.7, 453.0, "YIL/AY")]
    for i, etiket in enumerate(TAKVIM_SUTUNLARI):
        kelimeler.append(_kelime(142.7 + i * 62, 453.0, etiket))
    top = 493.5
    for yil, hucreler in satirlar.items():
        kelimeler.append(_kelime(51.0, top, str(yil)))
        for etiket, (x0, parcalar) in hucreler.items():
            if isinstance(parcalar, list):
                for dx, metin, dtop in parcalar:
                    kelimeler.append(_kelime(x0 + dx, top + dtop, metin))
            else:
                kelimeler.append(_kelime(x0, top, parcalar))
        top += 27
    if ikinci_tablo_offset:
        kelimeler.append(_kelime(58.7, ikinci_tablo_offset, "YIL/AY"))
        kelimeler.append(_kelime(51.0, ikinci_tablo_offset + 40, "2024"))
    return kelimeler


def _kolon_x0(index):
    return 142.7 + index * 62


def test_tabloyu_ayikla_duz_degerleri_dogru_sutuna_atar():
    kelimeler = _yilay_kelimeleri({
        2024: {"Oca.": (_kolon_x0(0), "86.3"), "Ara.": (_kolon_x0(11), "76.3")},
    })
    sonuc = _tabloyu_ayikla(_SahteSayfa("", kelimeler), "YIL/AY", TAKVIM_SUTUNLARI)
    assert sonuc == {"2024": {"Oca.": "86.3", "Ara.": "76.3"}}


def test_tabloyu_ayikla_bolunmus_ondaligi_birlestirir():
    """Ölçüldü: '103.8' PDF'te '103.' + '8' olarak iki farklı 'top'ta gelir."""
    kelimeler = _yilay_kelimeleri({
        2026: {"Nis.": (_kolon_x0(3), [(0, "103.", 0), (26, "8", 25.5)])},
    })
    sonuc = _tabloyu_ayikla(_SahteSayfa("", kelimeler), "YIL/AY", TAKVIM_SUTUNLARI)
    assert sonuc["2026"]["Nis."] == "103.8"


def test_tabloyu_ayikla_sagahizali_tek_hane_bitisik_sutuna_kaymaz():
    """Ölçüldü: tek haneli '5' değeri sağa hizalı geldiğinden `x0` bazlı
    en-yakın-sütun eşleştirmesi bunu BİR SONRAKİ sütuna (Ağu.) atıyordu;
    doğrusu `x1` (sağ kenar) ile kendi sütununda (Tem.) kalmalı."""
    # Tem. sütunu x0=142.7+6*62=514.7, genişlik ~56; "5" hücrenin SAĞINA
    # yakın (x0=514.7+30=544.7) yerleştirilir — bir sonraki sütun (Ağu.,
    # x0=576.7) x0 bazlı ölçekte daha yakın olurdu ama x1(551.2) hâlâ
    # Tem./Ağu. aralığında (514.7, 576.7] kalır.
    kelimeler = _yilay_kelimeleri({
        2023: {"Tem.": (_kolon_x0(6) + 30, "5")},
    })
    sonuc = _tabloyu_ayikla(_SahteSayfa("", kelimeler), "YIL/AY", TAKVIM_SUTUNLARI)
    assert sonuc["2023"] == {"Tem.": "5"}


def test_tabloyu_ayikla_ikinci_tabloya_sizmaz():
    """Sayfa aynı ızgarayı iki kez taşıyorsa (miktar + fiyat) satır
    araması İLK tablodan SONRAKİ 'YIL/AY' oluşumuna kadar sınırlanmalı —
    yoksa fiyat tablosunun aynı x0'daki yıl etiketi 'yinelenen satır' hatası
    verir."""
    kelimeler = _yilay_kelimeleri(
        {2024: {"Oca.": (_kolon_x0(0), "86.3")}}, ikinci_tablo_offset=933.2,
    )
    sonuc = _tabloyu_ayikla(_SahteSayfa("", kelimeler), "YIL/AY", TAKVIM_SUTUNLARI)
    assert sonuc == {"2024": {"Oca.": "86.3"}}


def test_tabloyu_ayikla_sutun_basligi_yoksa_hata():
    kelimeler = [_kelime(58.7, 453.0, "YIL/AY")] + [
        _kelime(142.7 + i * 62, 453.0, e) for i, e in enumerate(TAKVIM_SUTUNLARI[:3])
    ]
    with pytest.raises(RuntimeError, match="Nis.*sütun başlığı bulunamadı"):
        _tabloyu_ayikla(_SahteSayfa("", kelimeler), "YIL/AY", TAKVIM_SUTUNLARI)


def test_tabloyu_ayikla_anahtar_bulunamazsa_hata():
    with pytest.raises(RuntimeError, match="YIL/AY.*bulunamadı"):
        _tabloyu_ayikla(_SahteSayfa("", []), "YIL/AY", TAKVIM_SUTUNLARI)


# --- bulteni_ayikla: SEZON (mahsul yılı) -> takvim ayı çevrimi ---


def _tek_sayfali_pdf(baslik, anahtar_etiket, sutun_sirasi, satirlar):
    kelimeler = [_kelime(58.7, 453.0, anahtar_etiket)]
    for i, etiket in enumerate(sutun_sirasi):
        kelimeler.append(_kelime(142.7 + i * 62, 453.0, etiket))
    top = 493.5
    for satir_etiketi, hucreler in satirlar.items():
        kelimeler.append(_kelime(51.0, top, satir_etiketi))
        for etiket, metin in hucreler.items():
            j = sutun_sirasi.index(etiket)
            kelimeler.append(_kelime(142.7 + j * 62, top, metin))
        top += 27
    metin_baslik = f"{baslik}\nHAZİRAN 2026"
    return _SahtePdf([_SahteSayfa(metin_baslik, kelimeler)])


def test_bulteni_ayikla_sezon_temmuz_arasi_sezonun_ilk_yilina_gider(monkeypatch):
    """Sezon 'Tem.'-'Ara.' sütunları sezonun İLK yılına (ör. 2023/24 ->
    2023) düşmeli."""
    def sahte_pdfplumber_open(_baytlar):
        tanimlar = tmsd_mod._KALEM_TANIMLARI
        pdfler = {}
        for kalem, (baslik, anahtar, sutunlar) in tanimlar.items():
            if anahtar == "YIL/AY":
                pdfler[kalem] = _tek_sayfali_pdf(baslik, anahtar, sutunlar, {"2024": {"Oca.": "1.0"}})
            else:
                pdfler[kalem] = _tek_sayfali_pdf(baslik, anahtar, sutunlar, {"2023/24": {"Tem.": "5", "Oca.": "4"}})
        return _CokluSayfaPdf(pdfler, tanimlar)

    monkeypatch.setattr(tmsd_mod.pdfplumber, "open", sahte_pdfplumber_open)
    sonuc = bulteni_ayikla(b"pdf", "2026.06")
    assert sonuc[KALEM_DURUM_BUGDAY_ITHALAT]["2023-07-01"] == 5.0  # Tem -> sezonun ilk yılı
    assert sonuc[KALEM_DURUM_BUGDAY_ITHALAT]["2024-01-01"] == 4.0  # Oca -> sezonun ikinci yılı


class _CokluSayfaPdf:
    """Her kalemin kendi tek-sayfalı sahte PDF'inden ilgili sayfayı birleştirir."""

    def __init__(self, pdfler, tanimlar):
        self.pages = []
        for kalem, (baslik, _anahtar, _sutunlar) in tanimlar.items():
            self.pages.extend(pdfler[kalem].pages)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_bulteni_ayikla_sayisal_olmayan_hucre_hata_verir(monkeypatch):
    def sahte_pdfplumber_open(_baytlar):
        tanimlar = tmsd_mod._KALEM_TANIMLARI
        pdfler = {}
        for kalem, (baslik, anahtar, sutunlar) in tanimlar.items():
            if kalem == KALEM_MAKARNA_EKMEKLIK:
                pdfler[kalem] = _tek_sayfali_pdf(baslik, anahtar, sutunlar, {"2024": {"Oca.": "N/A"}})
            elif anahtar == "YIL/AY":
                pdfler[kalem] = _tek_sayfali_pdf(baslik, anahtar, sutunlar, {"2024": {"Oca.": "1.0"}})
            else:
                pdfler[kalem] = _tek_sayfali_pdf(baslik, anahtar, sutunlar, {"2023/24": {"Tem.": "1"}})
        return _CokluSayfaPdf(pdfler, tanimlar)

    monkeypatch.setattr(tmsd_mod.pdfplumber, "open", sahte_pdfplumber_open)
    with pytest.raises(RuntimeError, match="sayısal olmayan hücre"):
        bulteni_ayikla(b"pdf", "2026.06")


# --- seri_cek: kalem doğrulama, aylık geriye deneme, önbellek, start_date ---


class SahteYanit:
    def __init__(self, status_code, content=b""):
        self.status_code = status_code
        self.content = content


class SahteOturum:
    def __init__(self, yanitlar):
        self.yanitlar = yanitlar
        self.cagrilar = []

    def get(self, url, timeout=None):
        self.cagrilar.append(url)
        return self.yanitlar.get(url, SahteYanit(404, b"<html>404</html>"))


def _sahte_tum_kalemler_pdf_yaniti(monkeypatch, deger=108.0):
    def sahte_pdfplumber_open(_baytlar):
        tanimlar = tmsd_mod._KALEM_TANIMLARI
        pdfler = {}
        for kalem, (baslik, anahtar, sutunlar) in tanimlar.items():
            if anahtar == "YIL/AY":
                pdfler[kalem] = _tek_sayfali_pdf(baslik, anahtar, sutunlar, {"2026": {"Haz.": str(deger)}})
            else:
                pdfler[kalem] = _tek_sayfali_pdf(baslik, anahtar, sutunlar, {"2025/26": {"Haz.": str(deger)}})
        return _CokluSayfaPdf(pdfler, tanimlar)

    monkeypatch.setattr(tmsd_mod.pdfplumber, "open", sahte_pdfplumber_open)


def test_seri_cek_bilinmeyen_kalem_hata_verir():
    with pytest.raises(RuntimeError, match="bilinmeyen kalem"):
        seri_cek(tmsd_seri(tmsd_kalem="yok-olan-kalem"), session=SahteOturum({}), bugun=date(2026, 9, 18))


def test_seri_cek_kapak_adi_gecikmesinde_geriye_denemeyle_bulur(monkeypatch):
    """Eylül/Ağustos kapaklı raporlar henüz yoksa (404) Temmuz'a kadar
    geriye inilir (bkz. modül docstring'i: kapak adı veri ayından ileride)."""
    _sahte_tum_kalemler_pdf_yaniti(monkeypatch)
    oturum = SahteOturum({bulten_url(2026, 7): SahteYanit(200, b"pdf-baytlari")})

    df = seri_cek(tmsd_seri(), onbellek={}, session=oturum, bugun=date(2026, 9, 18))

    assert df["date"].iloc[-1] == "2026-06-01"
    assert df["value"].iloc[-1] == pytest.approx(108.0)
    denenen = oturum.cagrilar
    assert bulten_url(2026, 9) in denenen
    assert bulten_url(2026, 8) in denenen
    assert bulten_url(2026, 7) in denenen


def test_seri_cek_hicbir_rapor_yoksa_hata():
    with pytest.raises(RuntimeError, match="bulunamadı"):
        seri_cek(tmsd_seri(), session=SahteOturum({}), bugun=date(2026, 9, 18))


def test_seri_cek_onbellek_paylasilir_iki_kalem_icin_yeniden_indirmez(monkeypatch):
    _sahte_tum_kalemler_pdf_yaniti(monkeypatch)
    cagri_sayisi = SimpleNamespace(n=0)
    gercek_get = SahteOturum.get

    class SayanOturum(SahteOturum):
        def get(self, url, timeout=None):
            cagri_sayisi.n += 1
            return gercek_get(self, url, timeout)

    oturum = SayanOturum({bulten_url(2026, 7): SahteYanit(200, b"pdf-baytlari")})
    onbellek: dict = {}
    seri_cek(tmsd_seri(tmsd_kalem=KALEM_MAKARNA_EKMEKLIK), onbellek=onbellek, session=oturum, bugun=date(2026, 9, 18))
    ilk_cagri = cagri_sayisi.n
    seri_cek(tmsd_seri(tmsd_kalem=KALEM_DURUM_BUGDAY_ITHALAT), onbellek=onbellek, session=oturum, bugun=date(2026, 9, 18))
    assert cagri_sayisi.n == ilk_cagri


def test_seri_cek_start_date_oncesini_kirpar(monkeypatch):
    _sahte_tum_kalemler_pdf_yaniti(monkeypatch)
    oturum = SahteOturum({bulten_url(2026, 7): SahteYanit(200, b"pdf-baytlari")})

    df = seri_cek(
        tmsd_seri(start_date="2026-06-01"), onbellek={}, session=oturum, bugun=date(2026, 9, 18),
    )

    assert len(df) == 1
    assert df["date"].iloc[0] == "2026-06-01"
