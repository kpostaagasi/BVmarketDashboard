"""USK (Ulusal Süt Konseyi) çiğ süt tavsiye fiyatı ve üretim maliyeti istemcisi.

İki bağımsız kaynak:

1. **Tavsiye fiyatı** — `https://ulusalsutkonseyi.org.tr/yillara-gore-cig-sut-
   fiyatlari-2194/` sayfasındaki tek TablePress tablosu (`id="tablepress-27"`),
   2011'den bugüne DÖNEM bazlı (değişim tarihi + fiyat) kırıklı bir seri:
   her satır bir dönemin BAŞLANGICINI verir, bir sonraki satıra kadar geçerli
   kalır (ör. "1 Mayıs 2026 –" satırı, 24,30 TL/lt'nin hâlâ yürürlükte
   olduğu anlamına gelir). `aylik_seriye_yay` bu kırık noktaları AYLIK bir
   ızgaraya (dashboard'un geri kalanıyla aynı frekans) ileri-doldurur.
   Ölçüldü (2026-09-18): son satır "1 Mayıs - 24,30" — MarketVisuals
   `usk_sut_fiyatlari.html` referansıyla birebir.

2. **Üretim maliyeti** — `https://ulusalsutkonseyi.org.tr/bolgelere-gore-1-
   litre-cig-sut-maliyeti-1637/` sayfasından ay başına bir PDF linklenir.
   **Format kırılması (ölçüldü 2026-09-18): PDF şablonu Mart 2026'da
   değişti.** Şubat 2026 ve öncesi (`ESKI` format — Ocak 2021'e kadar
   doğrulandı) 4 bölgeyi (Marmara/Ege/İç Anadolu/Akdeniz) yan yana basıyor;
   bu çok sütunlu tablo `pdfplumber.extract_text()` ile OKUNAMAZ HALE
   karışıyor (sütunlar satır satır harmanlanıyor) — yalnızca dosyanın en
   altındaki temiz "TÜRKİYE ORTALAMASI <değer>" özet satırı güvenilir.
   Mart 2026'dan itibaren (`YENI` format) tek ulusal hesap var (bölge
   ayrımı yok), tüm alt kalemler (RASYON/GİDERLER/GELİRLER) TEMİZ metin
   olarak çıkıyor — bu yüzden granüler kalemler (yem birim fiyatları,
   buzağı fiyatı, giderler) yalnızca `YENI_FORMAT_BASLANGIC`'tan itibaren
   üretiliyor; `uretim-maliyeti` (ulusal ortalama) HER İKİ formatta da
   üretiliyor. `_format_tespit_et` iki şablonu ayırt eder, üçüncü/bilinmeyen
   bir şablonda RuntimeError fırlatır (sessiz şablon kayması yok).
   Ölçüldü (Ağustos 2026, YENI format): "ÇİĞ SÜT ÜRETİM MALİYETİ 21,48
   TL/Litre" — referansla birebir.

# ponytail: eski format için yalnızca ulusal ortalama (TÜRKİYE ORTALAMASI)
okunuyor, 4 bölgenin ayrı ayrı maliyeti değil — bölge sütunları pdfplumber
ile güvenilir ayrıştırılamıyor (yukarıda ölçüldü). Kaynak eski PDF'lerini
tek-bölge, temiz-metin şablona çevirirse (Mart 2026'dan sonrasında olduğu
gibi) bölge kırılımı eklenebilir.
"""

from __future__ import annotations

import re
from datetime import date
from io import BytesIO

import pandas as pd
import pdfplumber
import requests

from core.catalog import GECERLI_USK_KALEMLERI

TAVSIYE_URL = "https://ulusalsutkonseyi.org.tr/yillara-gore-cig-sut-fiyatlari-2194/"
MALIYET_LISTE_URL = "https://ulusalsutkonseyi.org.tr/bolgelere-gore-1-litre-cig-sut-maliyeti-1637/"
ZAMAN_ASIMI = 30

AY_ESLEME = {
    "Ocak": 1, "Şubat": 2, "Mart": 3, "Nisan": 4, "Mayıs": 5, "Haziran": 6,
    "Temmuz": 7, "Ağustos": 8, "Eylül": 9, "Ekim": 10, "Kasım": 11, "Aralık": 12,
}
_AY_DESENI = "|".join(AY_ESLEME)

# Ay başına tek, temiz "Ay, YYYY" bağlantı metni yalnızca 2021'den itibaren
# istikrarlı (öncesi çok-aylık aralıklar taşıyor, ör. "Ocak-Mart, 2019").
MALIYET_ILK_YIL = 2021
# Granüler kalemler (yem/gider/gelir kırılımı) yalnızca YENİ (tek ulusal)
# şablonda güvenilir — bkz. modül docstring'i.
YENI_FORMAT_BASLANGIC = "2026-03-01"

KALEM_TAVSIYE = "tavsiye-fiyati"
KALEM_MALIYET = "uretim-maliyeti"

# YENİ format alan adı -> katalog kalemi.
_YENI_FORMAT_ESLEME = {
    "canli_agirlik": "canli-agirlik",
    "sut_verimi": "sut-verimi",
    "buzagi_fiyati": "buzagi-fiyati",
    "karma_yem_fiyati": "karma-yem-fiyati",
    "misir_silaji_fiyati": "misir-silaji-fiyati",
    "yonca_fiyati": "yonca-fiyati",
    "saman_fiyati": "saman-fiyati",
    "yem_maliyeti_toplam": "yem-maliyeti-toplam",
    "diger_giderler": "diger-giderler",
    "buzagi_geliri": "buzagi-geliri",
    "fark": "net-maliyet-baz",
}
assert {KALEM_TAVSIYE, KALEM_MALIYET, *_YENI_FORMAT_ESLEME.values()} == GECERLI_USK_KALEMLERI


def _sayi(ham: str) -> float:
    """Türkçe biçimli sayı: nokta binlik ayraç, virgül ondalık; sondaki
    dipnot yıldızları (`1,21**`) yok sayılır."""
    m = re.match(r"\s*([\d.,]+)", ham)
    if not m:
        raise RuntimeError(f"USK: sayı ayrıştırılamadı: {ham!r}")
    return float(m.group(1).replace(".", "").replace(",", "."))


# --- Tavsiye fiyatı: TablePress tablosu ---


def tavsiye_tablosunu_ayikla(html: str) -> list[tuple[str, float]]:
    """Tek TablePress tablosundan kronolojik `(başlangıç_tarihi, TL/litre)`
    kırılma noktalarını çıkarır. Yıl başlığı satırları (`<strong>YYYY YILI
    ...`) bağlam sağlar, veri satırlarına dahil edilmez."""
    idx = html.find("<table")
    idx2 = html.find("</table>")
    if idx == -1 or idx2 == -1:
        raise RuntimeError("USK: tavsiye fiyatı tablosu bulunamadı")
    tablo = re.sub(r"</?strong>", "", html[idx : idx2 + len("</table>")])

    satirlar = re.findall(
        r'<tr[^>]*>\s*<td class="column-1">(.*?)</td><td class="column-2">(.*?)</td>\s*</tr>',
        tablo, re.S,
    )
    if not satirlar:
        raise RuntimeError("USK: tavsiye fiyatı tablosunda satır bulunamadı")

    noktalar: list[tuple[str, float]] = []
    yil: int | None = None
    for col1_ham, col2_ham in satirlar:
        col1, col2 = col1_ham.strip(), col2_ham.strip()
        yil_m = re.match(r"(\d{4}) YILI", col1)
        if yil_m:
            yil = int(yil_m.group(1))
            continue
        if yil is None:
            continue
        gun_m = re.match(r"\s*(\d+)", col1)
        ay_m = re.search(_AY_DESENI, col1)
        if not gun_m or not ay_m:
            raise RuntimeError(f"USK {yil}: dönem tarihi ayrıştırılamadı: {col1!r}")
        gun, ay = int(gun_m.group(1)), AY_ESLEME[ay_m.group(0)]
        noktalar.append((f"{yil:04d}-{ay:02d}-{gun:02d}", _sayi(col2)))

    return sorted(noktalar)


def aylik_seriye_yay(kirilma_noktalari: list[tuple[str, float]], bugun: date) -> dict[str, float]:
    """Dönem bazlı kırılma noktalarını AYLIK bir ızgaraya ileri-doldurur:
    her ay, o ayın 1'inde yürürlükte olan son değeri taşır."""
    if not kirilma_noktalari:
        return {}
    yil, ay = int(kirilma_noktalari[0][0][:4]), int(kirilma_noktalari[0][0][5:7])
    sonuc: dict[str, float] = {}
    idx = 0
    mevcut = kirilma_noktalari[0][1]
    while (yil, ay) <= (bugun.year, bugun.month):
        tarih = f"{yil:04d}-{ay:02d}-01"
        while idx < len(kirilma_noktalari) and kirilma_noktalari[idx][0] <= tarih:
            mevcut = kirilma_noktalari[idx][1]
            idx += 1
        sonuc[tarih] = mevcut
        ay += 1
        if ay > 12:
            ay, yil = 1, yil + 1
    return sonuc


# --- Üretim maliyeti: aylık PDF listesi + iki şablon ---


def maliyet_dosyalarini_ayikla(html: str) -> dict[tuple[int, int], str]:
    """Liste sayfasından `{(yıl, ay): pdf_url}` çıkarır. Yalnızca temiz
    "Ay, YYYY" bağlantı metnini kabul eder (çok-aylık aralıklar —
    "Ocak-Mart, 2019" gibi — ay adı eşleşmediğinden doğal olarak elenir)."""
    sonuc: dict[tuple[int, int], str] = {}
    for m in re.finditer(r'<a[^>]*href="([^"]+\.pdf)"[^>]*>\s*([^<]+?)\s*</a>', html, re.I):
        url, etiket = m.group(1), m.group(2).strip()
        etiket_m = re.match(r"^([^\d,]+),\s*(\d{4})$", etiket)
        if not etiket_m:
            continue
        ay_no = AY_ESLEME.get(etiket_m.group(1).strip())
        if ay_no is None:
            continue
        yil = int(etiket_m.group(2))
        sonuc[(yil, ay_no)] = url
    return sonuc


def cekilecek_maliyet_dosyalari(dosyalar: dict[tuple[int, int], str], bugun: date) -> dict[tuple[int, int], str]:
    return {
        (yil, ay): url for (yil, ay), url in dosyalar.items()
        if (yil, ay) >= (MALIYET_ILK_YIL, 1) and (yil, ay) <= (bugun.year, bugun.month)
    }


def _format_tespit_et(metin: str) -> str:
    if "ÇİĞ SÜT ÜRETİM MALİYETİ" in metin and "RASYON (Sağılan İnek)" in metin:
        return "yeni"
    if "TÜRKİYE ORTALAMASI" in metin:
        return "eski"
    raise RuntimeError("USK: maliyet PDF'i tanınmayan bir şablonda — ne yeni ne eski biçim eşleşti")


def _eski_format_ayikla(metin: str) -> float:
    m = re.search(r"TÜRKİYE ORTALAMASI\s+([\d,]+)", metin)
    if not m:
        raise RuntimeError("USK (eski format): 'TÜRKİYE ORTALAMASI' satırı bulunamadı")
    return _sayi(m.group(1))


def _yeni_format_ayikla(metin: str) -> dict[str, float]:
    alanlar: dict[str, float] = {}

    def bul(pattern: str, ad: str) -> None:
        m = re.search(pattern, metin)
        if not m:
            raise RuntimeError(f"USK (yeni format): {ad} bulunamadı")
        alanlar[ad] = _sayi(m.group(1))

    bul(r"CANLI AĞIRLIK \(KG\)\s+([\d.,]+)", "canli_agirlik")
    bul(r"SÜT VERİMİ \(LT/G[ÜU]N\s*\)\s+([\d.,]+)", "sut_verimi")
    bul(r"BUZAĞI FİYATI \(TL/BAŞ\)\s+([\d.,]+)", "buzagi_fiyati")
    bul(r"Karma Yem\s+\d+\s+([\d,]+)\s+[\d,]+", "karma_yem_fiyati")
    bul(r"Mısır Silajı\s+\d+\s+([\d,]+)\s+[\d,]+", "misir_silaji_fiyati")
    bul(r"Yonca\s+\d+\s+([\d,]+)\s+[\d,]+", "yonca_fiyati")
    bul(r"Saman\s+\d+\s+([\d,]+)\s+[\d,]+", "saman_fiyati")
    bul(r"\nTOPLAM ([\d,]+)\n", "yem_maliyeti_toplam")
    bul(r"Diğer Giderler\s*\n?\s*[\d,]+\s+([\d,]+)", "diger_giderler")
    bul(r"Buzağı Geliri \(Buzağı Fiyatı/\d+\)\s*\*0,9\s+([\d,]+)", "buzagi_geliri")
    bul(r"\nFARK\s+([\d,]+)", "fark")
    bul(r"ÇİĞ SÜT ÜRETİM MALİYETİ\s+([\d,]+)\s*TL", "maliyet")
    return alanlar


def maliyet_pdf_ayikla(baytlar: bytes) -> dict[str, float]:
    """Bir ayın maliyet PDF'inden `{katalog_kalemi: değer}` çıkarır.
    Sonuç HER ZAMAN `uretim-maliyeti` içerir; YENİ format ayrıca 10 granüler
    kalem daha döner (bkz. `_YENI_FORMAT_ESLEME`)."""
    with pdfplumber.open(BytesIO(baytlar)) as pdf:
        metin = pdf.pages[0].extract_text() or ""

    if _format_tespit_et(metin) == "eski":
        return {KALEM_MALIYET: _eski_format_ayikla(metin)}

    ham = _yeni_format_ayikla(metin)
    sonuc = {KALEM_MALIYET: ham["maliyet"]}
    for alan, kalem in _YENI_FORMAT_ESLEME.items():
        sonuc[kalem] = ham[alan]
    return sonuc


# --- Ağ kabuğu ---

# Ölçüm (2026-09-18): USK sunucusu varsayılan `python-requests/...` UA'sını
# HTTP 403 ile reddediyor, tarayıcı UA'sı 200 dönüyor. Yahoo adaptöründeki
# aynı desen (bkz. ingest/yahoo.py) — UA sabit ve gerekçesi burada.
BASLIKLAR = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def _sayfa_cek(url: str, session=None) -> str:
    http = session or requests
    yanit = http.get(url, timeout=ZAMAN_ASIMI, headers=BASLIKLAR)
    if yanit.status_code != 200:
        raise RuntimeError(f"USK sayfası HTTP {yanit.status_code} ({url})")
    return yanit.text


def _dosya_indir(url: str, session=None) -> bytes:
    http = session or requests
    yanit = http.get(url, timeout=ZAMAN_ASIMI, headers=BASLIKLAR)
    if yanit.status_code != 200:
        raise RuntimeError(f"USK maliyet PDF'i HTTP {yanit.status_code} ({url})")
    return yanit.content


def _tum_noktalari_getir(onbellek: dict, session=None, bugun: date | None = None) -> dict[str, dict[str, float]]:
    if "noktalar" in onbellek:
        return onbellek["noktalar"]
    bugun = bugun or date.today()

    noktalar: dict[str, dict[str, float]] = {
        KALEM_TAVSIYE: aylik_seriye_yay(
            tavsiye_tablosunu_ayikla(_sayfa_cek(TAVSIYE_URL, session)), bugun,
        ),
    }

    dosyalar = cekilecek_maliyet_dosyalari(
        maliyet_dosyalarini_ayikla(_sayfa_cek(MALIYET_LISTE_URL, session)), bugun,
    )
    if not dosyalar:
        raise RuntimeError(f"USK: {MALIYET_ILK_YIL} sonrası indirilecek maliyet PDF'i bulunamadı")

    for (yil, ay), url in dosyalar.items():
        tarih = f"{yil:04d}-{ay:02d}-01"
        for kalem, deger in maliyet_pdf_ayikla(_dosya_indir(url, session)).items():
            if kalem != KALEM_MALIYET and tarih < YENI_FORMAT_BASLANGIC:
                continue  # savunma: eski format hiç granüler alan döndürmez
            noktalar.setdefault(kalem, {})[tarih] = deger

    onbellek["noktalar"] = noktalar
    return noktalar


def seri_cek(seri, onbellek: dict | None = None, session=None, bugun: date | None = None):
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `onbellek` koşu boyunca paylaşılırsa 15 seri aynı tavsiye-fiyatı
    tablosunu ve aynı ~30-70 aylık maliyet PDF kümesini paylaşır.
    """

    onbellek = {} if onbellek is None else onbellek
    noktalar = _tum_noktalari_getir(onbellek, session, bugun)

    if seri.usk_kalem not in noktalar or not noktalar[seri.usk_kalem]:
        raise RuntimeError(f"USK: kalem bulunamadı: {seri.usk_kalem!r} ({seri.id})")

    df = pd.DataFrame(sorted(noktalar[seri.usk_kalem].items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)
