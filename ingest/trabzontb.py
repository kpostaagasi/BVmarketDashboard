"""Trabzon Ticaret Borsası (TTB) günlük bülten istemcisi.

Kaynak: `tb.org.tr` "Günlük Bültenler" sayfasından linklenen PDF'ler,
`https://www.tb.org.tr/uploads/files/970-DD.MM.YYYY.pdf`. "970-" öneki
istisnasız değil (ölçüldü: 11.09.2026 bülteni `970-omer.pdf` adıyla elle
yüklenmiş) — bu yüzden URL TAHMİN EDİLİR (hızlı, listeleme sayfası
taranmaz) ve HTTP 404 hataya düşürmez, "o gün bülten yok" sayılır (hafta
sonu, resmi tatil ya da nadir elle-isimlendirme hatası — hiçbiri ayırt
edilemez, hepsi aynı şekilde atlanır).

PDF'in "KURU MEYVELER > KABUKLU FINDIKLAR" bölümünde ürün başına (aynı gün
birden çok alıcı/şekil olabilir) satır satır sütunlar var:
`AD YIL AŞAĞI YUKARI ORTALAMA MİKTAR Kg TUTAR ŞEKLİ ADEDİ`. Fiyat sütunları
(AŞAĞI/YUKARI/ORTALAMA) ondalık nokta kullanır (`186.545` = 186,545 TL);
MİKTAR binlik nokta kullanır (`6.419` = 6.419 Kg DEĞİL, 6419 Kg — ölçüldü:
Tutar/Miktar oranı yalnızca bu yorumla ORTALAMA'ya yakın çıkıyor). TUTAR
AYRICA virgül-binlik/nokta-ondalık (İngilizce) biçiminde (`1,197,341.85`) —
üç sütun üç farklı biçim taşıdığı için TUTAR hiç okunmuyor; MarketVisuals'ın
"Ağırlıklı Ortalama" kartı yalnızca ORTALAMA×MİKTAR/ΣMİKTAR ile üretiliyor
(İTB'nin `ingest.istib.urun_agirlikli_fiyat`ıyla birebir aynı ilke: bir
satırın ORTALAMA'sı kendi Tutar/Miktar'ına tam eşit değil — küçük yuvarlama
farkı var, kaynağın kendi ORTALAMA'sı esas alınır).

Doğrulandı (2026-09-20, `pdfplumber` ile ham metin — `markit`/OCR
dönüştürücüleri Türkçe büyük harfleri bozuyor, KULLANILMADI):
- 18.09.2026 bülteni: "KABUKLU TOMBUL FINDIK(LEVANT)" tek satır, 189.659
  TL/kg → MarketVisuals "Fındık Levant (Ağ. Ort.)" `latestVal` 189.66 ile
  birebir.
- 14.09.2026 bülteni: "...(YAĞLI)" 3 satır (186.545×6419 + 210.116×870 +
  204.930×6554) / (6419+870+6554) = 196.7308 → MarketVisuals "Fındık
  Yağlık (Ağ. Ort.)" `latestVal` 196.73 ile birebir.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from io import BytesIO

import pandas as pd
import pdfplumber
import requests

from core.catalog import Seri

TABAN = "https://www.tb.org.tr/uploads/files/970-{gun}.pdf"
ZAMAN_ASIMI = 30
# ~13 ay: bir tam fındık hasat sezonunu (Ağustos-Ekim) YoY karşılaştırmaya
# yeter; günlük bülten olduğu için istib.py'nin 104 haftalık (yaklaşık 2
# yıllık) penceresinin izinde ama koşu süresini (400 ayrı PDF isteği)
# katlanılabilir tutmak için yarıya yakın kesildi.
AZAMI_GERI_GUN = 400

# Katalogdaki `trabzontb_urun` -> bültendeki tam ürün adı.
URUN_ESLEME = {
    "findik-yaglik": "KABUKLU TOMBUL FINDIK(YAĞLI)",
    "findik-levant": "KABUKLU TOMBUL FINDIK(LEVANT)",
}

_SATIR_RE = re.compile(
    r"^(KABUKLU TOMBUL FINDIK\((?:YAĞLI|LEVANT)\))\s+\d{4}\s+"
    r"[\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)\s+Kg\b"
)


def agirlikli_ortalama(satirlar: list[tuple[float, float]]) -> float:
    """`(ortalama, miktar)` çiftlerinden miktar ağırlıklı ortalama üretir."""
    toplam_miktar = sum(miktar for _, miktar in satirlar)
    if toplam_miktar <= 0:
        raise RuntimeError("Trabzon TB: sıfır miktarlı satırlardan ortalama hesaplanamaz")
    return sum(ortalama * miktar for ortalama, miktar in satirlar) / toplam_miktar


def bulten_satirlarini_cikar(metin: str) -> dict[str, list[tuple[float, float]]]:
    """Bülten metninden bültendeki ürün adı -> `[(ortalama, miktar), ...]` çıkarır."""
    sonuc: dict[str, list[tuple[float, float]]] = {}
    for satir in metin.splitlines():
        eslesme = _SATIR_RE.match(satir.strip())
        if not eslesme:
            continue
        urun, ortalama_ham, miktar_ham = eslesme.groups()
        ortalama = float(ortalama_ham)
        miktar = float(miktar_ham.replace(".", ""))
        sonuc.setdefault(urun, []).append((ortalama, miktar))
    return sonuc


def gunleri_uret(bugun: date, adet: int = AZAMI_GERI_GUN) -> list[date]:
    """`bugun`den geriye, en eskiden en yeniye sıralı `adet` takvim günü."""
    return [bugun - timedelta(days=i) for i in range(adet)][::-1]


def bulten_cek(gun: date, session: requests.Session | None = None) -> str | None:
    """O günün bülten PDF'inin tüm sayfa metnini birleştirip döner; HTTP 404'te `None`."""
    http = session or requests
    url = TABAN.format(gun=gun.strftime("%d.%m.%Y"))
    yanit = http.get(url, timeout=ZAMAN_ASIMI)
    if yanit.status_code == 404:
        return None
    if yanit.status_code != 200:
        raise RuntimeError(f"Trabzon TB HTTP {yanit.status_code} ({gun.isoformat()})")

    with pdfplumber.open(BytesIO(yanit.content)) as pdf:
        return "\n".join(sayfa.extract_text() or "" for sayfa in pdf.pages)


def _tum_noktalari_getir(onbellek: dict, bugun: date,
                          session: requests.Session | None = None) -> dict[str, list[tuple[str, float]]]:
    """Tüm gün pencerelerini bir kez çeker; 2 ürün aynı günlük bültenleri paylaşır."""
    if "noktalar" in onbellek:
        return onbellek["noktalar"]

    noktalar: dict[str, list[tuple[str, float]]] = {ad: [] for ad in URUN_ESLEME.values()}
    for gun in gunleri_uret(bugun):
        metin = bulten_cek(gun, session=session)
        if metin is None:
            continue
        for urun_adi, satirlar in bulten_satirlarini_cikar(metin).items():
            if urun_adi in noktalar:
                noktalar[urun_adi].append((gun.isoformat(), agirlikli_ortalama(satirlar)))

    onbellek["noktalar"] = noktalar
    return noktalar


def seri_cek(seri: Seri, onbellek: dict | None = None, session: requests.Session | None = None,
             bugun: date | None = None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı)."""
    onbellek = onbellek if onbellek is not None else {}
    bugun = bugun or date.today()
    urun_adi = URUN_ESLEME[seri.trabzontb_urun]

    tum_noktalar = _tum_noktalari_getir(onbellek, bugun, session=session)
    noktalar = tum_noktalar.get(urun_adi, [])
    if not noktalar:
        raise RuntimeError(f"Trabzon TB: {urun_adi} için hiç veri yok")

    return pd.DataFrame(noktalar, columns=["date", "value"])
