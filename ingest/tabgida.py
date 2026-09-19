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
biçiminde ÖNCEKİ yıl önce, CARİ yıl sonra gelir — bu yüzden `_metrik_deger`
etiketten sonraki İKİNCİ sayıyı alır (BigChefs'in ilkini aldığının tersi).

Bu adaptör yalnızca iki seriyi karşılıyor:
- `restoran-sayisi` (çeyreklik): her bültenin "toplam restoran sayımızı
  X'e ulaştırdık" / "yılı X lokasyonla kapattık" cümlesinden (iki farklı
  ifade biçimi gözlemlendi, ikisi de kabul edilir).
- `fis-sayisi` (yıllık): yalnızca 4. çeyrek (FY) bültenindeki "Önemli
  Operasyonel ve Finansal Göstergeler" tablosunun "Fiş sayısı ('000)"
  satırından — bu satır diğer çeyreklerde de var ama o çeyreğe/yarı yıla
  ait kümülatif değildir (TAM YIL değildir), bu yüzden yalnızca 4. çeyrek
  belgesi kullanılır.

Ölçüldü (2026-09-18, marketvisuals.net/tabgd.html ile birebir): FY 2025
Fiş sayısı 247.196 bin adet; 2Ç 2026 sonunda toplam restoran sayısı 2.100.

Kapsam dışı (ölçüldü): çalışan sayısı, ülke/marka bazında restoran dağılımı,
yatırım harcaması dağılımı — bültende ham alan olarak yok; yalnızca
"Yatırımcı Sunumu" sunum destesinde (grafik/görsel ağırlıklı, metin
çıkarımı güvenilir değil) olabilir, doğrulanmadı.
"""

from __future__ import annotations

import io
import re
from urllib.parse import urljoin

import pandas as pd
import pdfplumber
import requests

from ingest.ir_sunum import pdf_metnini_normallestir, tr_sayi

TABAN = "https://www.tabgida.com.tr/tr/yatirimci-iliskileri/"
SUNUM_URL = f"{TABAN}yatirimci-sunumlari"
ZAMAN_ASIMI = 60
_BASLIKLAR = {"User-Agent": "Mozilla/5.0"}

_YIL_TABLO = re.compile(
    r"<thead><tr><th>(\d{4})</th>.*?</thead>\s*<tbody>(.*?)</tbody>", re.S,
)
_CEYREK_SATIRI = re.compile(
    r'<tr><td>(\d)\.\s*Çeyrek</td>\s*<td>.*?</td>\s*'
    r'<td><a[^>]+href="([^"]+)"[^>]*>İncele</a></td>\s*</tr>',
    re.S,
)

_RESTORAN_DESENI = re.compile(
    r"toplam restoran sayımızı ([\d.]+)'?[ea] ulaştırdık"
    r"|yılı ([\d.]+) lokasyonla kapattık"
)

GECERLI_METRIKLER = {"restoran-sayisi", "fis-sayisi"}
_CEYREK_ILK_AY = {1: "01", 2: "04", 3: "07", 4: "10"}


def _bulten_listesi(session=None) -> list[dict]:
    """(yil, ceyrek_no, url) listesi — yatirimci-sunumlari sayfasından."""
    http = session or requests
    yanit = http.get(SUNUM_URL, headers=_BASLIKLAR, timeout=ZAMAN_ASIMI)
    yanit.raise_for_status()
    yanit.encoding = "utf-8"
    sonuc = []
    for yil, govde in _YIL_TABLO.findall(yanit.text):
        for ceyrek_no, goreli_url in _CEYREK_SATIRI.findall(govde):
            sonuc.append({
                "yil": int(yil),
                "ceyrek": int(ceyrek_no),
                "url": urljoin(SUNUM_URL, goreli_url),
            })
    if not sonuc:
        raise RuntimeError(
            "TAB Gıda yatırımcı sunumları sayfasında hiç 'Finansal Bülten' "
            "bağlantısı ayrıştırılamadı — şablon değişmiş olabilir"
        )
    return sonuc


def _belge_metnini_getir(url: str, onbellek: dict, session=None) -> str:
    if url in onbellek:
        return onbellek[url]
    http = session or requests
    yanit = http.get(url, headers=_BASLIKLAR, timeout=ZAMAN_ASIMI)
    yanit.raise_for_status()
    with pdfplumber.open(io.BytesIO(yanit.content)) as pdf:
        metin = pdf_metnini_normallestir("\n".join(sayfa.extract_text() or "" for sayfa in pdf.pages))
    onbellek[url] = metin
    return metin


def restoran_sayisini_ayikla(metin: str) -> float | None:
    m = _RESTORAN_DESENI.search(metin)
    if not m:
        return None
    ham = m.group(1) or m.group(2)
    return float(ham.replace(".", ""))


def fis_sayisini_ayikla(metin: str) -> float | None:
    """'Fiş sayısı ('000) ÖNCEKİ CARİ %değişim ...' satırından CARİ (ikinci)
    değeri alır. Değer zaten BİN adet cinsindendir (satır başlığı "('000)")
    — marketvisuals.net'in "Bin Adet" birimiyle birebir, AYRICA ölçeklenmez.
    """
    desen = re.compile(r"^Fiş sayısı \('000\)\s+([()%\d.,\-]+)\s+([()%\d.,\-]+)", re.M)
    m = desen.search(metin)
    if not m:
        return None
    try:
        return tr_sayi(m.group(2))
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
