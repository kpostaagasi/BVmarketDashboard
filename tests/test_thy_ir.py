"""THY çeyreklik Yatırımcı Sunumu istemcisi (`thy_ir` kaynak_tipi) + aylık
trafik PDF'inden Uçak Sayısı/Uçulan Nokta testleri.

Tablo satırları pdfplumber `extract_text()` çıktısıyla AYNI biçimde
sentetik metin olarak verilir (gerçek PDF üretmeye gerek yok — ayrıştırma
mantığı saf metin/kelime listesi üzerinde çalışır). Yalnızca iki grafik
(Net Borç/EBITDA, Passenger RASK) x0-konum eşlemesi kullanır; bunlar
`extract_words()` çıktısına eşdeğer sentetik kelime sözlükleriyle test
edilir (bkz. `ingest/thy.py` docstring'i — metin akış sırası bu ikisinde
güvenilmez).
"""

from types import SimpleNamespace

import pytest

from ingest.thy import (
    PDF_TOPLAM_OLCUTLERI,
    SUNUMLAR_SAYFASI,
    TABAN,
    _bilanco_noktalari,
    _bolgesel_noktalari,
    _ceyrek_tarihi,
    _filo_noktalari,
    _net_borc_favok_kelimelerden,
    _passenger_rask_kelimelerden,
    pdf_toplam_noktalari,
    pdf_toplam_seri_cek,
    sunum_bilgisi,
    sunum_seri_cek,
)


def thy_ir_seri(**kwargs):
    varsayilan = dict(id="havacilik/test", thy_metrik="rask2", start_date=None)
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


class SahteYanit:
    def __init__(self, content, status_code=200):
        self.content = content
        self.status_code = status_code

    @property
    def text(self):
        return self.content.decode("utf-8", errors="replace") if isinstance(self.content, bytes) else self.content


class SahteOturum:
    def __init__(self, yanit_haritasi):
        self.yanit_haritasi = yanit_haritasi
        self.cagrilar = []

    def get(self, url, **kwargs):
        self.cagrilar.append(url)
        return self.yanit_haritasi[url]


def _kelime(text, x0, top):
    return {"text": text, "x0": x0, "top": top, "x1": x0 + len(text) * 5.0}


# --- _bilanco_noktalari ---


def _bilanco_metni(cari_yil="2026", cari_ay="06", cari_gun="30"):
    return (
        f"Varlıklar (mn USD) 2020 2021 2022 2023 2024 2025 {cari_gun}.{cari_ay}.{cari_yil}\n"
        "Toplam Varlıklar 100 200 300 400 500 600 700\n"
        "Yükümlülükler (mn USD) 2020 2021 2022 2023 2024 2025 " f"{cari_gun}.{cari_ay}.{cari_yil}\n"
        "Kira Yükümlülükleri 10 20 30 40 50 60 70\n"
        "Banka Kredileri 11 21 31 41 51 61 71\n"
        "Yolcu Uçuş Yükümlülükleri 12 22 32 42 52 62 72\n"
        "Ticari Borçlar 13 23 33 43 53 63 73\n"
        "Diğer Yükümlülükler 14 24 34 44 54 64 74\n"
        "Toplam Yükümlülükler 60 110 160 210 260 310 360\n"
        "Toplam Özkaynaklar 40 90 140 190 240 290 340\n"
    )


def test_bilanco_noktalari_dogru_deger_ve_tarih_dondurur():
    sonuc = _bilanco_noktalari(_bilanco_metni())
    assert sonuc["varlik-toplam"]["2026-04-01"] == 700.0
    assert sonuc["varlik-toplam"]["2020-10-01"] == 100.0
    assert sonuc["yukumluluk-kira"]["2025-10-01"] == 60.0


def test_bilanco_noktalari_ceyrek_ay_dogru_eslenir():
    """Dönem sonu ay Ekim (10) ise 4. çeyrek -> yılın kendi ilk ayı değil,
    Ekim (10) kullanılmalı (çeyrek ilk ayı kuralı)."""
    sonuc = _bilanco_noktalari(_bilanco_metni(cari_yil="2026", cari_ay="12", cari_gun="31"))
    assert "2026-10-01" in sonuc["varlik-toplam"]


def test_bilanco_noktalari_baslik_bulunamazsa_hata():
    with pytest.raises(RuntimeError, match="başlık"):
        _bilanco_noktalari("rastgele metin, tablo yok")


def test_bilanco_noktalari_satir_eksikse_hata():
    metin = _bilanco_metni().replace("Ticari Borçlar 13 23 33 43 53 63 73\n", "")
    with pytest.raises(RuntimeError, match="satır"):
        _bilanco_noktalari(metin)


# --- _filo_noktalari ---


def _filo_metni(genis=50, dar=100, kargo=20, sahip=60, fin=70, opr=40):
    toplam = genis + dar + kargo
    assert sahip + fin + opr == toplam
    return (
        f"Toplam {genis} 20 20 10 46,5 9,3\n"
        f"Toplam {dar} 50 40 10 67,7 9,5\n"
        f"Toplam {kargo} 10 10 0 12,8\n"
        f"Genel Toplam {toplam} {sahip} {fin} {opr} 114,2 9,6\n"
    )


def test_filo_noktalari_govde_ve_mulkiyet_bilesenlerini_dondurur():
    sonuc = _filo_noktalari(_filo_metni())
    assert sonuc["filo-genis-govde"] == 50.0
    assert sonuc["filo-dar-govde"] == 100.0
    assert sonuc["filo-kargo"] == 20.0
    assert sonuc["filo-sahip-olunan"] == 60.0
    assert sonuc["filo-finansal-kira"] == 70.0
    assert sonuc["filo-operasyonel-kira"] == 40.0


def test_filo_noktalari_govde_toplami_genel_toplamla_uyusmazsa_hata():
    metin = _filo_metni().replace("Toplam 50 20 20 10 46,5 9,3", "Toplam 51 20 20 10 46,5 9,3")
    with pytest.raises(RuntimeError, match="Genel Toplam"):
        _filo_noktalari(metin)


def test_filo_noktalari_toplam_satiri_uc_taneden_azsa_hata():
    metin = "Toplam 50 20 20 10 46,5 9,3\nGenel Toplam 50 20 20 10 114,2 9,6\n"
    with pytest.raises(RuntimeError, match="'Toplam'"):
        _filo_noktalari(metin)


def test_filo_noktalari_genel_toplam_yoksa_hata():
    metin = "Toplam 50 20 20 10 46,5 9,3\nToplam 100 50 40 10 67,7 9,5\nToplam 20 10 10 0 12,8\n"
    with pytest.raises(RuntimeError, match="Genel Toplam"):
        _filo_noktalari(metin)


# --- _bolgesel_noktalari ---


def _bolgesel_metni():
    return (
        "Amerika Avrupa Uzak Doğu\n"
        "AKK -%0,5 %1,3 AKK %3,3 %6,8 AKK %17,9 %18,5\n"
        "RASK2 %15,4 %9,9 RASK2 %11,0 %8,4 RASK2 %26,0 %19,4\n"
        "Afrika Orta Doğu İç Hat\n"
        "AKK %0,4 %6,6 AKK -%48,3 -%28,6 AKK -%2,0 %1,8\n"
        "RASK2 %17,7 %16,6 RASK2 %18,6 %10,3 RASK2 %12,1 %9,5\n"
    )


def test_bolgesel_noktalari_alti_bolgeyi_dogru_sirada_dondurur():
    sonuc = _bolgesel_noktalari(_bolgesel_metni())
    assert sonuc["rask2-degisim-amerika"] == 15.4
    assert sonuc["rask2-degisim-orta-dogu"] == 18.6
    assert sonuc["rask2-degisim-ic-hat"] == 12.1


def test_bolgesel_noktalari_grup_sirasi_tersse_hata():
    metin = _bolgesel_metni().replace(
        "Afrika Orta Doğu İç Hat", "GEÇİCİ"
    ).replace("Amerika Avrupa Uzak Doğu", "Afrika Orta Doğu İç Hat").replace("GEÇİCİ", "Amerika Avrupa Uzak Doğu")
    with pytest.raises(RuntimeError, match="bölge grup sırası"):
        _bolgesel_noktalari(metin)


def test_bolgesel_noktalari_eksik_bolgede_hata():
    metin = _bolgesel_metni().replace("RASK2 %17,7 %16,6 RASK2 %18,6 %10,3 RASK2 %12,1 %9,5", "")
    with pytest.raises(RuntimeError, match="6 bekleniyor"):
        _bolgesel_noktalari(metin)


# --- Passenger RASK (geometrik x0 eşlemesi) ---


def test_passenger_rask_kelimelerden_x0_ile_dogru_esler():
    kelimeler = [
        _kelime("Passenger", 157.0, 207.7),
        _kelime("7,27", 387.2, 247.3),   # 2Ç'25 değeri (etikete yakın x0)
        _kelime("8,26", 463.1, 241.0),   # 2Ç'26 değeri
        _kelime("8,33", 538.9, 240.5),   # 2Ç'26 Kur Etkisi Hariç (uzak x0)
        _kelime("2Ç'25", 385.2, 314.4),
        _kelime("2Ç'26", 461.1, 314.4),
        _kelime("Revenue", 157.0, 358.0),
    ]
    onceki, simdiki = _passenger_rask_kelimelerden(kelimeler)
    assert onceki == 7.27
    assert simdiki == 8.26


def test_passenger_rask_kelimelerden_baslik_yoksa_hata():
    with pytest.raises(RuntimeError, match="Passenger RASK"):
        _passenger_rask_kelimelerden([_kelime("Revenue", 157.0, 358.0)])


def test_passenger_rask_kelimelerden_tolerans_asilirsa_hata():
    kelimeler = [
        _kelime("Passenger", 157.0, 207.7),
        _kelime("2Ç'25", 385.2, 314.4),
        _kelime("2Ç'26", 461.1, 314.4),
        _kelime("9,99", 900.0, 245.0),  # hiçbir etikete yakın değil
        _kelime("9,50", 905.0, 245.0),  # ikinci aday — yine hiçbirine yakın değil
        _kelime("Revenue", 157.0, 358.0),
    ]
    with pytest.raises(RuntimeError, match="konumca eşleşmedi"):
        _passenger_rask_kelimelerden(kelimeler)


# --- Net Borç / EBITDA (geometrik x0 eşlemesi) ---


def _net_borc_kelimeleri():
    yillar = ["2019", "2020", "2021", "2022", "2023", "2024", "2025", "S12A"]
    degerler = ["3,9x", "9,5x", "3,4x", "1,7x", "1,3x", "1,1x", "1,6x", "2,1x"]
    kelimeler = []
    for i, (yil, deger) in enumerate(zip(yillar, degerler)):
        x0 = 200.0 + i * 73.0
        kelimeler.append(_kelime(yil, x0, 453.6))
        kelimeler.append(_kelime(deger, x0 + 0.5, 400.0))
    return kelimeler


def test_net_borc_favok_kelimelerden_s12a_cari_ceyrege_damgalanir():
    sonuc = _net_borc_favok_kelimelerden(_net_borc_kelimeleri(), 2026, 2)
    assert sonuc["2026-04-01"] == 2.1
    assert sonuc["2019-10-01"] == 3.9
    assert sonuc["2020-10-01"] == 9.5


def test_net_borc_favok_kelimelerden_sekizden_az_deger_varsa_hata():
    with pytest.raises(RuntimeError, match="8/8"):
        _net_borc_favok_kelimelerden(_net_borc_kelimeleri()[:-2], 2026, 2)


def test_net_borc_favok_kelimelerden_ayni_etikete_iki_deger_eslesirse_hata():
    kelimeler = _net_borc_kelimeleri()
    # İkinci "2019" değerini ilkiyle AYNI x0'a koy (iki değer aynı etikete düşsün).
    kelimeler.append(_kelime("5,0x", kelimeler[1]["x0"] + 0.2, 380.0))
    with pytest.raises(RuntimeError, match="8/8"):
        _net_borc_favok_kelimelerden(kelimeler, 2026, 2)


# --- pdf_toplam_noktalari (aylık trafik PDF TOPLAM tablosu) ---


def _trafik_pdf_metni(ay="AĞUSTOS", yil="2026", ucak_onceki=501, ucak_simdi=566, nokta_onceki=353, nokta_simdi=358):
    return (
        f"{ay} {yil} TRAFİK\n"
        "TOPLAM\n"
        "2025 2026 Değişim (%)\n"
        f"Uçulan Nokta {nokta_onceki} {nokta_simdi} %1,4\n"
        f"Uçak Sayısı {ucak_onceki} {ucak_simdi} %13,0\n"
        "Arzedilen Koltuk Kilometre (milyar) 25,4 26,4 %4,2\n"
    )


def test_pdf_toplam_noktalari_dogru_tarih_ve_deger_dondurur():
    tarih, ucak, nokta = pdf_toplam_noktalari(_trafik_pdf_metni())
    assert tarih == "2026-08-01"
    assert ucak == 566.0
    assert nokta == 358.0


def test_pdf_toplam_noktalari_bilinmeyen_ay_adinda_hata():
    with pytest.raises(RuntimeError, match="ay adı"):
        pdf_toplam_noktalari(_trafik_pdf_metni(ay="AĞUSTOSS"))


def test_pdf_toplam_noktalari_baslik_yoksa_hata():
    with pytest.raises(RuntimeError, match="TRAFİK"):
        pdf_toplam_noktalari("Uçak Sayısı 501 566 %13,0")


def test_pdf_toplam_noktalari_satir_eksikse_hata():
    metin = _trafik_pdf_metni().replace("Uçak Sayısı 501 566 %13,0\n", "")
    with pytest.raises(RuntimeError, match="Uçak Sayısı"):
        pdf_toplam_noktalari(metin)


# --- sunum_bilgisi: sayfa kazıma ---


def test_sunum_bilgisi_ilk_baglantiyi_ve_donemi_dogru_ayristirir():
    html = (
        '<a href="/documents/ir-presentation-2q26tr.pdf">Haziran 2026</a>'
        '<a href="/documents/sunumlar/ir-presentation-1q26tr.pdf">Mart 2026</a>'
        '<a href="/documents/2c26-basin-sunumu.pdf">Basın Sunumu</a>'
    )
    oturum = SahteOturum({SUNUMLAR_SAYFASI: SahteYanit(html.encode("utf-8"))})
    url, yil, ceyrek = sunum_bilgisi(session=oturum)
    assert url == f"{TABAN}/documents/ir-presentation-2q26tr.pdf"
    assert (yil, ceyrek) == (2026, 2)


def test_sunum_bilgisi_baglanti_yoksa_hata():
    oturum = SahteOturum({SUNUMLAR_SAYFASI: SahteYanit(b"<html></html>")})
    with pytest.raises(RuntimeError, match="bulunamadı"):
        sunum_bilgisi(session=oturum)


def test_sunum_bilgisi_http_hatasi_yukselir():
    oturum = SahteOturum({SUNUMLAR_SAYFASI: SahteYanit(b"", status_code=500)})
    with pytest.raises(RuntimeError, match="HTTP 500"):
        sunum_bilgisi(session=oturum)


# --- sunum_seri_cek: önbellek + hata yolları (indirme/ayrıştırma test
# dışı: onbellek doğrudan doldurulur, ağ/PDF'e gerek kalmaz) ---


def test_sunum_seri_cek_onbellekten_okur_ve_tarihe_gore_sirali_doner():
    onbellek = {"noktalar": {"rask2": {"2026-04-01": 8.93, "2025-04-01": 7.67}}}
    df = sunum_seri_cek(thy_ir_seri(thy_metrik="rask2"), onbellek=onbellek)
    assert list(df["date"]) == ["2025-04-01", "2026-04-01"]
    assert list(df["value"]) == [7.67, 8.93]


def test_sunum_seri_cek_bilinmeyen_metrikte_hata():
    onbellek = {"noktalar": {"rask2": {"2026-04-01": 8.93}}}
    with pytest.raises(RuntimeError, match="thy_metrik"):
        sunum_seri_cek(thy_ir_seri(thy_metrik="yolcu-rask"), onbellek=onbellek)


def test_sunum_seri_cek_start_date_oncesini_kirpar():
    onbellek = {"noktalar": {"rask2": {"2025-04-01": 7.67, "2026-04-01": 8.93}}}
    df = sunum_seri_cek(thy_ir_seri(thy_metrik="rask2", start_date="2026-01-01"), onbellek=onbellek)
    assert list(df["date"]) == ["2026-04-01"]


# --- pdf_toplam_seri_cek dispatch: seri_cek yönlendirmesi ---


def test_pdf_toplam_olcutleri_iki_metrik_icerir():
    assert PDF_TOPLAM_OLCUTLERI == {"ucak-sayisi", "uculan-nokta"}


class _SahtePdfSayfa:
    def __init__(self, metin):
        self._metin = metin

    def extract_text(self):
        return self._metin


class _SahtePdf:
    """`pdfplumber.open(...)` dönüşünü taklit eder — gerçek PDF bayt
    biçimini (font/encoding) üretme karmaşıklığından kaçınmak için
    `pdfplumber.open` monkeypatch'lenir; HTTP kazıma + dispatch mantığı
    GERÇEK kalır."""

    def __init__(self, metin):
        self.pages = [_SahtePdfSayfa(metin)]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_pdf_toplam_seri_cek_dogru_deger_dondurur(monkeypatch):
    trafik_url = "https://investor.turkishairlines.com/documents/trafik/x.pdf"
    html = f'<a href="{trafik_url}" target="_blank">pdf</a>'.encode("utf-8")
    from ingest.thy import TRAFIK_SAYFASI
    import ingest.thy as thy_modul

    oturum = SahteOturum({
        TRAFIK_SAYFASI: SahteYanit(html),
        trafik_url: SahteYanit(b"sahte-pdf-baytlari"),
    })
    monkeypatch.setattr(thy_modul.pdfplumber, "open", lambda *a, **k: _SahtePdf(_trafik_pdf_metni()))

    df = pdf_toplam_seri_cek(
        SimpleNamespace(id="x", thy_segment="Toplam", thy_olcut="ucak-sayisi", start_date=None),
        session=oturum,
    )
    assert df["value"].iloc[0] == 566.0
    assert df["date"].iloc[0] == "2026-08-01"


def test_pdf_toplam_seri_cek_uculan_nokta_dogru_deger_dondurur(monkeypatch):
    trafik_url = "https://investor.turkishairlines.com/documents/trafik/x.pdf"
    html = f'<a href="{trafik_url}" target="_blank">pdf</a>'.encode("utf-8")
    from ingest.thy import TRAFIK_SAYFASI
    import ingest.thy as thy_modul

    oturum = SahteOturum({
        TRAFIK_SAYFASI: SahteYanit(html),
        trafik_url: SahteYanit(b"sahte-pdf-baytlari"),
    })
    monkeypatch.setattr(thy_modul.pdfplumber, "open", lambda *a, **k: _SahtePdf(_trafik_pdf_metni()))

    df = pdf_toplam_seri_cek(
        SimpleNamespace(id="x", thy_segment="Toplam", thy_olcut="uculan-nokta", start_date=None),
        session=oturum,
    )
    assert df["value"].iloc[0] == 358.0


def test_pdf_toplam_seri_cek_baglanti_yoksa_hata():
    from ingest.thy import TRAFIK_SAYFASI
    oturum = SahteOturum({TRAFIK_SAYFASI: SahteYanit(b"<html></html>")})
    with pytest.raises(RuntimeError, match="PDF bağlantısı"):
        pdf_toplam_seri_cek(
            SimpleNamespace(id="x", thy_segment="Toplam", thy_olcut="ucak-sayisi", start_date=None),
            session=oturum,
        )
