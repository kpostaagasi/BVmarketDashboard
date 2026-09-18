"""TAV Havalimanları aylık yolcu trafiği istemcisi testleri.

Bülten baytları testte openpyxl ile üretilir: gerçek dosyanın aynı şablonu
(A1 hücresinde "TAV Traffic Figures – <Ay> <Yıl>\\nTAV Havalimanları Yolcu
Sayıları – <Türkçe Ay> <Yıl>" başlığı, "Passengers / Yolcu" başlık satırı +
yıl sütunları, ardından varlık satırları ve opsiyonel International/
Domestic alt satır çifti). Gerçek dosyada ölçülen iki gerçek şablon
tuhaflığı (sekme adı "1212"in aslında Aralık 2022 olması, bir başlıkta
"Apil" yazım hatası) regresyon testi olarak sabitlenmiştir.
"""

import io
from types import SimpleNamespace

import openpyxl
import pytest

from ingest.tav import LISTE_SAYFASI, AY_EN, AY_TR, dosya_listesi, seri_cek, yolcu_noktalari


def _baslik(yil: int, ay_no: int) -> str:
    return (
        f"TAV Traffic Figures – {AY_EN[ay_no - 1]} {yil}\n"
        f"TAV Havalimanları Yolcu Sayıları –  {AY_TR[ay_no - 1]} {yil}"
    )


def _yolcu_govdesi(yil, ay_no, onceki_yil=None, varliklar=None, ucuncu_yil=None):
    """Gerçekçi bir 'Passengers / Yolcu' bloğu üretir (7 sütun: ad, önceki
    yıl aylık, cari yıl aylık, %chg, önceki yıl YTD, cari yıl YTD, %chg).

    YTD sütunları AYLIK'tan BİLİNÇLİ OLARAK farklı (5x) değer taşır: kod
    yanlışlıkla YTD'yi okursa test bunu yakalar.

    `ucuncu_yil` verilirse (gerçek '1212'/'0123' sayfalarındaki gibi) başlık
    satırına cari yıldan ÖNCE bir üçüncü karşılaştırma yılı eklenir — cari
    yılın sütunu artık C değil D olur; sabit sütun varsayımı böylece test
    edilir.
    """
    onceki_yil = onceki_yil if onceki_yil is not None else yil - 1
    if varliklar is None:
        varliklar = [
            ("Antalya", 1000.0, 700.0, 300.0),
            ("Zagreb", 200.0, None, None),
            ("TAV TOTAL", 1200.0, 700.0, 500.0),
        ]
    satirlar = [
        (_baslik(yil, ay_no), None, None, None, None, None, None),
        (None, f"{AY_TR[ay_no - 1]} / {AY_EN[ay_no - 1]}", None, None, "YTD", None, None),
        (None, None, None, "Chg %", None, None, "Chg %"),
    ]
    if ucuncu_yil is not None:
        satirlar.append(("Passengers / Yolcu", ucuncu_yil, onceki_yil, yil, None, None, ucuncu_yil))
    else:
        satirlar.append(("Passengers / Yolcu", onceki_yil, yil, None, onceki_yil, yil, None))
    for ad, toplam, dis, ic in varliklar:
        satirlar.append(_satir(ad, toplam, ucuncu_yil is not None))
        if dis is not None:
            satirlar.append(_satir("International / Dis Hat", dis, ucuncu_yil is not None))
            satirlar.append(_satir("Domestic / Ic Hat", ic, ucuncu_yil is not None))
    return satirlar


def _satir(ad, aylik_deger, uc_yil_kaydirmali):
    ytd = aylik_deger * 5.0
    if uc_yil_kaydirmali:
        return (ad, aylik_deger * 0.8, aylik_deger * 0.9, aylik_deger, aylik_deger * 5, None, None)
    return (ad, aylik_deger * 0.9, aylik_deger, aylik_deger * 0.05, ytd * 0.9, ytd, aylik_deger * 0.05)


def _kitap_baytlari(sayfalar: dict) -> bytes:
    kitap = openpyxl.Workbook()
    kitap.remove(kitap.active)
    for ad, satirlar in sayfalar.items():
        sayfa = kitap.create_sheet(ad)
        for satir in satirlar:
            sayfa.append(list(satir))
    tampon = io.BytesIO()
    kitap.save(tampon)
    return tampon.getvalue()


def _degistir(govde, satir_no, sutun_no, deger):
    """1-indeksli (satır, sütun) hücreyi değiştirip yeni gövdeyi döner."""
    yeni = [list(s) for s in govde]
    while len(yeni[satir_no - 1]) < sutun_no:
        yeni[satir_no - 1].append(None)
    yeni[satir_no - 1][sutun_no - 1] = deger
    return [tuple(s) for s in yeni]


def tav_seri(**kwargs):
    varsayilan = dict(
        id="havacilik/tav-antalya-toplam",
        kaynak_tipi="tav",
        tav_varlik="Antalya",
        tav_segment="toplam",
        start_date=None,
    )
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


class SahteYanit:
    def __init__(self, content=b"", text="", status_code=200):
        self.content = content
        self.text = text
        self.status_code = status_code


XLSX_URL = "https://ir.tav.aero/uploads/documents/Documents10092026140951_.xlsx"
LISTE_HTML = (
    '<a href="https://ir.tav.aero/uploads/documents/Documents08012026150054_.xlsx">eski</a>'
    f'<a href="{XLSX_URL}">yeni</a>'
)


class SahteOturum:
    """URL'e göre farklı yanıt döner: liste sayfası (HTML) vs xlsx indirme."""

    def __init__(self, liste_html=LISTE_HTML, xlsx_baytlar=b"", xlsx_status=200, liste_status=200):
        self.liste_html = liste_html
        self.xlsx_baytlar = xlsx_baytlar
        self.xlsx_status = xlsx_status
        self.liste_status = liste_status
        self.calls: list[str] = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append(url)
        assert headers["User-Agent"] == "Mozilla/5.0"
        if url == LISTE_SAYFASI:
            return SahteYanit(text=self.liste_html, status_code=self.liste_status)
        return SahteYanit(content=self.xlsx_baytlar, status_code=self.xlsx_status)


# --- yolcu_noktalari: varlık/segment bağlama ---


def test_yolcu_noktalari_segment_alt_satirlari_dogru_varliga_baglanir():
    """(a) Antalya'nın International/Domestic satırları Antalya'ya, Zagreb'in
    (kırılımsız) tek satırı yalnızca 'toplam'a, TAV TOTAL'ınki kendine bağlanır."""
    govde = _yolcu_govdesi(2026, 8)
    noktalar = yolcu_noktalari(_kitap_baytlari({"Sheet1": govde}))
    assert noktalar[("Antalya", "toplam")] == {"2026-08-01": 1000.0}
    assert noktalar[("Antalya", "dis-hat")] == {"2026-08-01": 700.0}
    assert noktalar[("Antalya", "ic-hat")] == {"2026-08-01": 300.0}
    assert noktalar[("TAV TOTAL", "toplam")] == {"2026-08-01": 1200.0}
    assert noktalar[("TAV TOTAL", "dis-hat")] == {"2026-08-01": 700.0}
    assert noktalar[("TAV TOTAL", "ic-hat")] == {"2026-08-01": 500.0}


def test_yolcu_noktalari_kirilimsiz_varlik_yalnizca_toplam_uretir():
    govde = _yolcu_govdesi(2026, 8)
    noktalar = yolcu_noktalari(_kitap_baytlari({"Sheet1": govde}))
    assert noktalar[("Zagreb", "toplam")] == {"2026-08-01": 200.0}
    assert ("Zagreb", "dis-hat") not in noktalar
    assert ("Zagreb", "ic-hat") not in noktalar


def test_yolcu_noktalari_ytd_sutunu_aylik_sanilmaz():
    """(c) YTD sütunu aylıktan 5 kat büyük kurgulandı; okunan değer aylık olmalı."""
    govde = _yolcu_govdesi(2026, 8, varliklar=[("Antalya", 1000.0, None, None)])
    noktalar = yolcu_noktalari(_kitap_baytlari({"Sheet1": govde}))
    assert noktalar[("Antalya", "toplam")]["2026-08-01"] == 1000.0


def test_yolcu_noktalari_ucuncu_karsilastirma_yili_varken_sutunu_dogru_bulur():
    """Cari yıl sütunu C değil D olduğunda (gerçek '1212'/'0123' şablonu) bile
    doğru sütun dinamik olarak bulunmalı — sabit sütun varsayımı yanlış olurdu."""
    govde = _yolcu_govdesi(2023, 1, onceki_yil=2022, ucuncu_yil=2019,
                            varliklar=[("Antalya", 930033.0, None, None)])
    noktalar = yolcu_noktalari(_kitap_baytlari({"Sheet1": govde}))
    assert noktalar[("Antalya", "toplam")] == {"2023-01-01": 930033.0}


def test_yolcu_noktalari_bos_hucre_sifir_uydurmaz():
    """(d) Yayımlanmamış/eksik hücre None gelirse anahtar hiç oluşmamalı."""
    govde = _yolcu_govdesi(2026, 8, varliklar=[("Antalya", 1000.0, None, None)])
    govde = _degistir(govde, 5, 3, None)  # satır5 = Antalya, sütun3 = cari yıl (C)
    noktalar = yolcu_noktalari(_kitap_baytlari({"Sheet1": govde}))
    assert ("Antalya", "toplam") not in noktalar


def test_yolcu_noktalari_sayisal_olmayan_hucrede_hata():
    govde = _yolcu_govdesi(2026, 8, varliklar=[("Antalya", 1000.0, None, None)])
    govde = _degistir(govde, 5, 3, "N/A")
    with pytest.raises(RuntimeError, match="sayısal olmayan hücre"):
        yolcu_noktalari(_kitap_baytlari({"Sheet1": govde}))


# --- yolcu_noktalari: ay/yıl başlığı çözümü ---


def test_yolcu_noktalari_tarih_sekme_adindan_degil_basliktan_cozulur():
    """(b) Regresyon: gerçek dosyada Aralık 2022 verisini taşıyan sekmenin adı
    '1212' (olması gereken '1222'). Sekme adını olduğu gibi ayrıştırmak
    2012'ye düşerdi; başlık metni doğru yıl/ayı (Aralık 2022) vermeli."""
    govde = _yolcu_govdesi(2022, 12, varliklar=[("Antalya", 950000.0, None, None)])
    noktalar = yolcu_noktalari(_kitap_baytlari({"1212": govde}))
    assert noktalar[("Antalya", "toplam")] == {"2022-12-01": 950000.0}


def test_yolcu_noktalari_ingilizce_ay_bozuksa_turkceye_duser():
    """(b) Regresyon: gerçek Nisan 2023 sayfasının başlığı 'Apil 2023' yazıyor
    (eksik harf). Türkçe kısım 'Nisan 2023' doğru; ona düşülmeli."""
    govde = _yolcu_govdesi(2023, 4, varliklar=[("Antalya", 92126.0, None, None)])
    bozuk_baslik = govde[0][0].replace("April", "Apil")
    assert "Apil 2023" in bozuk_baslik
    govde = _degistir(govde, 1, 1, bozuk_baslik)
    noktalar = yolcu_noktalari(_kitap_baytlari({"0423": govde}))
    assert noktalar[("Antalya", "toplam")] == {"2023-04-01": 92126.0}


def test_yolcu_noktalari_baslik_belirsizse_hata():
    govde = _yolcu_govdesi(2026, 8)
    govde = _degistir(govde, 1, 1, "TAV Traffic Figures – Bilinmeyen 2026")
    with pytest.raises(RuntimeError, match="ay/yıl başlığı"):
        yolcu_noktalari(_kitap_baytlari({"Sheet1": govde}))


def test_yolcu_noktalari_baslik_yoksa_hata():
    govde = _yolcu_govdesi(2026, 8)
    govde = _degistir(govde, 1, 1, "Bambaşka bir sayfa")
    with pytest.raises(RuntimeError, match="başlık bulunamadı"):
        yolcu_noktalari(_kitap_baytlari({"Sheet1": govde}))


def test_yolcu_noktalari_passengers_satiri_yoksa_hata():
    govde = _yolcu_govdesi(2026, 8)
    govde = _degistir(govde, 4, 1, "Başka Bir Blok")
    with pytest.raises(RuntimeError, match="Passengers"):
        yolcu_noktalari(_kitap_baytlari({"Sheet1": govde}))


def test_yolcu_noktalari_yil_sutunu_yoksa_sayfa_sessizce_atlanir_ama_digerlerini_dusurmez():
    """Ölçülen gerçek istisna (0120/Ocak 2020): başlık çözülüyor ama
    'Passengers' satırındaki karşılaştırma sütunlarında raporlanan yılın
    kendi sütunu yok. Bu TEK sayfa katkı vermemeli; diğer (sağlıklı) sayfa
    etkilenmemeli — tüm dosya çökmemeli."""
    bozuk = _yolcu_govdesi(2020, 1, onceki_yil=2018, varliklar=[("Ankara", 1045942.0, None, None)])
    # Başlık satırını (satır 4) cari yılı İÇERMEYECEK şekilde değiştir.
    bozuk = _degistir(bozuk, 4, 3, 2019)  # C sütunu (aylık) 2020 değil 2019 olsun
    bozuk = _degistir(bozuk, 4, 6, 2019)  # F sütunu (YTD) da 2020 taşımasın
    saglikli = _yolcu_govdesi(2026, 8, varliklar=[("Antalya", 1000.0, None, None)])
    noktalar = yolcu_noktalari(_kitap_baytlari({"0120": bozuk, "Sheet1": saglikli}))
    assert ("Ankara", "toplam") not in noktalar
    assert noktalar[("Antalya", "toplam")] == {"2026-08-01": 1000.0}


def test_yolcu_noktalari_tum_sayfalar_bozuksa_hata():
    bozuk = _yolcu_govdesi(2020, 1, onceki_yil=2018, varliklar=[("Ankara", 1045942.0, None, None)])
    bozuk = _degistir(bozuk, 4, 3, 2019)
    bozuk = _degistir(bozuk, 4, 6, 2019)
    with pytest.raises(RuntimeError, match="tanınan sayfa şablonu"):
        yolcu_noktalari(_kitap_baytlari({"0120": bozuk}))


def test_yolcu_noktalari_disclaimer_sayfasi_atlanir():
    govde = _yolcu_govdesi(2026, 8, varliklar=[("Antalya", 1000.0, None, None)])
    noktalar = yolcu_noktalari(
        _kitap_baytlari({"Sheet1": govde, "disclaimer": [("Notlar", None), ("Serbest metin", None)]})
    )
    assert noktalar[("Antalya", "toplam")] == {"2026-08-01": 1000.0}


# --- yolcu_noktalari: yapısal bozukluklar ---


def test_yolcu_noktalari_segment_etiketi_varlik_oncesi_gelirse_hata():
    govde = _yolcu_govdesi(2026, 8, varliklar=[])
    govde.append(_satir("International / Dis Hat", 100.0, False))
    with pytest.raises(RuntimeError, match="varlık adından önce"):
        yolcu_noktalari(_kitap_baytlari({"Sheet1": govde}))


def test_yolcu_noktalari_yinelenen_varlik_hata():
    govde = _yolcu_govdesi(
        2026, 8,
        varliklar=[("Antalya", 1000.0, None, None), ("Antalya", 2000.0, None, None)],
    )
    with pytest.raises(RuntimeError, match="yinelenen varlık"):
        yolcu_noktalari(_kitap_baytlari({"Sheet1": govde}))


def test_yolcu_noktalari_dis_hat_sonrasi_ic_hat_gelmezse_hata():
    govde = _yolcu_govdesi(2026, 8, varliklar=[])
    govde.append(_satir("Antalya", 1000.0, False))
    govde.append(_satir("International / Dis Hat", 700.0, False))
    govde.append(_satir("Izmir", 500.0, False))  # İç Hat yerine yeni varlık
    with pytest.raises(RuntimeError, match="İç Hat satırı beklenirken"):
        yolcu_noktalari(_kitap_baytlari({"Sheet1": govde}))


def test_yolcu_noktalari_iki_sayfa_ayni_tarihi_uretirse_hata():
    """Aynı (varlık, segment, tarih) iki farklı sayfadan gelirse (şablon
    çakışması) sessizce üzerine yazılmamalı."""
    govde1 = _yolcu_govdesi(2026, 8, varliklar=[("Antalya", 1000.0, None, None)])
    govde2 = _yolcu_govdesi(2026, 8, varliklar=[("Antalya", 2000.0, None, None)])
    with pytest.raises(RuntimeError, match="birden fazla sayfada"):
        yolcu_noktalari(_kitap_baytlari({"Sheet1": govde1, "0826": govde2}))


def test_yolcu_noktalari_birden_fazla_sayfa_birlestirir():
    govde_agustos = _yolcu_govdesi(2026, 8, varliklar=[("Antalya", 1000.0, None, None)])
    govde_temmuz = _yolcu_govdesi(2026, 7, varliklar=[("Antalya", 900.0, None, None)])
    noktalar = yolcu_noktalari(_kitap_baytlari({"Sheet1": govde_agustos, "0726": govde_temmuz}))
    assert noktalar[("Antalya", "toplam")] == {"2026-07-01": 900.0, "2026-08-01": 1000.0}


# --- dosya_listesi ---


def test_dosya_listesi_zaman_damgasina_gore_siralar():
    """HTML'de eski dosya ÖNCE, yeni dosya SONRA geçse bile en yeni [0] olmalı."""
    oturum = SahteOturum()
    dosyalar = dosya_listesi(oturum)
    assert dosyalar[0] == XLSX_URL
    assert len(dosyalar) == 2


def test_dosya_listesi_gecersiz_damgali_baglantilari_yok_sayar():
    html = LISTE_HTML + '<a href="https://ir.tav.aero/uploads/documents/rapor.xlsx">damgasız</a>'
    oturum = SahteOturum(liste_html=html)
    dosyalar = dosya_listesi(oturum)
    assert len(dosyalar) == 2
    assert all("rapor.xlsx" not in d for d in dosyalar)


def test_dosya_listesi_hicbir_baglanti_yoksa_hata():
    oturum = SahteOturum(liste_html="<html><body>boş</body></html>")
    with pytest.raises(RuntimeError, match="xlsx bağlantısı bulunamadı"):
        dosya_listesi(oturum)


def test_dosya_listesi_http_hatasi_yukselir():
    oturum = SahteOturum(liste_status=404)
    with pytest.raises(RuntimeError, match="HTTP 404"):
        dosya_listesi(oturum)


# --- seri_cek: ağ kabuğu ---


def test_seri_cek_dogru_deger_dondurur():
    govde = _yolcu_govdesi(2026, 8, varliklar=[("Antalya", 1000.0, 700.0, 300.0)])
    oturum = SahteOturum(xlsx_baytlar=_kitap_baytlari({"Sheet1": govde}))
    df = seri_cek(tav_seri(tav_varlik="Antalya", tav_segment="dis-hat"), onbellek={}, session=oturum)
    assert list(df["date"]) == ["2026-08-01"]
    assert df["value"].iloc[0] == 700.0


def test_seri_cek_onbellegi_paylasir():
    """28 seri aynı tek dosyayı paylaşır; ikinci/üçüncü seri ağdan hiç
    indirmemeli (liste sayfası + xlsx toplam 2 çağrı, kaç seri çekilirse
    çekilsin)."""
    govde = _yolcu_govdesi(2026, 8, varliklar=[("Antalya", 1000.0, 700.0, 300.0)])
    oturum = SahteOturum(xlsx_baytlar=_kitap_baytlari({"Sheet1": govde}))
    onbellek = {}
    seri_cek(tav_seri(tav_varlik="Antalya", tav_segment="toplam"), onbellek=onbellek, session=oturum)
    seri_cek(tav_seri(tav_varlik="Antalya", tav_segment="dis-hat"), onbellek=onbellek, session=oturum)
    seri_cek(tav_seri(tav_varlik="Antalya", tav_segment="ic-hat"), onbellek=onbellek, session=oturum)
    assert len(oturum.calls) == 2  # 1 liste sayfası + 1 xlsx indirme


def test_seri_cek_bilinmeyen_kombinasyonda_hata():
    """(e) Katalog geçerli segment kümesini zaten doğruluyor; burada asıl
    korunan senaryo bülten şablonunun kaymasıdır (bilinen bir varlık artık
    bültende yok, ya da yazım farklı)."""
    govde = _yolcu_govdesi(2026, 8, varliklar=[("Antalya", 1000.0, None, None)])
    oturum = SahteOturum(xlsx_baytlar=_kitap_baytlari({"Sheet1": govde}))
    with pytest.raises(RuntimeError, match="varlık/segment bulunamadı"):
        seri_cek(tav_seri(tav_varlik="Bilinmeyen Havalimanı", tav_segment="toplam"), onbellek={}, session=oturum)


def test_seri_cek_start_date_oncesini_kirpar():
    govde_agustos = _yolcu_govdesi(2026, 8, varliklar=[("Antalya", 1000.0, None, None)])
    govde_temmuz = _yolcu_govdesi(2026, 7, varliklar=[("Antalya", 900.0, None, None)])
    baytlar = _kitap_baytlari({"Sheet1": govde_agustos, "0726": govde_temmuz})
    oturum = SahteOturum(xlsx_baytlar=baytlar)
    df = seri_cek(tav_seri(start_date="2026-08-01"), onbellek={}, session=oturum)
    assert list(df["date"]) == ["2026-08-01"]


def test_seri_cek_xlsx_http_hatasi_yukselir():
    oturum = SahteOturum(xlsx_status=500)
    with pytest.raises(RuntimeError, match="HTTP 500"):
        seri_cek(tav_seri(), onbellek={}, session=oturum)
