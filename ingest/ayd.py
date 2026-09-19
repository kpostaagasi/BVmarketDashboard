"""AYD (Alışveriş Merkezleri ve Yatırımcıları Derneği) & Akademetre Research
"AVM Metrekare Verimlilik Endeksi" aylık bülteni istemcisi.

Kaynak yapılandırılmış bir dosya (XLSX/PDF/API) DEĞİL: her ay
`https://www.ayd.org.tr/<ay-adı>-<yıl>-ciro-endeksi` adresinde yayımlanan bir
duyuru sayfası (serbest metin). Site sitemap/arşiv sunmuyor (ölçüldü
2026-09-19: `arsiv.ayd.org.tr` 503, ana sitede sitemap.xml/haberler sayfası
yalnızca son birkaç ayı listeliyor) — bu yüzden ay URL'leri BURADA
üretiliyor (Türkçe ay adı + yıl) ve tek tek denenir; 404 = o ay için
bülten YOK (gerçek eksiklik, şablon kayması değil — atlanır).

Ölçüldü: bu slug kalıbı yalnızca 2025-01'den itibaren güvenilir çözülüyor;
öncesi (2024 ve öncesi) farklı bir slug şeması kullanıyor ("2024 Yıllık
Bülten" gibi ayrı yıllık sayfalar) ve tahmin edilebilir değil — bu yüzden
`ILK_YIL = 2025`. 2025-05 bilinen tek gerçek boşluk (o ay hiç yayımlanmamış,
ne kanonik ne alternatif slug'da bulunuyor).

Yalnızca ENDEKS SEVİYESİ (puan, Baz 2010=100) ingest edilir. Sayfa
metnindeki "yüzde XX artarak" ifadesi AYRI SERİ DEĞİLDİR: YoY/MoM büyüme
`core/stats.py` katmanında ardışık seviye değerlerinden hesaplanmalı — bu
zaten seviyenin kendisinden türetilebilir (ölçüldü: 5/6 ay için
[Temmuz'26/Temmuz'25, Haziran, Mart, Şubat, Nisan] bağımsız hesaplanan YoY,
sayfanın kendi metnindeki yüzde ile birebir eşleşti; yalnızca Ocak'26 farklı
çıktı — AYD/Akademetre'nin ara sıra metodoloji/baz revizyonu yaptığı
anlaşılıyor, bu METİN değil SEVİYE ingest edilerek en tutarlı yaklaşım).

Sayı biçimi ay ay değişiyor: bazı aylar "5.169 puan" (binlik nokta), bazıları
"5004 puan"/"5004 puana" (ayraçsız) yazıyor — `_PUAN_DESENI` ikisini de
karşılar.
ölçüldü 2026-09-18: "TrustSafe TLS RSA SubCA R1" + "E-Tugra TLS RSA CA R1"
ara sertifikaları certifi'de yok, sunucu da yalnızca yaprak sertifikayı
gönderiyor (`requests`: `SSLError: unable to get local issuer certificate`;
`curl`/macOS anahtarlığı sorunsuz — işletim sistemi zinciri tamamlıyor).
`verify=False` KULLANILMAZ; iki ara sertifika de certifi'ye eklenip kök
(SSL.com Root Certification Authority RSA, certifi'de zaten var) kadar
doğrulanıyor (bkz. `_ca_paketi`, `ingest/bddk.py`'deki desenle birebir).
"""

from __future__ import annotations

import re
import ssl
import tempfile
from datetime import date

import certifi
import pandas as pd
import requests

TABAN = "https://www.ayd.org.tr"
ZAMAN_ASIMI = 30
ILK_YIL = 2025
# CA Issuers (AIA) zincirinden alındı: yaprak -> TrustSafe SubCA -> E-Tugra CA
# -> SSL.com Root (certifi'de mevcut).
ARA_SERTIFIKA_URLLERI = (
    "http://cert.ssl.com/TrustSafe-TLS-I-RSA-R1.cer",
    "http://cert.ssl.com/ETugra-TLS-T-RSA-R1.cer",
)

_AY_SLUG = {
    1: "ocak", 2: "subat", 3: "mart", 4: "nisan", 5: "mayis", 6: "haziran",
    7: "temmuz", 8: "agustos", 9: "eylul", 10: "ekim", 11: "kasim", 12: "aralik",
}

# Gövde metni içinde ("...puan" ya da "...puana"/"...puanı" öncesi sayı);
# binlik nokta varsa onu, yoksa 3-5 haneli düz sayıyı yakalar. Sıra önemli:
# alternatifin ilk kolu (noktalı) önce denenir.
_PUAN_DESENI = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d{3,5})\s*puan")

_ca_yolu: str | None = None


def _ca_paketi(session=None) -> str:
    """certifi + AYD'nin göndermediği ara sertifikalar. Süreç başına bir kez."""
    global _ca_yolu
    if _ca_yolu is not None:
        return _ca_yolu
    http = session or requests
    pemler = []
    for url in ARA_SERTIFIKA_URLLERI:
        yanit = http.get(url, timeout=ZAMAN_ASIMI)
        if yanit.status_code != 200:
            raise RuntimeError(f"AYD: ara sertifika indirilemedi ({url}): HTTP {yanit.status_code}")
        ham = yanit.content
        pemler.append(ham.decode() if ham.startswith(b"-----") else ssl.DER_cert_to_PEM_cert(ham))
    dosya = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
    dosya.write(certifi.contents() + "\n" + "\n".join(pemler))
    dosya.close()
    _ca_yolu = dosya.name
    return _ca_yolu


def ay_url(yil: int, ay: int) -> str:
    return f"{TABAN}/{_AY_SLUG[ay]}-{yil}-ciro-endeksi"


def _govdeyi_ayikla(html: str) -> str:
    idx = html.find("content_box activityDescription")
    if idx == -1:
        raise RuntimeError("AYD: içerik kutusu ('content_box activityDescription') bulunamadı — şablon değişmiş olabilir")
    return html[idx: idx + 2000]


def puan_cek(html: str) -> float:
    """Bültenin gövde metninden endeks seviyesini (puan) çıkarır."""
    govde = _govdeyi_ayikla(html)
    m = _PUAN_DESENI.search(govde)
    if not m:
        raise RuntimeError("AYD: gövde metninde '<sayı> puan' bulunamadı — şablon değişmiş olabilir")
    return float(m.group(1).replace(".", ""))


def _ay_getir(session: requests.Session, yil: int, ay: int) -> float | None:
    yanit = session.get(ay_url(yil, ay), timeout=ZAMAN_ASIMI, verify=_ca_paketi(session))
    if yanit.status_code == 404:
        return None
    yanit.raise_for_status()
    return puan_cek(yanit.text)


def cekilecek_donemler(bugun: date) -> list[tuple[int, int]]:
    donemler = []
    for yil in range(ILK_YIL, bugun.year + 1):
        son_ay = 12 if yil < bugun.year else bugun.month
        for ay in range(1, son_ay + 1):
            donemler.append((yil, ay))
    return donemler


def _tum_noktalari_getir(onbellek: dict, session=None, bugun: date | None = None) -> list[tuple[str, float]]:
    if "noktalar" in onbellek:
        return onbellek["noktalar"]
    http = session or requests.Session()
    http.headers.setdefault("User-Agent", "Mozilla/5.0")
    bugun = bugun or date.today()
    noktalar = []
    for yil, ay in cekilecek_donemler(bugun):
        puan = _ay_getir(http, yil, ay)
        if puan is not None:
            noktalar.append((date(yil, ay, 1).isoformat(), puan))
    if not noktalar:
        raise RuntimeError("AYD: hiçbir aydan endeks seviyesi okunamadı")
    onbellek["noktalar"] = noktalar
    return noktalar


def seri_cek(seri, *, onbellek: dict | None = None, session=None, bugun: date | None = None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `date` ayın 1'i. Tek seri (`AVM Ciro Endeksi`, puan) — çoklu eksen yok.
    """
    onbellek = onbellek if onbellek is not None else {}
    noktalar = _tum_noktalari_getir(onbellek, session, bugun)
    return pd.DataFrame(noktalar, columns=["date", "value"])
