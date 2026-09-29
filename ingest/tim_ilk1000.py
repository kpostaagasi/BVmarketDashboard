"""TİM "Türkiye'nin İlk 1000 İhracatçısı" kitabı + KAP ticker eşleştirmesi.

Kaynak gerçekleri 2026-09-29'da canlı ölçüldü (sıfırdan yeniden keşfetmeye
çalışmayın; ayrıntı aşağıda):

- Kitap PDF'tir ve BAŞKA MAKİNE-OKUNUR KAYNAK YOKTUR (xlsx/csv/api yok).
  Dosyalar 17 MB (2025) – 336 MB (2023) arasında; `pdfplumber` ile okunuyor.
- **DOSYA ADI TÜRETİLEMEZ.** 2023 `tim_ilk_1000_ihracati_arastirmasi_2023.pdf`,
  2022 `ILK 1000 2022 TR (1).pdf` — ikisi de komşu yılın kalıbına uymuyor.
  Keşif `INDEKS_URL`'deki yıl alt sayfalarından yapılır: her yıl sayfasında
  `/Ihracat1000/<yıl>/` altındaki tam olarak bir kitap bağlantısı vardır
  ("Logolar" ayrı bir dosyadır ve bağlantı metninden elenir). Dizin listesi
  boş döner. Ölçüldü: 2004–2010 ve 2014'te `/Ihracat1000/` altında PDF
  bağlantısı YOK; 2011–2025'in tamamında var. 2026 sayfası henüz 404.
- Kitabın kullanılabilir tek tablosu **"(ALFABETİK)" bölümüdür**: dört sütun —
  `<yıl> Genel Sıralaması | <yıl> Sektörel Sıralaması | <yıl> İhracatı ($) |
  Firma Ünvanı`. Dört kitapta da sütun sırası AYNI. 2023 ve 2024 bu tabloyu
  karşılıklı iki sayfaya yayıp sayfa başına İKİ tablo basıyor (her satır iki
  ayrı tablo hâlinde gelir, iki parça da okunmalı); 2022 başlık satırı
  basmıyor, 2025 ise her sayfada bir başlık satırı basıyor (filtre dışı kalır).
- **TUZAK — "Sermaye Yapısı" tablosu (ilk 50 firma) ÜNVAN SÜTUNU İÇERMEZ**
  (2022 s.206–285, 2023 s.109–148, 2024 s.119–158, 2025 s.232–311). Konumla
  eşleştirme gerektirir; burada kullanılmıyor, çünkü ALFABETİK tablosu aynı
  sıra ve ihracat değerlerini ÜNVANLA birlikte veriyor.
- **Sıralama 1000'e gidiyor ama satır sayısı 1000 DEĞİL**: genel sıra basılmış
  firma sayısı 2022→750, 2023→763, 2024→701, 2025→702. 2025'te bölümdeki 733
  satırın 24'ü başlık, 7'si boş sıra hücreli (TİM o 7 firmaya sıra vermemiş)
  → 702. Karşılaştırma: aynı kitabın "(SEKTÖRLERE GÖRE)" bölümünde 1012
  giriş var. Yani TİM her kitapta listenin ~%70'ini ALFABETİK bölümüne basıyor;
  gerisi sırasız olarak yalnızca sektör bölümünde duruyor. Bölümde olmayan
  firma için o yılın puanı ÜRETİLMEZ (sıfır doldurulmaz). Somut sonucu:
  2025'teki 844. sıradaki "TAT GIDA SAN. A.Ş." (TATGD) ALFABETİK bölümünde
  yoktur, bu yüzden servis edilemez — bilinçli kabul, `_yil_dogrula` yine de
  satır sayısını denetler.
- Sayı biçimi **yıldan yıla değişti**: 2022 kitabı ANGLO yazıyor
  ("43,331,274.09"), 2023/2024/2025 TÜRKÇE ("1.212.229.004,18"). Bu, sessiz
  1000× hatanın en olası kaynağı. `_sayi` üç biçimi de kabul eder, başka
  hiçbirini değil; ayrım nokta, ondalık basamağı EN FAZLA iki hane olmalıdır
  (belirsiz "1.234" reddedilir — satır düşer, sayım denetimi yükselir).
- `İhracatı` sütunu **sektörel değil GENEL (toplam) ihracattır** — 2025
  kitabında THYAO 17.780.064.704 $, FROTO 11.353.366.166,03 $, TUPRS
  2.707.889.710,75 $; marketvisuals.net/tim_ilk1000_ihracatci.html'in
  "2025 İhracat ($)" sütunu ($17.78B / $11.35B / $2.71B) ile uyuşuyor.
- **KAP eşleştirmesi**: `KAP_ITIRALAR` 755 IGS üyesinin TAMAMINI döner;
  borsada işlem görmeyenlerde `stockCode` boştur. Birden çok pay sınıfı olan
  ihraççı (KRDMA/KRDMB/KRDMD, AKBANK/AKMEN…) tek satırda VİRGÜLLE ayrılmış
  kod taşır ve üçü birden yayımlanır. Eşleştirme KAP'ın **kayıtlı resmî
  ünvanı** ile yapılır; TİM ünvanları yıldan yıla kısaltması değişir ("FORD
  OTOMOTİV SAN. A.Ş." / "FORD OTOMOTİV SANAYİ A.Ş."), bu yüzden normalleştirme
  yasal biçim sözcüklerini atar. Geriye kalan farklar elle çözülür
  (`EL_KARSILAYICI`); bulanık (Jaccard) eşleştirme DENENDİ ve YANLIŞ üretti
  (BMC → İnallar, TÜRK HAVA YOLLARI TEKNİK → THYAO) — kullanılmıyor.
  Eşleşmeyen firma sessizce DÜŞÜRÜLÜR; yanlış ticker yanlış bilgiden kötüdür.
- **Satır seçimi ticker'la değil TİM ÜNANIyla yapılır.** Bir ihraççının birden
  çok tüzel kişiliği vardır ve TİM hepsini listeler: 2022 kitabında hem
  "ŞİŞECAM DIŞ TİC. A.Ş." (24) hem "TÜRKİYE ŞİŞE VE CAM FABRİKALARI A.Ş."
  (176) vardır ve ikisi de SISE'dir. Katalog girdisi hangi tüzel kişiliği
  istiyorsa onu verir; `_unvan_varyantlari` o unvanın yıllar arası yazım
  farklarını toplar, başka bir tüzel kişilik satırı seçilmez.
"""

from __future__ import annotations

import io
import re
import urllib.parse
from datetime import date

import pdfplumber
import pandas as pd
import requests

TABAN = "https://tim.org.tr"
INDEKS_URL = f"{TABAN}/tr/turkiyenin-ilk-1000-ihracatci-arastirmasi"
YIL_SAYFASI = f"{INDEKS_URL}-{{yil}}"
KAP_ITIRALAR = "https://www.kap.org.tr/tr/api/company/items/IGS/A"
ZAMAN_ASIMI = 120

# 2004–2010 ve 2014 yıl sayfalarında kitap PDF'i bağlanmıyor; 2011'den itibaren
# her yıl bir kitap var. Pencere bu yıldan başlar (2026'da otomatik büyür:
# üst sınır indeks sayfasındaki en yeni yıldan gelir).
ILK_YIL = 2022

# ALFABETİK bölümünün sayfa blokunu bulmak için kullanılan bölüm ayracı.
BIRAKILIS_AYRACI = "KARSILASTIRMALI"  # _sadeleştirilmiş metinde
BOLUM_BASLIGI = "ALFABET"

# Şablon kayarsa (sütun eklenir, satırlar kayar) ayrıştırma birkaç satır
# bulup sessizce devam edebilir. 2022–2025 ölçümleri 701–763; eşik bunun
# belirgin altında ama gürültüye kapalı bir yerde.
ASGARI_FIRMA = 500
AZAMI_FIRMA = 1000
# Türkiye'nin toplam ihracatı 2025'te ~400 Mr USD. En büyük tek firma 17,8 Mr
# USD; bu bant hem "binlik ayırıcı okunmadı" (17.780) hem "ondalık yanlış"
# hatalarını ve yıl kaymasını (2022'de 15,8 Mr) yakalar.
ASGARI_EN_BUYUK = 1e9
AZAMI_EN_BUYUK = 1e11

GECERLI_OLCUTLER = frozenset({"ihracat", "sira"})

# 2025 kitabı KAPARI: yayımlanmış bir yıl, kitap yeniden basılmaz. Değerler
# marketvisuals.net/tim_ilk1000_ihracatci.html ile birebir doğrulandı.
# Kilit: _sadeleştirilmiş TİM ünvanı, değer: USD cinsinden ihracat.
DOGRULAMA_2025 = {
    "TURK HAVA YOLLARI": 17_780_064_704.00,
    "FORD OTOMOTIV": 11_353_366_166.03,
    "TURKIYE PETROL RAFINERILERI": 2_707_889_710.75,
}

# Elle çözülmüş TİM ünvanı → KAP resmî ünvanı çiftleri. Hepsi AYNI tüzel
# kişiliktir; fark yalnızca kısaltma/abartma ya da KAP'ın kaydettiği ünvandaki
# farklılıktır (KAP listesi ölçüldü: TÜPRAŞ'ın ünvanında "TUPRAŞ" öneki,
# VESTEL'de "ELEKTRONİK", SASA'da "POLYESTER" vardır). Anahtarlar
# normalleştirilmiş hâliyle de aranır, böylece aynı firmanın yıllar arası
# kısaltma farkı (HAT-SAN "İNŞA"/"İNŞAA") tek girdiyle karşılanır.
EL_KARSILAYICI = {
    "TÜRKİYE PETROL RAFİNERİLERİ A.Ş.": "TUPRAŞ-TÜRKİYE PETROL RAFİNERİLERİ A.Ş.",
    "HAT-SAN GEMİ İNŞA BAKIM ONARIM DENİZ NAKLİYAT SAN. TİC A.Ş.":
        "HAT-SAN GEMİ İNŞAA BAKIM ONARIM DENİZ NAKLİYAT SANAYİ VE TİCARET A.Ş.",
    "TÜRK TRAKTÖR VE ZİRAAT MAK. A.Ş.": "TÜRK TRAKTÖR VE ZİRAAT MAKİNELERİ A.Ş.",
    "GÖKNUR GIDA MADDELERİ ENERJİ İMALAT İTH. İHR. TİC. VE SAN. A.Ş.":
        "GÖKNUR GIDA MADDELERİ ENERJİ İMALAT İTHALAT İHRACAT TİCARET VE SANAYİ A.Ş.",
    "KOTON MAĞAZACILIK TEKS. SAN. VE TİC. A.Ş.":
        "KOTON MAĞAZACILIK TEKSTİL SANAYİ VE TİCARET A.Ş.",
    "TÜRKİYE HALK BANKASI A.Ş.GENEL MÜDÜRLÜĞÜ": "TÜRKİYE HALK BANKASI A.Ş.",
    "BATIÇİM BATI ANADOLU ÇİMENTO SAN. A.Ş.":
        "BATIÇİM BATI ANADOLU SANAYİ VE TİCARET A.Ş.",
    "VESTEL TİCARET A.Ş.": "VESTEL ELEKTRONİK SANAYİ VE TİCARET A.Ş.",
    "ŞİŞECAM DIŞ TİC. A.Ş.": "TÜRKİYE ŞİŞE VE CAM FABRİKALARI A.Ş.",
    "SASA DIŞ TİC. A.Ş.": "SASA POLYESTER SANAYİ A.Ş.",
    "SANKO DIŞ TİC. A.Ş.": "SANKO PAZARLAMA İTHALAT İHRACAT A.Ş.",
    "YİĞİT AKÜ MALZEMELERİ NAK. TUR. İNŞ. SAN. VE TİC. A.Ş.":
        "YİĞİT AKÜ MALZEMELERİ NAKLIYAT TURİZM İNŞAAT SANAYİ VE TİCARET A.Ş.",
}

_YIL_BAGLANTISI = re.compile(r'href="([^"]*Ihracat1000[^"]*\.pdf)"[^>]*>(.*?)</a>', re.S | re.I)
_YIL_LISTESI = re.compile(r"arastirmasi-(20\d\d)")
# -?\d{1,3}[.\d{3}]+,\d+  → Türkçe   1.212.229.004,18
# -?\d{1,3}[,\d{3}]*\.\d+  → Anglo     43,331,274.09
# -?\d+                   → tam sayı
_SAYI_BICIMI = re.compile(r"^-?\d{1,3}(\.\d{3})+,\d+$|^-?\d{1,3}(,\d{3})*\.\d+$|^-?\d+$")
# Türkçe harf varyantlarını (ve TİM'in bazen yazdığı ASCII karşılıklarını)
# tek harfe indirger: "İhracatçı" ile "IHRACATCI" aynı anahtara düşsün.
_SADELESTIR = str.maketrans("İIıiĞğÜüŞşÖöÇç", "IIIIGGUUSSOOCC")


def _sadelestir(metin: str) -> str:
    """Türkçe harf varyantlarını eşitler (bkz. `ingest/tim.py::_sadelestir`)."""
    return metin.translate(_SADELESTIR).upper()


# Ünvanın sonundaki yasal biçim ve genel ticari sözcükler. Noktalar ve
# tireler BOŞLUĞA çevrilir: "A.Ş." → "A Ş", "T.A.Ş." → "T A Ş", "SAN.TİC" →
# "SAN TİC", "HAT-SAN" → "HAT SAN" — böylece kısaltmalar bitişik yazıldığında
# ("SAN.TİC") tek parça kalmaz. Kalan tek harfler de yasal biçimden gelir.
# Liste de katlanır: "SANAYİ" yazılmış olsa bile karşılaştırma "SANAYI" ile
# yapılır; liste katlanmadan karşılaştırılırsa "SANAYİ"/"TİC"/"HOLDİNG"
# sessizce atılmaz ve "FORD OTOMOTİV SANAYİ A.Ş." ile "FORD OTOMOTİV SAN.
# A.Ş." birbirine uymaz (ölçüldü). KAP'ın yazdığı "SANAYİİ" (çift İ) de
# ayrıca listelenmiştir: Çelik Halat, Karsan, Parsan, Anadolu Efes.
_YASAL_SOZCUK = {_sadelestir(s) for s in {
    "AŞ", "AÜ", "AO", "AOU", "AOLL", "ASH", "ASG", "TAŞ",
    "ANONİM", "ŞİRKET", "ŞİRKETİ", "LTD", "STİ", "LTDŞTİ",
    "SAN", "SANAYİ", "SANAYİİ", "TİC", "TİCARET", "HOLDİNG", "HOLDINGS",
    "VE", "Sİ",
    "A", "O", "U", "S", "T", "I", "L", "LL",
}}


def _anahtar(unvan: str) -> str:
    """Unvanı karşılaştırılabilir tek satıra indirger.

    Nokta/tireler boşluğa çevrilir ("SAN.TİC" → "SAN TİC", "HAT-SAN" →
    "HAT SAN"), sonra yasal biçim sözcükleri atılır. "FORD OTOMOTİV SAN. A.Ş."
    ile "FORD OTOMOTİV SANAYİ A.Ş." ikisi de `FORD OTOMOTIV` olur.
    """
    duz = _sadelestir(str(unvan))
    parcalar = re.sub(r"[^A-Z0-9]+", " ", duz).split()
    return " ".join(p for p in parcalar if p not in _YASAL_SOZCUK)


def _sayi(metin: object) -> float | None:
    """TÜRKÇE/ANGLO para biçimini float'a çevirir; tanınmayanı None yapar.

    Kural: ONDALIK ayırıcı sonuncu ayırıcıdır. "1.212.229.004,18" →
    1212229004.18 (virgül), "43,331,274.09" → 43331274.09 (nokta). Kaba
    kural "virgül varsa Türkçe" olsaydı Anglo sayılar 1000× küçük, Türkçe
    ondalıksız "17.780" ise 1000× büyük çıkardı.

    Bu yüzden ondalık basamağı EN FAZLA iki hane olmalıdır: "1.234" (Türkçe
    binlik ayırıcı olabilir, Anglo 3 ondalık olabilir) belirsiz olduğu için
    REDDEDİLİR — satır düşer ve `_yil_dogrula`'daki firma sayısı eşiği
    yükselir. Yanlış değer yazmaktansa satır kaybı yeğdir.
    """
    duz = re.sub(r"\s", "", str(metin or ""))
    if not _SAYI_BICIMI.match(duz):
        return None
    if "," in duz and duz.rfind(",") > duz.rfind("."):
        ondalik = duz.rsplit(",", 1)[1]
        if len(ondalik) > 2:
            return None
        return float(duz.replace(".", "").replace(",", "."))
    if "," in duz:
        return float(duz.replace(",", ""))
    if "." in duz and len(duz.rsplit(".", 1)[1]) > 2:
        return None
    return float(duz)


def _getir(url: str, session=None) -> str:
    """Yıl sayfası/index HTML'ini döner; hata yükselir."""
    http = session or requests
    return http.get(url, timeout=ZAMAN_ASIMI).text


def _kitap_baglantilari(session=None) -> dict[int, str]:
    """`{yıl: pdf_url}` — indeks sayfasındaki yıl alt sayfalarından keşfedilir.

    Dosya adı asla yeniden inşa edilmez (2023'teki ad 2024 kalıbına uymaz).
    Her yıl sayfasında "Logolar" dışında tam olarak bir kitap bağlantısı
    beklenir; 0 ya da birden çok çıkarsa RuntimeError — yıl atlanmaz.
    """
    html = _getir(INDEKS_URL, session)
    yillar = sorted({int(y) for y in _YIL_LISTESI.findall(html)})
    if not yillar:
        raise RuntimeError(
            "TİM İlk 1000 indeks sayfasında yıl listesi bulunamadı "
            f"({INDEKS_URL}) — sayfa yapısı değişmiş olabilir"
        )
    baglantilar: dict[int, str] = {}
    for yil in range(ILK_YIL, max(yillar) + 1):
        sayfa = _getir(YIL_SAYFASI.format(yil=yil), session)
        adaylar = []
        for hedef, metin in _YIL_BAGLANTISI.findall(sayfa):
            duz = re.sub(r"<[^>]+>", " ", metin)
            if "Logo" in duz or f"/{yil}/" not in hedef:
                continue
            adaylar.append(urllib.parse.urljoin(TABAN, urllib.parse.quote(hedef)))
        if len(adaylar) != 1:
            raise RuntimeError(
                f"TİM {yil} yıl sayfasında tam olarak bir kitap PDF'i "
                f"bekleniyordu, {len(adaylar)} bulundu: {YIL_SAYFASI.format(yil=yil)} "
                "— dosya adı ya da sayfa yapısı değişmiş olabilir, yıl atlanmaz"
            )
        baglantilar[yil] = adaylar[0]
    return baglantilar


def _indir(url: str, session=None) -> bytes:
    """Kitabı indirir; PDF değilse RuntimeError."""
    http = session or requests
    yanit = http.get(url, timeout=ZAMAN_ASIMI)
    if "pdf" not in (yanit.headers.get("content-type") or "").lower():
        raise RuntimeError(f"TİM kitabı PDF değil: {url} ({yanit.status_code})")
    return yanit.content


def _bolum_sayfalari(kitap) -> tuple[int, int]:
    """`(ilk, son)` — ALFABETİK bölümünün sayfa aralığı (0 tabanlı, son dâhil).

    Sayfaların TAMAMININ metni taranır (tablolar değil — metin katmanı ucuz):
    "ALFABET" bölüm başlığının bulunduğu sayfa, "KARŞILAŞTIRMALI VERİLER"
    bölüm başlığının bulunduğu sayfa bölümün sonudur. Bu, 336 MB'lık 2023
    kitabında 460 saniyelik tam-tablo taramasını ~30 saniyeye indirir.
    """
    ilk = son = None
    for i, sayfa in enumerate(kitap.pages):
        metin = _sadelestir(sayfa.extract_text() or "")
        if ilk is None:
            if BOLUM_BASLIGI in metin and "ILK 1000" in metin:
                ilk = i
        elif BIRAKILIS_AYRACI in metin:
            son = i - 1
            break
    if ilk is None or son is None or son < ilk:
        raise RuntimeError(
            "TİM kitabında ALFABETİK bölümü bulunamadı "
            f"(ilk={ilk}, son={son}) — bölüm başlıkları değişmiş olabilir"
        )
    return ilk, son


def _kitabi_ayikla(baytlar: bytes, yil: int) -> dict[str, tuple[int, float]]:
    """`{TİM ünvanı: (genel sıra, ihracat $)}` — bir yıl kitabının tamamı.

    Tablo dört sütunludur ve her kitapta aynı sırada gelir; 2023/2024'te
    sayfa başına iki tablo basıldığı için hepsi okunur. Başlık satırı
    (`2025 Genel\nSıralaması`) ve boş sıra hücreli satırlar doğal olarak elenir.
    """
    noktalar: dict[str, tuple[int, float]] = {}
    siralar: dict[int, str] = {}
    with pdfplumber.open(io.BytesIO(baytlar)) as kitap:
        ilk, son = _bolum_sayfalari(kitap)
        for sayfa in kitap.pages[ilk + 1: son + 1]:
            for tablo in sayfa.extract_tables() or []:
                for satir in tablo:
                    if len(satir) != 4:
                        continue
                    sira = _sayi(satir[0])
                    tutar = _sayi(satir[2])
                    unvan = re.sub(r"\s+", " ", str(satir[3] or "")).strip()
                    if sira is None or tutar is None or not unvan:
                        continue
                    if not 1 <= sira <= AZAMI_FIRMA:
                        continue
                    onceki = siralar.get(int(sira))
                    if onceki is not None and onceki != unvan:
                        raise RuntimeError(
                            f"TİM {yil} kitabında {int(sira)}. sıra iki farklı "
                            f"firmaya ait: {onceki!r} / {unvan!r}"
                        )
                    siralar[int(sira)] = unvan
                    noktalar[unvan] = (int(sira), tutar)
    return noktalar


def _yil_dogrula(yil: int, noktalar: dict[str, tuple[int, float]]) -> None:
    """Satır sayısı, büyüklük bandı ve 2025 bilinen değerleri.

    Üçü de sessiz bozulmayı yakalar: eksik tablo (sayı düşer), binlik
    ayırıcının/ondalık ayırıcının yanlış çözülmesi (bant dışı) ve şablon
    değişikliği (2025 çapası).
    """
    adet = len(noktalar)
    if not ASGARI_FIRMA <= adet <= AZAMI_FIRMA:
        raise RuntimeError(
            f"TİM {yil} kitabından {adet} firma okundu "
            f"(beklenen {ASGARI_FIRMA}-{AZAMI_FIRMA}) — tablo şablonu kaymış olabilir"
        )
    en_buyuk = max(tutar for _, tutar in noktalar.values())
    if not ASGARI_EN_BUYUK <= en_buyuk <= AZAMI_EN_BUYUK:
        raise RuntimeError(
            f"TİM {yil} kitabında en büyük ihracat {en_buyuk:,.2f} $ — "
            "beklenen bant 1-100 Mr $ dışında; sayı biçimi yanlış çözülüyor olabilir"
        )
    if yil != 2025:
        return
    for parca, beklenen in DOGRULAMA_2025.items():
        eslesen = [tutar for unvan, (_, tutar) in noktalar.items()
                   if _anahtar(unvan).startswith(parca)]
        if not eslesen:
            raise RuntimeError(f"TİM 2025 kitabında çapa firma bulunamadı: {parca}")
        if abs(eslesen[0] - beklenen) > beklenen * 0.005:
            raise RuntimeError(
                f"TİM 2025 kitabında {parca} ihracatı {eslesen[0]:,.2f} $, "
                f"beklenen {beklenen:,.2f} $ — kitap veya sayı biçimi değişmiş"
            )


def _kap_anahtarlari(session=None) -> dict[str, tuple[str, ...]]:
    """`{normalleştirilmiş KAP ünvanı: (hisse kodları)}`.

    `stockCode` birden çok pay sınıfını virgülle taşır; hepsi yayımlanır.
    Hissesi olmayan üyeler (KAP listesindeki 755 üyenin bir kısmı) elenir.

    İki AYRI KAP üyesi aynı anahtara düşerse RuntimeError: normalleştirme
    fazla agresifleşmiş demektir ve o üye sessizce kaybolurdu.
    """
    http = session or requests
    yanit = http.get(KAP_ITIRALAR, timeout=ZAMAN_ASIMI,
                     headers={"Accept": "application/json"})
    ham = yanit.json()
    if not isinstance(ham, list) or not ham:
        raise RuntimeError(f"KAP şirket listesi okunamadı: {KAP_ITIRALAR}")
    tablo: dict[str, tuple[str, ...]] = {}
    for uye in ham:
        kodlar = tuple(sorted({
            k.strip() for k in str(uye.get("stockCode") or "").split(",") if k.strip()
        }))
        if not kodlar:
            continue
        anahtar = _anahtar(uye["kapMemberTitle"])
        onceki = tablo.setdefault(anahtar, kodlar)
        if onceki != kodlar:
            raise RuntimeError(
                f"KAP'ta iki farklı üye aynı anahtara düştü: {anahtar!r} — "
                f"{onceki} / {kodlar} (normalleştirme fazla agresif)"
            )
    if not tablo:
        raise RuntimeError("KAP listesinde hisse kodu taşıyan üye bulunamadı")
    return tablo


def eslestir(unvan: str, kap: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    """TİM ünvanını hisse kodlarına çevirir; eşleşme yoksa/çoksa boş demet.

    Sıra: doğrudan normalleştirilmiş eşitlik → `EL_KARSILAYICI` → boş. Bir
    anahtarda birden çok KAP üyesi birleşiyorsa da boş döner (belirsizlik);
    hissesi olmayan KAP üyeleri zaten `kap` içinde değildir.
    """
    anahtar = _anahtar(unvan)
    bulunan = kap.get(anahtar)
    if bulunan:
        return bulunan
    el = EL_KARSILAYICI.get(unvan)
    if el is not None:
        return kap.get(_anahtar(el), ())
    for tim_ad, kap_ad in EL_KARSILAYICI.items():
        if _anahtar(tim_ad) == anahtar:
            return kap.get(_anahtar(kap_ad), ())
    return ()


def _tum_noktalar(onbellek: dict, session=None) -> dict[int, dict[str, tuple[int, float]]]:
    """`{yıl: {TİM ünvanı: (genel sıra, ihracat $)}}` — koşu boyunca paylaşılır.

    N+ seri aynı dört kitabı okuduğu için indirme + ayrıştırma bir kez yapılır
    (kitaplar toplam ~440 MB; onsuz her seri için tekrar indirilirdi).
    """
    if "noktalar" not in onbellek:
        sozluk: dict[int, dict[str, tuple[int, float]]] = {}
        for yil, url in _kitap_baglantilari(session).items():
            noktalar = _kitabi_ayikla(_indir(url, session), yil)
            _yil_dogrula(yil, noktalar)
            sozluk[yil] = noktalar
        onbellek["noktalar"] = sozluk
    return onbellek["noktalar"]


def _kap_indeksi(onbellek: dict, session=None) -> dict[str, tuple[str, ...]]:
    """KAP indeksi koşu boyunca paylaşılır (yüzlerce seri aynı listeyi okur)."""
    if "kap" not in onbellek:
        onbellek["kap"] = _kap_anahtarlari(session)
    return onbellek["kap"]


def eslesen_kodlar(seri, onbellek: dict, session=None) -> tuple[str, ...]:
    """Katalogdaki TİM ünvanının BIST hisse kodları; eşleşme yoksa boş demet.

    TİM ünvanı yıldan yıla kısaltması değişir ("FORD OTOMOTİV SAN. A.Ş." /
    "FORD OTOMOTİV SANAYİ A.Ş."); eşleştirme normalleştirilmiş ad üzerinden
    yapıldığı için tek katalog girdisi her yıl için geçerlidir.
    """
    return eslestir(seri.tim_firma, _kap_indeksi(onbellek, session))


def _unvan_varyantlari(seri_firma: str, kodlar: tuple[str, ...],
                       kap: dict[str, tuple[str, ...]]) -> set[str]:
    """Serinin TİM ünvanının o kodlara giden normalleştirilmiş YAZIMLARINI verir.

    Bir ihraççının birden çok tüzel kişiliği olabilir ve TİM bunların hepsini
    listeler: 2025 kitabında "ŞİŞECAM DIŞ TİC. A.Ş." (genel sıra 34) ile
    "TÜRKİYE ŞİŞE VE CAM FABRİKALARI A.Ş." (176) ayrı ayrı vardır ve ikisi de
    SISE'dir. Hangi satırın kullanılacağı TİM ÜNANIYLE belirlenir, ticker'la
    değil — bu yüzden varyantlar katalog ünvanının kendi anahtarı ve AYNI
    kodlara giden `EL_KARSILAYICI` anahtarlarıyla sınırlıdır.
    """
    varyantlar = {_anahtar(seri_firma)}
    varyantlar |= {_anahtar(tim_ad) for tim_ad in EL_KARSILAYICI
                   if eslestir(tim_ad, kap) == kodlar}
    return varyantlar


def seri_cek(seri, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `onbellek` verilirse kitaplar ve KAP listesi koşu boyunca paylaşılır.

    `tim_olcut="ihracat"` ise yıl başına ihracat değerini ($), `"sira"` ise genel
    sıralamayı verir; her nokta 1 Ocak'a indirgenir. TİM'in ALFABETİK bölümü
    listenin yalnızca ~%70'ini basığı için bir firma bazı bir yıl eksik
    kalabilir — o yıl için nokta ÜRETİLMEZ, sıfır da yazılmaz. Serinin tamamında
    hiç nokta oluşmazsa RuntimeError.
    """
    olcut = getattr(seri, "tim_olcut", None) or "ihracat"
    if olcut not in GECERLI_OLCUTLER:
        raise ValueError(f"Geçersiz tim_olcut: {olcut!r} ({seri.id})")
    onbellek = {} if onbellek is None else onbellek
    noktalar = _tum_noktalar(onbellek, session)
    kap = _kap_indeksi(onbellek, session)
    kodlar = eslesen_kodlar(seri, onbellek, session)
    if not kodlar:
        raise RuntimeError(
            f"TİM ünvanı '{seri.tim_firma}' hiçbir BIST koduyla eşleşmedi "
            f"({seri.id}) — ünvan KAP kaydıyla örtüşmüyor; eşleştirme elle "
            "çözülmeli (EL_KARSILAYICI)"
        )
    varyantlar = _unvan_varyantlari(seri.tim_firma, kodlar, kap)

    kendi: dict[date, float] = {}
    for yil, nokta in sorted(noktalar.items()):
        satirlar = [deger for ad, deger in nokta.items()
                    if _anahtar(ad) in varyantlar]
        if not satirlar:
            continue
        if len(satirlar) > 1:
            raise RuntimeError(
                f"TİM {yil} kitabında {kodlar} için {len(satirlar)} farklı yazım "
                f"bulundu — hangisinin kullanılacağı belirsiz, seri atlanmaz"
            )
        sira, tutar = satirlar[0]
        kendi[date(yil, 1, 1)] = float(tutar if olcut == "ihracat" else sira)

    if not kendi:
        raise RuntimeError(
            f"TİM İlk 1000 kitaplarında '{seri.tim_firma}' bulunamadı "
            f"({seri.id}, {kodlar}) — TİM listesinde yer almıyor olabilir"
        )
    df = pd.DataFrame(sorted(kendi.items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)
