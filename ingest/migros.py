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


# --- Format bazında yeni mağaza açılışları (2023 3Ç'ten itibaren) ---
#
# Aynı "Ara Dönem Faaliyet Raporu"nun GİRİŞ bölümünde (mağaza envanteri
# cümlesinden AYRI, ondan ÖNCE gelen) yıl-başından-itibaren kümülatif bir
# açılış cümlesi var: "1 Ocak – [tarih] döneminde N1 adet Migros, N2 adet
# Migros Jet, ... olmak üzere toplam T yeni mağaza açılmıştır." Ölçüldü
# (2026-09-19): 2023 3Ç'ten önce (2023 1Ç/2Ç raporları) bu cümle YOK —
# seri o çeyrekten başlar. Bu GERÇEK brüt açılış sayısıdır (toplam mağaza
# sayısındaki NET değişimden bilhassa farklı: aynı çeyrekte kapanışlar da
# olabiliyor, ör. 2Ç 2026'da format optimizasyonuyla 19 Mion kapatıldı —
# bkz. Migros 2Ç 2026 Yatırımcı Sunumu s.7), bu yüzden toplam mağaza
# sayısı serisinden fark alarak ÜRETİLEMEZ.
GECERLI_FORMAT_ACILIS_METRIKLERI = {
    "toplam-yeni-magaza-acilis",
    "migros-format-magaza-acilis",
    "migros-jet-format-magaza-acilis",
    "macrocenter-format-magaza-acilis",
    "mion-format-magaza-acilis",
}

_ACILIS_CUMLESI = re.compile(
    r"1\s*Ocak\s*[-–]\s*\d{1,2}\s+\w+\s+\d{4}\s+döneminde\s+(.+?)\s+"
    r"olmak\s+üzere\s+toplam\s+([\d.]+)\s+yeni\s+mağaza\s+aç[ıi]lm[ıi]şt[ıi]r",
    re.S,
)
# Format adı → cümle gövdesindeki sayısını çeken desen. "adet" bazı
# çeyreklerde yok (ör. 2023 3Ç: "195 Migros, 105 Migros Jet"), format
# sırası ve tam liste (Macrokiosk/hipermarket/Toptan/Petimo/Minigros de
# geçebiliyor ama kartlarımız yalnızca dördünü karşılıyor) çeyrekten
# çeyreğe değişiyor — bu yüzden her format kendi bağımsız deseniyle
# aranır, sabit pozisyon varsayılmaz.
_FORMAT_ACILIS_DESENLERI = {
    "migros-format-magaza-acilis": re.compile(r"([\d.]+)\s+(?:adet\s+)?Migros(?!\s+Jet)\b"),
    "migros-jet-format-magaza-acilis": re.compile(r"([\d.]+)\s+(?:adet\s+)?Migros\s+Jet\b"),
    "macrocenter-format-magaza-acilis": re.compile(r"([\d.]+)\s+(?:adet\s+)?Macrocenter\b"),
    "mion-format-magaza-acilis": re.compile(r"([\d.]+)\s+(?:adet\s+)?Mion\b"),
}


def format_acilislarini_ayikla(metin: str) -> dict[str, float] | None:
    """Rapor GİRİŞ bölümündeki yıl-başından-kümülatif açılış cümlesinden
    toplamı ve format bazında dökümü okur; cümle yoksa (2023 3Ç öncesi)
    None döner. Dönen sözlük yalnızca metinde GEÇEN formatları içerir —
    ör. bir çeyrekte "Mion" hiç açılmamışsa anahtar hiç yok (uydurma 0
    YASAK, bkz. modül genelindeki ilke)."""
    m = _ACILIS_CUMLESI.search(metin)
    if not m:
        return None
    sonuc: dict[str, float] = {"toplam-yeni-magaza-acilis": float(m.group(2).replace(".", ""))}
    govde = m.group(1)
    for metrik, desen in _FORMAT_ACILIS_DESENLERI.items():
        fm = desen.search(govde)
        if fm:
            sonuc[metrik] = float(fm.group(1).replace(".", ""))
    return sonuc


_CEYREK_ONCEKI_AY = {"04": "01", "07": "04", "10": "07"}


def _kumulatif_ceyregi_cevir(noktalar: dict[str, float]) -> dict[str, float]:
    """Yılbaşından kümülatif çeyrek-sonu değerini o çeyreğe özgü akışa
    çevirir (bkz. `ingest.bddk.kumulatifi_ayliga_cevir` — aynı desenin
    çeyreklik hali). 1Ç (Ocak damgası) zaten tek çeyrekliktir. Sonraki
    çeyrekler aynı yıl içindeki BİR ÖNCEKİ çeyrek damgasından farkla
    bulunur; önceki çeyrek eksikse (o çeyreğin raporu bu cümleyi
    taşımıyorsa) bu çeyrek ATLANIR — eksiğin üstüne fark almak iki
    çeyreği tek çeyreğe yığar ve sessizce yanlış değer üretir."""
    sonuc: dict[str, float] = {}
    for tarih in sorted(noktalar):
        yil, ay = tarih[:4], tarih[5:7]
        if ay == "01":
            sonuc[tarih] = noktalar[tarih]
            continue
        onceki_ay = _CEYREK_ONCEKI_AY.get(ay)
        onceki = f"{yil}-{onceki_ay}-01" if onceki_ay else None
        if onceki and onceki in noktalar:
            sonuc[tarih] = noktalar[tarih] - noktalar[onceki]
    return sonuc


def _format_acilislarini_getir(onbellek: dict, session=None) -> dict[str, dict[str, float]]:
    """Tüm raporları TARA (rapor listesi/metin önbelleği `seri_cek`'in
    `toplam-magaza-sayisi` dalıyla paylaşılır), her metriği yılbaşından-
    kümülatiften çeyrekliğe çevirip {metrik: {tarih: değer}} döner. Beş
    metrik (toplam + 4 format) aynı tek taramayı paylaşır."""
    if "format_acilis" in onbellek:
        return onbellek["format_acilis"]
    if "raporlar" not in onbellek:
        onbellek["raporlar"] = _rapor_listesi(session=session)
    kumulatif: dict[str, dict[str, float]] = {m: {} for m in GECERLI_FORMAT_ACILIS_METRIKLERI}
    for r in onbellek["raporlar"]:
        metin = _belge_metnini_getir(r["url"], onbellek, session=session)
        if metin is None:
            continue
        ayiklanan = format_acilislarini_ayikla(metin)
        if ayiklanan is None:
            continue
        for metrik, deger in ayiklanan.items():
            kumulatif[metrik][r["tarih"]] = deger
    sonuc = {metrik: _kumulatif_ceyregi_cevir(noktalar) for metrik, noktalar in kumulatif.items()}
    onbellek["format_acilis"] = sonuc
    return sonuc


# --- Migros One / MoneyPay dijital ekosistem ölçütleri (Yatırımcı Sunumu) ---
#
# migroskurumsal.com'un aynı finansal-bilgiler sayfasında "Yatırımcı
# Sunumları" sekmesi 1Ç 2011'den bugüne çeyreklik PDF listeler (Ara Dönem
# Faaliyet Raporu'ndan AYRI belge ailesi, aynı sayfadaki AYRI bir
# `<table>`). Migros One (e-ticaret/GMV/aktif kullanıcı) ve MoneyPay
# (fintek) verisi yalnızca yakın geçmişte ortaya çıktı; `SUNUM_ILK_YIL`
# öncesi hiç taranmıyor (performans + zaten veri yok).
SUNUM_ILK_YIL = 2023

_SUNUM_BASLIK = re.compile(r"^(\d)Ç\s*(\d{4})(?:\s+Migros)?\s+Yatırımcı Sunumu$")

GECERLI_DIJITAL_METRIKLERI = {
    "migros-one-gmv", "migros-one-aktif-kullanici",
    "migros-one-siparis-sayisi", "moneypay-kayitli-kullanici",
}


def _sunum_listesi(session=None) -> list[dict]:
    """finansal-bilgiler sayfasının "Yatırımcı Sunumları" tablosundan
    (yıl, çeyrek, url) satırlarını okur. Başlık ya "NÇ YYYY Yatırımcı
    Sunumu" (2026'dan itibaren) ya da "NÇ YYYY Migros Yatırımcı Sunumu"
    (daha eski) biçiminde — "Migros" sözcüğü opsiyonel eşleşir."""
    http = session or requests
    yanit = http.get(TABAN, headers=_BASLIKLAR, timeout=ZAMAN_ASIMI)
    yanit.raise_for_status()
    yanit.encoding = "utf-8"
    sonuc = []
    for baslik, hucre in re.findall(r"<tr>\s*<td>([^<]+)</td>\s*<td>(.*?)</td>\s*</tr>", yanit.text, re.S):
        eslesme = _SUNUM_BASLIK.match(baslik.strip())
        if not eslesme:
            continue
        yil = int(eslesme.group(2))
        if yil < SUNUM_ILK_YIL:
            continue
        href = re.search(r'href="([^"]+)"', hucre)
        if not href:
            continue
        sonuc.append({"yil": yil, "ceyrek": int(eslesme.group(1)), "url": href.group(1)})
    if not sonuc:
        raise RuntimeError(
            "Migros finansal bilgiler sayfasında hiç 'Yatırımcı Sunumu' bağlantısı "
            "ayrıştırılamadı — şablon değişmiş olabilir"
        )
    return sonuc


def _sunum_pdfsini_getir(url: str, onbellek: dict, session=None) -> bytes | None:
    """Ham PDF baytlarını döner (metne değil — ekosistem ızgarası konum
    bilgisine ihtiyaç duyar); 404 kalıcı yokluğunda None. Anahtarı
    `_belge_metnini_getir`'in METİN önbelleğinden AYRI tutulur (baytlar
    çok daha büyük ve iki farklı çıkarımda tekrar kullanılıyor)."""
    anahtar = ("sunum_bayt", url)
    if anahtar in onbellek:
        return onbellek[anahtar]
    http = session or requests
    yanit = http.get(url, headers=_BASLIKLAR, timeout=ZAMAN_ASIMI)
    if yanit.status_code == 404:
        onbellek[anahtar] = None
        return None
    yanit.raise_for_status()
    baytlar = pdf_ayikla(yanit.content)
    onbellek[anahtar] = baytlar
    return baytlar


def _moneypay_kayitli_kullanici_ayikla(pdf_baytlari: bytes) -> float | None:
    """'Fintek Operasyonları: Moneypay' başlık kutusunu taşıyan sayfayı
    bulup kayıtlı kullanıcı sayısını okur (sayfa-izole arama şart: sayı
    ve etiketler pdfplumber'da SÜTUN BAZLI satır-satır çıkarıldığından
    -- ör. "Migros Yemek GMV" gibi iki satırlı başlıklar komşu sütunların
    metniyle iç içe geçiyor -- tüm belge metninde arama yanlış sayfayı
    yakalayabilir; ölçüldü). Üç kardeş ölçüt (Toplam Ödeme Hacmi, Günlük
    İşlem, Hasılat) hep 'milyar TL'/'bin'/'milyon TL' birimi taşırken
    yalnız kayıtlı kullanıcı TL'siz çıplak 'milyon' alır — tek ölçüt bu
    birimle ayırt edilebiliyor. Sayfa bu başlığı taşımıyorsa (ör.
    3Ç/4Ç sunumlarının eski 'Hasılat/TPV' çerçevesi) None döner."""
    with pdfplumber.open(io.BytesIO(pdf_baytlari)) as pdf:
        sayfa_metni = None
        for p in pdf.pages:
            t = p.extract_text() or ""
            if "Moneypay" in t and "Kayıtlı kullanıcı" in t:
                sayfa_metni = t
                break
        if sayfa_metni is None:
            return None
    metin = pdf_metnini_normallestir(sayfa_metni)
    sinir = metin.find("yıllık")
    govde = metin if sinir == -1 else metin[:sinir]
    m = re.search(r"(\d+[.,]\d+)\s+milyon\b(?!\s*TL)", govde)
    return float(m.group(1).replace(",", ".")) if m else None


_EKOSISTEM_ETIKET_KELIMELERI = {"Aktif", "Sipariş", "GMV", "Kayıtlı", "İşlem", "TPV"}
_EKOSISTEM_ANAHTARLARI = (
    "migros-one-aktif-kullanici", "migros-one-siparis-sayisi", "migros-one-gmv",
    "moneypay-kayitli-kullanici", "moneypay-islem-sayisi", "moneypay-tpv",
)


def ekosistem_izgarasini_ayikla(
    pdf_baytlari: bytes, sunum_yili: int, sunum_ceyregi: int
) -> dict[str, dict[str, float]] | None:
    """'Migros Dijital Ekosistemi Performans Göstergeleri' sayfasını
    (varsa) bulur ve 6 sütun x 5 çeyreklik ızgarayı x-konumuna göre
    ayrıştırır. Her sunumda YOK (ölçüldü: 4Ç24/3Ç25/4Ç25/1Ç26'da var,
    2Ç26'da yok) — yoksa None döner.

    Sayfa sunumun KENDİ çeyreğiyle biten 5 ardışık çeyreği gösterir. X
    ekseni metni PDF'te vektör/resim olarak gömülü olduğundan OCR
    EDİLMEZ: tarihler sunumun BİLİNEN kendi çeyreğinden geriye doğru
    hesaplanır. Görsel doğrulama (2026-09-19, 4Ç2025 sunumu sayfa 26):
    x ekseni "4Ç24 1Ç25 2Ç25 3Ç25 4Ç25" — soldan sağa eskiden yeniye.

    Yalnızca gösterge amaçlı üç ek sütun da (Sipariş Sayısı, MoneyPay
    İşlem Sayısı, MoneyPay TPV) döner; `seri_cek` yalnızca ihtiyaç
    duyduğu beşini kullanır."""
    with pdfplumber.open(io.BytesIO(pdf_baytlari)) as pdf:
        sayfa = None
        for p in pdf.pages:
            metin = p.extract_text() or ""
            if "Ekosistemi" in metin and "Göstergeleri" in metin:
                sayfa = p
                break
        if sayfa is None:
            return None
        kelimeler = sayfa.extract_words()

    baslik_topu = min(
        (k["top"] for k in kelimeler if k["text"] in _EKOSISTEM_ETIKET_KELIMELERI), default=None
    )
    if baslik_topu is None:
        raise RuntimeError("ekosistem ızgarası: sütun başlıkları bulunamadı")

    sayi_deseni = re.compile(r"^\d+[.,]\d+$")
    degerler = sorted(
        (k for k in kelimeler if sayi_deseni.match(k["text"]) and k["top"] > baslik_topu + 20),
        key=lambda k: k["x0"],
    )
    if len(degerler) != 30:
        raise RuntimeError(f"ekosistem ızgarası: 30 değer bekleniyordu, {len(degerler)} bulundu")

    araliklar = sorted(
        (degerler[i + 1]["x0"] - degerler[i]["x0"], i) for i in range(len(degerler) - 1)
    )
    kesim_noktalari = sorted(i for _, i in araliklar[-5:])
    gruplar, basla = [], 0
    for i in kesim_noktalari:
        gruplar.append(degerler[basla:i + 1])
        basla = i + 1
    gruplar.append(degerler[basla:])
    if len(gruplar) != 6 or any(len(g) != 5 for g in gruplar):
        raise RuntimeError(f"ekosistem ızgarası: eşit olmayan gruplar {[len(g) for g in gruplar]}")

    ceyrekler = []
    yil, ceyrek = sunum_yili, sunum_ceyregi
    for _ in range(5):
        ceyrekler.append((yil, ceyrek))
        yil, ceyrek = (yil - 1, 4) if ceyrek == 1 else (yil, ceyrek - 1)
    ceyrekler.reverse()

    sonuc: dict[str, dict[str, float]] = {}
    for anahtar, grup in zip(_EKOSISTEM_ANAHTARLARI, gruplar):
        harita = {}
        for (yy, cc), kelime in zip(ceyrekler, grup):
            ay = {1: "01", 2: "04", 3: "07", 4: "10"}[cc]
            harita[f"{yy}-{ay}-01"] = float(kelime["text"].replace(",", "."))
        sonuc[anahtar] = harita
    return sonuc


def _dijital_metrikleri_getir(onbellek: dict, session=None) -> dict[str, dict[str, float]]:
    """Tüm sunumları TARA (ekosistem ızgarası + Moneypay başlığı), dört
    metriği birleştirip {metrik: {tarih: değer}} döner. Çakışan
    çeyreklerde SONRAKİ (kronolojik olarak daha yeni yayımlanan) sunum
    kazanır — şirket geçmiş çeyrekleri revize edebiliyor (ölçüldü:
    4Ç2024 sunumunun kendi '4Ç23' aktif kullanıcı rakamı [2,7 milyon]
    sonraki sunumlarda [3Ç2025: 5,3 milyon] geriye dönük değişti —
    muhtemelen ölçüt tanımı genişletildi; en güncel sunumun rakamı daha
    güvenilir kabul edilir, `AGENTS.md`'deki "revizyonlar yakalanmalı"
    ilkesiyle tutarlı)."""
    if "dijital" in onbellek:
        return onbellek["dijital"]
    if "sunumlar" not in onbellek:
        onbellek["sunumlar"] = _sunum_listesi(session=session)
    birlesik: dict[str, dict[str, float]] = {m: {} for m in GECERLI_DIJITAL_METRIKLERI}
    for s in sorted(onbellek["sunumlar"], key=lambda s: (s["yil"], s["ceyrek"])):
        baytlar = _sunum_pdfsini_getir(s["url"], onbellek, session=session)
        if baytlar is None:
            continue
        izgara = ekosistem_izgarasini_ayikla(baytlar, s["yil"], s["ceyrek"])
        if izgara:
            for metrik in GECERLI_DIJITAL_METRIKLERI:
                if metrik in izgara:
                    birlesik[metrik].update(izgara[metrik])
        ay = {1: "01", 2: "04", 3: "07", 4: "10"}[s["ceyrek"]]
        tarih = f"{s['yil']}-{ay}-01"
        moneypay = _moneypay_kayitli_kullanici_ayikla(baytlar)
        if moneypay is not None:
            birlesik["moneypay-kayitli-kullanici"][tarih] = moneypay
    onbellek["dijital"] = birlesik
    return birlesik


def seri_cek(seri, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    Üç bağımsız metrik ailesi aynı imzayı paylaşır ama farklı belge
    kümelerini tarar: `GECERLI_METRIKLER` (toplam mağaza sayısı — Ara
    Dönem Faaliyet Raporu'nun ENVANTER cümlesi), `GECERLI_FORMAT_ACILIS_METRIKLERI`
    (aynı raporun AÇILIŞ cümlesi, format bazında), `GECERLI_DIJITAL_METRIKLERI`
    (Yatırımcı Sunumu — Migros One/MoneyPay). Üçü de `onbellek` üzerinden
    kendi belge taramasını tek seferde yapıp paylaşır."""
    onbellek = onbellek if onbellek is not None else {}
    metrik = seri.migros_metrik

    if metrik in GECERLI_METRIKLER:
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
    elif metrik in GECERLI_FORMAT_ACILIS_METRIKLERI:
        harita = _format_acilislarini_getir(onbellek, session=session).get(metrik, {})
        if not harita:
            raise RuntimeError(f"Migros {metrik!r} için hiçbir raporda açılış cümlesi bulunamadı")
        noktalar = list(harita.items())
    elif metrik in GECERLI_DIJITAL_METRIKLERI:
        harita = _dijital_metrikleri_getir(onbellek, session=session).get(metrik, {})
        if not harita:
            raise RuntimeError(f"Migros {metrik!r} için hiçbir Yatırımcı Sunumu'nda değer bulunamadı")
        noktalar = list(harita.items())
    else:
        raise RuntimeError(f"Bilinmeyen migros_metrik: {metrik!r}")

    df = (
        pd.DataFrame(noktalar, columns=["date", "value"])
        .drop_duplicates("date", keep="last")
        .sort_values("date")
        .reset_index(drop=True)
    )
    return df
