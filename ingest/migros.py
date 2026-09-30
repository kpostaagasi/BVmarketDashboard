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

import calendar
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
    r"1\s*Ocak\s*[-–]\s*\d{1,2}\s+\w+\s+\d{4}\s+döneminde\s+(.{1,400}?)\s+"
    r"olmak\s+üzere\s+toplam\s+([\d.]+)\s+yeni\s+mağaza\s+aç[ıi]lm[ıi]şt[ıi]r",
    re.S,
)
# Gövde uzunluğu SINIRLI: raporun başka bölümlerinde de "1 Ocak – [tarih]
# döneminde ..." kalıbıyla başlayan alakasız cümleler var (ör. "esas
# sözleşmede değişiklik yapılmamıştır" — 2024 Mart raporunda ölçüldü).
# Sınırsız `.+?` bu alakasız cümleden başlayıp binlerce karakter sonraki
# GERÇEK açılış cümlesinin "olmak üzere toplam ... açılmıştır" ucuna
# atlayıp gövdeyi tamamen yanlış içerikle dolduruyordu. 400 karakter en
# uzun gözlemlenen gövdeden (Petimo dahil tam format dökümü, ~200 kr.)
# bolca pay bırakır.
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


_CEYREK_ONCEKI_AY = {"06": "03", "09": "06"}


def _kumulatif_ceyregi_cevir(noktalar: dict[str, float]) -> dict[str, float]:
    """Yılbaşından kümülatif çeyrek-sonu değerini o çeyreğe özgü akışa
    çevirir (bkz. `ingest.bddk.kumulatifi_ayliga_cevir` — aynı desenin
    çeyreklik hali). Tarihler `_rapor_listesi`'nin kendi damgasını
    kullanır (raporun kapsadığı TAKVİM AYI — Mart="03", Haziran="06",
    Eylül="09"; bu adaptör hiç Ç4/"12" görmüyor), genel "çeyreğin ilk
    ayı" kuralı DEĞİL. 1Ç (Mart damgası) zaten tek çeyrekliktir. Sonraki
    çeyrekler aynı yıl içindeki BİR ÖNCEKİ çeyrek damgasından farkla
    bulunur; önceki çeyrek eksikse (o çeyreğin raporu bu cümleyi
    taşımıyorsa — ör. 2023 3Ç'ten önce) bu çeyrek ATLANIR — eksiğin
    üstüne fark almak iki çeyreği tek çeyreğe yığar ve sessizce yanlış
    değer üretir."""
    sonuc: dict[str, float] = {}
    for tarih in sorted(noktalar):
        yil, ay = tarih[:4], tarih[5:7]
        if ay == "03":
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
    (daha eski) biçiminde — "Migros" sözcüğü opsiyonel eşleşir.

    DİL: tabloda her çeyrek için TAM OLARAK BİR satır var ve başlık
    TÜRKÇE (ölçüldü 2026-09-30: 1Ç 2011'den 2Ç 2026'ya kadar tek satır
    / çeyrek). Aynı çeyreğin hem Türkçe hem İngilizce varyantı
    sunulmadığı için dedupe/çok-dilli öncelik sorunu YOK; eklendiği gün
    çift görülürse ilk bulunan (tablo sırası) kazanır."""
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
# Izgaranın kaç çeyrek geriye baktığı (x ekseni vektör olduğu için
# sayfa metninden okunamıyor, sunumun kendi çeyreğinden geriye doğru
# hesaplanıyor). Ölçüldü: 4Ç24/3Ç25/4Ç25/1Ç25 sunumlarında hep 5.
_IZGARA_CEYREK_SAYISI = 5


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
    beklenen = len(_EKOSISTEM_ANAHTARLARI) * _IZGARA_CEYREK_SAYISI
    if len(degerler) != beklenen:
        # Sunum şablonu değişti (ölçüldü: 2Ç 2026'da bu sayfa TAMAMEN
        # kaldırıldı, yerine "Online Operasyonlar" geldi — bkz. aşağıdaki
        # bölüm). Bu sayfa kullanılamaz; tüm dijital taramayı patlatmak
        # yerine None dönülür, çağıran taraf bu dalı yok sayıp daha eski
        # sunumların değerlerini korur. Daha önceki davranış RuntimeError
        # idi ve tek sayfa değişikliği ÜÇ dijital seriyi de düşürüyordu.
        return None

    # Sabit boyutlu dilimleme: 6 grup x 5 çeyrek her zaman x0'a göre
    # sıralandığında ARDIŞIK bloklar halinde gelir (gruplar arası boşluk
    # bazen bir grubun KENDİ içindeki iki çeyrek kümesi arasındaki
    # boşluktan küçük olabiliyor — ölçüldü, 2Ç2024 sunumu — bu yüzden en
    # büyük N boşluğu ayıraç seçen bir yöntem YANLIŞ gruplar üretebilir).
    # Toplam tam sayı doğrulandığı için basit 5'li dilimleme güvenlidir.
    dilim = _IZGARA_CEYREK_SAYISI
    gruplar = [degerler[i:i + dilim] for i in range(0, beklenen, dilim)]

    ceyrekler = []
    yil, ceyrek = sunum_yili, sunum_ceyregi
    for _ in range(_IZGARA_CEYREK_SAYISI):
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


# --- 2Ç 2026'dan itibaren "Online Operasyonlar" sayfası ---
#
# 2Ç 2026 sunumu (s.24) "Migros Dijital Ekosistemi Performans
# Göstergeleri" ızgarasını KALDIRDI; yerine aynı çeyreğin dört
# tekil mini-grafiğini taşıyan "Online Operasyonlar" sayfası geldi.
# Ölçülen değerler (x-konumlarıyla eşleştirilerek, s.24):
#   grup 1 "Migros One GMV (milyar TL)"   18,6 | 23,5 | 28,5  (2Ç24|25|26)
#           (+ altında ikinci seri: Migros Yemek GMV 1,9 | 2,9 | 5,0)
#   grup 2 "Günlük Sipariş"               226k | 263k | 327k
#           (+ altında ikinci seri: 45k | 57k | 91k)
#   grup 3 "Migros'ta e-ticaret payı (%)(1)" 18,5 | 20,7 | 23,1
#   grup 4 "Aktif kullanıcı sayısı(2) (milyon)" 5,1 | 5,8 | 6,6
# (2) dipnotu "Yıllıklandırılmış (Son 12 ay)" — ESKİ ızgaranın "Son 12
# aylık aktif kullanıcı sayısı" tanımıyla AYNI.
#
# ÇAPRAZ KONTROL (s.5 özeti): "28,5 milyar TL GMV", "6,6 milyon tekil
# online müşteri (2Ç 2025: 5,8 milyon)" ve "günlük siparişlerde %24
# artışla 327 bine ulaşıldı" — 327k/263k = 1,244 ✓. Yani sütun
# eşleştirmesi doğru ve üç değer de sunumun KENDİ çeyreğine ait.
#
# BİRİM TUZAĞI: "Günlük Sipariş" GÜNLÜK ORTALAMA. `migros-one-
# siparis-sayisi` ise ÇEYREKLİK TOPLAM tutuyor. Doğrulama: eski
# ızgaranın 2Ç25 çeyreklik sipariş değeri 23,9 mn; 263k × 91 gün =
# 23,93 mn ✓ birebir. Bu yüzden günlük değer, EKSEN ETİKETİNDEN
# türetilen çeyreğin gerçek gün sayısıyla çarpılır — sabit 90/91
# hardcode edilmez (1Ç 2026 = 90 gün, 2Ç 2026 = 30+31+30 = 91 gün).
#
# GEÇMİŞ ÇEYREKLERİ ALMIYORUZ: yeni sayfadaki 2Ç24/2Ç25 sütunları eski
# ızgarayla AYNI DEĞİL (GMV 2Ç25: yeni 23,5, eski 17,5; 2Ç24: 18,6 vs
# 11,5) ve farkın nedeni belgelenemedi. Sessiz bir seviye sıçraması
# yaratmamak için yalnızca sunumun KENDİ çeyreği alınır, geçmiş eski
# ızgaradan gelmeye devam eder.

_ONLINE_SAYFA_BASLIGI = re.compile(r"Online\s+Operasyonlar|Online\s+Operations")
# DİL: 2026-09-30 itibarıyla sunumlar YALNIZCA TÜRKÇE; "Online
# Operasyonlar" başlığı ölçüldü (2Ç26 s.24), İngilizce "Online
# Operations" varyantı DOĞRULANMADI — şablon başlığını eşleştiren tek
# kalem, İngilizce eklendiği halde Türkçe olan sunumda çalışır durumda.


# Grafik başlığındaki tek sözcük -> seri. Anahtar sözcüklerin hepsi
# AYNI başlık bandında (ölçüldü 2Ç26 s.24: "Aktif" top=243,7, "GMV"
# top=248,2, "Sipariş" top=248,5 — en büyük fark 4,8pt); sayfanın
# üstündeki "Çeyreksel Öne Çıkanlar" şeridindeki GMV ise 97,95pt
# yukarıda (top=145,6). O yüzden "anahtarı en çok geçen bant" seçilir.
_ONLINE_BASLIK_ANAHTARLARI = {
    "GMV": "migros-one-gmv",
    "Sipariş": "migros-one-siparis-sayisi",
    "Aktif": "migros-one-aktif-kullanici",
}

_CEYREK_AYLARI = {1: (1, 2, 3), 2: (4, 5, 6), 3: (7, 8, 9), 4: (10, 11, 12)}

_CEYREK_ETIKETI = re.compile(r"^(\d)Ç$")


def _ceyrek_gun_sayisi(yil: int, ceyrek: int) -> int:
    """Verilen çeyreğin GERÇEK gün sayısı (2Ç 2026 = 30+31+30 = 91,
    1Ç 2026 = 31+28+31 = 90). Sabit 90/91 hardcode edilmez."""
    return sum(calendar.monthrange(yil, ay)[1] for ay in _CEYREK_AYLARI[ceyrek])


def online_operasyonlarini_ayikla(
    pdf_baytlari: bytes, sunum_yili: int, sunum_ceyregi: int
) -> dict[str, float] | None:
    """'Online Operasyonlar' sayfasından Migros One'ın ÜÇ ölçütünü
    (GMV milyar TL, aktif kullanıcı milyon, sipariş milon ÇEYREKLİK
    TOPLAM) yalnızca SUNUMUN KENDİ ÇEYREĞİ için okur; sayfa yoksa
    (2Ç 2026 öncesi tüm sunumlar) None döner.

    Ayrıştırma x-konumuna dayanır: sayfadaki "NÇ YYYY" eksen
    etiketleri dört grafiği aynı sayıda sütuna böler (ölçülen: 4 grup
    × 3 sütun = 12 etiket), her grafiğin başlığı x-merkeziyle hangi
    gruba ait olduğunu belirler, değerler kendi eksen etiketine EN
    YAKIN olan sütundan ve o sütunda EN ÜSTTEKİ kutudan okunur
    (sütunda ikinci, daha küçük bir seri varsa — Migros Yemek GMV gibi —
    üstteki kutu asıl seridir: 2Ç26'da 28,5 / 5,0 ve 327k / 91k).

    Birim dönüşümü: günlük sipariş -> çeyreklik toplam (gün sayısı
    EKSEN ETİKETİNDEN türetilir); GMV ve aktif kullanıcı zaten
    çeyreklik/milyon birimindedir."""
    with pdfplumber.open(io.BytesIO(pdf_baytlari)) as pdf:
        for p in pdf.pages:
            if _ONLINE_SAYFA_BASLIGI.search(p.extract_text() or ""):
                kelimeler = p.extract_words()
                break
        else:
            return None

    # Eksen etiketleri sayfanın EN ALTINDA (ölçüldü 2Ç26 s.24: eksen
    # top≈418-420, değerler top≈277-338). Çeyrek etiketi ("NÇ") ayrıca
    # sağdaki dipnot şeridinde de geçiyor ("677 bin yeni müşteri 2Ç
    # 2026'da katıldı", top=262) — bu yüzden en ALTTAKİ çeyrek
    # etiketi satırı seçilir.
    eksen_topu = max((k["top"] for k in kelimeler if _CEYREK_ETIKETI.fullmatch(k["text"])), default=None)
    if eksen_topu is None:
        return None

    eksenler = []
    for k in kelimeler:
        ceyrek = _CEYREK_ETIKETI.fullmatch(k["text"])
        if not ceyrek or abs(k["top"] - eksen_topu) > 3:
            continue
        yil = min(
            (
                w for w in kelimeler
                if re.fullmatch(r"\d{4}", w["text"])
                and abs(w["top"] - k["top"]) < 3
                and w["x0"] > k["x1"]
            ),
            key=lambda w: w["x0"],
            default=None,
        )
        if yil is not None:
            eksenler.append(((k["x0"] + k["x1"]) / 2, int(yil["text"]), int(ceyrek.group(1))))
    eksenler.sort()
    if not eksenler:
        return None

    # Her grafik aynı çeyrek kümesini gösterir -> sütun sayısı eksen
    # etiketlerinin benzersiz çeyrek sayısıdır, grup sayısı bölümden
    # gelir. Sabit bir boşluk eşiği kullanılmıyor: ölçülen 2Ç26'da
    # grup-içi merkez farkı en fazla 40,0pt, grup-arası en az 85,2pt
    # olduğu için her eşik keyfi olurdu.
    periyotlar = {(y, c) for _, y, c in eksenler}
    if len(eksenler) % len(periyotlar):
        return None
    sutun = len(periyotlar)
    gruplar = [eksenler[i * sutun:(i + 1) * sutun] for i in range(len(eksenler) // sutun)]

    # Başlık bandı: en çok anahtar sözcük içeren bant.
    adaylar = sorted(
        (k for k in kelimeler if k["text"] in _ONLINE_BASLIK_ANAHTARLARI), key=lambda k: k["top"]
    )
    bantlar: list[list] = []
    for k in adaylar:
        if bantlar and k["top"] - bantlar[-1][0]["top"] < 20:
            bantlar[-1].append(k)
        else:
            bantlar.append([k])
    basliklari = max(bantlar, key=len) if bantlar else []
    baslik_sonu = max((k["top"] for k in basliklari), default=None)
    if baslik_sonu is None:
        return None

    sayi_deseni = re.compile(r"^\d+(?:[.,]\d+)?k?$")
    sonuc: dict[str, float] = {}
    for k in basliklari:
        metrik = _ONLINE_BASLIK_ANAHTARLARI[k["text"]]
        merkez = (k["x0"] + k["x1"]) / 2
        # Başlık sözcüğünün kendisi eksen etiketinin TAM ortasında
        # değildir (ölçüldü 2Ç26 s.24: grup1 başlığı "GMV" merkezi
        # 167,7; en sağdaki etiket merkezi 164,0), bu yüzden ARAYA
        # DÜŞMÜYOR — başlığı en yakın eksen etiketine bağlanır.
        grup = min(
            gruplar, key=lambda g: min(abs(merkez - t[0]) for t in g), default=None
        )
        if grup is None:
            continue
        eksen_merkezi, yil, ceyrek = grup[-1]  # sağdaki sütun = sunumun kendi çeyreği
        if (yil, ceyrek) != (sunum_yili, sunum_ceyregi):
            continue
        kutu = min(
            (
                w for w in kelimeler
                if sayi_deseni.fullmatch(w["text"])
                and baslik_sonu + 20 < w["top"] < eksen_topu - 5
                and abs((w["x0"] + w["x1"]) / 2 - eksen_merkezi) <= 20
            ),
            key=lambda w: w["top"],
            default=None,
        )
        if kutu is None:
            continue
        bin_kat = 1000 if kutu["text"].endswith("k") else 1  # "327k" -> bin adet/gün
        deger = float(kutu["text"].rstrip("k").replace(",", ".")) * bin_kat
        if metrik == "migros-one-siparis-sayisi":
            deger = deger * _ceyrek_gun_sayisi(yil, ceyrek) / 1e6  # adet/gün -> milyon/çeyrek
        sonuc[metrik] = deger
    return sonuc or None


def _dijital_metrikleri_getir(onbellek: dict, session=None) -> dict[str, dict[str, float]]:
    """Tüm sunumları TARA (ekosistem ızgarası + Moneypay başlığı +
    2Ç 2026'dan itibaren "Online Operasyonlar" sayfası), dört metriği
    birleştirip {metrik: {tarih: değer}} döner. Çakışan
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
        # 2Ç 2026'dan itibaren dijital sayfa değişti: Migros One'ın üç
        # ölçütü artık eski ızgaradan değil "Online Operasyonlar"
        # sayfasından geliyor (yalnızca sunumun KENDİ çeyreği için).
        online = online_operasyonlarini_ayikla(baytlar, s["yil"], s["ceyrek"])
        if online:
            for metrik, deger in online.items():
                birlesik[metrik][tarih] = deger
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
