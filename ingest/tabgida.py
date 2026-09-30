"""TAB Gıda (Burger King/Popeyes/Arby's/Sbarro/Usta Dönerci/Usta Pideci/
Subway Türkiye ana bayii) çeyreklik "Finansal Bülten" PDF istemcisi.

TAB Gıda BIST'te işlem görmüyor (TABGD, marketvisuals.net'in dahili kısa
kodu) — tahvil yatırımcıları için gönüllü şeffaflık amacıyla
`tabgida.com.tr/tr/yatirimci-iliskileri/yatirimci-sunumlari` sayfasında yıl
başlıklı statik bir tabloda çeyreklik "Finansal Bülten" (temiz metin/tablo,
sunum destesi DEĞİL) yayımlıyor. Tablo satırı zaten "N. Çeyrek" etiketi
taşıdığından dönem, PDF içeriği ayrıştırılmadan doğrudan (yıl, çeyrek no)
ikilisinden biliniyor — 4. çeyrek satırı FY (tam yıl) bültenine işaret
ediyor.

**Sütun sırası BigChefs'in TERSİ**: "(milyon TL) | 2Ç 2025 | 2Ç 2026 | ... "
biçiminde ÖNCEKİ yıl önce, CARİ yıl sonra gelir.

Bu adaptör yalnızca iki seriyi karşılıyor:
- `restoran-sayisi` (çeyreklik): bültenin işletme özeti paragrafındaki
  toplam restoran/lokasyon cümlesinden. İFADE BİÇİMİ ÇEYREKTEN ÇEYREĞE
  DEĞİŞİR, ölçülen beş biçim (`_RESTORAN_DESENI`):
    * "restoran sayımızı 1.654'e çıkardık" / "toplam restoran sayımızı
      1.572'ye çıkardık" — iki ayrım var: `toplam` kelimesi BAZI
      çeyreklerde yok ve sonek `e` ya da `ye` (1Ç24, 3Ç23, 2Ç24, 3Ç25)
    * "toplam restoran sayımızı 2.100'e ulaştırdık" (2Ç26) — cümle metin
      satır ortasında bölündüğü için aradaki boşluk için `\\s` eşleşmesi şart
    * "yılı 2.030 lokasyonla kapattık"                (4Ç25)
    * "toplamda 1.830 lokasyona ulaştık" / "portföyümüzü 1.906 lokasyona
      genişlettik" / "restoran portföyümüz 1.854 lokasyona ulaştı" /
      "1.615 restorana ulaştık"                       (4Ç23, 4Ç24, 1Ç25, 2Ç25)
  ELENEN (çeyreklik toplam bildirmeyen, yalnızca "N yeni restoran açtık"
  diyen): 3Ç24, 1Ç26 — bu çeyreklerde sayı yok, seri o dönem boş kalır.
- `fis-sayisi` (yıllık): yalnızca 4. çeyrek (FY) bültenindeki "Önemli
  Operasyonel ve Finansal Göstergeler" tablosunun fiş sayısı satırından.
  4. çeyrek bültenlerinde tablo 4Ç ve FY olmak üzere İKİ çift gösterir:
  `Fiş sayısı ('000) 47.287 47.081 %0 183.140 203.718 %11` → FY 2023
  DEĞERİ beşinci alandır (203.718), ikincisi 4Ç 2023'tür (47.081).
  Sadece FY özeti olan tabloda (`Fiş sayısı ('000) 183.140 203.718 %11`)
  dört değer yoktur ve ikinci alan zaten FY'dir. 4Ç 2024 tek çeyrekte
  İngilizce yayımlandı: satır etiketi `Number of tickets ('000)` — iki
  etiket de kabul edilir. Elenen: 4Ç bültenindeki 4Ç değeri (kümülatif
  değil) ve metin içindeki "Fiş sayısı 51,3 milyona ulaşarak" anlatım
  cümlesi.

Ölçüldü (30 Eylül 2026, canlı): 12 bültenin 12'si de okundu. Seri
çıktıları: `restoran-sayisi` 10 çeyrek (3Ç23 1.572 → 2Ç26 2.100, artan),
`fis-sayisi` 3 yıl (FY2023 203.718 / FY2024 207.648 / FY2025 247.196 bin
adet — 2024 bülteni İngilizce olduğu için etiket eşleşmesi şarttı).

**TLS/WAF (ölçüldü 30 Eylül 2026, sistemsik).** `tabgida.com.tr`
Python'ın varsayılan şifre listesini (`@SECLEVEL=2:...:!SHA1:!AESCCM`)
teklif eden ClientHello'yu `ConnectionResetError(54)` ile sıfırlıyor —
`curl`, `urllib` ve `requests` FARK YOK; hepsi aynı OpenSSL bağlamını
paylaşıyor. WAF'ın kabul ettiği tek ayrım `!SHA1` kaldırılmış listedir
(`:!AESCCM` yeterli değil, `AES256-SHA` eklemek de yetmez — OpenSSL'de
negasyonlar sonraki girdileri de siler). `_WafAdapter` bunu yapar. Bu
makinede `!SHA1`'sız liste 4/4, varsayılan liste 0/4 el bağlantı kuruyor.

**Göreli yol çözümü (ölçüldü 30 Eylül 2026).** Sayfa `/tr/yatirimci-
iliskileri/` altında ama CMS dosyaları site KÖKÜNDE: `href="../cmsfiles/..."`
satırından türetilen `urljoin` `/tr/cmsfiles/...` veriyor ve o yol 404 → ana
sayfaya YÖNLENDİRME döndürüyor (200 `text/html`, 36.378 bayt — PDF değil).
Bu yüzden göreli yol köke göre çözülür, baştaki `../` atılır.

**Bozuk `href` (ölçüldü 30 Eylül 2026, 2024/4.Çeyrek).** Ham HTML'de
`href="<../cmsfiles/..."` — baştaki `<` fazlalık. `.strip("<> ")` bunu
onar; onarılamayan (boş/hâlâ `<` içeren) bağlantı AYRIŞTIRICIYI DÜŞÜRMEZ,
atlanır. Daha önce buradaki tek bozuk satır `_belge_metnini_getir` içinde
tüm seriyi öldürüyordu.

Kapsam dışı (ölçüldü): çalışan sayısı, ülke/marka bazında restoran dağılımı,
yatırım harcaması dağılımı — bültende ham alan olarak yok.
"""

from __future__ import annotations

import io
import re
import ssl
from urllib.parse import urljoin

import pandas as pd
import pdfplumber
import requests
from requests.adapters import HTTPAdapter

from ingest.ir_sunum import pdf_metnini_normallestir, tr_sayi

TABAN = "https://www.tabgida.com.tr/tr/yatirimci-iliskileri/"
SUNUM_URL = f"{TABAN}yatirimci-sunumlari"
_KOK = "https://www.tabgida.com.tr/"
ZAMAN_ASIMI = 60
_BASLIKLAR = {"User-Agent": "Mozilla/5.0"}

# WAF'ın kabul ettiği şifre listesi: Python varsayılanı (`ssl` modülünün
# `_DEFAULT_CIPHERS`) SONUNDA `!SHA1` ile SHA1 CBC paketlerini eliyor ve
# sunucu bu ClientHello'yu sıfırlıyor. `!AESCCM` kaldırılmış hâli yeterli.
_SIFRE_LISTESI = "@SECLEVEL=2:ECDH+AESGCM:ECDH+CHACHA20:ECDH+AES:DHE+AES:!aNULL:!eNULL:!aDSS:!AESCCM"


class _WafAdapter(HTTPAdapter):
    """`!SHA1` içermeyen şifre listesiyle bağlanır — aksi hâlde WAF el
    sıfırlıyor (docstring'deki ölçüm)."""

    def init_poolmanager(self, *args, **kwargs):
        baglam = ssl.create_default_context()
        baglam.set_ciphers(_SIFRE_LISTESI)
        kwargs["ssl_context"] = baglam
        return super().init_poolmanager(*args, **kwargs)


def _oturum(session=None) -> requests.Session:
    """Bu kaynak için WAF uyumlu TLS bağdaştırıcısını bağlar.

    `ingest.run` koşu boyunca paylaşılan TEK bir `requests.Session` verir ve
    o oturumun `https://` bağdaştırıcısı varsayılan şifre listesiyle
    çalışır — WAF onu sıfırlar. Bu yüzden sunucuya ÖZGÜ önek
    (`https://www.tabgida.com.tr`) bağdaştırıcısı değiştirilir; diğer
    kaynakların oturumu olduğu gibi kalır."""
    oturum = session if session is not None else requests.Session()
    if not isinstance(oturum.get_adapter(SUNUM_URL), _WafAdapter):
        oturum.mount("https://www.tabgida.com.tr", _WafAdapter(max_retries=2))
    return oturum


_YIL_TABLO = re.compile(
    r"<thead><tr><th>(\d{4})</th>.*?</thead>\s*<tbody>(.*?)</tbody>", re.S,
)
_CEYREK_SATIRI = re.compile(
    r'<tr><td>(\d)\.\s*Çeyrek</td>\s*<td>.*?</td>\s*'
    r'<td><a[^>]+href="([^"]+)"[^>]*>İncele</a></td>\s*</tr>',
    re.S,
)

_RESTORAN_DESENI = re.compile(
    r"(?:toplam\s+)?restoran sayımızı\s+([\d.]+)'y?[ea]\s+(?:ulaştırdık|çıkardık)"
    r"|yılı\s+([\d.]+)\s+lokasyonla kapattık"
    r"|toplam(?:da)?\s+([\d.]+)\s+lokasyona ulaştık"
    r"|portföyümüzü\s+([\d.]+)\s+lokasyona genişlettik"
    r"|restoran portföyümüz\s+([\d.]+)\s+lokasyona ulaştı"
    r"|([\d.]+)\s+restorana ulaştık"
)

GECERLI_METRIKLER = {"restoran-sayisi", "fis-sayisi"}
_CEYREK_ILK_AY = {1: "01", 2: "04", 3: "07", 4: "10"}


def _bulten_listesi(session=None) -> list[dict]:
    """(yil, ceyrek_no, url) listesi — yatirimci-sunumlari sayfasından."""
    http = _oturum(session)
    yanit = http.get(SUNUM_URL, headers=_BASLIKLAR, timeout=ZAMAN_ASIMI)
    yanit.raise_for_status()
    yanit.encoding = "utf-8"
    sonuc = []
    for yil, govde in _YIL_TABLO.findall(yanit.text):
        for ceyrek_no, goreli_url in _CEYREK_SATIRI.findall(govde):
            # 2024/4.Çeyrek satırının href'i baştaki `<` ile bozuk geliyor
            # ("<../cmsfiles/..."). Ayırıcı temizlenir; temizlenemeyen
            # bağlantı atlanır — ayrıştırıcıyı düşürmemek için.
            temiz = goreli_url.strip("<> ")
            if not temiz or "<" in temiz:
                continue
            # CMS dosyaları sayfadan değil site KÖKÜNDE (docstring ölçümü):
            # `../` atılıp köke göre çözülür.
            sonuc.append({
                "yil": int(yil),
                "ceyrek": int(ceyrek_no),
                "url": urljoin(_KOK, temiz.lstrip("./")),
            })
    if not sonuc:
        raise RuntimeError(
            "TAB Gıda yatırımcı sunumları sayfasında hiç 'Finansal Bülten' "
            "bağlantısı ayrıştırılamadı — şablon değişmiş olabilir"
        )
    return sonuc


def _belge_metnini_getir(url: str, onbellek: dict, session=None) -> str | None:
    """Belge metnini döndürür; 404/bozuk dosyada `None` — TEK bozuk bülten
    seriyi düşürmemeli (liste zaten boşsa `seri_cek` zaten hata veriyor)."""
    if url in onbellek:
        return onbellek[url]
    http = _oturum(session)
    try:
        yanit = http.get(url, headers=_BASLIKLAR, timeout=ZAMAN_ASIMI)
    except requests.RequestException:
        onbellek[url] = None
        return None
    if yanit.status_code != 200 or not yanit.content.startswith(b"%PDF"):
        # CMS yolu tutmazsa sunucu 200 döndürüp ana sayfaya YÖNLENDİRİR
        # (ölçüldü: 36.378 bayt `text/html`); PDF imzası yoksa PDF değildir.
        onbellek[url] = None
        return None
    with pdfplumber.open(io.BytesIO(yanit.content)) as pdf:
        metin = pdf_metnini_normallestir("\n".join(sayfa.extract_text() or "" for sayfa in pdf.pages))
    onbellek[url] = metin
    return metin


def restoran_sayisini_ayikla(metin: str) -> float | None:
    """Toplam restoran/lokasyon cümlesinden değeri alır (biçimler ve elenen
    alternatifler modül docstring'inde — canlı 12 bültenin 10'u eşleşiyor)."""
    m = _RESTORAN_DESENI.search(metin)
    if not m:
        return None
    ham = next(g for g in m.groups() if g)
    return float(ham.replace(".", ""))


def fis_sayisini_ayikla(metin: str) -> float | None:
    """"Fiş sayısı ('000) ..." satırından FY değerini alır.

    Değer zaten BİN adet cinsindendir (satır başlığı "('000)") — ayrıca
    ölçeklenmez. 4.Ç bültenlerinde satır 4Ç ve FY olmak üzere iki çift
    gösterir (`... %0 183.140 203.718 %11`); FY **beşinci** alandadır, ikinci
    alan 4Ç'dir. Yalnızca FY özeti olan tabloda üçüncü alan yoktur ve
    ikinci alan zaten FY'dir. 2024 tek çeyrekte satır İngilizce
    ("Number of tickets") — iki etiket de kabul edilir.
    """
    desen = re.compile(
        r"^(?:Fiş sayısı|Number of tickets) \('000\)\s+(.+)$", re.M,
    )
    m = desen.search(metin)
    if not m:
        return None
    # Değer alanlarını topla; YÜZDE değişim alanları elenir.
    sayilar = [a for a in m.group(1).split() if not a.startswith("%")]
    if len(sayilar) < 2:
        return None
    # 4Ç+FY tablosunda 4 değer var (4Ç öncü, 4Ç cari, FY öncü, FY cari) →
 # FY cari dördüncüsü; sadece FY tablosunda 2 değer var → ikincisi.
    ham = sayilar[3] if len(sayilar) >= 4 else sayilar[1]
    try:
        return tr_sayi(ham)
    except ValueError:
        return None


def seri_cek(seri, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı)."""
    onbellek = onbellek if onbellek is not None else {}
    metrik = seri.tabgida_metrik
    if metrik not in GECERLI_METRIKLER:
        raise RuntimeError(f"Bilinmeyen tabgida_metrik: {metrik!r}")

    if "bultenler" not in onbellek:
        onbellek["bultenler"] = _bulten_listesi(session=session)
    bultenler = onbellek["bultenler"]

    noktalar: list[tuple[str, float]] = []
    if metrik == "restoran-sayisi":
        for b in bultenler:
            metin = _belge_metnini_getir(b["url"], onbellek, session=session)
            if metin is None:  # bozuk/erişilemeyen bülten; sağlam olanlar sürer
                continue
            deger = restoran_sayisini_ayikla(metin)
            if deger is None:
                continue
            tarih = f"{b['yil']}-{_CEYREK_ILK_AY[b['ceyrek']]}-01"
            noktalar.append((tarih, deger))
    else:  # fis-sayisi: yalnızca 4. çeyrek (FY) bültenleri
        for b in bultenler:
            if b["ceyrek"] != 4:
                continue
            metin = _belge_metnini_getir(b["url"], onbellek, session=session)
            if metin is None:
                continue
            deger = fis_sayisini_ayikla(metin)
            if deger is None:
                continue
            noktalar.append((f"{b['yil']}-10-01", deger))

    if not noktalar:
        raise RuntimeError(
            f"TAB Gıda {metrik!r} için taranan {len(bultenler)} bültenin "
            "hiçbirinde değer bulunamadı — şablon değişmiş olabilir"
        )
    df = (
        pd.DataFrame(noktalar, columns=["date", "value"])
        .drop_duplicates("date", keep="last")
        .sort_values("date")
        .reset_index(drop=True)
    )
    return df
