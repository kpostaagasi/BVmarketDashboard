"""TEPAV Gıda Fiyat Endeksi (TEGE) aylık bülten istemcisi.

Kaynak gerçekleri 2026-09-18'de canlı ölçüldü:

- TEPAV, TEGE'yi ayrı bir Excel/CSV veri seti olarak YAYIMLAMIYOR — her ay
  5 sayfalık bir PDF "bülten" (`files.tepav.org.tr/upload/files/...TEGE<Ay>
  <Yıl>.pdf`) ve aynı içeriği anlatan bir haber sayfası
  (`tepav.org.tr/tr/haberler/s/<id>`) yayımlıyor. Bülten PDF'inin metin
  katmanında üç rakam DÜZ METİN olarak geçiyor (taranmış görsel değil):
  "aylık gıda enflasyonu yüzde X,XX olarak hesaplandı", "yıllık gıda
  enflasyonu ... yüzde XX,X ... hesaplanmıştır", "KKTC-TEGE kapsamında ...
  aylık gıda enflasyonu yüzde X,XX olarak hesaplandı" — haber sayfasının
  gövde metninde AYNI cümleler birebir tekrarlanıyor, bu yüzden PDF
  indirmeye gerek yok, haber sayfası HTML'i yeterli. Çok aylık geçmiş
  (Şekil 1/5 grafikleri) yalnızca GÖRSEL olarak çizili — bülten içinde
  ayrı bir sayısal tablo/CSV YOK, geçmiş yalnızca ay ay bülten
  taranarak inşa edilebilir (bu adaptörün yaptığı).
- Toplu bir indeks/API YOK: "Bültenler" hub sayfası
  (`tepav.org.tr/tr/calismalarimiz/s/470`) yalnızca YIL bazlı alt
  sayfalara bağlantı verir (`.../s/492`=2026, `/s/484`=2025, `/s/471`=2024
  — ölçüldü); HER YIL SAYFASI o yılın haber bağlantılarını listeler. 2023
  (TEGE Eylül 2023'te başladı) için hub sayfasında bağlantı YOK — TEPAV'ın
  kendi navigasyonu 2024 öncesine gitmiyor, bu adaptör de gidemiyor (ölçüm
  sınırı, sessizce atlanmıyor — yalnızca keşfedilebilen ay noktaları
  üretilir).
- Dönem, "İlgili Yayın Dosyaları" bölümünün bağlantı METNİNDEN DEĞİL —
  bu metin bültenden bültene tutarsız (bazı aylarda "TEPAV Gıda Fiyat
  Endeksi (TEGE) - Ağustos 2026" biçiminde, bazılarında (ör. Mart 2026)
  hiç yok, yalnızca ikon var, ölçüldü) — PDF DOSYA ADINDAN okunur: her
  bülten linki `...TEGE[_]?<Ay>[_]?<Yıl>.pdf` kalıbını taşır (ör.
  `TEGEAgustos2026.pdf`, `TEGE_Mart_2026.pdf` — alt çizgi kullanımı
  tutarsız ama TEGE+ay+yıl+.pdf sırası sabit). Ay adı PDF dosya adında
  bazen Türkçe aksansız gelir (`Agustos`, `Subat`) — `AY_NO` ikisini de
  tanır.
- Ölçüldü (2026-09-18, referans marketvisuals.net/tepav_tege.html ile
  birebir): Ağustos 2026 — TEGE aylık %1,07, TEGE yıllık %30,9,
  KKTC-TEGE aylık %2,72.
"""

from __future__ import annotations

import re

import pandas as pd
import requests

TABAN = "https://www.tepav.org.tr"
HUB_URL = f"{TABAN}/tr/calismalarimiz/s/470"
ZAMAN_ASIMI = 60
_BASLIKLAR = {"User-Agent": "Mozilla/5.0"}

_HABER_BAGLANTISI = re.compile(r'href="(?:https://www\.tepav\.org\.tr)?(/tr/haberler/s/\d+)"')
_YAYIN_DOSYASI_DONEMI_AD = re.compile(
    r"TEGE_?([A-Za-zçğıöşüÇĞİÖŞÜ]+?)_?\d{0,4}\.pdf", re.IGNORECASE
)
_YAYIN_DOSYASI_DONEMI_NO = re.compile(r"TEGE_?(\d{2})(?:_?\d{4})?\.pdf")
_BOSLUK = r"(?:\s|&nbsp;|\\u0026nbsp;)+"
_TEGE_AYLIK = re.compile(
    r"aylık gıda enflasyonu(?:nu)?" + _BOSLUK + r"yüzde" + _BOSLUK
    + r"(-?[\d,]+)" + _BOSLUK + r"(?:olarak hesapland|art|olarak ölçül)"
)
_TEGE_YILLIK = re.compile(r"yıllık gıda enflasyonu[^.]*?yüzde" + _BOSLUK + r"(-?[\d,]+)")
_KKTC_TEGE_AYLIK = re.compile(
    r"KKTC-TEGE kapsamında[^.]*?aylık gıda enflasyonu" + _BOSLUK + r"yüzde" + _BOSLUK
    + r"(-?[\d,]+)" + _BOSLUK + r"(?:olarak hesapland|art|olarak ölçül)"
)

# PDF dosya adları Türkçe aksanları bazen düşürür (ör. "Ağustos" ->
# "Agustos", "Şubat" -> "Subat") — hem aksanlı hem ASCII biçim burada.
AY_NO = {
    "ocak": "01", "şubat": "02", "subat": "02", "mart": "03", "nisan": "04",
    "mayıs": "05", "mayis": "05", "mays": "05", "haziran": "06", "temmuz": "07",
    "ağustos": "08", "agustos": "08", "eylül": "09", "eylul": "09",
    "ekim": "10", "kasım": "11", "kasim": "11", "aralık": "12", "aralik": "12",
}
METRIK_DESENLERI = {
    "tege-aylik": _TEGE_AYLIK,
    "tege-yillik": _TEGE_YILLIK,
    "kktc-tege-aylik": _KKTC_TEGE_AYLIK,
}


def _yuzde_parse(ham: str) -> float:
    return float(ham.replace(".", "").replace(",", "."))


def _get(url: str, session=None) -> str:
    http = session or requests
    yanit = http.get(url, headers=_BASLIKLAR, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"TEPAV: {url} HTTP {yanit.status_code}")
    return yanit.text


def yil_sayfalarini_bul(hub_html: str) -> dict[int, str]:
    """Hub sayfasındaki yıl bağlantılarından `{yıl: yol}` çıkarır.

    Gerçek HTML `<a href="https://www.tepav.org.tr/tr/calismalarimiz/
    s/492">...<strong>2026</strong>...</a>` biçimindedir (mutlak URL,
    yıl metni birkaç iç içe etiket sonra gelir) — markdown DEĞİLDİR.
    Dönen yol her zaman GÖRELİDİR (mutlak URL'nin TABAN'dan sonrası),
    `haber_baglantilarini_bul` ile aynı biçimde kullanılabilsin diye.
    """
    sonuc: dict[int, str] = {}
    desen = re.compile(
        r'href="([^"]*calismalarimiz/s/\d+)"[^>]*>.{0,120}?<strong>(\d{4})</strong>',
        re.DOTALL,
    )
    for href, yil in desen.findall(hub_html):
        yol = href[len(TABAN):] if href.startswith(TABAN) else href
        sonuc[int(yil)] = yol
    return sonuc


def haber_baglantilarini_bul(yil_html: str) -> list[str]:
    """Bir yıl sayfasındaki tüm haber bağlantılarını (yol) döner."""
    return sorted(set(_HABER_BAGLANTISI.findall(yil_html)))


def haberden_noktalari_cikar(haber_html: str, yil: int) -> tuple[str, dict[str, float]] | None:
    """Bir haber sayfasından `(tarih, {metrik: değer})` çıkarır.

    `yil` çağıran tarafından (hangi yıl sayfasından geldiğinden) verilir —
    PDF dosya adı her zaman yıl taşımıyor (bkz. modül docstring'i, ör.
    "TEGE07.pdf"). Ay, PDF dosya adından İKİ olası kalıpla okunur: önce ay
    ADI (çoğu bülten), sonra 2 haneli ay NUMARASI (bazı bültenler, ör.
    Temmuz 2026). İkisi de bulunamazsa None döner — çağıran bu haberi
    atlar (yeni bülten şablonu kırılmaz, sessizce eksik veri üretmez:
    `seri_cek` en az bir nokta bulunmazsa zaten hata verir).
    """
    ay_no = None
    ad_eslesme = _YAYIN_DOSYASI_DONEMI_AD.search(haber_html)
    if ad_eslesme:
        ay_no = AY_NO.get(ad_eslesme.group(1).casefold())
    if ay_no is None:
        no_eslesme = _YAYIN_DOSYASI_DONEMI_NO.search(haber_html)
        if no_eslesme and 1 <= int(no_eslesme.group(1)) <= 12:
            ay_no = no_eslesme.group(1)
    if ay_no is None:
        return None
    tarih = f"{yil}-{ay_no}-01"

    degerler: dict[str, float] = {}
    for metrik, desen in METRIK_DESENLERI.items():
        eslesme = desen.search(haber_html)
        if eslesme:
            degerler[metrik] = _yuzde_parse(eslesme.group(1))
    if not degerler:
        return None
    return tarih, degerler


def _tum_noktalari_getir(onbellek: dict, session=None) -> list[tuple[str, dict[str, float]]]:
    if "noktalar" in onbellek:
        return onbellek["noktalar"]

    hub_html = _get(HUB_URL, session=session)
    yil_sayfalari = yil_sayfalarini_bul(hub_html)
    if not yil_sayfalari:
        raise RuntimeError("TEPAV: hub sayfasında yıl bağlantısı bulunamadı — şablon değişmiş olabilir")

    noktalar: list[tuple[str, dict[str, float]]] = []
    for yil, yol in yil_sayfalari.items():
        yil_html = _get(f"{TABAN}{yol}", session=session)
        for haber_yolu in haber_baglantilarini_bul(yil_html):
            haber_html = _get(f"{TABAN}{haber_yolu}", session=session)
            sonuc = haberden_noktalari_cikar(haber_html, yil)
            if sonuc is not None:
                noktalar.append(sonuc)

    if not noktalar:
        raise RuntimeError("TEPAV: hiçbir bültenden veri noktası çıkarılamadı")
    onbellek["noktalar"] = noktalar
    return noktalar


def seri_cek(seri, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `onbellek` verilirse hub + tüm yıl/haber sayfaları koşu boyunca bir kez
    indirilir; 3 TEPAV serisi (tege-aylik/tege-yillik/kktc-tege-aylik) aynı
    taramayı paylaşır.
    """
    onbellek = {} if onbellek is None else onbellek
    metrik = seri.tepav_seri
    if metrik not in METRIK_DESENLERI:
        raise RuntimeError(f"TEPAV: {seri.id} — bilinmeyen tepav_seri {metrik!r}")

    noktalar = _tum_noktalari_getir(onbellek, session=session)
    veri = [
        (tarih, degerler[metrik]) for tarih, degerler in noktalar if metrik in degerler
    ]
    if not veri:
        raise RuntimeError(f"TEPAV: {seri.id} için hiç veri noktası bulunamadı")

    df = (
        pd.DataFrame(veri, columns=["date", "value"])
        .drop_duplicates(subset="date", keep="last")
        .sort_values("date")
        .reset_index(drop=True)
    )
    if seri.start_date:
        df = df[df["date"] >= seri.start_date].reset_index(drop=True)
    return df
