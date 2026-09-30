"""BigChefs (BIST: BIGCH) yatırımcı ilişkileri istemcisi.

İki ayrı belge türü. Aylık bildirimler ve bildirimi olmayan çeyrekler
`bigchefs.com.tr/duyurular/` + `bigchefs.com.tr/yatirimci-iliskileri/`
sayfalarının Elementor ikon-listesinden kazınıyor (dosya yolları öngörülemez —
bazıları tarihli açıklayıcı ad taşıyor, bazıları `duyuru_N.pdf` gibi sıra
numaralı; indeks sayfası her koşuda yeniden taranmak zorunda, OSD'nin bülten
indeksiyle aynı gerekçe). Üçüncü sayfa `bigchefs.com.tr/finansal-bilgiler/`
KALIBI FARKLI (düz ikon bağlantısı + ayrı `<h2>` etiketi, ayrı dal) ve
1Ç 2026'dan sonraki çeyrekleri YALNIZCA o sayfa listeliyor:

- **Aylık "Şube Sayısı Bildirimi"** (KAP ÖDA'nın şirket sitesi aynası): her
  belgenin "Şirket Profili" paragrafı sabit bir kalıp taşıyor — "[TARİH]
  tarihi itibarıyla Türkiye'de N şehirde M şube; yurt dışında K ülkede L
  şube olmak üzere toplam T şube ... ile hizmet vermektedir." Şube/şehir/
  ülke sayısı buradan okunuyor; bildirimin KENDİ tarihi (ayın günü ne
  olursa olsun) o AYA damgalanıyor.
- **Çeyreklik "Bilgilendirme Notu"** (`/yatirimci-iliskileri/` sayfasında da
  mirror'lanıyor ama tam arşiv yalnızca `/finansal-bilgiler/`'de — 2Ç 2026
  notu öbür ikisinde YOK):
  "Finansal ve Operasyonel Özet" tablosu + marka bazında "Fiş ortalaması TL"
  tablosu. TÜM DEĞERLER YIL BAŞINDAN O ÇEYREK SONUNA KÜMÜLATİFTİR — 1Ç raporu
  yalnızca Ocak-Mart'ı, 9A raporu Ocak-Eylül'ü, "FY"/yıl sonu raporu tüm yılı
  kapsar (çeyrek-tek DEĞİL; marketvisuals.net'in "(Kümülatif Değil)"
  etiketli kartları ardışık çeyrekler arası fark alarak türetiyor — bu
  adaptör yalnızca KÜMÜLATİF hâli sunar, türetilmiş fark kapsam dışı).
  "Grup Hakkında" paragrafı aynı şube/şehir/ülke kalıbını taşır VE ayrıca
  "... toplam T şube ve kendi bünyesinde Ç çalışan ile hizmet vermektedir"
  ekiyle çalışan sayısını da verir (her çeyrekte raporlanmıyor olabilir —
  o çeyrek atlanır, seri KESİLMEZ). Mart 2026'dan sonra aylık "Şube Sayısı
  Bildirimi" YAYIMLANMADIĞI için şube/şehir/ülke serilerinin son noktası
  artık bu çeyreklik paragraftan gelir — tarih, çeyreğin İLK AYINA
  (`donem_tarihi`) damgalanır.

Ölçülen tutarsızlık (2026-09-30): aylık bildirim ile çeyreklik not aynı
kalıbı kullanır ama kapsam farklı görünüyor. 02.03.2026 aylık bildirimi
"30 şehirde ... yurt dışında 10 ülkede ... toplam 138 şube" derken,
30.06.2026 çeyreklik notu "29 şehirde 124 şube; yurt dışında 4 ülkede 4
şube ... toplam 128 şube ve 1.501 çalışan" diyor. Seri, kendi kaynağı
çevrimiçi olduğu için bu kırılmayı DÜZELTMEZ — 2026-03-01 (aylık, 138/30/10)
ve 2026-04-01 (çeyreklik, 128/29/4) noktaları birbirini tutmayan iki kaynak
olur. Kaynak aylık bildirimi geri açarsa değerler yine kendi ifadesiyle
damgalanır (bkz. aşağıdaki ölçüm notu).

Ölçüldü (2026-09-18, `marketvisuals.net/bigch.html` ile birebir): 30.06.2026
şube sayısı 128 (124 yurt içi + 4 yurt dışı — NOT: bu belirli ay hem aylık
bildirim hem çeyreklik faaliyet raporu örtüşüyor, iki kaynağın birleşimi
referans sitede ayrı bir mantık taşıyor, bu adaptör YALNIZCA aylık
bildirimlerin kendi tarihini kullanıyor — ölçülen sapma ±1 ay mertebesinde
olabilir, bkz. ölçüm raporu). 1Ç 2026 net satışlar (konsolide) 1.170.003.689
TL, FAVÖK marjı %17,8, Fiş ortalaması Bigchefs 1.704 TL.

Bazı belgeler bir Java `byte[]` serileştirme sarmalayıcısıyla geliyor
(bkz. `ingest.ir_sunum.pdf_ayikla`).

Kapsam dışı (ölçüldü, bkz. `docs` — burada tekrar edilmiyor): marka bazında
şube kırılımı (SOR/FR), restoran yatırım harcaması, "Kümülatif Değil"
çeyrek-tek gelir tablosu/gider kalemleri, türetilmiş oranlar (şube başı fiş,
fiş başı ziyaretçi) — Bilgilendirme Notu'nda ham alan olarak yok, ya Ara
Dönem Faaliyet Raporu'nun ayrı bir tablosunu (doğrulanmadı) ya da başka bir
kartın türetilmesini gerektiriyor.
"""

from __future__ import annotations

import io
import re

import pandas as pd
import pdfplumber
import requests

from ingest.ir_sunum import donem_tarihi, pdf_ayikla, pdf_metnini_normallestir, tr_sayi

TABAN = "https://bigchefs.com.tr"
DUYURULAR_URL = f"{TABAN}/duyurular/"
# "Bilgilendirme Notu" bağlantılarının TAMAMI /duyurular/'da değil — o sayfa
# yalnızca bazı çeyrekleri "GÜN AY YIL - ... Bilgilendirme Notu" biçiminde
# listeliyor (ölçüldü: yalnızca 2). Çoğu çeyrek yalnızca YI ana sayfasının
# "Finansal Bilgiler" akordiyonunda, TARİHSİZ başlıkla ("BuyukSefler 1C2026
# Bilgilendirme Notu") yer alıyor — iki sayfa BİRLİKTE taranır.
YI_URL = f"{TABAN}/yatirimci-iliskileri/"
# YI sayfası 1Ç 2026'da KESİLİYOR (ölçüldü 2026-09-30): 2Ç 2026 notu
# yalnızca bu üçüncü sayfada listeleniyor. Kalıbı FARKLI (aşağıda ölçüldü)
# → ayrı ayrıştırma dalı.
FINANSAL_BILGILER_URL = f"{TABAN}/finansal-bilgiler/"
ZAMAN_ASIMI = 60
_BASLIKLAR = {"User-Agent": "Mozilla/5.0"}

_AYLAR = {
    "ocak": "01", "şubat": "02", "subat": "02", "mart": "03", "nisan": "04",
    "mayıs": "05", "mayis": "05", "haziran": "06", "temmuz": "07",
    "ağustos": "08", "agustos": "08", "eylül": "09", "eylul": "09",
    "ekim": "10", "kasım": "11", "kasim": "11", "aralık": "12", "aralik": "12",
}

_DUYURU_SPAN = re.compile(
    r'<a href="([^"]+\.pdf)"[^>]*>\s*<span class="elementor-icon-list-icon">.*?</span>\s*'
    r'<span class="elementor-icon-list-text">\s*([^<]+?)\s*</span>',
    re.S,
)

# /finansal-bilgiler/ sayfası `_DUYURU_SPAN`'ın beklediği ikon-listesini
# KULLANMIYOR (ölçüldü 2026-09-30, ham HTML): çeyrek blokları düz
# `<a class="elementor-icon elementor-animation-float" href="...pdf">`
# bağlantılarından ve bağlantının ARDINDAN gelen ayrı bir `<h2>` etiketinden
# oluşuyor ("Finansal Tablolar" / "Faaliyet Raporu" / "Bilgilendirme Notu" /
# "Yatırımcı Sunumu"); çeyrek ayracı "N.Çeyrek" başlığı. Dosya adı güvenilir
# değil ("3Q25.pdf", "1Q2024.pdf", "4C24_bilgilendirme.pdf") — tek güvenilir
# sinyal etiket. Aynı sayfanın MOBİL akordiyon bloğunda başlıklar PDF'lerden
# ÖNCE geliyor; orada etiket eşleşmez, o bağlantı bilinçli atlanır.
_FINANSAL_BILGI_OGESI = re.compile(r'(<a\b[^>]*>)|(<h2\b[^>]*>.*?</h2>)', re.S)
_HREF_PDF = re.compile(r'href="([^"]+\.pdf)"')
_BASLIK_TARIH = re.compile(r"(\d{1,2})\s+(\S+?)\s+(\d{4})\s*[-–]\s*(.+)")

# "Şirket Profili" (aylık bildirim) / "Grup Hakkında" (çeyreklik not)
# paragrafı — her iki belge türünde de aynı kalıp.
_SUBE_PARAGRAFI = re.compile(
    r"tarihi\s+itibarıyla\s+Türkiye'?de\s+(\d+)\s+şehirde\s+(\d+)\s+şube;?\s+"
    r"yurt\s+dışında\s+(\d+)\s+ülkede\s+(\d+)\s+şube\s+olmak\s+üzere\s+toplam\s+"
    r"(\d+)\s+şube(?:\s+ve\s+kendi\s+bünyesinde\s+([\d.]+)\s+çalışan)?\s+ile\s+hizmet"
)

# Bilgilendirme Notu'nun "Finansal ve Operasyonel Özet" tablosu satır
# etiketi -> o satırdaki İLK sayı (cari dönem, kümülatif).
_METRIK_ETIKET = {
    "sistem-geneli-net-satislar": "Sistem genelinde net satışlar",
    "net-satislar": "Net satışlar",
    "brut-kar": "Brüt kar",
    "brut-kar-marji": "Brüt kar marjı",
    "favok": "FAVÖK",
    "favok-marji": "FAVÖK marjı",
    "net-kar": "Net kar",
    "net-kar-marji": "Net kar marjı",
    "fis-sayisi": "Fiş sayısı",
    "ziyaretci-sayisi": "Ziyaretçi sayısı",
    "nakit": "Nakit ve Nakit Benzerleri",
    "toplam-borclar": "Toplam Borçlar",
    "net-nakit-pozisyonu": "Net (Borç)/Nakit Pozisyonu",
    "geri-alinan-paylar": "Geri Alınmış Paylar",
}
_FIS_ORTALAMASI_MARKA = {
    "fis-ortalamasi-bigchefs": "Bigchefs",
    "fis-ortalamasi-buselik": "Buselik",
    "fis-ortalamasi-numnum": "Numnum",
}
_AYLIK_METRIKLER = {"sube-sayisi", "sehir-sayisi", "ulke-sayisi"}
_SUBE_ALAN = {"sube-sayisi": 0, "sehir-sayisi": 1, "ulke-sayisi": 2}

GECERLI_METRIKLER = (
    _AYLIK_METRIKLER
    | {"calisan-sayisi"}
    | set(_METRIK_ETIKET)
    | set(_FIS_ORTALAMASI_MARKA)
)


def _finansal_bilgi_baglantilari(html: str) -> list[dict]:
    """`/finansal-bilgiler/` sayfasını ayrıştırır: her PDF ikon bağlantısı,
    hemen ardından gelen `<h2>` etiketiyle eşleştirilir (konu = etiket,
    tarih = None — dönem belge içinden okunur). İki PDF ikonu art arda
    geliyorsa yalnızca sonuncusu etiketlenir; etiketi olmayan bağlantı
    atlanır (konusu bilinmeyen belgeye konu uydurmak yanlış olur)."""
    sonuc: list[dict] = []
    bekleyen_url: str | None = None
    for oge in _FINANSAL_BILGI_OGESI.finditer(html):
        if oge.group(1):
            etiket = oge.group(1)
            m = _HREF_PDF.search(etiket)
            if m and "elementor-icon" in etiket:
                bekleyen_url = m.group(1)
        elif bekleyen_url:
            konu = re.sub(r"<[^>]+>", "", oge.group(2)).strip()
            sonuc.append({"tarih": None, "konu": konu, "url": bekleyen_url})
            bekleyen_url = None
    return sonuc


def _duyuru_listesi(session=None) -> list[dict]:
    """Üç sayfayı (duyurular + yatırımcı ilişkileri + finansal bilgiler)
    kazır; her PDF için (tarih 'YYYY-MM-01' ya da None, konu, url). Tarih
    yalnızca başlığın KENDİSİ "GÜN AY YIL - ..." öneki taşıyorsa çözülür
    (aylık şube bildirimleri hep taşır); taşımıyorsa None — yalnızca
    çeyreklik Bilgilendirme Notu taraması bunu kullanır ve dönemi kendi
    içeriğinden (`donem_tarihi`) okur, bu alana ihtiyaç duymaz."""
    http = session or requests
    sonuc: list[dict] = []
    gorulen_url: set[str] = set()
    for sayfa_url in (DUYURULAR_URL, YI_URL):
        yanit = http.get(sayfa_url, headers=_BASLIKLAR, timeout=ZAMAN_ASIMI)
        yanit.raise_for_status()
        yanit.encoding = "utf-8"
        for url, ham_baslik in _DUYURU_SPAN.findall(yanit.text):
            if url in gorulen_url:
                continue
            gorulen_url.add(url)
            ham_baslik = ham_baslik.strip()
            m = _BASLIK_TARIH.match(ham_baslik)
            if m:
                gun, ay_adi, yil, konu = m.groups()
                ay = _AYLAR.get(ay_adi.lower())
                tarih = f"{yil}-{ay}-01" if ay else None
                konu = konu.strip()
            else:
                tarih, konu = None, ham_baslik
            sonuc.append({"tarih": tarih, "konu": konu, "url": url})
    # Üçüncü sayfa farklı kalıp kullanıyor → ayrı dal (bkz. yukarıdaki ölçüm)
    yanit = http.get(FINANSAL_BILGILER_URL, headers=_BASLIKLAR, timeout=ZAMAN_ASIMI)
    yanit.raise_for_status()
    yanit.encoding = "utf-8"
    for b in _finansal_bilgi_baglantilari(yanit.text):
        if b["url"] in gorulen_url:
            continue
        gorulen_url.add(b["url"])
        sonuc.append(b)
    if not sonuc:
        raise RuntimeError(
            "BigChefs duyurular/yatırımcı ilişkileri/finansal bilgiler "
            "sayfalarında hiç PDF bağlantısı ayrıştırılamadı — şablon "
            "değişmiş olabilir"
        )
    return sonuc


def _belge_metnini_getir(url: str, onbellek: dict, session=None) -> str:
    if url in onbellek:
        return onbellek[url]
    http = session or requests
    yanit = http.get(url, headers=_BASLIKLAR, timeout=ZAMAN_ASIMI)
    yanit.raise_for_status()
    baytlar = pdf_ayikla(yanit.content)
    with pdfplumber.open(io.BytesIO(baytlar)) as pdf:
        metin = pdf_metnini_normallestir("\n".join(sayfa.extract_text() or "" for sayfa in pdf.pages))
    onbellek[url] = metin
    return metin


def _sube_bilgisi(metin: str) -> tuple[float, float, float, float | None] | None:
    m = _SUBE_PARAGRAFI.search(metin)
    if not m:
        return None
    sehir, yurtici, ulke, yurtdisi, toplam, calisan = m.groups()
    return (
        float(toplam),
        float(sehir),
        float(ulke),
        float(calisan.replace(".", "")) if calisan else None,
    )



def _donem_coz(metin: str) -> str | None:
    """Belgenin dönem başlığından damgalamayı üretir; başlık tanınamıyorsa
    None döner (belge atlanır). Ölçüldü 2026-09-30: 2023 öncesi notlar
    dönem başlığıyla DEĞİL, CEO'nun değerlendirme mektubuyla başlıyor —
    3C23/1C23'te başlık 600 karakterden sonra, 2C23'te hiç yok. Tek bir
    belgenin seriyi düşürmemesi için `donem_tarihi`'nin fırlattığı hata
    burada yutulur; pencerenin genişletilmemesinin sebebi, gövde metnindeki
    '3Ç 2023' gibi geçişlerin yanlış dönem damgalaması üretmesi."""
    try:
        return donem_tarihi(metin[:600])
    except RuntimeError:
        return None


def _metrik_deger(metin: str, etiket: str) -> float | None:
    desen = re.compile(rf"^{re.escape(etiket)}\s+([()%\d.,\-]+)", re.M)
    m = desen.search(metin)
    if not m:
        return None
    try:
        return tr_sayi(m.group(1))
    except ValueError:
        return None


def seri_cek(seri, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı)."""
    onbellek = onbellek if onbellek is not None else {}
    metrik = seri.bigchefs_metrik
    if metrik not in GECERLI_METRIKLER:
        raise RuntimeError(f"Bilinmeyen bigchefs_metrik: {metrik!r}")

    belgeler = _duyuru_listesi(session=session)
    noktalar: list[tuple[str, float]] = []

    if metrik in _AYLIK_METRIKLER:
        alan_idx = _SUBE_ALAN[metrik]
        adaylar = [b for b in belgeler if "Şube Sayısı Bildirimi" in b["konu"]]
        for b in adaylar:
            metin = _belge_metnini_getir(b["url"], onbellek, session=session)
            bilgi = _sube_bilgisi(metin)
            if bilgi is None:
                continue
            noktalar.append((b["tarih"], bilgi[alan_idx]))
        # Mart 2026'dan sonra aylık bildirim YAYIMLANMIYOR; aynı büyüklükleri
        # çeyreklik notun "Grup Hakkında" paragrafı veriyor (30.06.2026: 128
        # şube / 29 şehir / 4 ülke). Yalnızca aylık seride BOŞ kalan dönemler
        # doldurulur; aylık bildirimin kendi tarihindeki mevcut noktalar
        # ezilmez (o dönemin değeri kaynağının kendi ifadesiyle kalır).
        son_aylik = max((d for d, _ in noktalar if d), default="")
        for b in (x for x in belgeler if "Bilgilendirme Notu" in x["konu"]):
            metin = _belge_metnini_getir(b["url"], onbellek, session=session)
            bilgi = _sube_bilgisi(metin)
            if bilgi is None:
                continue
            donem = _donem_coz(metin)
            if donem and donem > son_aylik:
                noktalar.append((donem, bilgi[alan_idx]))
    else:
        adaylar = [b for b in belgeler if "Bilgilendirme Notu" in b["konu"]]
        for b in adaylar:
            metin = _belge_metnini_getir(b["url"], onbellek, session=session)
            if metrik == "calisan-sayisi":
                bilgi = _sube_bilgisi(metin)
                deger = bilgi[3] if bilgi else None
            elif metrik in _METRIK_ETIKET:
                deger = _metrik_deger(metin, _METRIK_ETIKET[metrik])
            else:
                deger = _metrik_deger(metin, _FIS_ORTALAMASI_MARKA[metrik])
            if deger is None:
                continue
            donem = _donem_coz(metin)
            if donem is None:
                continue
            noktalar.append((donem, deger))

    if not noktalar:
        raise RuntimeError(
            f"BigChefs {metrik!r} için taranan {len(adaylar)} belgenin hiçbirinde "
            "değer bulunamadı — şablon değişmiş olabilir"
        )
    df = (
        pd.DataFrame(noktalar, columns=["date", "value"])
        .drop_duplicates("date", keep="last")
        .sort_values("date")
        .reset_index(drop=True)
    )
    return df
