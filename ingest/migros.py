"""Migros Ticaret A.Ş. (BIST: MGROS) "Ara Dönem Faaliyet Raporu" PDF istemcisi.

`migroskurumsal.com/yatirimci-iliskileri/finansal-bilgiler` sayfası her yıl
için üç ayrı "Migros Ticaret Ara Dönem Faaliyet Raporu {Mart|Haziran|Eylül}"
satırı listeliyor (4. çeyrek/yıl sonu AYRI bir belge ailesinde —
"Migros Entegre Faaliyet Raporu {Yıl}", çok daha uzun ve farklı yapıda,
bu adaptörün KAPSAMI DIŞINDA bırakıldı, bkz. aşağı). Her ara dönem raporunun
"Operasyonel Faaliyetler" bölümünde tek bir cümle dönem sonu mağaza
envanterini veriyor: "Şirketimiz, [TARİH] itibarıyla yurt içinde N coğrafi
bölgede ... olmak üzere toplam T mağazaya ulaştı."

**Bu, marketvisuals.net'in AYLIK "Toplam Mağaza Sayısı" kartıyla AYNI
KADANS DEĞİL** — yalnızca üç çeyrek-sonu anlık görüntüsü (Mart/Haziran/Eylül
sonu) veriyor, ayın her biri için değil. Migros'un KAP'a yaptığı aylık
mağaza sayısı bildirimi bu şirket sitesinde AYNA'LANMIYOR (BigChefs'in
aksine) — yalnızca KAP'ın kendisinden (resmî ama JS-render'lı SPA, yalnızca
gayrı-resmî/tersine-mühendislik API'si var) erişilebilir, bu yüzden aylık
seri KAPSAM DIŞI bırakıldı (bkz. ölçüm raporu). Bu adaptör yalnızca genuine
(gerçek, kümülatif olmayan anlık görüntü) çeyreklik veriyi sunuyor.

Ölçüldü (2026-09-18, marketvisuals.net/mgros.html'deki Haziran 2026 ayı
değeriyle birebir): 30 Haziran 2026 itibarıyla toplam mağaza sayısı 3.830.

4. çeyrek/yıl sonu KAPSAM DIŞI: "Migros Entegre Faaliyet Raporu" belgesinin
aynı cümleyi taşıyıp taşımadığı doğrulanmadı (belge çok daha uzun,
sürdürülebilirlik/kurumsal yönetim ağırlıklı — aynı tek-cümlelik özet
garanti değil).
"""

from __future__ import annotations

import io
import re

import pandas as pd
import pdfplumber
import requests

from ingest.ir_sunum import pdf_ayikla, pdf_metnini_normallestir

TABAN = "https://www.migroskurumsal.com/yatirimci-iliskileri/finansal-bilgiler"
ZAMAN_ASIMI = 60
_BASLIKLAR = {"User-Agent": "Mozilla/5.0"}

_AYLAR = {"mart": "03", "haziran": "06", "eylül": "09", "eylul": "09"}

_ARA_DONEM_SATIRI = re.compile(
    r'<td>Migros Ticaret Ara Dönem Faaliyet Raporu (\w+)</td>\s*'
    r'<td align="center">(\d{4})</td>\s*'
    r'<td align="center"><a href="([^"]+)"',
)

# İki farklı ifade kalıbı gözlemlendi: bazı çeyreklerde format bazında
# ayrıntılı döküm ("... olmak üzere toplam N mağazaya ulaştı"), bazılarında
# yalnızca özet cümle ("[TARİH] itibarıyla toplam mağaza sayısı N oldu").
_MAGAZA_CUMLESI = re.compile(
    r"itibarıyla\s+yurt\s+içinde\s+\d+\s+coğrafi\s+bölgede\s+.+?\s+olmak\s+üzere\s+"
    r"toplam\s+([\d.]+)\s+mağazaya\s+ulaştı",
    re.S,
)
_MAGAZA_CUMLESI_OZET = re.compile(
    r"itibarıyla\s+toplam\s+mağaza\s+sayısı\s+([\d.]+)\s+oldu",
)

GECERLI_METRIKLER = {"toplam-magaza-sayisi"}


def _rapor_listesi(session=None) -> list[dict]:
    http = session or requests
    yanit = http.get(TABAN, headers=_BASLIKLAR, timeout=ZAMAN_ASIMI)
    yanit.raise_for_status()
    yanit.encoding = "utf-8"
    sonuc = []
    for ay_adi, yil, url in _ARA_DONEM_SATIRI.findall(yanit.text):
        ay = _AYLAR.get(ay_adi.lower())
        if ay is None:
            continue
        sonuc.append({"tarih": f"{yil}-{ay}-01", "url": url})
    if not sonuc:
        raise RuntimeError(
            "Migros finansal bilgiler sayfasında hiç 'Ara Dönem Faaliyet "
            "Raporu' bağlantısı ayrıştırılamadı — şablon değişmiş olabilir"
        )
    return sonuc


def magaza_sayisini_ayikla(metin: str) -> float | None:
    m = _MAGAZA_CUMLESI.search(metin) or _MAGAZA_CUMLESI_OZET.search(metin)
    if not m:
        return None
    return float(m.group(1).replace(".", ""))


def _belge_metnini_getir(url: str, onbellek: dict, session=None) -> str | None:
    """Belge metnini döner; kaynak kalıcı olarak yok olmuşsa (404 —
    eski yıllardaki dosya bağlantılarında ölçülen link çürümesi, ör.
    2012 "Ara Dönem Faaliyet Raporu Eylül") None döner. Başka bir HTTP
    hatası ya da ayrıştırma hatası olağan şekilde yükselir (fail loud)."""
    if url in onbellek:
        return onbellek[url]
    http = session or requests
    yanit = http.get(url, headers=_BASLIKLAR, timeout=ZAMAN_ASIMI)
    if yanit.status_code == 404:
        onbellek[url] = None
        return None
    yanit.raise_for_status()
    baytlar = pdf_ayikla(yanit.content)
    with pdfplumber.open(io.BytesIO(baytlar)) as pdf:
        metin = pdf_metnini_normallestir("\n".join(sayfa.extract_text() or "" for sayfa in pdf.pages))
    onbellek[url] = metin
    return metin


def seri_cek(seri, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı)."""
    onbellek = onbellek if onbellek is not None else {}
    metrik = seri.migros_metrik
    if metrik not in GECERLI_METRIKLER:
        raise RuntimeError(f"Bilinmeyen migros_metrik: {metrik!r}")

    if "raporlar" not in onbellek:
        onbellek["raporlar"] = _rapor_listesi(session=session)
    raporlar = onbellek["raporlar"]

    noktalar: list[tuple[str, float]] = []
    for r in raporlar:
        metin = _belge_metnini_getir(r["url"], onbellek, session=session)
        if metin is None:  # 404 — belge kalıcı olarak yok, dönem atlanır
            continue
        deger = magaza_sayisini_ayikla(metin)
        if deger is None:
            continue
        noktalar.append((r["tarih"], deger))

    if not noktalar:
        raise RuntimeError(
            f"Migros {metrik!r} için taranan {len(raporlar)} raporun "
            "hiçbirinde mağaza sayısı bulunamadı — şablon değişmiş olabilir"
        )
    df = (
        pd.DataFrame(noktalar, columns=["date", "value"])
        .drop_duplicates("date", keep="last")
        .sort_values("date")
        .reset_index(drop=True)
    )
    return df
