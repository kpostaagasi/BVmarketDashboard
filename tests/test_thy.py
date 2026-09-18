"""THY (Türk Hava Yolları) trafik bülteni istemcisi testleri.

Bülten iki farklı şablonda geliyor (ölçüldü 2026-09-18, bkz. `ingest/thy.py`
docstring'i): yeni şablonda segment adı ilk metrik satırıyla aynı satırda
(A sütunu), eski şablonda segment kendi başına bir satırda (B sütunu).
Testler her iki şablonu da kapsar.
"""

import io
from types import SimpleNamespace

import openpyxl
import pytest

from ingest.thy import (
    TRAFIK_SAYFASI,
    dosya_listesi,
    seri_cek,
    trafik_noktalari,
)

AYLAR = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]

METRIKLER = [
    "Konma Sayısı (Yolcu Seferleri)",
    "Arzedilen Koltuk Km ('000)",
    "Yolcu Doluluk Oranı (%)",
    "Yolcu Sayısı",
    "Kargo + Posta (Ton)",
]


def _degerler(kod, ay_sayisi=12):
    """`kod` tabanlı, ay ay birbirinden ayırt edilebilir değerler üretir."""
    taban = [kod * 1000.0 + i for i in range(ay_sayisi)]
    return taban + [None] * (12 - ay_sayisi)


def _format_a_govde(bolgesel=True, ay_sayisi=12):
    """Yeni şablon: segment adı yalnızca segmentin ilk metrik satırında (A
    sütunu), ay başlığı satır 2'de."""
    satirlar = [
        (None,) * 14,
        (None, None, *AYLAR),
    ]
    for si, segment in enumerate(["Toplam", "Yurt İçi", "Yurt Dışı"]):
        for mi, metrik in enumerate(METRIKLER):
            etiket = segment if mi == 0 else None
            satirlar.append((etiket, metrik, *_degerler(si * 10 + mi, ay_sayisi)))
        satirlar.append((None,) * 14)
    if bolgesel:
        satirlar.append((None, "BÖLGESEL", *([None] * 12)))
        satirlar.append(
            ("Yurt İçi", "Arzedilen Koltuk Km ('000)", *_degerler(999, ay_sayisi))
        )
    return satirlar


def _format_b_govde(segment_buyuk="TOPLAM", metrikler=None):
    """Eski şablon: segment kendi başına bir satırda (B sütunu), ay başlığı
    bir sonraki satırda."""
    if metrikler is None:
        metrikler = [("Konma Sayısı (Yolcu Seferleri)", _degerler(1))]
    satirlar = [
        (None,) * 14,
        (None, segment_buyuk, *([None] * 12)),
        (None, None, *AYLAR),
    ]
    for metrik, degerler in metrikler:
        satirlar.append((None, metrik, *degerler))
    return satirlar


def _tek_metrik_govde(segment="Toplam", metrik="Yolcu Sayısı", degerler=None):
    if degerler is None:
        degerler = _degerler(1)
    return [
        (None,) * 14,
        (None, None, *AYLAR),
        (segment, metrik, *degerler),
    ]


def _degistir(govde, satir_no, sutun_no, deger):
    """1-indeksli (satır, sütun) hücreyi değiştirip yeni gövdeyi döner."""
    yeni = [list(s) for s in govde]
    yeni[satir_no - 1][sutun_no - 1] = deger
    return [tuple(s) for s in yeni]


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


def thy_seri(**kwargs):
    varsayilan = dict(
        id="havacilik/thyao-toplam-yolcu",
        kaynak_tipi="thy",
        thy_segment="Toplam",
        thy_olcut="yolcu",
        start_date=None,
    )
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


class SahteYanit:
    def __init__(self, content, status_code=200):
        self.content = content
        self.status_code = status_code


class SahteOturum:
    def __init__(self, yanit_haritasi):
        """`yanit_haritasi`: url -> SahteYanit."""
        self.yanit_haritasi = yanit_haritasi
        self.cagrilar = []

    def get(self, url, timeout=None, headers=None):
        self.cagrilar.append(url)
        assert headers["User-Agent"] == "Mozilla/5.0"
        return self.yanit_haritasi[url]


def _dosya_oturumu(dosya_url, dosya_baytlari):
    html = f'<a href="{dosya_url}" target="_blank">xlsx</a>'.encode("utf-8")
    return SahteOturum({
        TRAFIK_SAYFASI: SahteYanit(html),
        dosya_url: SahteYanit(dosya_baytlari),
    })


# --- trafik_noktalari: yapı çıkarma ---


def test_trafik_noktalari_segment_ilk_satirdan_miras_alinir():
    """Segment adı yalnızca segmentin ilk metrik satırında; sonraki dört
    metrik satırında A sütunu boştur — yine de aynı segmente bağlanmalı."""
    noktalar = trafik_noktalari(_kitap_baytlari({"2026": _format_a_govde(bolgesel=False)}))
    # Toplam: si=0 -> konma(mi=0)=0, ask(mi=1)=1, doluluk(mi=2)=2, yolcu(mi=3)=3, kargo(mi=4)=4
    assert noktalar[("Toplam", "konma")]["2026-01-01"] == 0.0
    assert noktalar[("Toplam", "ask")]["2026-01-01"] == 1000.0
    assert noktalar[("Toplam", "kargo")]["2026-01-01"] == 4000.0
    # Yurt İçi: si=1 -> konma=10, yolcu=13
    assert noktalar[("Yurt İçi", "konma")]["2026-01-01"] == 10000.0
    assert noktalar[("Yurt İçi", "yolcu")]["2026-01-01"] == 13000.0
    # Yurt Dışı: si=2 -> kargo=24
    assert noktalar[("Yurt Dışı", "kargo")]["2026-01-01"] == 24000.0


def test_trafik_noktalari_eski_sablonda_segment_kendi_satirinda():
    """Eski şablon: segment B sütununda kendi başına bir satırda; izlenmeyen
    ek ölçüt (Ücretli Yolcu Km) sessizce atlanmalı."""
    govde = _format_b_govde(
        segment_buyuk="YURT İÇİ",
        metrikler=[
            ("Konma Sayısı (Yolcu Seferleri)", _degerler(5)),
            ("Ücretli Yolcu Km ('000)", _degerler(1)),
            ("Yolcu Sayısı", _degerler(500)),
        ],
    )
    noktalar = trafik_noktalari(_kitap_baytlari({"2025": govde}))
    assert noktalar[("Yurt İçi", "konma")]["2025-01-01"] == 5000.0
    assert noktalar[("Yurt İçi", "yolcu")]["2025-01-01"] == 500000.0
    assert len(noktalar) == 2  # "Ücretli Yolcu Km" izlenmiyor, anahtar yaratmaz


def test_trafik_noktalari_bolgesel_blogu_okunmadan_durur():
    """'BÖLGESEL' bloğu ana bloktaki bir (segment, ölçüt) çiftini tekrar
    listeler; durmazsa yinelenen anahtar hatası verirdi."""
    noktalar = trafik_noktalari(_kitap_baytlari({"2026": _format_a_govde(bolgesel=True)}))
    # Ana bloktaki Yurt İçi/ask değeri (kod=11) BÖLGESEL'deki (kod=999) ile
    # EZİLMEMİŞ olmalı — BÖLGESEL satırında durulduğunun kanıtı.
    assert noktalar[("Yurt İçi", "ask")]["2026-01-01"] == 11000.0


def test_trafik_noktalari_cok_yillik_dosyada_tum_yil_sayfalarini_okur():
    sayfalar = {
        "Notlar": [(None,) * 14] * 3,
        "2025": _format_a_govde(bolgesel=False),
        "2026": _format_a_govde(bolgesel=False),
    }
    noktalar = trafik_noktalari(_kitap_baytlari(sayfalar))
    tarihler = noktalar[("Toplam", "konma")]
    assert "2025-01-01" in tarihler
    assert "2026-01-01" in tarihler
    assert len(tarihler) == 24  # iki yıl × 12 ay


def test_trafik_noktalari_bos_hucrede_sifir_uydurmaz():
    degerler = _degerler(1)
    degerler[8] = None  # Eylül yayımlanmamış
    govde = _tek_metrik_govde(degerler=degerler)
    noktalar = trafik_noktalari(_kitap_baytlari({"2026": govde}))
    tarihler = noktalar[("Toplam", "yolcu")]
    assert "2026-09-01" not in tarihler
    assert tarihler["2026-08-01"] == 1007.0


def test_trafik_noktalari_bilinmeyen_segmentte_hata():
    govde = _tek_metrik_govde(segment="Bilinmeyen Segment")
    with pytest.raises(RuntimeError, match="segment"):
        trafik_noktalari(_kitap_baytlari({"2026": govde}))


def test_trafik_noktalari_bilinmeyen_olcutte_hata():
    """Eski şablonun izlenmeyen ölçütlerinden FARKLI: beyaz listede olmayan
    bir etiket şablon bozulmasıdır, sessizce atlanmaz."""
    govde = _tek_metrik_govde(metrik="Bambaşka Bir Ölçüt")
    with pytest.raises(RuntimeError, match="ölçüt"):
        trafik_noktalari(_kitap_baytlari({"2026": govde}))


def test_trafik_noktalari_sayisal_olmayan_hucrede_hata():
    degerler = _degerler(1)
    degerler[0] = "abc"
    govde = _tek_metrik_govde(degerler=degerler)
    with pytest.raises(RuntimeError, match="sayısal olmayan"):
        trafik_noktalari(_kitap_baytlari({"2026": govde}))


def test_trafik_noktalari_ay_basligi_bulunamazsa_hata():
    """Ay başlığı satırı hiç yoksa (şablon kayması), veri satırı tek başına
    ölçüt olarak geçerli olsa bile sessizce geçilmemeli."""
    govde = [
        (None,) * 14,
        ("Toplam", "Yolcu Sayısı", *_degerler(1)),
    ]
    with pytest.raises(RuntimeError, match="ay başlığı"):
        trafik_noktalari(_kitap_baytlari({"2026": govde}))


def test_trafik_noktalari_yil_sayfasi_yoksa_hata():
    with pytest.raises(RuntimeError, match="yıl sayfası"):
        trafik_noktalari(_kitap_baytlari({"Notlar": [(None,) * 14] * 3}))


# --- dosya_listesi: sayfa kazıma ---


def test_dosya_listesi_xlsx_baglantilarini_mutlak_url_olarak_doner():
    html = (
        '<a href="/documents/trafik/turkish-airlines-trafik-agustos_2026.xlsx" '
        'target="_blank">xlsx</a>'
        '<a href="/documents/trafik/agustos-2026-trafik.pdf" target="_blank">pdf</a>'
        '<a href="/documents/turkish-airlines-trafik-aralik_2024.xlsx" '
        'target="_blank">xlsx2</a>'
    ).encode("utf-8")
    oturum = SahteOturum({TRAFIK_SAYFASI: SahteYanit(html)})
    dosyalar = dosya_listesi(session=oturum)
    assert dosyalar == [
        "https://investor.turkishairlines.com/documents/trafik/"
        "turkish-airlines-trafik-agustos_2026.xlsx",
        "https://investor.turkishairlines.com/documents/"
        "turkish-airlines-trafik-aralik_2024.xlsx",
    ]


def test_dosya_listesi_xlsx_yoksa_hata():
    oturum = SahteOturum({TRAFIK_SAYFASI: SahteYanit(b"<html></html>")})
    with pytest.raises(RuntimeError, match="xlsx"):
        dosya_listesi(session=oturum)


def test_dosya_listesi_http_hatasi_yukselir():
    oturum = SahteOturum({TRAFIK_SAYFASI: SahteYanit(b"", status_code=500)})
    with pytest.raises(RuntimeError, match="HTTP 500"):
        dosya_listesi(session=oturum)


# --- seri_cek: ağ kabuğu ---


def test_seri_cek_dogru_deger_dondurur():
    dosya_url = "https://investor.turkishairlines.com/documents/trafik/x.xlsx"
    oturum = _dosya_oturumu(
        dosya_url, _kitap_baytlari({"2026": _format_a_govde(bolgesel=False)})
    )
    df = seri_cek(thy_seri(thy_segment="Toplam", thy_olcut="yolcu"), onbellek={}, session=oturum)
    assert list(df.columns) == ["date", "value"]
    assert df[df.date == "2026-01-01"].value.iloc[0] == 3000.0
    assert len(df) == 12


def test_seri_cek_onbellegi_paylasir():
    """15 seri aynı ~5 dosyalık kümeyi paylaşır; ikinci seri hiç indirmemeli."""
    dosya_url = "https://investor.turkishairlines.com/documents/trafik/x.xlsx"
    oturum = _dosya_oturumu(
        dosya_url, _kitap_baytlari({"2026": _format_a_govde(bolgesel=False)})
    )
    onbellek: dict = {}
    seri_cek(thy_seri(thy_segment="Toplam", thy_olcut="yolcu"), onbellek=onbellek, session=oturum)
    ilk_cagri = len(oturum.cagrilar)
    seri_cek(thy_seri(thy_segment="Yurt İçi", thy_olcut="kargo"), onbellek=onbellek, session=oturum)
    assert len(oturum.cagrilar) == ilk_cagri


def test_seri_cek_start_date_oncesini_kirpar():
    dosya_url = "https://investor.turkishairlines.com/documents/trafik/x.xlsx"
    sayfalar = {
        "2025": _format_a_govde(bolgesel=False),
        "2026": _format_a_govde(bolgesel=False),
    }
    oturum = _dosya_oturumu(dosya_url, _kitap_baytlari(sayfalar))
    df = seri_cek(
        thy_seri(thy_segment="Toplam", thy_olcut="yolcu", start_date="2026-01-01"),
        onbellek={}, session=oturum,
    )
    assert df["date"].min() == "2026-01-01"
    assert len(df) == 12


def test_seri_cek_bilinmeyen_kombinasyonda_hata():
    """Katalog geçerli segment/ölçüt kümesini zaten doğruluyor; burada
    dosyada gerçekten bulunmayan bir çift savunma amaçlı test ediliyor."""
    dosya_url = "https://investor.turkishairlines.com/documents/trafik/x.xlsx"
    oturum = _dosya_oturumu(
        dosya_url,
        _kitap_baytlari({"2026": _tek_metrik_govde(segment="Toplam", metrik="Yolcu Sayısı")}),
    )
    with pytest.raises(RuntimeError, match="bulunamadı"):
        seri_cek(
            thy_seri(thy_segment="Yurt Dışı", thy_olcut="kargo"),
            onbellek={}, session=oturum,
        )


def test_seri_cek_dosya_http_hatasi_yukselir():
    dosya_url = "https://investor.turkishairlines.com/documents/trafik/x.xlsx"
    html = f'<a href="{dosya_url}" target="_blank">xlsx</a>'.encode("utf-8")
    oturum = SahteOturum({
        TRAFIK_SAYFASI: SahteYanit(html),
        dosya_url: SahteYanit(b"", status_code=404),
    })
    with pytest.raises(RuntimeError, match="HTTP 404"):
        seri_cek(thy_seri(), onbellek={}, session=oturum)
