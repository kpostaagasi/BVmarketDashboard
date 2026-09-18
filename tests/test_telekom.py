"""Turkcell (`ingest/turkcell.py`) ve Türk Telekom (`ingest/ttkom.py`)
çeyreklik operasyonel veri istemcisi testleri.

İki adaptörün de EN GÜNCEL Excel'i (kendi başına tüm pencereyi taşıyan
tek dosya) tek seferde indirip önbelleklediği ve aynı sayfa/etiket
içindeki BLOK ÇAKIŞMALARINI (ör. "Turkcell Türkiye" hem Revenue hem
EBITDA tablosunda; TTKOM'un "Mobil Karma ARPU" büyümesinin 2025 Ç3'te
M2M dahil/hariç rejim değiştirmesi) doğru ayırt ettiği burada pinlenir.
"""

import io
from types import SimpleNamespace

import openpyxl
import pytest

from ingest.turkcell import (
    CEYREK_SAYFASI,
    en_guncel_dosya_url as tcell_en_guncel_dosya_url,
    seri_cek as tcell_seri_cek,
    _blok_sinirlari,
    _ceyrek_tarihi as tcell_ceyrek_tarihi,
    _seriyi_bul,
)
from ingest.ttkom import (
    ARSIV_SAYFASI,
    en_guncel_dosya_url as ttkom_en_guncel_dosya_url,
    seri_cek as ttkom_seri_cek,
    _buyume_serisi,
    _ceyrek_tarihi as ttkom_ceyrek_tarihi,
    _en_yakin_baslik_satiri,
    _etiket_serisi,
)


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


def _kitabi_ac(sayfalar: dict):
    return openpyxl.load_workbook(io.BytesIO(_kitap_baytlari(sayfalar)), data_only=True)


class SahteYanit:
    def __init__(self, content=b"", text=None, status_code=200):
        self.content = content
        self.text = text if text is not None else content.decode("utf-8", errors="replace")
        self.status_code = status_code


class SahteOturum:
    def __init__(self, yanit_haritasi):
        self.yanit_haritasi = yanit_haritasi
        self.cagrilar = []

    def get(self, url, timeout=None, headers=None):
        self.cagrilar.append(url)
        return self.yanit_haritasi[url]


def tcell_seri(**kwargs):
    varsayilan = dict(id="telekom/tcell-x", turkcell_metrik="mobil-postpaid-abone", start_date=None)
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


def ttkom_seri(**kwargs):
    varsayilan = dict(id="telekom/ttkom-x", ttkom_metrik="mobil-toplam-abone", start_date=None)
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


# --- Turkcell: _blok_sinirlari / _seriyi_bul (blok çakışması) ---


def _segment_sayfasi():
    """'Turkcell Türkiye' hem Revenue hem EBITDA bloğunda FARKLI değerlerle
    geçiyor — gerçek 'Segment Revenue-EBITDA_Unadj' sayfasının küçültülmüş
    hâli."""
    return _kitabi_ac({
        "Segment Revenue-EBITDA_Unadj": [
            (None, None),
            (None, "Revenue Breakdown (Unadjusted)"),
            (None, None),
            (None, "(million TRY)", "Q123", "Q223"),
            (None, "Turkcell Türkiye", 100.0, 110.0),
            (None, None),
            (None, "EBITDA Breakdown (Unadjusted)"),
            (None, None),
            (None, "(million TRY)", "Q123", "Q223"),
            (None, "Turkcell Türkiye", 40.0, 44.0),
        ],
    })["Segment Revenue-EBITDA_Unadj"]


def test_blok_sinirlari_baslik_yoksa_tum_sayfa_tek_blok():
    ws = _kitabi_ac({"Operational KPIs": [(None, None), (None, "Mobile postpaid subscribers (million)", 1.0)]})["Operational KPIs"]
    bloklar = _blok_sinirlari(ws)
    assert bloklar == [(None, 1, ws.max_row)]


def test_blok_sinirlari_iki_baslikli_bloga_ayirir():
    ws = _segment_sayfasi()
    bloklar = _blok_sinirlari(ws)
    basliklar = [b for b, _, _ in bloklar]
    assert basliklar == ["Revenue Breakdown (Unadjusted)", "EBITDA Breakdown (Unadjusted)"]


def test_seriyi_bul_ayni_etiketi_blok_ipucuyla_ayirt_eder():
    """Blok ipucu olmasaydı ilk (Revenue) blok her zaman kazanırdı; EBITDA
    isteyen bir seri sessizce yanlış (Revenue) değeri alırdı."""
    ws = _segment_sayfasi()
    gelir = _seriyi_bul(ws, "Turkcell Türkiye", "Revenue Breakdown")
    favok = _seriyi_bul(ws, "Turkcell Türkiye", "EBITDA Breakdown")
    assert gelir == {"Q123": 100.0, "Q223": 110.0}
    assert favok == {"Q123": 40.0, "Q223": 44.0}


def test_seriyi_bul_merged_baslik_blogunda_calisir():
    """Subsidiaries_Unadj tipi sayfalarda blok başlığı ('XXX Summary Data')
    çeyrek sütunlarını da AYNI satırda taşır — ayrı bir başlık satırı yok."""
    ws = _kitabi_ac({
        "Subsidiaries_Unadj": [
            (None, "BeST1 (Unadjusted)"),
            (None, None),
            (None, "BeST Summary Data", "Q123", "Q223"),
            (None, "Revenue (million TRY)", 5.0, 6.0),
            (None, None),
            (None, "Paycell Business (Unadjusted)"),
            (None, None),
            (None, "Paycell Summary Data", "Q123", "Q223"),
            (None, "Revenue (million TRY)", 20.0, 22.0),
        ],
    })["Subsidiaries_Unadj"]
    best = _seriyi_bul(ws, "Revenue (million TRY)", "BeST Summary Data")
    paycell = _seriyi_bul(ws, "Revenue (million TRY)", "Paycell Summary Data")
    assert best == {"Q123": 5.0, "Q223": 6.0}
    assert paycell == {"Q123": 20.0, "Q223": 22.0}


def test_seriyi_bul_bulunamazsa_bos_sozluk_doner():
    ws = _kitabi_ac({"Operational KPIs": [(None, None), (None, "Mobile postpaid subscribers (million)", 1.0)]})["Operational KPIs"]
    assert _seriyi_bul(ws, "Bilinmeyen Etiket", None) == {}


def test_tcell_ceyrek_tarihi_her_ceyregi_dogru_aya_esler():
    assert tcell_ceyrek_tarihi("Q126") == "2026-01-01"
    assert tcell_ceyrek_tarihi("Q226") == "2026-04-01"
    assert tcell_ceyrek_tarihi("Q326") == "2026-07-01"
    assert tcell_ceyrek_tarihi("Q426") == "2026-10-01"


# --- Turkcell: en_guncel_dosya_url (__NEXT_DATA__ ayrıştırma) ---


def _next_data_html(kayitlar: list[dict]) -> str:
    import json
    veri = {
        "props": {"pageProps": {"dehydratedState": {"queries": [
            {"state": {"data": "ilgisiz"}},
            {"state": {"data": kayitlar}},
        ]}}}
    }
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(veri)}</script></html>'


def test_en_guncel_dosya_url_en_son_ceyregi_secer():
    """Next.js sorgu listesinde birden çok girdi olabilir; şekle göre (year/
    quarter/content anahtarları) arama yapılır, sabit indekse güvenilmez."""
    html = _next_data_html([
        {"year": 2025, "quarter": 4, "content": [
            {"title": "Q4 2025 Financial and Operational Data", "url": "/eski.xlsx"},
        ]},
        {"year": 2026, "quarter": 1, "content": [
            {"title": "Q1 2026 Financial and Operational Data", "url": "/guncel.xlsx"},
        ]},
    ])
    oturum = SahteOturum({CEYREK_SAYFASI: SahteYanit(text=html)})
    url = tcell_en_guncel_dosya_url(session=oturum)
    assert url == "https://ffo3gv1cf3ir.merlincdn.net/guncel.xlsx"


def test_en_guncel_dosya_url_mutlak_url_oldugu_gibi_kalir():
    html = _next_data_html([
        {"year": 2026, "quarter": 1, "content": [
            {"title": "Q1 2026 Financial and Operational Data", "url": "https://baska-cdn.com/x.xlsx"},
        ]},
    ])
    oturum = SahteOturum({CEYREK_SAYFASI: SahteYanit(text=html)})
    assert tcell_en_guncel_dosya_url(session=oturum) == "https://baska-cdn.com/x.xlsx"


def test_en_guncel_dosya_url_next_data_yoksa_hata():
    oturum = SahteOturum({CEYREK_SAYFASI: SahteYanit(text="<html>boş</html>")})
    with pytest.raises(RuntimeError, match="__NEXT_DATA__"):
        tcell_en_guncel_dosya_url(session=oturum)


def test_en_guncel_dosya_url_http_hatasi_yukselir():
    oturum = SahteOturum({CEYREK_SAYFASI: SahteYanit(status_code=500)})
    with pytest.raises(RuntimeError, match="HTTP 500"):
        tcell_en_guncel_dosya_url(session=oturum)


def test_en_guncel_dosya_url_fo_baglantisi_yoksa_hata():
    html = _next_data_html([
        {"year": 2026, "quarter": 1, "content": [{"title": "Q1 2026 Press Release", "url": "/pr.pdf"}]},
    ])
    oturum = SahteOturum({CEYREK_SAYFASI: SahteYanit(text=html)})
    with pytest.raises(RuntimeError, match="Financial and Operational Data"):
        tcell_en_guncel_dosya_url(session=oturum)


# --- Turkcell: seri_cek (ağ kabuğu + önbellek) ---


def _tcell_dosya_oturumu(dosya_url: str, kitap_baytlari: bytes) -> SahteOturum:
    html = _next_data_html([
        {"year": 2026, "quarter": 2, "content": [
            {"title": "Q2 2026 Financial and Operational Data", "url": dosya_url},
        ]},
    ])
    return SahteOturum({
        CEYREK_SAYFASI: SahteYanit(text=html),
        dosya_url: SahteYanit(content=kitap_baytlari),
    })


def test_tcell_seri_cek_dogru_deger_ve_onbellek_paylasir():
    dosya_url = "https://cdn.example.com/Q226-FO-Info.xlsx"
    kitap = _kitap_baytlari({
        "Operational KPIs": [
            (None, None), (None, None, "Q123", "Q223"),
            (None, "Mobile postpaid subscribers (million)", 24.1, 24.5),
        ],
    })
    oturum = _tcell_dosya_oturumu(dosya_url, kitap)
    onbellek: dict = {}

    df1 = tcell_seri_cek(tcell_seri(turkcell_metrik="mobil-postpaid-abone"), onbellek=onbellek, session=oturum)
    assert list(df1["date"]) == ["2023-01-01", "2023-04-01"]
    assert df1["value"].tolist() == pytest.approx([24.1, 24.5])

    cagri_sayisi = len(oturum.cagrilar)
    tcell_seri_cek(tcell_seri(turkcell_metrik="mobil-postpaid-abone"), onbellek=onbellek, session=oturum)
    assert len(oturum.cagrilar) == cagri_sayisi  # ikinci çağrı hiç ağa çıkmamalı


def test_tcell_seri_cek_start_date_oncesini_kirpar():
    dosya_url = "https://cdn.example.com/Q226-FO-Info.xlsx"
    kitap = _kitap_baytlari({
        "Operational KPIs": [
            (None, None), (None, None, "Q123", "Q223"),
            (None, "Mobile postpaid subscribers (million)", 24.1, 24.5),
        ],
    })
    oturum = _tcell_dosya_oturumu(dosya_url, kitap)
    df = tcell_seri_cek(
        tcell_seri(turkcell_metrik="mobil-postpaid-abone", start_date="2023-02-01"),
        onbellek={}, session=oturum,
    )
    assert list(df["date"]) == ["2023-04-01"]


def test_tcell_seri_cek_sayfa_yoksa_hata():
    dosya_url = "https://cdn.example.com/Q226-FO-Info.xlsx"
    kitap = _kitap_baytlari({"Operational KPIs": [(None, None)]})
    oturum = _tcell_dosya_oturumu(dosya_url, kitap)
    with pytest.raises(RuntimeError, match="ARPU_IAS29"):
        tcell_seri_cek(tcell_seri(turkcell_metrik="prepaid-arpu"), onbellek={}, session=oturum)


def test_tcell_seri_cek_etiket_bulunamazsa_hata():
    """Şablon kayması (satır/sütun kayması, kaldırılan metrik) sessizce eksik
    veri üretmek yerine hataya düşmeli."""
    dosya_url = "https://cdn.example.com/Q226-FO-Info.xlsx"
    kitap = _kitap_baytlari({
        "Operational KPIs": [(None, None), (None, None, "Q123"), (None, "Başka Satır", 1.0)],
    })
    oturum = _tcell_dosya_oturumu(dosya_url, kitap)
    with pytest.raises(RuntimeError, match="bulunamadı"):
        tcell_seri_cek(tcell_seri(turkcell_metrik="mobil-postpaid-abone"), onbellek={}, session=oturum)


# --- TTKOM: _etiket_serisi / _en_yakin_baslik_satiri (çok bölümlü sayfa) ---


def _tms29_benzeri_sayfa():
    """Aynı sayfada İKİ ayrı çeyrek başlık satırı: 'Düzeltme Katsayısı'
    (satır 3) ile 'Operasyonel Veriler' (satır 7) bölümleri FARKLI sütun
    kümeleri taşıyor — etiket kendi bölümünün başlığını bulmalı, sayfanın
    İLK (yanlış) başlığını değil."""
    return _kitabi_ac({
        "Finansal&Oper. Veriler (TMS29)": [
            (None, None),
            (None, "Dönem Endeksi"),
            (None, None, "2023 1Ç", "2024 1Ç"),
            (None, "Düzeltme Katsayısı", 3.0, 1.5),
            (None, None),
            (None, "Operasyonel Veriler"),
            (None, "TL", "2023 1Ç", "2024 1Ç", "2025 2Ç", "2026 1Ç", "2026 2Ç"),
            (None, "Genişbant ARPU", 300.0, 315.0, 345.0, 400.0, 420.0),
            (None, "Mobil Karma ARPU", 200.0, 220.0, 260.0, 999.0, 999.0),
            (None, "Mobil Karma ARPU (M2M hariç)", None, None, 250.0, 290.0, 310.0),
        ],
    })["Finansal&Oper. Veriler (TMS29)"]


def test_etiket_serisi_kendi_bolumunun_basligini_kullanir():
    ws = _tms29_benzeri_sayfa()
    seri = _etiket_serisi(ws, "Genişbant ARPU")
    assert seri == {"2023 1Ç": 300.0, "2024 1Ç": 315.0, "2025 2Ç": 345.0, "2026 1Ç": 400.0, "2026 2Ç": 420.0}


def test_etiket_serisi_bulunamazsa_bos_sozluk_doner():
    ws = _tms29_benzeri_sayfa()
    assert _etiket_serisi(ws, "Yok Böyle Bir Satır") == {}


def test_en_yakin_baslik_satiri_basligi_olmayan_satirda_hata():
    ws = _kitabi_ac({"Boş": [(None, "etiket", 1.0)]})["Boş"]
    with pytest.raises(RuntimeError, match="çeyrek başlığı"):
        _en_yakin_baslik_satiri(ws, 1)


def test_ttkom_ceyrek_tarihi_her_ceyregi_dogru_aya_esler():
    assert ttkom_ceyrek_tarihi("2026 1Ç") == "2026-01-01"
    assert ttkom_ceyrek_tarihi("2026 2Ç") == "2026-04-01"
    assert ttkom_ceyrek_tarihi("2026 3Ç") == "2026-07-01"
    assert ttkom_ceyrek_tarihi("2026 4Ç") == "2026-10-01"


# --- TTKOM: _buyume_serisi (nominal 2023 + TAS29 2024+ + M2M rejim kırılması) ---


def _ttkom_buyume_kitabi():
    return _kitabi_ac({
        "ARPU (Tarihsel)": [
            (None, "Periyod", "2022 1Ç", "2023 1Ç"),
            (None, "Genişbant ARPU  (TL)", 100.0, 150.0),
            (None, "Mobil Karma ARPU (TL)", 150.0, 200.0),
        ],
        "Finansal&Oper. Veriler (TMS29)": [
            (None, "TL", "2023 1Ç", "2024 1Ç", "2025 2Ç", "2026 1Ç", "2026 2Ç"),
            (None, "Genişbant ARPU", 300.0, 315.0, 345.0, 400.0, 420.0),
            (None, "Mobil Karma ARPU", 200.0, 220.0, 260.0, 999.0, 999.0),
            (None, "Mobil Karma ARPU (M2M hariç)", None, None, 250.0, 290.0, 310.0),
        ],
    })


def test_buyume_serisi_2023_nominalden_2024_tas29dan_hesaplanir():
    """Sabit genişbant büyümesinde rejim kırılması yalnızca nominal->TAS29
    (2023->2024); M2M ayrımı yok, tek satır her iki dönemde de geçerli."""
    kitap = _ttkom_buyume_kitabi()
    sonuc = _buyume_serisi(kitap, "sabit-genisbant-arpu-buyume")
    assert sonuc["2023 1Ç"] == pytest.approx(50.0)  # nominal: 150/100-1
    assert sonuc["2024 1Ç"] == pytest.approx(5.0)   # TAS29: 315/300-1
    assert sonuc["2026 2Ç"] == pytest.approx(420 / 345 * 100 - 100)  # TAS29: 420/345-1


def test_buyume_serisi_mobil_karma_2025c3_oncesi_dahil_sonrasi_haric_kullanir():
    """2025 Ç3'ten ÖNCE 'Mobil Karma ARPU' (M2M dahil), SONRA 'Mobil Karma
    ARPU (M2M hariç)' satırı kullanılmalı. dahil satırındaki 2026
    sütunlarına bilinçli olarak saçma (999) değer konuldu: kod yanlış
    satırı okursa büyüme ~%284 çıkar, doğru satırı okursa %24 çıkar."""
    kitap = _ttkom_buyume_kitabi()
    sonuc = _buyume_serisi(kitap, "mobil-karma-arpu-buyume")
    assert sonuc["2023 1Ç"] == pytest.approx(200 / 150 * 100 - 100)  # nominal
    assert sonuc["2024 1Ç"] == pytest.approx(10.0)  # TAS29 dahil: 220/200-1
    assert sonuc["2026 2Ç"] == pytest.approx(24.0)  # TAS29 hariç: 310/250-1 (dahil olsaydı ~284 çıkardı)


def test_buyume_serisi_onceki_yil_yoksa_atlanir():
    """Referans yılı (2023 1Ç -> 2022 1Ç TAS29'da yok) eksikse sessizce
    atlanmalı, sıfır/hatalı değer uydurulmamalı."""
    kitap = _ttkom_buyume_kitabi()
    sonuc = _buyume_serisi(kitap, "sabit-genisbant-arpu-buyume")
    assert "2025 2Ç" not in sonuc  # önceki yıl (2024 2Ç) sütunu yok
    assert "2026 1Ç" not in sonuc  # önceki yıl (2025 1Ç) sütunu yok


# --- TTKOM: en_guncel_dosya_url ve seri_cek (ağ kabuğu + önbellek) ---


def test_ttkom_en_guncel_dosya_url_ilk_baglantiyi_secer():
    """Arşiv sayfası yeniden-eskiye sıralı; ilk 'Özet Finansal ve
    Operasyonel Veriler' bağlantısı en güncel çeyreğe ait."""
    html = (
        '<a href="/media/guncel/dosya-2c-26.xlsx">Özet Finansal ve Operasyonel Veriler</a>'
        '<a href="/media/eski/dosya-1c-25.xlsx">Özet Finansal ve Operasyonel Veriler</a>'
    )
    oturum = SahteOturum({ARSIV_SAYFASI: SahteYanit(text=html)})
    assert ttkom_en_guncel_dosya_url(session=oturum) == (
        "https://www.ttyatirimciiliskileri.com.tr/media/guncel/dosya-2c-26.xlsx"
    )


def test_ttkom_en_guncel_dosya_url_baglanti_yoksa_hata():
    oturum = SahteOturum({ARSIV_SAYFASI: SahteYanit(text="<html>boş</html>")})
    with pytest.raises(RuntimeError, match="Özet Finansal"):
        ttkom_en_guncel_dosya_url(session=oturum)


def test_ttkom_en_guncel_dosya_url_http_hatasi_yukselir():
    oturum = SahteOturum({ARSIV_SAYFASI: SahteYanit(status_code=404)})
    with pytest.raises(RuntimeError, match="HTTP 404"):
        ttkom_en_guncel_dosya_url(session=oturum)


def _ttkom_dosya_oturumu(dosya_url: str, kitap_baytlari: bytes) -> SahteOturum:
    html = f'<a href="{dosya_url}">Özet Finansal ve Operasyonel Veriler</a>'
    return SahteOturum({
        ARSIV_SAYFASI: SahteYanit(text=html),
        dosya_url: SahteYanit(content=kitap_baytlari),
    })


def test_ttkom_seri_cek_dogrudan_metrikte_dogru_deger_ve_onbellek_paylasir():
    dosya_url = "https://www.ttyatirimciiliskileri.com.tr/media/x/dosya.xlsx"
    kitap = _kitap_baytlari({
        "Abone Verileri": [
            (None, "Periyod", "2025 1Ç", "2025 2Ç"),
            (None, "Mobil Toplam Abone Sayısı (mn)", 30.0, 31.0),
        ],
    })
    oturum = _ttkom_dosya_oturumu(dosya_url, kitap)
    onbellek: dict = {}

    df = ttkom_seri_cek(ttkom_seri(ttkom_metrik="mobil-toplam-abone"), onbellek=onbellek, session=oturum)
    assert list(df["date"]) == ["2025-01-01", "2025-04-01"]
    assert df["value"].tolist() == pytest.approx([30.0, 31.0])

    cagri_sayisi = len(oturum.cagrilar)
    ttkom_seri_cek(ttkom_seri(ttkom_metrik="mobil-toplam-abone"), onbellek=onbellek, session=oturum)
    assert len(oturum.cagrilar) == cagri_sayisi


def test_ttkom_seri_cek_buyume_metrigini_hesaplayarak_doner():
    dosya_url = "https://www.ttyatirimciiliskileri.com.tr/media/x/dosya.xlsx"
    kitap_bayt = _kitap_baytlari({
        "ARPU (Tarihsel)": [
            (None, "Periyod", "2022 1Ç", "2023 1Ç"),
            (None, "Genişbant ARPU  (TL)", 100.0, 150.0),
        ],
        "Finansal&Oper. Veriler (TMS29)": [
            (None, "TL", "2023 1Ç", "2024 1Ç"),
            (None, "Genişbant ARPU", 300.0, 315.0),
        ],
    })
    oturum = _ttkom_dosya_oturumu(dosya_url, kitap_bayt)
    df = ttkom_seri_cek(ttkom_seri(ttkom_metrik="sabit-genisbant-arpu-buyume"), onbellek={}, session=oturum)
    degerler = dict(zip(df["date"], df["value"]))
    assert degerler["2023-01-01"] == pytest.approx(50.0)
    assert degerler["2024-01-01"] == pytest.approx(5.0)


def test_ttkom_seri_cek_bilinmeyen_metrikte_hata():
    dosya_url = "https://www.ttyatirimciiliskileri.com.tr/media/x/dosya.xlsx"
    kitap = _kitap_baytlari({"Abone Verileri": [(None, "Periyod", "2025 1Ç")]})
    oturum = _ttkom_dosya_oturumu(dosya_url, kitap)
    with pytest.raises(RuntimeError, match="Bilinmeyen ttkom_metrik"):
        ttkom_seri_cek(ttkom_seri(ttkom_metrik="olmayan-metrik"), onbellek={}, session=oturum)
