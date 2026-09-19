"""ebebek Mağazacılık A.Ş. Yatırımcı İlişkileri aylık operasyonel veri istemcisi.

Kaynak: `kurumsal.ebebek.com/yatirimci-duyurulari` — "Özel Durum Açıklamaları"
grubu altında her ay üç ayrı KAP bildirimi (PDF) yayımlanır: "<Ay> <Yıl> Satış
Adedi", "<Ay> <Yıl> Ziyaretçi Sayısı", "<Ay> <Yıl> Mağaza Sayısı". Tek liste
sayfası TÜM tarihçeyi (Ekim 2023'ten bugüne) taşır — pgsus/thy gibi tek bir
indirilebilir tablo yerine burada 100+ küçük PDF'ye dağılmış aynı seri var;
`onbellek` üç kategoriyi ("satis"/"ziyaret"/"magaza") ayrı ayrı önbellekler ki
6 seri aynı ~35 PDF'yi paylaşsın (aksi halde her seri kendi 35 PDF'ini
indirirdi).

Ölçüldü (2026-09-18): Ağustos 2026 Satış Adedi/Mağaza Ziyaretçi/Web
Ziyaret/Toplam Mağaza/Mega Mağaza/Standart Mağaza sırasıyla 10.737.113 /
4.992.875 / 10.978.359 / 316 / 2 / 282 — kurumsal.ebebek.com'daki KAP
bildirimleriyle birebir eşleşiyor.

Mağaza Sayısı bildirimi iki şablon taşır: Ağustos 2026'dan ÖNCE "X tanesi
geleneksel/standart, Y tanesi mini olmak üzere Z'ye ulaşmıştır" (mega kırılımı
yok); Ağustos 2026'DAN İTİBAREN "Türkiye (Z Mağaza): G mega, X standart, Y
mini" (KAP'ın kendi sınıflandırma değişikliği — bkz. şirketin ebebek.html
sayfasındaki not: mega mağazalar öncesinde standart sayısının içindeydi,
gerçek bir mağaza değişikliği değil). `standart_magaza` iki şablonda da aynı
alanı okur (etiket adı değişse de kavram sürekli); `mega_magaza` yalnızca yeni
şablonda var olduğu için katalogda `start_date: "2026-08-01"` taşımalı, aksi
halde önceki aylarda RuntimeError alınır.

Bilinen kaynak hatası: "Nisan 2025 Ziyaretçi Sayıları" başlıklı duyurunun PDF
içeriği aslında "Nisan 2025 Mağaza Sayısı" metnidir (ebebek IR sitesindeki
yanlış dosya eşlemesi; 2026-09-18'de canlı doğrulandı). Bu TEK ay
`BOZUK_DUYURULAR`da açıkça listelenir ve atlanır — sessiz atlama DEĞİL:
beklenen rakamın bulunamadığı başka bir ay hâlâ RuntimeError verir. Aksi
halde kaynak tarafındaki tek dosya hatası 34 ayın tamamını kullanılamaz
kılıyordu. Kaynak düzeltilince liste boşaltılmalı.

Bazı aylar aynı (ay, yıl, kategori) için İKİ duyuru içerir (ör. Aralık 2024
Mağaza Sayısı, Eylül 2024 Ziyaretçi Sayıları) — ikisi de aynı değeri taşıyorsa
tekilleştirilir; değerler çelişirse RuntimeError.
"""

from __future__ import annotations

import io
import re

import pandas as pd
import pdfplumber
import requests

from core.catalog import GECERLI_EBEBEK_METRIKLERI

LISTE_SAYFASI = "https://kurumsal.ebebek.com/yatirimci-duyurulari"
ZAMAN_ASIMI = 30

AY_ADLARI = (
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
)
AY_INDEKS = {ad: i + 1 for i, ad in enumerate(AY_ADLARI)}

# Kaynakta içeriği başlığıyla uyuşmayan duyurular (duyuru başlığı, kategori).
# Liste AÇIK tutulur: buraya yazılmayan bir uyuşmazlık hâlâ hata verir.
# "Nisan 2025 Ziyaretçi Sayıları" PDF'i gerçekte mağaza sayısı metni taşıyor
# (2026-09-18'de canlı doğrulandı; referans platform da o ayı boş gösteriyor).
BOZUK_DUYURULAR = {("Nisan 2025 Ziyaretçi Sayıları", "ziyaret")}
_AY_DESENI = "|".join(AY_ADLARI)

# Başlık kalıpları. "ebebek " öneki bazı eski duyurularda var (ör. "ebebek
# Ağustos 2024 Satış Adetleri"); "Adedi"/"Adetleri" ve "Sayısı"/"Sayıları"
# zaman içinde değişmiş, ikisi de kabul edilir.
_SATIS_BASLIK = re.compile(rf"^(?:ebebek )?({_AY_DESENI}) (\d{{4}}) Satış Ade(?:di|tleri)$")
_ZIYARET_BASLIK = re.compile(rf"^(?:ebebek )?({_AY_DESENI}) (\d{{4}}) Ziyaretçi Sayı(?:sı|ları)$")
_MAGAZA_BASLIK = re.compile(rf"^(?:ebebek )?({_AY_DESENI}) (\d{{4}}) Mağaza Sayısı$")

# Değer kalıpları (PDF metni normalize edilip — tüm boşluk/satır sonu tek
# boşluğa indirgenip — aranır). Her belgede ay değeri her zaman kümülatif
# değerden ÖNCE geçtiği için `re.search` ilk (ay) eşleşmesini döner.
_SATIS_DEGER = re.compile(r"toplam ürün ade(?:di|ti) ([\d.]+) olarak")
_MAGAZA_ZIYARETCI_DEGER = re.compile(r"mağazalarını ziyaret eden ziyaretçi sayısı ([\d.]+) olarak")
_WEB_ZIYARET_DEGER = re.compile(r"ebebek\.com internet sitesi ziyaret(?:çi)? sayısı ([\d.]+) olarak")
# Ağustos 2026 öncesi şablon: "... tarihi itibarıyla N tanesi
# geleneksel/standart, M tanesi mini olmak üzere T'ye ulaşmıştır / olarak
# devam etmektedir." Mağaza sayısı DEĞİŞMEDİYSE "ulaşmıştır" yerine "olarak
# devam etmektedir" kullanılır.
_MAGAZA_ESKI = re.compile(
    r"mağaza sayısı.*?itibarıyla (\d+) tanesi (geleneksel|standart), "
    r"(\d+) tanesi mini olmak üzere (\d+)['’]?\w*\s*(?:ulaşmıştır|olarak devam etmektedir)"
)
# Ağustos 2026'dan itibaren şablon: "Türkiye (T Mağaza): G mega, N standart, M mini".
_MAGAZA_YENI = re.compile(r"Türkiye \((\d+) Mağaza\): (\d+) mega, (\d+) standart, (\d+) mini")


def _normalize(metin: str) -> str:
    return re.sub(r"\s+", " ", metin.replace("&#039;", "'").replace("&rsquo;", "'"))


def _sayi(metin: str) -> int:
    return int(metin.replace(".", ""))


def duyuru_listesi(session=None) -> list[tuple[str, str]]:
    """(başlık, pdf_url) çiftlerini döner — "Özel Durum Açıklamaları" grubu.

    Tek sayfa TÜM tarihçeyi taşır (sayfalama yok); bu yüzden tek istekte
    duyuru listesi + URL'leri çözülür.
    """
    http = session or requests
    yanit = http.get(LISTE_SAYFASI, headers={"User-Agent": "Mozilla/5.0"}, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"ebebek yatirimci-duyurulari HTTP {yanit.status_code}")
    kayitlar = re.findall(
        r'data-gtm-doc="([^"]+)"[^>]*data-gtm-doc-group="Özel Durum Açıklamaları".*?'
        r'href="(https://kurumsal\.ebebek\.com/download\?path=[^"]+)"',
        yanit.text, re.S,
    )
    if not kayitlar:
        raise RuntimeError("ebebek yatirimci-duyurulari sayfasında 'Özel Durum Açıklamaları' bulunamadı")
    return [(_normalize(baslik), url) for baslik, url in kayitlar]


def _pdf_metni(url: str, session=None) -> str:
    http = session or requests
    yanit = http.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"ebebek duyuru PDF HTTP {yanit.status_code}: {url}")
    with pdfplumber.open(io.BytesIO(yanit.content)) as pdf:
        metin = "\n".join((sayfa.extract_text() or "") for sayfa in pdf.pages)
    return _normalize(metin)


def _tarih(ay_adi: str, yil: str) -> str:
    return f"{yil}-{AY_INDEKS[ay_adi]:02d}-01"


def _tekillestir(sonuc: dict, tarih: str, deger, baslik: str, url: str, aciklama: str) -> None:
    if tarih in sonuc and sonuc[tarih] != deger:
        raise RuntimeError(
            f"ebebek: {tarih} için çelişen yinelenen '{aciklama}' duyurusu ({baslik}: {url})"
        )
    sonuc[tarih] = deger


def satis_noktalari(session=None) -> dict[str, int]:
    sonuc: dict[str, int] = {}
    for baslik, url in duyuru_listesi(session):
        eslesme = _SATIS_BASLIK.match(baslik)
        if not eslesme:
            continue
        tarih = _tarih(*eslesme.groups())
        metin = _pdf_metni(url, session)
        deger_eslesme = _SATIS_DEGER.search(metin)
        if not deger_eslesme:
            raise RuntimeError(f"ebebek: 'Satış Adedi' rakamı ayıklanamadı ({baslik}: {url})")
        _tekillestir(sonuc, tarih, _sayi(deger_eslesme.group(1)), baslik, url, "Satış Adedi")
    if not sonuc:
        raise RuntimeError("ebebek: hiç 'Satış Adedi' duyurusu bulunamadı")
    return sonuc


def _icerik_donemi(metin: str, baslik: str, url: str, kategori: str) -> str:
    """Dönemi PDF METNİNDEN okur; başlık güvenilmez.

    Ölçüm (2026-09-18): iki duyuru da "Eylül 2024 Ziyaretçi Sayıları"
    başlığını taşıyor ama birinin içeriği Eylül 2025'e ait (referans
    platform da Eylül 2024'ü boş, Eylül 2025'i 4.597.348 gösteriyor).
    Başlığa güvenmek iki farklı ayı aynı anahtara yazıp "çelişen yinelenen
    duyuru" hatası üretiyordu. İki kalıp ölçüldü: gövdede "<Ay> <Yıl>
    ayında/ayı" ve (yeni şablonda) başlık satırında "<Ay> <Yıl>
    <kategori>". Serbest ilk tarih eşleşmesi KULLANILMAZ: PDF'ler
    yayım tarihini ("01 Temmuz 2025") ve geçen yıl karşılaştırmasını da
    yazıyor, ilk eşleşme yanlış ayı verir.
    """
    for desen in (
        rf"({_AY_DESENI})\s+(\d{{4}})\s+ay[ıi]",
        rf"({_AY_DESENI})\s+(\d{{4}})\s+{kategori.split()[0]}",
    ):
        eslesme = re.search(desen, metin)
        if eslesme is not None:
            return _tarih(*eslesme.groups())
    raise RuntimeError(
        f"ebebek: '{kategori}' PDF içeriğinde dönem bulunamadı ({baslik}: {url})"
    )


def ziyaret_noktalari(session=None) -> dict[str, tuple[int, int]]:
    """(mağaza ziyaretçi, web ziyaret) çiftleri."""
    sonuc: dict[str, tuple[int, int]] = {}
    for baslik, url in duyuru_listesi(session):
        if not _ZIYARET_BASLIK.match(baslik):
            continue
        metin = _pdf_metni(url, session)
        magaza_eslesme = _MAGAZA_ZIYARETCI_DEGER.search(metin)
        web_eslesme = _WEB_ZIYARET_DEGER.search(metin)
        if not magaza_eslesme or not web_eslesme:
            if (baslik, "ziyaret") in BOZUK_DUYURULAR:
                continue  # kaynak tarafı dosya eşleme hatası; docstring'de belgeli
            raise RuntimeError(
                f"ebebek: 'Ziyaretçi Sayısı' rakamları ayıklanamadı ({baslik}: {url}) "
                "— PDF içeriği başlıkla uyuşmuyor olabilir"
            )
        tarih = _icerik_donemi(metin, baslik, url, "Ziyaretçi Sayısı")
        deger = (_sayi(magaza_eslesme.group(1)), _sayi(web_eslesme.group(1)))
        _tekillestir(sonuc, tarih, deger, baslik, url, "Ziyaretçi Sayısı")
    if not sonuc:
        raise RuntimeError("ebebek: hiç 'Ziyaretçi Sayısı' duyurusu bulunamadı")
    return sonuc


def magaza_noktalari(session=None) -> dict[str, dict[str, int]]:
    """{"toplam", "standart", "mini", opsiyonel "mega"} alanları."""
    sonuc: dict[str, dict[str, int]] = {}
    for baslik, url in duyuru_listesi(session):
        eslesme = _MAGAZA_BASLIK.match(baslik)
        if not eslesme:
            continue
        tarih = _tarih(*eslesme.groups())
        metin = _pdf_metni(url, session)
        eski = _MAGAZA_ESKI.search(metin)
        yeni = _MAGAZA_YENI.search(metin)
        if yeni:
            toplam, mega, standart, mini = (int(x) for x in yeni.groups())
            deger = {"toplam": toplam, "standart": standart, "mini": mini, "mega": mega}
        elif eski:
            standart, _etiket, mini, toplam = eski.groups()
            deger = {"toplam": int(toplam), "standart": int(standart), "mini": int(mini)}
        else:
            raise RuntimeError(f"ebebek: 'Mağaza Sayısı' rakamları ayıklanamadı ({baslik}: {url})")
        _tekillestir(sonuc, tarih, deger, baslik, url, "Mağaza Sayısı")
    if not sonuc:
        raise RuntimeError("ebebek: hiç 'Mağaza Sayısı' duyurusu bulunamadı")
    return sonuc


# --- Çeyreklik "Analist Toplantısı Sunumu" (Yatırımcı İlişkileri) ---
#
# `finansal-bilgiler` sayfasının "Finansal Sonuçlara İlişkin Sunumlar"
# bölümü 2023 3Ç'ten bugüne çeyreklik PDF listeler (aylık KAP
# duyurularından AYRI belge ailesi, aylık duyuru sayfasından da AYRI bir
# URL). "NÇ Türkiye Operasyonlarına Genel Bakış" sayfası kanal bazlı
# satış büyümesi/payı okur; bir sonraki sayfa fatura/sipariş ortalaması,
# PL payı ve LFL'yi; "Kategoriler arası..." sayfası kategori kırılımını
# okur. Üçü de yalnızca YAKIN GEÇMİŞTE (ölçüldü: kanal/fatura/LFL/PL
# sayfası ilk kez 4Ç 2025'te, kategori sayfası ilk kez 4Ç 2024'te)
# ortaya çıktı — daha eski sunumlarda sayfa hiç yok, `None`/atlama ile
# ele alınır (hata değil).
FINANSAL_SAYFA = "https://kurumsal.ebebek.com/finansal-bilgiler"

_SUNUM_SATIRI = re.compile(
    r'data-gtm-doc="Analist Toplantısı Sunumu[^"]*"\s*'
    r'data-gtm-doc-group="Finansal Sonuçlara İlişkin Sunumlar">'
    r'.*?<strong>(\d{2})\.(\d{2})\.(\d{2})</strong>'
    r'.*?href="(https://kurumsal\.ebebek\.com/download\?path=[^"]+)"',
    re.S,
)
_AY_CEYREK = {"03": 1, "06": 2, "09": 3, "12": 4}

GECERLI_SUNUM_METRIKLERI = {
    "kanal_buyume_magaza", "kanal_buyume_web", "kanal_buyume_pazaryeri",
    "kanal_payi_magaza", "kanal_payi_web", "kanal_payi_pazaryeri",
    "magaza_fatura_ortalama", "web_siparis_ortalama",
    "lfl_satis_adedi", "lfl_giris_sayisi",
    "pl_payi_toplam", "pl_payi_magaza", "pl_payi_web", "pl_payi_pazaryeri",
    "kategori_buyume_hizli_tuketim", "kategori_buyume_tamamlayici",
    "kategori_buyume_tekstil", "kategori_buyume_bebek_arac_gerec",
}


def _sunum_listesi(session=None) -> list[dict]:
    """finansal-bilgiler sayfasının "Finansal Sonuçlara İlişkin Sunumlar"
    bölümünden (yıl, çeyrek, url) satırlarını okur. Tarih başlığın kendi
    metninden ("2025 2. Çeyrek" vb. — yıllar arası ifade farklı) değil,
    belgeye eklenmiş sabit "GG.AA.YY" damgasından (her zaman dönem SONU)
    okunur — çok daha güvenilir."""
    http = session or requests
    yanit = http.get(FINANSAL_SAYFA, headers={"User-Agent": "Mozilla/5.0"}, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"ebebek finansal-bilgiler HTTP {yanit.status_code}")
    sonuc = []
    for _gun, ay, yy, url in _SUNUM_SATIRI.findall(yanit.text):
        sonuc.append({"yil": 2000 + int(yy), "ceyrek": _AY_CEYREK[ay], "url": url})
    if not sonuc:
        raise RuntimeError(
            "ebebek finansal-bilgiler sayfasında hiç 'Analist Toplantısı Sunumu' bulunamadı"
        )
    return sonuc


def _sunum_pdfsini_getir(url: str, onbellek: dict, session=None) -> bytes | None:
    """Ham PDF baytlarını döner (metne değil — üç ayrıştırıcı da konum
    bilgisine ihtiyaç duyar); 404 kalıcı yokluğunda None."""
    anahtar = ("sunum_bayt", url)
    if anahtar in onbellek:
        return onbellek[anahtar]
    http = session or requests
    yanit = http.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=ZAMAN_ASIMI)
    if yanit.status_code == 404:
        onbellek[anahtar] = None
        return None
    if yanit.status_code != 200:
        raise RuntimeError(f"ebebek sunum PDF HTTP {yanit.status_code}: {url}")
    onbellek[anahtar] = yanit.content
    return yanit.content


_KANAL_BUYUME_DESENI = re.compile(r"(%-?\d+,\d+|-%\d+,\d+)")


def kanal_buyume_ve_payini_ayikla(pdf_baytlari: bytes) -> dict[str, float] | None:
    """"NÇ Türkiye Operasyonlarına Genel Bakış" sunumunun "Satış Kanalı
    Bazında satış adedi kırılımı" bölümünü taşıyan sayfayı bulur. Sayfa
    yoksa (2025 4Ç'ten önce) None döner.

    Mağaza/ebebek.com/Pazaryeri satış adedi BÜYÜME YÜZDELERİ ve PASTA
    GRAFİĞİ PAYLARI gerçek metin katmanında var (regex/konumla okunabilir)
    ama üç panelin MUTLAK bin-adet çubuk değerleri PDF'te vektör/görsel
    olarak gömülü — metin katmanında HİÇ yok (ölçüldü: `extract_text()`
    çıktısında "23.288" gibi hiçbir çubuk etiketi geçmiyor, yalnızca
    başlıklar/yüzdeler geçiyor). Bu yüzden mutlak bileşen serisi yerine
    doğrudan yüzde serileri üretilir (büyüme + pay).

    Büyüme: metin sırası panel sırasıyla (Mağaza, ebebek.com, Pazaryeri)
    eşleşir — üç panelin başlığı da bu sırada, garipleşmiyor (yalnızca
    "Mağaza Fatura Başına..." sayfasındaki İKİ SATIRLI başlıklar
    garipleşiyor, bkz. `_fatura_siparis_pl_lfl_ayikla`). Tek çeyreklik
    sunumlarda (1Ç) panel başına TEK büyüme yüzdesi, çeyrek+YBİ
    kümülatif sunan sunumlarda (2Ç/3Ç/4Ç) panel başına İKİ (çeyrek, YBİ
    kümülatif) — yalnızca ÇEYREĞE özgü ilk değer kullanılır.

    Pay: pasta grafiğinin üç dilim yüzdesi konumdan okunur ama hangi
    sayının hangi kanala ait olduğu metin sırasından ÇIKARILAMAZ (üç
    sayı da pasta çevresinde serbestçe konumlanmış). Mağaza/ebebek.com/
    Pazaryeri payları HER ölçülen çeyrekte hep BÜYÜKTEN KÜÇÜĞE bu sırada
    olduğundan (Mağaza her zaman baskın, Pazaryeri her zaman en küçük —
    üç farklı çeyrekte doğrulandı) büyüklüğe göre eşlenir."""
    with pdfplumber.open(io.BytesIO(pdf_baytlari)) as pdf:
        sayfa = None
        for p in pdf.pages:
            t = p.extract_text() or ""
            if "Satış Kanalı Bazında satış" in t and "Mağaza Satış Adetleri" in t:
                sayfa = p
                break
        if sayfa is None:
            return None
        tam_metin = sayfa.extract_text() or ""
        kelimeler = sayfa.extract_words()

    idx_panel = tam_metin.find("Satış Kanalı Bazında satış")
    legend_eslesme = re.search(r"Mağaza\s+ebebek\.com\s+Pazar\s*[Yy]eri", tam_metin)
    if idx_panel == -1 or legend_eslesme is None:
        raise RuntimeError("ebebek kanal sayfası: beklenen bölüm sınırları bulunamadı")
    idx_legend = legend_eslesme.start()
    buyume_ham = _KANAL_BUYUME_DESENI.findall(tam_metin[idx_panel:idx_legend])
    buyume = [float(g.replace("%", "").replace(",", ".")) for g in buyume_ham]
    if len(buyume) == 3:
        magaza_b, web_b, pazar_b = buyume
    elif len(buyume) == 6:
        magaza_b, web_b, pazar_b = buyume[0], buyume[2], buyume[4]
    else:
        raise RuntimeError(f"ebebek kanal büyümesi: 3 ya da 6 değer bekleniyordu, {len(buyume)} bulundu")

    tek_ve_iki_hane = re.compile(r"^\d{1,2}$")
    yuzde_kelimesi = [w for w in kelimeler if w["text"] == "%"]
    pay_degerleri = []
    for w in kelimeler:
        if tek_ve_iki_hane.match(w["text"]) and any(
            abs(p["top"] - w["top"]) < 40 and abs(p["x0"] - w["x0"]) < 60 for p in yuzde_kelimesi
        ):
            pay_degerleri.append(float(w["text"]))
        elif re.match(r"^\d{1,2}%$", w["text"]):
            pay_degerleri.append(float(w["text"].rstrip("%")))
    if len(pay_degerleri) != 3:
        raise RuntimeError(f"ebebek kanal payı: 3 değer bekleniyordu, {len(pay_degerleri)} bulundu")
    magaza_p, web_p, pazar_p = sorted(pay_degerleri, reverse=True)

    return {
        "kanal_buyume_magaza": magaza_b, "kanal_buyume_web": web_b, "kanal_buyume_pazaryeri": pazar_b,
        "kanal_payi_magaza": magaza_p, "kanal_payi_web": web_p, "kanal_payi_pazaryeri": pazar_p,
    }


def fatura_siparis_pl_lfl_ayikla(pdf_baytlari: bytes) -> dict[str, float] | None:
    """"Mağaza Fatura Başına Nominal Tutar" + "ebebek.com Sipariş Başına
    Nominal Tutar" + "Satış Kanalı Bazında PL (Öz Marka) Adet Payı" +
    "Aynı Mağaza (LFL) Satış/Giriş" hepsini TEK sayfada taşıyan sayfayı
    bulur. Sayfa yoksa (2025 4Ç'ten önce) None döner.

    Bu sayfanın başlıkları (ör. "Mağaza Fatura Başına Nominal Tutar")
    pdfplumber'da SÜTUN BAZLI satır-satır çıkarıldığından komşu sütunların
    metniyle karakter düzeyinde iç içe geçiyor (ölçüldü: "Dönem sonu
    itibarıyla" ile karışıp "Dön M em a ğ so a nu z a iti b F..." gibi
    okunuyor) — bu yüzden hiçbir etiket metinden ARANMAZ, sayfa yalnızca
    LFL alt başlığından (garipleşmiyor) tanınır ve sayı DEĞERLERİ salt
    KONUMDAN (x0/top) okunur:
    - Değerler iki SATIRA ayrılır (üstte Fatura+Sipariş, altta LFL
      Satış+Giriş) — ikisi arasındaki EN BÜYÜK dikey boşluk ayraçtır.
    - Her satır kendi içinde x0'a göre sıralanıp TAM ORTADAN ikiye
      bölünür (soldaki panel, sağdaki panel) — iki panel arasındaki
      boşluk bazen panel İÇİ çeyrek-grupları arasındaki boşluktan küçük
      olduğundan (ölçüldü) en büyük boşluğa göre bölmek YANLIŞ; sabit
      orta nokta güvenli.
    - Her panel içinde soldan sağa sıra hep [önceki yıl aynı çeyrek, bu
      çeyrek, (yalnızca 2Ç/3Ç/4Ç sunumlarında) önceki yıl YBİ kümülatif,
      bu yıl YBİ kümülatif] — yalnızca ilk iki (ÇEYREĞE özgü) kullanılır.
    PL payı dört değeri (Toplam/Mağaza/ebebek.com/Pazaryeri) "%" sonekiyle
    ayrı toplanır, aynı soldan-sağa sırayla."""
    with pdfplumber.open(io.BytesIO(pdf_baytlari)) as pdf:
        sayfa = None
        for p in pdf.pages:
            t = p.extract_text() or ""
            if "Aynı Mağaza (LFL)" in t and "Adet Payı" in t:
                sayfa = p
                break
        if sayfa is None:
            return None
        kelimeler = sayfa.extract_words()

    sayi_deseni = re.compile(r"^\d[\d.,]*%?$")
    yil_deseni = re.compile(r"^20\d{2}$")

    def sayiya_cevir(metin: str) -> float:
        return float(metin.replace(".", "").replace(",", "."))

    tum_sayilar = [w for w in kelimeler if sayi_deseni.match(w["text"]) and not yil_deseni.match(w["text"])]
    yuzdeli = sorted((w for w in tum_sayilar if w["text"].endswith("%")), key=lambda w: w["x0"])
    if len(yuzdeli) != 4:
        raise RuntimeError(f"ebebek PL adet payı: 4 değer bekleniyordu, {len(yuzdeli)} bulundu")
    pl_toplam, pl_magaza, pl_web, pl_pazar = (sayiya_cevir(w["text"].rstrip("%")) for w in yuzdeli)

    duz = sorted((w for w in tum_sayilar if not w["text"].endswith("%")), key=lambda w: w["top"])
    if len(duz) < 4:
        raise RuntimeError(f"ebebek fatura/sipariş/LFL: en az 4 değer bekleniyordu, {len(duz)} bulundu")
    araliklar = [(duz[i + 1]["top"] - duz[i]["top"], i) for i in range(len(duz) - 1)]
    araliklar.sort(reverse=True)
    ayrac = araliklar[0][1]
    satir1 = duz[: ayrac + 1]
    satir2 = duz[ayrac + 1 : ayrac + 1 + len(satir1)]  # dipnot/sayfa no artıklarını at

    def ikiye_bol(satir):
        satir = sorted(satir, key=lambda w: w["x0"])
        orta = len(satir) // 2
        return (
            [sayiya_cevir(w["text"]) for w in satir[:orta]],
            [sayiya_cevir(w["text"]) for w in satir[orta:]],
        )

    fatura, siparis = ikiye_bol(satir1)
    lfl_satis, lfl_giris = ikiye_bol(satir2)
    return {
        "magaza_fatura_ortalama": fatura[1], "web_siparis_ortalama": siparis[1],
        "lfl_satis_adedi": lfl_satis[1], "lfl_giris_sayisi": lfl_giris[1],
        "pl_payi_toplam": pl_toplam, "pl_payi_magaza": pl_magaza,
        "pl_payi_web": pl_web, "pl_payi_pazaryeri": pl_pazar,
    }


_KATEGORI_SIRASI = (
    "kategori_buyume_hizli_tuketim", "kategori_buyume_tamamlayici",
    "kategori_buyume_tekstil", "kategori_buyume_bebek_arac_gerec",
)


def kategori_buyumesini_ayikla(pdf_baytlari: bytes) -> dict[str, float] | None:
    """"Kategoriler arası stratejik konumlandırma..." sayfasındaki dört
    kategorinin (Hızlı Tüketim/Tamamlayıcı/Tekstil/Bebek Araç-Gereç)
    adet büyüme yüzdesini okur. Sayfa yoksa (2024 4Ç'ten önce) None
    döner.

    Büyüme rozetleri ("+%NN adet büyümesi") metinde her zaman 2x2
    kutunun SATIR sırasıyla (Hızlı Tüketim, Tamamlayıcı, Tekstil, Bebek
    Araç-Gereç) geçiyor — dört rozet güvenle sıralı okunur. Kategori
    PAYLARI (pasta grafiği, bu fonksiyonda KULLANILMIYOR — yalnızca
    yüzde büyüme card'ı hedefleniyor) ise metin sırasında karışıyor
    (kutuların açıklama metinleriyle iç içe geçiyor, ölçüldü), konumdan
    (sayfa dörtte-bir çeyreği) okunması gerekir; büyüme rozetleri bu
    sorunu yaşamıyor çünkü rozet kutucuğu kendi başına bağımsız bir metin
    bloğu."""
    with pdfplumber.open(io.BytesIO(pdf_baytlari)) as pdf:
        tam_metin = None
        for p in pdf.pages:
            t = p.extract_text() or ""
            if "stratejik konumlandırmaya" in t and "Hızlı tüketim" in t:
                tam_metin = t
                break
        if tam_metin is None:
            return None
    buyume = [
        float(m.group(1).replace(",", "."))
        for m in re.finditer(r"\+\s*%\s*(\d+(?:,\d+)?)", tam_metin)
    ]
    if len(buyume) != 4:
        raise RuntimeError(f"ebebek kategori büyümesi: 4 değer bekleniyordu, {len(buyume)} bulundu")
    return dict(zip(_KATEGORI_SIRASI, buyume))


def _sunum_metriklerini_getir(onbellek: dict, session=None) -> dict[str, dict[str, float]]:
    """Tüm "Analist Toplantısı Sunumu" PDF'lerini TARA (üç ayrı sayfa
    türü, her biri kendi varlığını kontrol eder), on sekiz metriği
    birleştirip {metrik: {tarih: değer}} döner. Çakışan çeyreklerde
    SONRAKİ (daha yeni yayımlanan) sunum kazanır.

    Sayfa bulunduğu halde ayrıştırma başarısızsa (`RuntimeError`) o
    SUNUM atlanır, tüm tarama iptal edilmez: en eski sunumlar (ör. 2024
    4Ç) daha yeni sürümlerle aynı şablonu paylaşmıyor (ölçüldü — "Pazar
    Yeri" pasta diliminin "%" işareti farklı konumlanmış), tek bir eski
    belgenin şablon sapması on sekiz metrikten hiçbirini düşürmemeli."""
    if "sunum_metrikleri" in onbellek:
        return onbellek["sunum_metrikleri"]
    if "sunumlar" not in onbellek:
        onbellek["sunumlar"] = _sunum_listesi(session=session)
    birlesik: dict[str, dict[str, float]] = {m: {} for m in GECERLI_SUNUM_METRIKLERI}
    for s in sorted(onbellek["sunumlar"], key=lambda s: (s["yil"], s["ceyrek"])):
        baytlar = _sunum_pdfsini_getir(s["url"], onbellek, session=session)
        if baytlar is None:
            continue
        ay = {1: "01", 2: "04", 3: "07", 4: "10"}[s["ceyrek"]]
        tarih = f"{s['yil']}-{ay}-01"
        for ayiklayici in (kanal_buyume_ve_payini_ayikla, fatura_siparis_pl_lfl_ayikla, kategori_buyumesini_ayikla):
            try:
                sonuc = ayiklayici(baytlar)
            except RuntimeError:
                continue  # bu sunumun bu sayfası şablon sapmış — atla, diğer sunumlar/sayfalar etkilenmez
            if sonuc:
                for metrik, deger in sonuc.items():
                    birlesik[metrik][tarih] = deger
    onbellek["sunum_metrikleri"] = birlesik
    return birlesik


def seri_cek(seri, onbellek: dict | None = None, session=None):
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `onbellek` üç aylık kategoriyi ("satis"/"ziyaret"/"magaza") ayrı ayrı
    taşır: altı seri üç kategoriyi paylaşır, aksi halde her seri kendi
    ~35 PDF'ini indirirdi. Çeyreklik "Analist Toplantısı Sunumu" metrik
    ailesi (`GECERLI_SUNUM_METRIKLERI`) dördüncü, bağımsız bir önbellek
    anahtarı ("sunum_metrikleri") kullanır — on sekiz seri aynı ~12
    sunumu paylaşır.
    """
    onbellek = {} if onbellek is None else onbellek
    metrik = seri.ebebek_metrik

    if metrik == "satis_adedi":
        if "satis" not in onbellek:
            onbellek["satis"] = satis_noktalari(session)
        kendi = dict(onbellek["satis"])
    elif metrik in ("magaza_ziyaretci", "web_ziyaret"):
        if "ziyaret" not in onbellek:
            onbellek["ziyaret"] = ziyaret_noktalari(session)
        indeks = 0 if metrik == "magaza_ziyaretci" else 1
        kendi = {tarih: deger[indeks] for tarih, deger in onbellek["ziyaret"].items()}
    elif metrik in ("toplam_magaza", "standart_magaza", "mega_magaza"):
        if "magaza" not in onbellek:
            onbellek["magaza"] = magaza_noktalari(session)
        alan = {"toplam_magaza": "toplam", "standart_magaza": "standart", "mega_magaza": "mega"}[metrik]
        kendi = {tarih: deger[alan] for tarih, deger in onbellek["magaza"].items() if alan in deger}
    elif metrik in GECERLI_SUNUM_METRIKLERI:
        harita = _sunum_metriklerini_getir(onbellek, session=session).get(metrik, {})
        if not harita:
            raise RuntimeError(f"ebebek {metrik!r} için hiçbir Analist Toplantısı Sunumu'nda değer bulunamadı")
        kendi = harita
    else:
        raise RuntimeError(f"bilinmeyen ebebek_metrik: {metrik!r} ({seri.id})")

    df = pd.DataFrame(sorted(kendi.items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)
