"""TÇÜD (Türkiye Çelik Üreticileri Derneği) aylık basın bülteni istemcisi.

celik.org.tr'nin (Next.js) sitemap.xml'i ölçüldü (2026-09-18): ayrı bir
istatistik/veri tabanı sayfası YOK — `bilgi-merkezi` altında yalnızca
`basin-bulteni`, `dergi`, `degerlendirme`, `teknik`, `sozluk` var. Dokuz
kart da TEK kaynaktan geliyor: her ay için ayrı bir HTML sayfası olan
"Basın Bülteni"
(`celik.org.tr/tr/bilgi-merkezi/basin-bulteni/basin-buelteni-<ay>-<yıl>`).
XLSX/PDF değil — serbest metin, ama düzenli cümle kalıpları taşıyan bir
haber sayfası (`<article class="max-w-none space-y-6">` içinde `<h3>`/`<p>`).

Dokuz kalemin YEDİSİ (ham çelik üretimi, nihai mamul tüketimi, ihracat/
ithalat miktar+değer, dünya ham çelik üretimi) bültende AYLIK (tek ay)
değer olarak doğrudan yazılı: "... aynı ayına göre %X artışla/azalışla Y
milyon/bin ton" kalıbı. Çin ve Hindistan ise YALNIZCA YILBAŞINDAN
KÜMÜLATİF veriliyor ("Ocak-<ay> döneminde" / "ilk N ayında" / Ocak için
doğrudan "Ocak ayında" — bu durumda kümülatif=aylık). Aylık değer,
`ingest.bddk.kumulatifi_ayliga_cevir` ile AYNI teknikle (ardışık ayların
kümülatifleri farkı, Ocak kendi başına aylık) üretiliyor — bu modül
kendi `_kumulatifi_ayliga_cevir`'ini taşır (bddk.py'ye çapraz bağımlılık
kurulmuyor; her ingest istemcisi tek başına duruyor, ayrı test edilebilir
kalıyor, bkz. ingest/*.py'nin hiçbiri birbirini import etmiyor).

Ölçüldü (2026-09-18, canlı): Şubat 2026 Çin kümülatifi (Ocak-Şubat)
160,3 milyon ton − Ocak 2026 tekil değeri 75,3 milyon ton = 85,0 milyon
ton — MarketVisuals referans değeriyle (85.0) birebir. Aynı teknikle
Hindistan 28,9 − 15,1 = 13,8 — referansla (13.8) birebir.

Sayı BİRİMLERİ AY BAZINDA DEĞİŞİYOR (ölçüldü, örnekler canlı): büyüklüğe
göre bülten "bin ton"/"milyon ton" ve "milyon dolar"/"milyar dolar"
arasında geçiş yapıyor (ör. Ocak 2026 ihracat miktarı "911,8 bin ton",
Temmuz 2026 ithalat değeri "1,1 milyar dolar"). `_sayi_ton`/`_sayi_dolar`
birimi SAYIYLA BİRLİKTE okuyup Türkiye'nin dört miktar kalemini kataloğun
beklediği "bin ton"a, ihracat/ithalat değerini "milyon dolar"a çevirir —
aksi halde bin/milyon karışıklığı sessizce 1000× hatalı veri üretirdi.
Dünya/Çin/Hindistan HER ZAMAN "milyon ton" (ölçülen aralıkta, tek ay ya da
9 aya kadar kümülatif, hiçbir örnekte 1000'i aşmıyor) — bu üçü için birim
çevrimi YOK, beklenmeyen birim (ör. "milyar ton") RuntimeError'a düşer.

Cümle kalıbındaki "oranında" eklentisi VE "artışla" (bitişik ek) ~
"artış ile" (ayrı sözcük) tercihi yazardan yazara DEĞİŞİYOR (ölçüldü:
aynı bültende bile miktar cümlesi "la" bitişik, değer cümlesi "ile" ayrı
olabiliyor) — `_YON` deseni ikisini de kabul eder. Virgülün "artışla"dan
hemen sonra gelip gelmemesi de tutarsız (ölçüldü: Temmuz 2026 miktar
cümlesinde virgül yok, değer cümlesinde var) — `_YON` bu virgülü de
isteğe bağlı yutar.

ILK_YIL=2025 gerekçesi (ölçüldü): 2021-2024 bültenleri "artarak"/
"kaydederek" (ulaç) gibi FARKLI fiil kalıpları da kullanıyor (ör. Şubat
2021: "%19,5 artarak", Ocak 2021 dünya cümlesi: "artış kaydederek") —
bunlar `_YON`'un "artış/azalış" gövdesini içermediği için eşleşmez ve
RuntimeError fırlatır (şablon kayması korumasının doğal sonucu). 2025
Ocak, 2025 Ağustos, 2026 Ocak/Şubat/Temmuz canlı örnekleri (5 örnek, iki
yıla yayılı) tutarlı "artış/azalış+la/ile" kalıbında — pencere bu yüzden
2025 Ocak'tan başlıyor. Daha geriye gitmek için ek fiil kalıpları
tanınmalı (bkz. yukarıdaki örnekler); bilinçli olarak kapsam dışı
bırakıldı.

# ponytail: "artarak"/"kaydederek" gibi eski ulaç kalıpları + tarihsel
"1.234,5" gibi binlik ayraçlı sayılar desteklenmiyor (ölçülen hiçbir
2025-2026 örneğinde binlik ayraç yok, değerler hep <1000). ILK_YIL'i
geriye çekmek ya da devasa sayılara karşı dayanıklı olmak gerekirse yeni
desen/eşik eklenir.
"""

from __future__ import annotations

import re
from datetime import date
from html import unescape

import pandas as pd
import requests

TABAN = "https://celik.org.tr/tr/bilgi-merkezi/basin-bulteni"
ZAMAN_ASIMI = 30

# Bkz. modül docstring'i: eski bültenler farklı fiil kalıpları kullanıyor.
ILK_YIL = 2025
ILK_AY = 1

AY_SLUG = {
    1: "ocak", 2: "subat", 3: "mart", 4: "nisan", 5: "mayis", 6: "haziran",
    7: "temmuz", 8: "agustos", 9: "eylul", 10: "ekim", 11: "kasim", 12: "aralik",
}

KALEM_URETIM = "uretim"
KALEM_TUKETIM = "tuketim"
KALEM_IHRACAT_MIKTAR = "ihracat-miktar"
KALEM_IHRACAT_DEGER = "ihracat-deger"
KALEM_ITHALAT_MIKTAR = "ithalat-miktar"
KALEM_ITHALAT_DEGER = "ithalat-deger"
KALEM_DUNYA = "dunya-uretim"
KALEM_CIN = "cin-uretim"
KALEM_HINDISTAN = "hindistan-uretim"

# Çin/Hindistan bültende yalnızca yılbaşından kümülatif veriliyor —
# aylığa çevirmek `_kumulatifi_ayliga_cevir` gerektirir (bkz. modül docstring'i).
_KUMULATIF_KALEMLER = {KALEM_CIN, KALEM_HINDISTAN}

GECERLI_TCUD_KALEMLERI = {
    KALEM_URETIM, KALEM_TUKETIM,
    KALEM_IHRACAT_MIKTAR, KALEM_IHRACAT_DEGER,
    KALEM_ITHALAT_MIKTAR, KALEM_ITHALAT_DEGER,
    KALEM_DUNYA, KALEM_CIN, KALEM_HINDISTAN,
}

# --- Metin kalıpları ---
#
# "oranında" eklentisi isteğe bağlı; "artışla" (bitişik) ile "artış ile"
# (ayrı) eş değer kabul edilir; sonrasındaki virgül de isteğe bağlı
# (bkz. modül docstring'i — ikisi de yazardan yazara değişiyor).
# Ölçüldü (2026-09-18, ek örnek Ekim 2025): "düşüşle" ("düşüş" + ünlü
# uyumuyla "-le") de "artış/azalış"ın eş anlamlısı olarak kullanılıyor.
_YON = r"(?:oranında\s+)?(?:artış|azalış|düşüş)\s*(?:l[ae]\b|ile\b),?"
_SAYI = r"(\d+(?:,\d+)?)"
_BIRIM_TON = r"(bin|milyon)\s*ton"
_BIRIM_DOLAR = r"(milyon|milyar)\s*dolar"

_URETIM_DESENI = re.compile(
    rf"Türkiye['’]nin ham çelik üretimi,.{{0,100}}?%\s*\d+(?:,\d+)?\s*{_YON}\s*{_SAYI}\s*{_BIRIM_TON}",
    re.S,
)
_TUKETIM_DESENI = re.compile(
    rf"Nihai mamul(?: çelik)? tüketimi.{{0,100}}?%\s*\d+(?:,\d+)?\s*{_YON}\s*{_SAYI}\s*{_BIRIM_TON}",
    re.S,
)
_IHRACAT_DESENI = re.compile(
    rf"çelik ürünleri ihracatı,.{{0,100}}?miktar yönünden\s*%\s*\d+(?:,\d+)?\s*{_YON}\s*{_SAYI}\s*{_BIRIM_TON},"
    rf"\s*değer yönünden ise,?\s*%\s*\d+(?:,\d+)?\s*{_YON}\s*{_SAYI}\s*{_BIRIM_DOLAR}",
    re.S,
)
_ITHALAT_DESENI = re.compile(
    rf"çelik ürünleri ithalatı,.{{0,100}}?miktar yönünden\s*%\s*\d+(?:,\d+)?\s*{_YON}\s*{_SAYI}\s*{_BIRIM_TON},"
    rf"\s*değer yönünden ise,?\s*%\s*\d+(?:,\d+)?\s*{_YON}\s*{_SAYI}\s*{_BIRIM_DOLAR}",
    re.S,
)
# Cümle "... aynı ayına kıyasla, %X ... Y milyon ton, Ocak-<ay> döneminde
# ise ..." şeklinde İKİ değer taşıyabilir (tekil ay + kümülatif); `.{0,100}?`
# tembel eşleşme ve `kıyasla` çapası SADECE ilkini (tekil ay) yakalar.
_DUNYA_DESENI = re.compile(
    rf"dünya ham çelik üretimi,.{{0,100}}?kıyasla,?\s*%\s*\d+(?:,\d+)?\s*{_YON}\s*{_SAYI}\s*milyon ton",
    re.S,
)
# Bazı aylarda (ölçüldü: 2025 Ekim-Aralık) "Çin'in" ile "ham çelik
# üretimi" arasına ay adı + tekil ay istatistiği giriyor (ör. "Çin'in
# Ekim ayında %12,1 oranında gerileyen ham çelik üretimi, Ocak-Ekim
# döneminde ... %3,9 azalış ile 817,9 milyon ton oldu."); `.{0,80}?` bu
# ek metni yutar, kümülatif değeri taşıyan `Ocak-<ay> döneminde ...`
# ibaresi hâlâ ilk anchor'dan SONRA arandığı için erken/yanlış cümleye
# sıçrama riski yok (ilk % işareti "Çin'in" ile "ham çelik üretimi"
# arasında kalıyor, aranan asıl % ondan SONRAKİ ilk eşleşme).
_CIN_DESENI = re.compile(
    rf"Çin['’]in.{{0,80}}?ham çelik üretimi,.{{0,100}}?%\s*\d+(?:,\d+)?\s*{_YON}\s*{_SAYI}\s*milyon ton",
    re.S,
)
_HINDISTAN_DESENI = re.compile(
    rf"Hindistan['’]ın ham çelik üretimi,.{{0,100}}?%\s*\d+(?:,\d+)?\s*{_YON}\s*{_SAYI}\s*milyon ton",
    re.S,
)

# Yukarıdaki `.{0,100}?` sınırı KASITLI: sınırsız `.*?` bir cümlenin fiil
# kalıbı eşleşmezse (ör. eski "artarak" ulaç kalıbı) BİR SONRAKİ paragrafa
# sızıp YANLIŞ bir kalemin değerini sessizce doğru kalem sanabilirdi (ör.
# ÜRETİM deseni TÜKETİM cümlesindeki "%5,1 azalışla 3,5 milyon ton"u
# eşleştirebilir). 100 karakter gerçek cümlelerin (~30-60 karakter, ölçüldü)
# tamamını kapsar ama bir SONRAKİ cümleye sıçramaya yetmez.

# İçerik gövdesi bu etiketin içinde (bkz. modül docstring'i); <head>'deki
# <meta description>/JSON-LD KISALTILMIŞ bir kopyasını taşıyor — gövdeyi
# izole etmeden aramak o kısaltılmış metne yanlışlıkla eşleşebilir.
_GOVDE_DESENI = re.compile(r'<article class="max-w-none space-y-6[^"]*"[^>]*>(.*?)</article>', re.S)


def bulten_url(yil: int, ay: int) -> str:
    return f"{TABAN}/basin-buelteni-{AY_SLUG[ay]}-{yil}"


def cekilecek_bultenler(bugun: date) -> list[tuple[int, int]]:
    """ILK_YIL/ILK_AY'dan bugünün ayına kadar TÜM (yıl, ay) çiftleri.

    TİM'in "yıl başına tek dosya" kısayolu burada YOK: Çin/Hindistan'ın
    kümülatiften aylığa çevrilmesi ARDIŞIK ayların tamamını gerektirir
    (bkz. `_kumulatifi_ayliga_cevir`), bu yüzden her ay ayrı bülten,
    hepsi çekiliyor (paylaşılan `onbellek` tekrar indirmeyi önler).
    """
    aylar: list[tuple[int, int]] = []
    yil, ay = ILK_YIL, ILK_AY
    while (yil, ay) <= (bugun.year, bugun.month):
        aylar.append((yil, ay))
        ay += 1
        if ay > 12:
            ay = 1
            yil += 1
    return aylar


def _icerik_govdesini_ayikla(html: str) -> str:
    """Ana `<article>` gövdesini izole edip düz metne çevirir."""
    m = _GOVDE_DESENI.search(html)
    if not m:
        raise RuntimeError(
            "TÇÜD: bülten içerik gövdesi bulunamadı — sayfa yapısı değişmiş olabilir"
        )
    govde = re.sub(r"<[^>]+>", " ", m.group(1))
    return unescape(re.sub(r"\s+", " ", govde)).strip()


def _sayi_ton(esleme: re.Match, sayi_grubu: int, birim_grubu: int) -> float:
    """Sayıyı birimiyle (bin/milyon) birlikte okuyup BİN TON'a çevirir.

    `birim_grubu` yalnızca `_BIRIM_TON`'un kendi ("bin"|"milyon") eşleşmiş
    alternatiflerinden birini taşıyabilir — üçüncü bir değer regex
    tarafından zaten elenir (bkz. `bulteni_ayikla`: eşleşmeyen alan
    "bulunamadı" RuntimeError'ına düşer, sessizce yanlış birime değil).
    """
    deger = float(esleme.group(sayi_grubu).replace(",", "."))
    return deger * 1000 if esleme.group(birim_grubu) == "milyon" else deger


def _sayi_dolar(esleme: re.Match, sayi_grubu: int, birim_grubu: int) -> float:
    """Sayıyı birimiyle (milyon/milyar) birlikte okuyup MİLYON DOLAR'a çevirir."""
    deger = float(esleme.group(sayi_grubu).replace(",", "."))
    return deger * 1000 if esleme.group(birim_grubu) == "milyar" else deger


def bulteni_ayikla(metin: str, yil: int, ay: int) -> dict[str, float]:
    """Bir bültenin düz metninden dokuz kalemi çıkarır.

    Çin/Hindistan burada HÂLÂ KÜMÜLATİF (Ocak..ay) — aylığa çevirme
    `seri_cek` içinde `_kumulatifi_ayliga_cevir` ile yapılıyor (ayrı
    endişe: ayrıştırma vs. zamana yayma).
    """
    etiket = f"{yil}-{ay:02d}"

    def _zorunlu(desen: re.Pattern, ad: str) -> re.Match:
        eslesen = desen.search(metin)
        if not eslesen:
            raise RuntimeError(
                f"TÇÜD {etiket}: '{ad}' bulunamadı — bülten şablonu değişmiş olabilir"
            )
        return eslesen

    sonuc: dict[str, float] = {}

    e = _zorunlu(_URETIM_DESENI, "ham çelik üretimi")
    sonuc[KALEM_URETIM] = _sayi_ton(e, 1, 2)

    e = _zorunlu(_TUKETIM_DESENI, "nihai mamul tüketimi")
    sonuc[KALEM_TUKETIM] = _sayi_ton(e, 1, 2)

    e = _zorunlu(_IHRACAT_DESENI, "çelik ihracatı")
    sonuc[KALEM_IHRACAT_MIKTAR] = _sayi_ton(e, 1, 2)
    sonuc[KALEM_IHRACAT_DEGER] = _sayi_dolar(e, 3, 4)

    e = _zorunlu(_ITHALAT_DESENI, "çelik ithalatı")
    sonuc[KALEM_ITHALAT_MIKTAR] = _sayi_ton(e, 1, 2)
    sonuc[KALEM_ITHALAT_DEGER] = _sayi_dolar(e, 3, 4)

    e = _zorunlu(_DUNYA_DESENI, "dünya ham çelik üretimi")
    sonuc[KALEM_DUNYA] = float(e.group(1).replace(",", "."))

    e = _zorunlu(_CIN_DESENI, "Çin ham çelik üretimi")
    sonuc[KALEM_CIN] = float(e.group(1).replace(",", "."))

    e = _zorunlu(_HINDISTAN_DESENI, "Hindistan ham çelik üretimi")
    sonuc[KALEM_HINDISTAN] = float(e.group(1).replace(",", "."))

    return sonuc


def _kumulatifi_ayliga_cevir(noktalar: dict[str, float]) -> dict[str, float]:
    """Yılbaşından kümülatif Çin/Hindistan üretimini aylık akıma çevirir.

    `ingest.bddk.kumulatifi_ayliga_cevir` ile AYNI teknik (bkz. modül
    docstring'i): Ocak zaten tek aylıktır; sonraki aylar önceki aydan
    farkla bulunur. Bir ay eksikse (bülten atlanmışsa) o ay ATLANIR —
    eksik ayın üstüne fark almak iki ayı tek aya yığar.
    """
    aylik: dict[str, float] = {}
    for tarih in sorted(noktalar):
        yil, ay = int(tarih[:4]), int(tarih[5:7])
        if ay == 1:
            aylik[tarih] = noktalar[tarih]
            continue
        onceki = f"{yil}-{ay - 1:02d}-01"
        if onceki in noktalar:
            aylik[tarih] = noktalar[tarih] - noktalar[onceki]
    return aylik


def _bulten_indir(url: str, session=None) -> str | None:
    """404 → None (o ay henüz yayımlanmamış); diğer hatalar yükselir."""
    http = session or requests
    yanit = http.get(url, timeout=ZAMAN_ASIMI)
    if yanit.status_code == 404:
        return None
    if yanit.status_code != 200:
        raise RuntimeError(f"TÇÜD HTTP {yanit.status_code} ({url})")
    return yanit.text


def _bulteni_getir(yil: int, ay: int, onbellek: dict, session=None) -> dict[str, float] | None:
    """Bir ayın bültenini önbellekten ya da ağdan alır; yoksa None."""
    anahtar = (yil, ay)
    if anahtar in onbellek:
        return onbellek[anahtar]
    html = _bulten_indir(bulten_url(yil, ay), session=session)
    if html is None:
        onbellek[anahtar] = None
        return None
    metin = _icerik_govdesini_ayikla(html)
    sonuc = bulteni_ayikla(metin, yil, ay)
    onbellek[anahtar] = sonuc
    return sonuc


def seri_cek(seri, *, onbellek: dict | None = None, session=None,
             bugun: date | None = None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    Dokuz TÇÜD serisi aynı aylık bülten kümesini paylaşır; `onbellek`
    (yıl, ay) -> ayrıştırılmış-alan-sözlüğü (ya da yayımlanmamışsa None)
    tutar, bu yüzden N kalem için tek indirme kümesi yeter.
    """
    if seri.tcud_kalem not in GECERLI_TCUD_KALEMLERI:
        raise RuntimeError(f"TÇÜD: bilinmeyen kalem '{seri.tcud_kalem}'")

    bugun = bugun or date.today()
    onbellek = {} if onbellek is None else onbellek

    kumulatif_noktalar: dict[str, float] = {}
    for yil, ay in cekilecek_bultenler(bugun):
        kayit = _bulteni_getir(yil, ay, onbellek, session=session)
        if kayit is None:
            continue  # henüz yayımlanmamış (cari) ay
        kumulatif_noktalar[f"{yil}-{ay:02d}-01"] = kayit[seri.tcud_kalem]

    if seri.tcud_kalem in _KUMULATIF_KALEMLER:
        noktalar = _kumulatifi_ayliga_cevir(kumulatif_noktalar)
    else:
        noktalar = kumulatif_noktalar

    if not noktalar:
        raise RuntimeError(f"TÇÜD: '{seri.tcud_kalem}' için hiç veri toplanamadı")

    tarihler = sorted(t for t in noktalar if seri.start_date is None or t >= seri.start_date)
    df = pd.DataFrame({"date": tarihler, "value": [noktalar[t] for t in tarihler]})
    return df.reset_index(drop=True)
