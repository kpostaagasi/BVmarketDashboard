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


def seri_cek(seri, onbellek: dict | None = None, session=None):
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `onbellek` üç kategoriyi ("satis"/"ziyaret"/"magaza") ayrı ayrı taşır: altı
    seri üç kategoriyi paylaşır, aksi halde her seri kendi ~35 PDF'ini
    indirirdi.
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
    else:
        raise RuntimeError(f"bilinmeyen ebebek_metrik: {metrik!r} ({seri.id})")

    df = pd.DataFrame(sorted(kendi.items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)
