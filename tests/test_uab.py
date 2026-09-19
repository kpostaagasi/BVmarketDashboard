"""UAB liman başkanlığı bazında yük elleçleme istemcisi testleri.

Bülten baytları pandas ile üretilir: gerçek dosyanın şablonu (0. satır
dosyanın dönemini taşıyan başlık metni — "..., Ocak 2026" ya da "...,
Ocak-Ağustos 2026" ya da yıl sonu bülteninde yalnızca "..., 2024"; 4.
satırda son sütun "Toplam Yük Elleçleme" başlığını taşır; 6. satırdan
itibaren "Liman Başkanlığı" satırları, ardından "Toplam / Total" satırı).
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from types import SimpleNamespace

import pandas as pd
import pytest
import requests

from ingest.uab import (
    GECMIS_YIL_SAYISI,
    _donem_coz,
    _donem_ve_deger,
    dosya_listesi,
    seri_cek,
)


def _bulten_dataframe(baslik: str, degerler: dict[str, float]) -> pd.DataFrame:
    satirlar = [[None] * 19 for _ in range(6)]
    satirlar[0][0] = baslik
    satirlar[4][18] = "Toplam Yük Elleçleme /\nTotal Cargo Handling"
    for ad, deger in degerler.items():
        satir = [None] * 19
        satir[0] = ad
        satir[18] = deger
        satirlar.append(satir)
    toplam_satir = [None] * 19
    toplam_satir[0] = "Toplam / Total"
    toplam_satir[18] = sum(degerler.values())
    satirlar.append(toplam_satir)
    return pd.DataFrame(satirlar)


def _bulten_baytlari(baslik: str, degerler: dict[str, float]) -> bytes:
    df = _bulten_dataframe(baslik, degerler)
    tampon = BytesIO()
    df.to_excel(tampon, header=False, index=False, engine="openpyxl")
    return tampon.getvalue()


def uab_seri(**kwargs):
    varsayilan = dict(id="denizcilik/aliaga-yuk-ellecleme", uab_liman="aliaga")
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


class SahteYanit:
    def __init__(self, content=b"", text="", status_code=200):
        self.content = content
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class SahteOturum:
    """Yıl alt sayfalarını (HTML) ve .xls dosyalarını URL'e göre ayırır."""

    def __init__(self, yil_html: dict[int, str], dosya_baytlar: dict[str, bytes],
                 eksik_yillar: set[int] = frozenset()):
        self.yil_html = yil_html
        self.dosya_baytlar = dosya_baytlar
        self.eksik_yillar = eksik_yillar
        self.calls: list[str] = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        if "/yuk-istatistikleri-" in url and url.rsplit("-", 1)[-1].isdigit():
            yil = int(url.rsplit("-", 1)[-1])
            if yil in self.eksik_yillar:
                return SahteYanit(status_code=404)
            return SahteYanit(text=self.yil_html.get(yil, ""), status_code=200)
        return SahteYanit(content=self.dosya_baytlar[url], status_code=200)


def _yil_sayfasi_html(yil: int, urls: list[str]) -> str:
    linkler = "".join(
        f'<a href="{u}">Liman Başkanlıkları Bazında Elleçleme</a>' for u in urls
    )
    return f"<html><body>{linkler}</body></html>"


# --- _donem_coz ---


def test_donem_coz_tek_ay():
    assert _donem_coz("Liman ... yük elleçleme istatistikleri, Ocak 2026\n") == (2026, 1)


def test_donem_coz_ay_araligi_son_ayi_alir():
    assert _donem_coz("...istatistikleri, Ocak-Ağustos 2026\n") == (2026, 8)


def test_donem_coz_ay_adi_yoksa_aralik_varsayilir():
    """Yıl tamamlandığında son bülten ay adı taşımaz — tam yıl (Aralık) kümülatifi."""
    assert _donem_coz("Liman ... yük elleçleme istatistikleri, 2024\n") == (2024, 12)


def test_donem_coz_yil_bulunamazsa_hata():
    with pytest.raises(RuntimeError, match="dönem çözülemedi"):
        _donem_coz("bilinmeyen başlık")


# --- _donem_ve_deger: şablon kayması ---


def test_donem_ve_deger_toplam_sutunu_bulunamazsa_hata():
    df = pd.DataFrame([[None] * 10 for _ in range(8)])
    df.iat[0, 0] = "..., Ocak 2026\n"
    df.iat[6, 0] = "Aliağa"
    df.iat[6, 5] = 1000.0
    tampon = BytesIO()
    df.to_excel(tampon, header=False, index=False, engine="openpyxl")
    with pytest.raises(RuntimeError, match="'Toplam Yük Elleçleme' sütunu bulunamadı"):
        _donem_ve_deger(tampon.getvalue(), "Aliağa")


def test_donem_ve_deger_liman_satiri_eksikse_hata():
    baytlar = _bulten_baytlari("..., Ocak 2026\n", {"Trabzon": 500.0})
    with pytest.raises(RuntimeError, match="'Aliağa' satırı yok"):
        _donem_ve_deger(baytlar, "Aliağa")


def test_donem_ve_deger_dogru_deger_ve_donemi_dondurur():
    baytlar = _bulten_baytlari("..., Mart 2026\n", {"Aliağa": 1234.5, "Trabzon": 10.0})
    yil, ay, deger = _donem_ve_deger(baytlar, "Aliağa")
    assert (yil, ay, deger) == (2026, 3, 1234.5)


# --- seri_cek: ardışık kümülatif fark ---


def test_seri_cek_ardisik_kumulatif_farki_aylik_akisa_cevirir():
    bugunku_yil = date.today().year
    url_ocak = f"https://denizcilikistatistikleri.uab.gov.tr/uploads/pages/yuk-istatistikleri-{bugunku_yil}/liman-baskanliklari-bazinda-yuk-ellecleme-aaa.xls"
    url_subat = f"https://denizcilikistatistikleri.uab.gov.tr/uploads/pages/yuk-istatistikleri-{bugunku_yil}/liman-baskanliklari-bazinda-yuk-ellecleme-bbb.xls"
    dosyalar = {
        url_ocak: _bulten_baytlari(f"..., Ocak {bugunku_yil}\n", {"Aliağa": 100.0, "Trabzon": 20.0}),
        url_subat: _bulten_baytlari(f"..., Ocak-Şubat {bugunku_yil}\n", {"Aliağa": 250.0, "Trabzon": 45.0}),
    }
    yil_html = {bugunku_yil: _yil_sayfasi_html(bugunku_yil, [url_ocak, url_subat])}
    oturum = SahteOturum(yil_html, dosyalar, eksik_yillar={y for y in range(bugunku_yil - GECMIS_YIL_SAYISI, bugunku_yil)})

    df = seri_cek(uab_seri(uab_liman="aliaga"), onbellek={}, session=oturum)
    satir_ocak = df[df["date"] == f"{bugunku_yil}-01-01"].iloc[0]
    satir_subat = df[df["date"] == f"{bugunku_yil}-02-01"].iloc[0]
    assert satir_ocak["value"] == 100.0
    assert satir_subat["value"] == 150.0  # 250 - 100


def test_seri_cek_farkli_liman_secimi_farkli_deger_dondurur():
    bugunku_yil = date.today().year
    url = f"https://denizcilikistatistikleri.uab.gov.tr/uploads/pages/yuk-istatistikleri-{bugunku_yil}/liman-baskanliklari-bazinda-yuk-ellecleme-ccc.xls"
    dosyalar = {url: _bulten_baytlari(f"..., Ocak {bugunku_yil}\n", {"Aliağa": 100.0, "Trabzon": 20.0, "Toplam / Total": 120.0})}
    yil_html = {bugunku_yil: _yil_sayfasi_html(bugunku_yil, [url])}
    oturum = SahteOturum(yil_html, dosyalar, eksik_yillar={y for y in range(bugunku_yil - GECMIS_YIL_SAYISI, bugunku_yil)})

    df_aliaga = seri_cek(uab_seri(uab_liman="aliaga"), onbellek={}, session=oturum)
    df_toplam = seri_cek(uab_seri(uab_liman="toplam"), onbellek={}, session=oturum)
    assert df_aliaga["value"].iloc[0] == 100.0
    assert df_toplam["value"].iloc[0] == 120.0


def test_seri_cek_eksik_yil_sayfasini_sessizce_atlar():
    """Bir önceki yılın alt sayfası kaldırılmışsa (404) o yıl atlanır,
    diğer yıllar etkilenmez."""
    bugunku_yil = date.today().year
    url = f"https://denizcilikistatistikleri.uab.gov.tr/uploads/pages/yuk-istatistikleri-{bugunku_yil}/liman-baskanliklari-bazinda-yuk-ellecleme-ddd.xls"
    dosyalar = {url: _bulten_baytlari(f"..., Ocak {bugunku_yil}\n", {"Aliağa": 100.0})}
    yil_html = {bugunku_yil: _yil_sayfasi_html(bugunku_yil, [url])}
    eksik = {y for y in range(bugunku_yil - GECMIS_YIL_SAYISI, bugunku_yil + 1)} - {bugunku_yil}
    oturum = SahteOturum(yil_html, dosyalar, eksik_yillar=eksik)

    df = seri_cek(uab_seri(uab_liman="aliaga"), onbellek={}, session=oturum)
    assert list(df["date"]) == [f"{bugunku_yil}-01-01"]


def test_seri_cek_onbellegi_dosya_baytlarini_paylasir():
    bugunku_yil = date.today().year
    url = f"https://denizcilikistatistikleri.uab.gov.tr/uploads/pages/yuk-istatistikleri-{bugunku_yil}/liman-baskanliklari-bazinda-yuk-ellecleme-eee.xls"
    dosyalar = {url: _bulten_baytlari(f"..., Ocak {bugunku_yil}\n", {"Aliağa": 100.0, "Trabzon": 20.0})}
    yil_html = {bugunku_yil: _yil_sayfasi_html(bugunku_yil, [url])}
    eksik = {y for y in range(bugunku_yil - GECMIS_YIL_SAYISI, bugunku_yil)}
    oturum = SahteOturum(yil_html, dosyalar, eksik_yillar=eksik)
    onbellek: dict = {}

    seri_cek(uab_seri(uab_liman="aliaga"), onbellek=onbellek, session=oturum)
    ilk_cagri = len(oturum.calls)
    seri_cek(uab_seri(uab_liman="trabzon"), onbellek=onbellek, session=oturum)
    assert len(oturum.calls) == ilk_cagri, "ikinci seri yıl sayfasını/dosyayı yeniden indirmemeli"


def test_dosya_listesi_http_hatasi_yukselir():
    oturum = SahteOturum({}, {}, eksik_yillar={2019})
    with pytest.raises(requests.HTTPError, match="HTTP 404"):
        dosya_listesi(2019, session=oturum)
