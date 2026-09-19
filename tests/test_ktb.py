"""KTB Sınır İstatistikleri Bülteni (Gelen Yabancılar) istemcisi testleri.

Bülten baytları pandas ile üretilir: gerçek dosyanın "Gelen Yabancılar"
sayfası şablonu (0. satır tablo başlığı, 1. satır "YILLAR" grup başlığı,
2. satır "AYLAR" + yıl sütunları, 3-14. satırlar OCAK..ARALIK). Gerçek
bültende ölçülen tuhaflık (sayfada BİRDEN ÇOK bülten bağlantısı olabiliyor
— eski bir dönemin bağlantısı DOM'da güncel bültenden ÖNCE geçebiliyor)
regresyon testi olarak sabitlenmiştir.
"""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pandas as pd
import pytest

from ingest.ktb import SAYFA, SHEET, TABAN, dosya_url, seri_cek

_AYLAR_TR = (
    "OCAK", "ŞUBAT", "MART", "NİSAN", "MAYIS", "HAZİRAN", "TEMMUZ",
    "AĞUSTOS", "EYLÜL", "EKİM", "KASIM", "ARALIK",
)


def _bulten_dataframe(yillar: list[int], degerler: dict[str, list[float | None]]) -> pd.DataFrame:
    """`degerler`: {ay_adi: [yıl1_değeri, yıl2_değeri, ...]} (None = yayımlanmamış)."""
    satirlar = [[None] * 6, [None, "YILLAR", None, None, "% DEĞİŞİM", None]]
    satirlar.append(["AYLAR", *yillar, "d1", "d2"][:6])
    for ay in _AYLAR_TR:
        degerlist = degerler.get(ay, [None] * len(yillar))
        satirlar.append([ay, *degerlist, None, None][:6])
    return pd.DataFrame(satirlar)


def _bulten_baytlari(yillar: list[int], degerler: dict[str, list]) -> bytes:
    df = _bulten_dataframe(yillar, degerler)
    tampon = BytesIO()
    with pd.ExcelWriter(tampon, engine="openpyxl") as yazici:
        df.to_excel(yazici, sheet_name=SHEET, header=False, index=False)
    return tampon.getvalue()


class SahteYanit:
    def __init__(self, content=b"", text="", status_code=200):
        self.content = content
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class SahteOturum:
    def __init__(self, sayfa_html: str, dosya_baytlar: dict[str, bytes]):
        self.sayfa_html = sayfa_html
        self.dosya_baytlar = dosya_baytlar
        self.calls: list[str] = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        if url == SAYFA:
            return SahteYanit(text=self.sayfa_html, status_code=200)
        return SahteYanit(content=self.dosya_baytlar[url], status_code=200)


def _fake_seri():
    return SimpleNamespace(id="turizm/yabanci-ziyaretci-sayisi")


# --- dosya_url ---


def test_dosya_url_tek_baglanti():
    html = '<a href="/Eklenti/150564,temm-z-2026-bultenixls.xls?0">güncel</a>'
    oturum = SahteOturum(html, {})
    assert dosya_url(session=oturum) == TABAN + "/Eklenti/150564,temm-z-2026-bultenixls.xls"


def test_dosya_url_en_buyuk_id_secilir():
    """Eski bir dönemin bağlantısı DOM'da güncelden ÖNCE geçebiliyor —
    ilk eşleşme değil, Eklenti ID'si en büyük olan alınmalı."""
    html = (
        '<a href="/Eklenti/125765,agustos-2024-sinir-bultenixls.xls?0"></a>'
        '<a href="/Eklenti/150564,temm-z-2026-bultenixls.xls?0">güncel</a>'
    )
    oturum = SahteOturum(html, {})
    assert dosya_url(session=oturum) == TABAN + "/Eklenti/150564,temm-z-2026-bultenixls.xls"


def test_dosya_url_baglanti_bulunamazsa_hata():
    oturum = SahteOturum("<html>boş</html>", {})
    with pytest.raises(RuntimeError, match="bağlantısı sayfada bulunamadı"):
        dosya_url(session=oturum)


# --- seri_cek: şablon kayması ---


def test_seri_cek_aylar_basligi_degismisse_hata():
    df = pd.DataFrame([[None] * 6] * 5)
    df.iat[2, 0] = "BEKLENMEYEN"
    tampon = BytesIO()
    with pd.ExcelWriter(tampon, engine="openpyxl") as yazici:
        df.to_excel(yazici, sheet_name=SHEET, header=False, index=False)
    url = TABAN + "/Eklenti/1,x.xls"
    oturum = SahteOturum('<a href="/Eklenti/1,x.xls">x</a>', {url: tampon.getvalue()})
    with pytest.raises(RuntimeError, match="şablonu değişmiş"):
        seri_cek(_fake_seri(), onbellek={}, session=oturum)


def test_seri_cek_ay_satiri_beklenmeyen_sirada_hata():
    baytlar = _bulten_baytlari([2025, 2026], {"OCAK": [100.0, 110.0]})
    # 3. veri satırını (index 3, ŞUBAT) bozarak sırayı kaydır
    df = pd.read_excel(BytesIO(baytlar), sheet_name=SHEET, header=None)
    df.iat[4, 0] = "BEKLENMEYEN_AY"
    tampon = BytesIO()
    with pd.ExcelWriter(tampon, engine="openpyxl") as yazici:
        df.to_excel(yazici, sheet_name=SHEET, header=False, index=False)
    url = TABAN + "/Eklenti/1,x.xls"
    oturum = SahteOturum('<a href="/Eklenti/1,x.xls">x</a>', {url: tampon.getvalue()})
    with pytest.raises(RuntimeError, match="ay satırı beklenmiyor"):
        seri_cek(_fake_seri(), onbellek={}, session=oturum)


# --- seri_cek: mutlu yol ---


def test_seri_cek_uc_yil_sutununu_aylik_seriye_cevirir():
    baytlar = _bulten_baytlari(
        [2024, 2025, 2026],
        {
            "OCAK": [2047027.0, 2171118.0, 2246639.0],
            "TEMMUZ": [7333812.0, 7116096.0, 7096564.0],
            "AĞUSTOS": [6825403.0, 6965343.0, None],  # 2026 Ağustos henüz yayımlanmamış
        },
    )
    url = TABAN + "/Eklenti/1,x.xls"
    oturum = SahteOturum('<a href="/Eklenti/1,x.xls">x</a>', {url: baytlar})
    df = seri_cek(_fake_seri(), onbellek={}, session=oturum)

    satirlar = dict(zip(df["date"], df["value"]))
    assert satirlar["2026-07-01"] == 7096564.0
    assert satirlar["2024-01-01"] == 2047027.0
    assert "2026-08-01" not in satirlar, "yayımlanmamış (None) hücre satır üretmemeli"


def test_seri_cek_onbellegi_bulteni_tek_kez_indirir():
    baytlar = _bulten_baytlari([2025, 2026], {"OCAK": [100.0, 110.0]})
    url = TABAN + "/Eklenti/1,x.xls"
    oturum = SahteOturum('<a href="/Eklenti/1,x.xls">x</a>', {url: baytlar})
    onbellek: dict = {}
    seri_cek(_fake_seri(), onbellek=onbellek, session=oturum)
    ilk_cagri = len(oturum.calls)
    seri_cek(_fake_seri(), onbellek=onbellek, session=oturum)
    assert len(oturum.calls) == ilk_cagri, "ikinci çağrı ağa çıkmamalı"
