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

**Tarihsel arşiv: HTML'de YOK, PDF'lerde VAR (ölçüldü 2026-09-29).** BOTAŞ'ın
"Tarifeler" alt menüsünde ve /439'da GEÇMİŞ tarife HTML'lerine bağlantı yok;
eski duyuru sayfaları (`/Sayfa/<tarihli-slug>/<id>`, ör. 2024-02 → /600) içeriği
SİLİNMİŞ — HTTP 200 dönüyor ama gövde boş ("4/5" breadcrumb), yani soft-404.
Ancak her tarifenin PDF'i BOTAŞ'ın KENDİ dosya deposunda
(`/uploads/dosyaYoneticisi/<id>-<slug>.pdf`) kalıcı duruyor ve HTTP 200 veriyor.
Depo dizin listelemesi 403 döndürüyor, site içi arama ucu zaman aşımına uğruyor
ve HİÇBİR BOTAŞ sayfası bu PDF'leri listelemiyor — bu yüzden dosya adları
`TARIFE_PDFLERI`'ne elle yazıldı (21 dosya, tek tek doğrulandı). 2021-03 ve
2021-11 PDF'leri görüntü taraması (metin katmanı 0 karakter) — listede yoklar.

Ad teşhisi canlı yapıldı: güncel duyuru sayfası (/Sayfa/.../812) tarife PDF'ini
`/uploads/dosyaYoneticisi/139364-4-nisan_2026_tarife.pdf` olarak bağlantılar —
`nisan` ile `2026` arasında TİRE var. Bu dosya adı listenin en sonunda TİRE
yazılmamış haliyle duruyordu ve soft-404 üretiyordu (bkz. aşağıdaki tuzak).

**Soft-404 tuzağı (ölçüldü 2026-09-30) — PDF okuyan her kaynakta geçerli.**
BOTAŞ'ın dosya deposu yanlış/eksik dosya adında **HTTP 200 + `text/html` ana
sayfa** gövdesi döndürüyor. Yalnızca `status_code` kontrol eden kod bunu
GEÇERİR; `pdfplumber` 65 KB HTML'de ya patlar ya dakikalarca asılı kalır ve
arşiv sessizce boş küme üretir — CSV'ye yalnızca güncel tarife noktası yazılır
(n=1). `_pdf_icerigi` bu yüzden `Content-Type: application/pdf` + `%PDF` gövde
başı olmadan PDF saymaz ve dosya adını hatırlatan bir hata yükseltir. Aynı
"200 = PDF" varsayımı `osd`/`mkk` gibi PDF kullanan diğer kaynaklarda da
susuz çalışıyorsa aynı düzeltme gerekir.

`seri_cek` bu yüzden İKİ kaynağı birleştirir: (a) /439 → güncel tarihli duyuru
HTML'i, kod değişmeden YENİ tarifeleri otomatik takip eder; (b) dondurulmuş PDF
arşivi, geçmişi verir. Örtüştükleri 4 Nisan 2026 tarifesinde ikisi BEŞİ DE
aynı: konut 10,625 · şehit 5,3125 · ekmek 10,395938 · el-amaclı 18 · el-dışı 18.

PDF arşivi üç farklı tablo düzeni taşıyor (hepsi pdfplumber `extract_text()`):
- **2020-2021** "Konut" satırı YOK; karşılığı "Serbest Olmayan Tüketici /
  (Abone)" — `Serbest Olmayan Tüketici <fiyat> (Abone)`. Elektrik fiyatları
  "Kademe 1 <dışı> <dışı_kwh> <amaçlı> <amaçlı_kwh>" satırında. Ekmek/şehit
  bu dönemde yok.
- **2022-2024** konut etiketi satır KIRILMIŞ ("Konut Tüketicileri (Evsel" /
  "Tüketiciler) 4,080634"); düzleştirilmiş metinde `Tüketiciler) <fiyat>`
  yakalanır. Elektrik yine `Kademe 1` satırında. Ekmek/şehit yok.
- **2025+** konut tek satırda; elektrik ve ekmek AÇIK etiketli ("Elektrik
  Üretim Amacı Dışındaki Kullanım <fiyat> ..."). Şehit 2025-07'de belirdi
  ve etiketi YINE kırık ("Şehit Ailesi ... Olan Konut" / "3,885895" /
  "Tüketicileri (Evsel Tüketiciler)") — düzleştirmede `Gazi Olan Konut <fiyat>`
  olarak yakalanır. 2026'da konut ayrıca "Kademe-1"/"Kademe-2" ayrımına
  geçti; katalogdaki `konut` = Kademe-1 (HTML referansıyla doğrulandı).

`Kademe 1` satırının 1. ve 3. sütunu, 2025+ etiketlerinin verdiği iki elektrik
fiyatıyla ÇAPRAZ doğrulandı (2025-03: etiket 11,380913/12,000000 = Kademe 1'in
o satırları), bu yüzden eski düzenler de aynı iki kategoriye yazılır.


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
from io import BytesIO

import pandas as pd
import pdfplumber
import requests

from core.catalog import GECERLI_BOTAS_KATEGORILERI, Seri

INDEKS_URL = "https://www.botas.gov.tr/Sayfa/satis-fiyat-tarifesi/439"
DOSYA_TABANI = "https://www.botas.gov.tr/uploads/dosyaYoneticisi"
ZAMAN_ASIMI = 60

# Geçmiş tarife PDF'leri. BOTAŞ bunları hiçbir sayfada listelemiyor (depo dizin
# listelemesi 403, arama ucu zaman aşımı) ve eski duyuru sayfaları soft-404 —
# dosya adları bu yüzden ölçülmüş, elle sabitlenmiştir. 2021-03 ve 2021-11
# PDF'leri görüntü taraması (metin katmanı boş) bilinçli olarak yok.
#
# **TÜZEL TUZAK — soft-404 (ölçüldü 2026-09-30).** Dosya deposu yanlış/eksik
# adda HTTP 200 + `text/html` ANA SAYFA gövdesi döndürüyor; PDF değil. Tek
# yanlışlı örnek: `139364-4-nisan-2026_tarife.pdf` (tire yerine alt çizgi) →
# 65852 bayt HTML. Yalnızca `status_code` kontrol eden kod bunu GEÇER ve
# pdfplumber 65 KB HTML'de ya patlar ya dakikalarca asılı kalır — arşiv
# sessizce boş küme üretip CSV'ye yalnızca güncel noktayı yazar. `_pdf_icerigi`
# bu yüzden PDF olmayan gövdeyi İŞARETİYLE reddeder. Aynı tuzak `osd`/`mkk`
# gibi PDF okuyan diğer kaynaklarda da geçerli.
#
# Doğru ad DİKKAT: 2026-04 PDF'i duyuru sayfasından (/Sayfa/.../812) bağlantı
# olarak okundu — `nisan` ve `2026` arasında TİRE vardir. 2026-09-30'da 21
# dosyanın 21'i de `application/pdf` + `%PDF-` ile doğrulandı.
TARIFE_PDFLERI = (
    "958090-mayis_2020_tarifesi_29042020.pdf",
    "551538-temmuz_2020_tarifesi_29062020.pdf",
    "2285-ekim_2020_tarifesi_28092020.pdf",
    "597667-ocak_2021_tarifesi_31122020.pdf",
    "10212-ubat_2022_tarifesi.pdf",
    "333970-mart_2022_tarifesi.pdf",
    "666177-nisan_2022_tarifesi.pdf",
    "435696-mayis_2022_tarifesi_v2.pdf",
    "265942-haziran_2022_tarifesi.pdf",
    "551551-temmuz_2022_tarifesi.pdf",
    "949372-agustos_2022_tarifesi.pdf",
    "134057-ekim_2022_tarifesi.pdf",
    "791347-kasim_2022_tarifesi.pdf",
    "161300-aralik_2022_tarifesi.pdf",
    "572108-mart_2023_tarifesi.pdf",
    "768642-ubat_2023_tarifesi.pdf",
    "410797-ubat_2024_tarifesi.pdf",
    "611215-mart_2025_tarifesi.pdf",
    "169807-5-nisan_2025_tarifesi.pdf",
    "128513-2_temmuz_2025_tarifesi.pdf",
    "139364-4-nisan_2026_tarife.pdf",
)

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

# --- PDF arşivi (2020-2026) desenleri -------------------------------------
# PDF başlığı iki biçimde geliyor: "2022 Yılı Şubat Ayı ..." (ayın 1'i) ve
# "5 Nisan 2025 Tarihinden İtibaren Geçerli ..." (gerçek yürürlük günü).
_PDF_YIL_AY_RE = re.compile(
    r"(\d{4})\s+Yılı\s+(" + "|".join(TAM_AY_ADLARI) + r")\s+Ayı"
)
_PDF_KONUT_RE = re.compile(
    r"Konut Tüketicileri \(Evsel Tüketiciler\)(?: Kademe-1)?\s+([\d,]+)"
)
# 2022-2024: etiket iki biçimde kırılıyor — "(Evsel 1,860118 Tüketiciler)"
# (2022-02..04) ve "2,511159 (Evsel Tüketiciler)" (2022-05..08) ve
# "Tüketiciler) 4,080634" (2022-10+).
_PDF_KONUT_KIRIK_RE = re.compile(
    r"Konut Tüketicileri (?:\(Evsel ([\d,]+) Tüketiciler\)|([\d,]+) \(Evsel Tüketiciler\)|\(Evsel Tüketiciler\) ([\d,]+))"
)
_PDF_ABONE_RE = re.compile(r"Serbest Olmayan Tüketici\s+([\d,]+)")  # 2020-2021
_PDF_KONUT_DESENLERI = (_PDF_KONUT_RE, _PDF_KONUT_KIRIK_RE, _PDF_ABONE_RE)
_PDF_SEHIT_RE = re.compile(r"Gazi Olan Konut\s+([\d,]+)")
_PDF_EKMEK_RE = re.compile(r"Ekmek Üreticileri\s+([\d,]+)")
_PDF_ELEKTRIK_RE = re.compile(
    r"Elektrik Üretim Amacı Dışındaki Kullanım\s+([\d,]+).*?"
    r"Elektrik Üretimi Amaçlı Kullanım\s+([\d,]+)",
    re.S,
)
# 2020-2024'te elektrik fiyatları etiketsiz "Kademe 1" satırında:
# <dışı> <dışı_kwh> <amaçlı> <amaçlı_kwh>. 2025+ etiketleriyle çapraz doğrulandı.
_PDF_KADEME_RE = re.compile(r"Kademe 1\s+([\d,]+)\s+[\d,]+\s+([\d,]+)")


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


def _sayi(ham: str) -> float:
    return float(ham.replace(".", "").replace(",", "."))


def pdf_yururluk_tarihi(metin: str) -> str:
    """PDF'in ilk satırından yürürlük tarihini `YYYY-MM-DD` olarak çıkarır.

    "5 Nisan 2025 Tarihinden İtibaren Geçerli" → gerçek gün (05-04-2025);
    "2022 Yılı Şubat Ayı" → ayın 1'i (2022-02-01), çünkü PDF günü yazmıyor.
    """
    duz = re.sub(r"\s+", " ", metin)
    eslesme = _BASLIK_RE.search(duz)
    if eslesme is not None:
        gun, ay_adi, yil = eslesme.groups()
        return f"{yil}-{TAM_AY_ADLARI[ay_adi]:02d}-{int(gun):02d}"
    eslesme = _PDF_YIL_AY_RE.search(duz)
    if eslesme is None:
        raise RuntimeError("BOTAŞ: tarife PDF'inden yürürlük tarihi okunamadı")
    yil, ay_adi = eslesme.groups()
    return f"{yil}-{TAM_AY_ADLARI[ay_adi]:02d}-01"


def pdf_kategori_fiyatlari(metin: str) -> dict[str, float]:
    """PDF metninden `{botas_kategori: TL/Sm3}` (bkz. modül docstring'i).

    PDF'ler 2020-2026 arasında üç farklı tablo düzeni taşıyor; her düzen için
    ayrı regex var ve döneminde VAR OLMAYAN kategoriler (2020-2024'te ekmek ve
    şehit) sonuçta YOKTUR — uydurulmaz.
    """
    duz = re.sub(r"\s+", " ", metin)
    sonuc: dict[str, float] = {}

    for desen in _PDF_KONUT_DESENLERI:
        eslesme = desen.search(duz)
        if eslesme is None:
            continue
        ham = next((g for g in eslesme.groups() if g), None)
        if ham is not None:
            sonuc["konut"] = _sayi(ham)
        break

    eslesme = _PDF_SEHIT_RE.search(duz)
    if eslesme is not None:
        sonuc["sehit-ailesi"] = _sayi(eslesme.group(1))

    eslesme = _PDF_EKMEK_RE.search(duz)
    if eslesme is not None:
        sonuc["ekmek-ureticileri"] = _sayi(eslesme.group(1))

    eslesme = _PDF_ELEKTRIK_RE.search(duz)
    if eslesme is not None:
        sonuc["elektrik-uretimi-disi"] = _sayi(eslesme.group(1))
        sonuc["elektrik-uretimi-amacli"] = _sayi(eslesme.group(2))
    else:
        eslesme = _PDF_KADEME_RE.search(duz)
        if eslesme is not None:
            sonuc["elektrik-uretimi-disi"] = _sayi(eslesme.group(1))
            sonuc["elektrik-uretimi-amacli"] = _sayi(eslesme.group(2))
    return sonuc


def _pdf_icerigi(yanit, url: str) -> bytes:
    """Soft-404'u reddedip PDF baytlarını döner (bkz. `TARIFE_PDFLERI` notu).

    BOTAŞ dosya deposu yanlış dosya adında HTTP 200 + `text/html` ana sayfa
    döndürür. Yalnızca `status_code` kontrolü bu tuzağı kaçırır; iki sinyal
    birlikte aranır: `Content-Type: application/pdf` VE gövdenin `%PDF` ile
    başlaması.
    """
    icerik_tip = (yanit.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if icerik_tip != "application/pdf" or not yanit.content.startswith(b"%PDF"):
        raise RuntimeError(
            f"BOTAŞ tarife PDF'i değil (Content-Type: {icerik_tip or 'yok'}, "
            f"gövde başı: {yanit.content[:5]!r}) — dosya adı büyük olasılıkla "
            f"yanlış, soft-404 sayfası geldi: {url}"
        )
    return yanit.content


def arsiv_tarifeleri_cek(onbellek: dict, session=None) -> dict[str, dict[str, float]]:
    """`{YYYY-MM-DD: {botas_kategori: TL/Sm3}}` — `TARIFE_PDFLERI` arşivinden."""
    http = session or requests
    if "arsiv" not in onbellek:
        noktalar: dict[str, dict[str, float]] = {}
        for dosya_adi in TARIFE_PDFLERI:
            url = f"{DOSYA_TABANI}/{dosya_adi}"
            yanit = http.get(url, timeout=ZAMAN_ASIMI)
            if yanit.status_code != 200:
                raise RuntimeError(f"BOTAŞ tarife PDF'i HTTP {yanit.status_code} ({url})")
            with pdfplumber.open(BytesIO(_pdf_icerigi(yanit, url))) as pdf:
                metin = "\n".join(sayfa.extract_text() or "" for sayfa in pdf.pages)
            noktalar[pdf_yururluk_tarihi(metin)] = pdf_kategori_fiyatlari(metin)
        onbellek["arsiv"] = noktalar
    return onbellek["arsiv"]


def seri_cek(seri: Seri, onbellek: dict | None = None, session: requests.Session | None = None) -> pd.DataFrame:
    """Yürürlükteki tarife + PDF arşivindeki geçmiş tarifeler birleşik döner.

    PDF arşivinde o kategorinin o dönemde karşılığı yoksa (ör. 2020-2021'de
    ekmek/şehit tarifesi yayımlanmadı) o tarih ATLANIR — sahte nokta üretilmez.
    Güncel HTML noktası aynı PDF'de de varsa HTML kazanır (ikisi 4 Nisan 2026
    için birebir aynı; bkz. modül docstring'i).
    """
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

    noktalar = {
        tarih: degerler[seri.botas_kategori]
        for tarih, degerler in arsiv_tarifeleri_cek(onbellek, session=session).items()
        if seri.botas_kategori in degerler
    }
    noktalar[tarife["tarih"]] = deger
    return pd.DataFrame(sorted(noktalar.items()), columns=["date", "value"])
