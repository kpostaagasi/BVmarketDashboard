"""BOTAŞ doğal gaz toptan satış fiyat tarifesi istemcisi.

Kaynak: `https://www.botas.gov.tr/Sayfa/satis-fiyat-tarifesi/439` — BOTAŞ'ın
"güncel tarife" İNDEKS sayfası. Bu sayfanın KENDİSİ tarife tablosunu
TAŞIMAZ (ölçüldü) — yalnızca yürürlükteki tarife duyurusuna bir küçük
resim/bağlantı kartı gösterir (`/Sayfa/4-nisan-2026-tarihinden-itibaren-
gecerli-botas-dogal-gaz-toptan-satis-fiyat-tarifesi/812` gibi tarihli bir
URL'e). BOTAŞ her yeni tarife yayımladığında BU bağlantıyı günceller (İNDEKS
URL'i /439 sabit kalır); adaptör bu yüzden ÖNCE /439'u çekip güncel tarihli
bağlantıyı bulur, SONRA o sayfadaki tabloyu okur — böylece kod değişmeden
her yeni tarifeyi otomatik takip eder.

**Tarihsel arşiv YOK (ölçüldü 2026-09-18).** BOTAŞ'ın "Duyurular" kategorisi
(`/Kategori/duyurular/2`, 10 sayfa `?sira=N` ile paylandırılmış) taranan
TÜM sayfalarında tek bir tarife duyurusu bile yok (yalnızca personel/basın
açıklamaları); "Tarifeler" alt menüsünde ve /439 sayfasının kendisinde
GEÇMİŞ tarife sürümlerine bağlantı yok (yalnızca güncel olana); site içi
arama ucu (`/Arama/?key=...`) istek zaman aşımına uğruyor (>300 sn, iki
farklı sorguyla denendi). Bu yüzden `seri_cek` yalnızca ŞU AN yürürlükteki
tek noktayı döner — sahte geçmiş nokta ÜRETİLMEZ. BOTAŞ her tarife
değiştirdiğinde bu adaptör bir sonraki ingest koşusunda otomatik yeni
değeri yakalar; seri zamanla gerçek (uydurma olmayan) çok noktalı bir
tarihçeye dönüşür.

Dated sayfa iki ayrı tarife tablosu taşıyor: "Dağıtım Şirketleri İçin..."
ve "...Organize Sanayi Bölgeleri ve Serbest Tüketiciler İçin...". Referans
kartı ("Dağıtım Şirketlerine Uygulanan Tarife") yalnızca BİRİNCİYİ
kapsıyor — `_dagitim_bolumu` bu yüzden ikinci başlıktan önceki metni keser.

Referans doğrulaması (ölçüldü 2026-09-18): Konut Kademe-1 10,625 TL/Sm³,
botas_dogalgaz_tarifesi.html'in "Konut (Mesken) Tüketici Fiyatı" kartıyla
BİREBİR eşleşti.
"""

from __future__ import annotations

import html as html_modul
import re

import pandas as pd
import requests

from core.catalog import GECERLI_BOTAS_KATEGORILERI, Seri

INDEKS_URL = "https://www.botas.gov.tr/Sayfa/satis-fiyat-tarifesi/439"
ZAMAN_ASIMI = 60

TAM_AY_ADLARI = {
    "Ocak": 1, "Şubat": 2, "Mart": 3, "Nisan": 4, "Mayıs": 5, "Haziran": 6,
    "Temmuz": 7, "Ağustos": 8, "Eylül": 9, "Ekim": 10, "Kasım": 11, "Aralık": 12,
}

_BASLIK_RE = re.compile(
    r"(\d{1,2})\s+(" + "|".join(TAM_AY_ADLARI) + r")\s+(\d{4})\s+Tarihinden İtibaren Geçerli"
)
_SATIR_RE = re.compile(
    r"<strong>([^<]+)</strong>.*?"
    r"(?:<center>|<div[^>]*>)\s*([\d.,]+)\s*(?:</center>|</div>)",
    re.S,
)
_IKINCI_BOLUM_BASLANGICI = "Organize Sanayi B"  # "Bölgeleri" — &ouml; entity'siz de eşleşsin diye kısa
_GUNCEL_LINK_RE = re.compile(
    r'href="(https://www\.botas\.gov\.tr/Sayfa/[a-z0-9\-]*tarihinden-itibaren-gecerli[a-z0-9\-]*/\d+)"',
    re.I,
)


def guncel_tarife_url(indeks_html: str) -> str:
    """/439 indeks sayfasından güncel tarihli tarife duyurusunun URL'ini bulur."""
    eslesme = _GUNCEL_LINK_RE.search(indeks_html)
    if eslesme is None:
        raise RuntimeError("BOTAŞ: indeks sayfasında güncel tarife bağlantısı bulunamadı")
    return eslesme.group(1)


def yururluk_tarihi(html: str) -> str:
    """Sayfa başlığından yürürlük tarihini `YYYY-MM-DD` olarak çıkarır."""
    metin = html_modul.unescape(html)
    eslesme = _BASLIK_RE.search(metin)
    if eslesme is None:
        raise RuntimeError("BOTAŞ: sayfa başlığından yürürlük tarihi okunamadı")
    gun, ay_adi, yil = eslesme.groups()
    return f"{yil}-{TAM_AY_ADLARI[ay_adi]:02d}-{int(gun):02d}"


def _dagitim_bolumu(html: str) -> str:
    """Yalnızca 'Dağıtım Şirketleri' tablosunu (ikinci OSB tablosundan önce) döner."""
    metin = html_modul.unescape(html)
    bitis = metin.find(_IKINCI_BOLUM_BASLANGICI)
    return metin[:bitis] if bitis > 0 else metin


def _kategori_belirle(etiket: str) -> str | None:
    e = " ".join(etiket.split())  # &nbsp;/çoklu boşluk sadeleştir
    if "Konut" in e and "Kademe-1" in e:
        return "konut"
    if "Şehit Ailesi" in e or "Muharip" in e:
        return "sehit-ailesi"
    if "Ekmek" in e:
        return "ekmek-ureticileri"
    if "Amaçlı Kullanım" in e:
        return "elektrik-uretimi-amacli"
    if "Dışındaki" in e:
        return "elektrik-uretimi-disi"
    return None


def kategori_fiyatlarini_cikar(html: str) -> dict[str, float]:
    """`{botas_kategori: TL/Sm3}` — GECERLI_BOTAS_KATEGORILERI'nin alt kümesi
    (CNG/Kademe-2 gibi kapsam dışı satırlar sessizce atlanır)."""
    bolum = _dagitim_bolumu(html)
    sonuc: dict[str, float] = {}
    for etiket, deger in _SATIR_RE.findall(bolum):
        kategori = _kategori_belirle(etiket)
        if kategori is None or kategori in sonuc:
            continue
        sonuc[kategori] = float(deger.strip().replace(".", "").replace(",", "."))
    return sonuc


def tarifeyi_cek(session=None) -> dict:
    http = session or requests
    indeks = http.get(INDEKS_URL, timeout=ZAMAN_ASIMI)
    if indeks.status_code != 200:
        raise RuntimeError(f"BOTAŞ indeks sayfası HTTP {indeks.status_code}")
    detay_url = guncel_tarife_url(indeks.text)

    detay = http.get(detay_url, timeout=ZAMAN_ASIMI)
    if detay.status_code != 200:
        raise RuntimeError(f"BOTAŞ detay sayfası HTTP {detay.status_code} ({detay_url})")
    html = detay.text
    return {"tarih": yururluk_tarihi(html), "kategoriler": kategori_fiyatlarini_cikar(html)}


def seri_cek(seri: Seri, onbellek: dict | None = None, session: requests.Session | None = None) -> pd.DataFrame:
    """Tek nokta döner: şu an yürürlükteki tarife (bkz. modül docstring'i —
    kaynakta erişilebilir bir tarihsel arşiv yok)."""
    if onbellek is None:
        onbellek = {}
    if "tarife" not in onbellek:
        onbellek["tarife"] = tarifeyi_cek(session=session)
    tarife = onbellek["tarife"]

    deger = tarife["kategoriler"].get(seri.botas_kategori)
    if deger is None:
        raise RuntimeError(
            f"BOTAŞ: '{seri.botas_kategori}' kategorisi tarife sayfasında bulunamadı "
            f"(bulunanlar: {sorted(tarife['kategoriler'])})"
        )
    return pd.DataFrame([(tarife["tarih"], deger)], columns=["date", "value"])
