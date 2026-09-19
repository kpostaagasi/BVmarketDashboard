"""TSPB (Türkiye Sermaye Piyasaları Birliği) "Veriler" sayfası istemcisi.

Kaynak gerçekleri 2026-09-18'de canlı ölçüldü:

- Sayfanın "pretty URL"si (`https://tspb.org.tr/veriler/`) `requests` (ve
  tam tarayıcı User-Agent'lı `curl`) ile çekildiğinde TSPB'yle hiçbir
  ilgisi olmayan bir Shopify/kumar sitesine (ALTARTOTO, Endonezya Toto
  Macau) yönleniyor — 3 farklı User-Agent ve cache-bust query string'iyle
  tekrar tekrar doğrulandı, yanıt `X-Cache: HIT from Backend` + `Age`
  başlıklarıyla sunucu tarafında GERÇEKTEN önbellekleniyor (rastgele bir
  hata değil). Muhtemelen ters proxy/CDN yapılandırma hatası ya da sayfa
  ele geçirme (hack); TSPB'nin kendisiyle görüşülmeden kökeni kesin
  değil. WordPress REST API bu path'i BYPASS ediyor ve gerçek sayfa
  içeriğini (aynı gün 09:39 UTC güncellenmiş) doğru döndürüyor:
  `GET https://tspb.org.tr/wp-json/wp/v2/pages?slug=veriler` — bu yüzden
  bu modül sayfayı HTML olarak değil, bu REST uç noktasından okur.
- `content.rendered` alanındaki `href`lerden xlsx bağlantıları regex ile
  çekilir. Her yayında GÜNCEL dönem dosyasının adına `_YYYYMMDD_HHMMSS`
  damgası ekleniyor (ör. `..._20260917_133754.xlsx`) — sabit bir URL YOK,
  indeks her koşuda yeniden taranmalı (bkz. `ingest.osd` ile aynı desen).
  ARŞİV dosyaları sabit `-YYYYMM-YYYYMM.xlsx` adı taşır (yıl sonunda bir
  kez güncellenir) ve GÜNCEL dosyayla ARALIKSIZ ardışıktır (arşiv Aralık
  ayında kesilir, güncel dosya bir sonraki Ocak'tan başlar) — ikisi
  BİRLEŞTİRİLEREK okunur, çakışma yoktur (ölçüldü: 116 ay, 2017-01 →
  2026-08, PYŞ Aylık; 112 nokta, 2002-01 → 2026-08, Krediler).
- İki bağımsız dataset/sheet, TEK "Veriler" sayfasından linklenir:
    * "PYŞ Aylık" sayfası (`BTVY-PYS-Aylik-Veri-AMC-Monthly-Data*.xlsx`):
      4. satır GRUP başlığı (" Ay Sonu Müşteri / Fon Sayısı", " Ay Sonu
      Portföy Büyüklüğü (TL)", "PYŞ'lerin Aylık Portföy Yönetimi Geliri
      (TL)" — dördüncü grup "Aylık Ortalama Portföy Büyüklüğü (TL)" ve
      beşinci "Yatırım Fonu Yönetimi Geliri Dağılımı" bu adaptörün
      kapsamı DIŞINDA, kullanılmıyor), 6. satır her grup içindeki SABİT
      kategori sırası (Bireysel Portföy Yönetimi, Yatırım Ortaklığı,
      Emeklilik Yatırım Fonu, Yatırım Fonu, Toplam). Tarih sütunu (B)
      "YYYYMM" (6 hane, ayraçsız).
    * "Krediler" sayfası (`BTVY_Araci_Kurumlarin_Kredili_Islemleri*.xlsx`
      + arşiv `BTVY_Krediler_*.xlsx`): 4. satırda TEK satırlık dört ölçüt
      (Aracı Kurum Sayısı*, Kredi Sözleşmeli Yatırımcı Sayısı, Kredi
      Kullanan Yatırımcı Sayısı, Kredi Hacmi (TL)) + BEŞİNCİ bir sütun
      "Yatırımcı Başına Kredi Hacmi (TL)" — bu son sütun kaynakta
      doğrudan var olsa da matematiksel olarak `Kredi Hacmi ÷ Kredi
      Kullanan Yatırımcı Sayısı`dır; katalog bilinçli olarak bu oranı
      AYRI bir seri yapmaz (bkz. `core/catalog.py` GECERLI_TSPB_*),
      ihtiyaç anında `core/stats.py` katmanında iki bileşenden
      hesaplanabilir. Tarih sütunu (B) İKİ biçimli: 2025 öncesi
      ÇEYREKSEL "YYYY-MM" (çeyrek SONU ayı: 03/06/09/12 — dosyanın kendi
      dipnotu: "2025 yılından itibaren aylık derlenmektedir"), 2025+
      AYLIK "YYYY - MM" (tirenin İKİ YANINDA BOŞLUK). Çeyreksel noktalar
      repo kuralına uyacak şekilde çeyreğin İLK ayına kaydırılır
      (03→01, 06→04, 09→07, 12→10).
- Ölçüldü (2026-09-18, referans marketvisuals.net/tspb_pys.html ve
  /tspb_kredili.html ile karşılaştırıldı): 2026-07 Toplam AUM bileşenleri
  toplamı 15.163,97 Mr TL (referans KPI: 15.164,1 Mr TL — yuvarlama
  farkı), Müşteri/Fon Sayısı Toplam 19.045 (referans 19.046 — TSPB'nin
  kendi revizyonundan kaynaklanan ±1 farkı, ölçüldü), Portföy Yönetimi
  Geliri Toplamı 5,3657 Mr TL (referans 5,36 Mr TL). Kredili: Kredi Hacmi
  131.635.202.797 TL ≈ 131,6 Mr TL, Kredi Kullanan Yatırımcı Sayısı
  48.935, Kredi Sözleşmeli Yatırımcı Sayısı 646.804, Aracı Kurum Sayısı
  55 — dördü de referansla birebir.
"""

from __future__ import annotations

import io
import re

import openpyxl
import pandas as pd
import requests

TABAN = "https://tspb.org.tr"
VERILER_API_URL = f"{TABAN}/wp-json/wp/v2/pages?slug=veriler"
ZAMAN_ASIMI = 60
# Sıradan bir `Mozilla/5.0` kısa UA'sı da (curl varsayılanı gibi) ALTARTOTO
# yönlendirmesini tetikliyor; tam masaüstü Chrome UA'sı tetiklemiyor —
# bkz. modül docstring'i. Hangi katmanın (WAF/CDN) bunu yaptığı belirsiz,
# ama davranış tekrarlanabilir, o yüzden bu UA sabitlenmiştir.
_BASLIKLAR = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

_PYS_GUNCEL = re.compile(
    r'href="(https://tspb\.org\.tr/wp-content/uploads/[^"]*?'
    r"BTVY-PYS-Aylik-Veri-AMC-Monthly-Data_\d{8}_\d{6}\.xlsx)\""
)
_PYS_ARSIV = re.compile(
    r'href="(https://tspb\.org\.tr/wp-content/uploads/[^"]*?'
    r"BTVY-PYS-Aylik-Veri-AMC-Monthly-Data-\d{6}-\d{6}\.xlsx)\""
)
_KREDILI_GUNCEL = re.compile(
    r'href="(https://tspb\.org\.tr/wp-content/uploads/[^"]*?'
    r"BTVY_Araci_Kurumlarin_Kredili_Islemleri_\d{8}_\d{6}\.xlsx)\""
)
_KREDILI_ARSIV = re.compile(
    r'href="(https://tspb\.org\.tr/wp-content/uploads/[^"]*?'
    r"BTVY_Krediler_\d{4}-\d{6}\.xlsx)\""
)

# `tspb_kategori` (pys_* tablolar) -> "PYŞ Aylık" sayfasının 6. satırındaki
# TAM Türkçe kategori etiketi; sıra kaynaktaki sütun sırasıyla BİREBİR
# aynı olmalı (bkz. `_pys_kolon_haritasi`).
PYS_KOLON_ETIKETLERI = {
    "bireysel": "Bireysel Portföy Yönetimi",
    "yatirim-ortakligi": "Yatırım Ortaklığı",
    "emeklilik-yatirim-fonu": "Emeklilik Yatırım Fonu",
    "yatirim-fonu": "Yatırım Fonu",
    "toplam": "Toplam",
}
# `tspb_tablo` -> "PYŞ Aylık" sayfasının 4. satırındaki grup başlığı
# (baştaki/sondaki boşluklar `_pys_kolon_haritasi`de strip edilir).
PYS_TABLO_GRUP_BASLIGI = {
    "musteri-fon-sayisi": "Ay Sonu Müşteri / Fon Sayısı",
    "portfoy-buyuklugu": "Ay Sonu Portföy Büyüklüğü (TL)",
    "portfoy-yonetimi-geliri": "PYŞ'lerin Aylık Portföy Yönetimi Geliri (TL)",
}
_PYS_TARIH_DESENI = re.compile(r"^(\d{4})(\d{2})$")

# `tspb_kategori` (tablo="kredili") -> "Krediler" sayfasının 4. satırındaki
# etiketin BAŞLANGICI (kaynakta "Aracı Kurum Sayısı*" gibi dipnot yıldızı/
# "(TL)" birim eki taşıyanlar var, `startswith` ile eşleşir).
KREDILI_KOLON_ETIKETLERI = {
    "araci-kurum-sayisi": "Aracı Kurum Sayısı",
    "sozlesmeli-yatirimci-sayisi": "Kredi Sözleşmeli Yatırımcı Sayısı",
    "kullanan-yatirimci-sayisi": "Kredi Kullanan Yatırımcı Sayısı",
    "kredi-hacmi": "Kredi Hacmi",
}
# Tire etrafında boşluk olsun/olmasın kabul eder: "2026 - 01" (2025+ aylık)
# ve "2024-03" (2025 öncesi çeyreksel, ay = çeyrek SONU) ikisi de eşleşir.
_KREDILI_TARIH_DESENI = re.compile(r"^(\d{4})\s*-\s*(\d{2})$")
# Çeyrek SONU ayı -> çeyreğin İLK ayı (repo kuralı: "çeyrekselde çeyreğin
# İLK ayı"). 2025'ten önce yalnızca bu dört ay görülür.
_CEYREK_ILK_AY = {"03": "01", "06": "04", "09": "07", "12": "10"}
_CEYREKSEL_SON_YIL = 2024  # 2025+ zaten aylık, kaydırma uygulanmaz.


def _sayfa_icerigini_cek(session=None) -> str:
    """WordPress REST API'sinden "Veriler" sayfasının HTML içeriğini döner.

    Sayfanın kendi pretty URL'i (`/veriler/`) yerine bu uç nokta kullanılır
    — bkz. modül docstring'i.
    """
    http = session or requests
    yanit = http.get(VERILER_API_URL, headers=_BASLIKLAR, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"TSPB wp-json 'veriler' sayfası HTTP {yanit.status_code}")
    sayfalar = yanit.json()
    if not sayfalar:
        raise RuntimeError("TSPB: wp-json'da 'veriler' slug'lı sayfa bulunamadı")
    return sayfalar[0]["content"]["rendered"]


def _baglanti_bul(html: str, desen: re.Pattern, ad: str) -> str:
    eslesme = desen.search(html)
    if not eslesme:
        raise RuntimeError(
            f"TSPB: '{ad}' dosya bağlantısı 'Veriler' sayfasında bulunamadı "
            "— sayfa şablonu değişmiş olabilir"
        )
    return eslesme.group(1)


def _workbook_indir(url: str, session=None):
    http = session or requests
    yanit = http.get(url, headers=_BASLIKLAR, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"TSPB dosyası indirilemedi ({url}): HTTP {yanit.status_code}")
    return openpyxl.load_workbook(io.BytesIO(yanit.content), data_only=True)


def _pys_kolon_haritasi(satirlar: list[tuple]) -> dict[str, dict[str, int]]:
    """`{grup_baslik: {kategori_etiket: sütun_indeksi}}` eşlemesi kurar.

    4. satır (0-index 3) grup başlıklarını, 6. satır (0-index 5) her grubun
    İÇİNDEKİ sabit kategori sırasını taşır. Bir grup, kategori satırının
    kendi aralığında BEKLENEN sırayla (Bireysel/Yatırım Ortaklığı/
    Emeklilik Yatırım Fonu/Yatırım Fonu/Toplam) eşleşmiyorsa atlanır (ör.
    "Yatırım Fonu Yönetimi Geliri Dağılımı" grubu farklı bir kategori
    seti — Kurucu/Yönetici/Dağıtıcı — taşır, bu adaptörün kapsamı dışında).
    """
    grup_satiri = satirlar[3]
    kategori_satiri = satirlar[5]
    beklenen_sira = list(PYS_KOLON_ETIKETLERI.values())
    harita: dict[str, dict[str, int]] = {}
    for idx, ham_etiket in enumerate(grup_satiri):
        if not ham_etiket:
            continue
        etiket = str(ham_etiket).strip()
        alt = [
            str(kategori_satiri[idx + off]).strip()
            if idx + off < len(kategori_satiri) and kategori_satiri[idx + off]
            else None
            for off in range(len(beklenen_sira))
        ]
        if alt != beklenen_sira:
            continue
        harita[etiket] = {kat: idx + off for off, kat in enumerate(beklenen_sira)}
    return harita


def _pys_satirlarini_cikar(kitap) -> list[tuple[str, dict[str, dict[str, float | None]]]]:
    """Bir "PYŞ Aylık" workbook'undan `(tarih, {grup: {kategori: değer}})` listesi."""
    ws = kitap["PYŞ Aylık"]
    satirlar = list(ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True))
    harita = _pys_kolon_haritasi(satirlar)
    eksik = set(PYS_TABLO_GRUP_BASLIGI.values()) - set(harita)
    if eksik:
        raise RuntimeError(f"TSPB 'PYŞ Aylık': sütun grubu bulunamadı: {sorted(eksik)}")
    sonuc = []
    for r in satirlar:
        ham_tarih = r[1]
        if ham_tarih is None:
            continue
        eslesme = _PYS_TARIH_DESENI.match(str(ham_tarih).strip())
        if not eslesme:
            continue
        yil, ay = eslesme.groups()
        gruplar = {
            grup: {kat: r[col] for kat, col in kats.items()} for grup, kats in harita.items()
        }
        sonuc.append((f"{yil}-{ay}-01", gruplar))
    return sonuc


def _kredili_kolon_haritasi(satirlar: list[tuple]) -> dict[str, int]:
    grup_satiri = satirlar[3]
    harita: dict[str, int] = {}
    for slug, etiket in KREDILI_KOLON_ETIKETLERI.items():
        for idx, ham in enumerate(grup_satiri):
            if ham and str(ham).strip().startswith(etiket):
                harita[slug] = idx
                break
        else:
            raise RuntimeError(f"TSPB 'Krediler': '{etiket}' sütunu bulunamadı")
    return harita


def _kredili_satirlarini_cikar(kitap) -> list[tuple[str, dict[str, float | None]]]:
    """Bir "Krediler" workbook'undan `(tarih, {kategori: değer})` listesi."""
    ws = kitap["Krediler"]
    satirlar = list(ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True))
    harita = _kredili_kolon_haritasi(satirlar)
    sonuc = []
    for r in satirlar:
        ham_tarih = r[1]
        if ham_tarih is None:
            continue
        eslesme = _KREDILI_TARIH_DESENI.match(str(ham_tarih).strip())
        if not eslesme:
            continue
        yil, ay = eslesme.groups()
        if int(yil) <= _CEYREKSEL_SON_YIL:
            ilk_ay = _CEYREK_ILK_AY.get(ay)
            if ilk_ay is None:
                raise RuntimeError(
                    f"TSPB 'Krediler': {yil} çeyreksel döneminde beklenmeyen ay {ay!r} "
                    f"(beklenen: {sorted(_CEYREK_ILK_AY)})"
                )
            ay = ilk_ay
        degerler = {slug: r[col] for slug, col in harita.items()}
        sonuc.append((f"{yil}-{ay}-01", degerler))
    return sonuc


def _pys_satirlari(onbellek: dict, html: str, session=None):
    if "pys_satirlari" not in onbellek:
        arsiv_url = _baglanti_bul(html, _PYS_ARSIV, "PYŞ Aylık arşiv")
        guncel_url = _baglanti_bul(html, _PYS_GUNCEL, "PYŞ Aylık güncel")
        arsiv_kitap = _workbook_indir(arsiv_url, session=session)
        guncel_kitap = _workbook_indir(guncel_url, session=session)
        onbellek["pys_satirlari"] = (
            _pys_satirlarini_cikar(arsiv_kitap) + _pys_satirlarini_cikar(guncel_kitap)
        )
    return onbellek["pys_satirlari"]


def _kredili_satirlari(onbellek: dict, html: str, session=None):
    if "kredili_satirlari" not in onbellek:
        arsiv_url = _baglanti_bul(html, _KREDILI_ARSIV, "Krediler arşiv")
        guncel_url = _baglanti_bul(html, _KREDILI_GUNCEL, "Krediler güncel")
        arsiv_kitap = _workbook_indir(arsiv_url, session=session)
        guncel_kitap = _workbook_indir(guncel_url, session=session)
        onbellek["kredili_satirlari"] = (
            _kredili_satirlarini_cikar(arsiv_kitap) + _kredili_satirlarini_cikar(guncel_kitap)
        )
    return onbellek["kredili_satirlari"]


def seri_cek(seri, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `onbellek` verilirse "Veriler" sayfası ve indirilen iki workbook (PYŞ
    Aylık, Krediler) koşu boyunca bir kez indirilir/ayrıştırılır; 9 PYŞ +
    4 kredili serisi aynı önbelleği paylaşır.
    """
    onbellek = {} if onbellek is None else onbellek
    if "html" not in onbellek:
        onbellek["html"] = _sayfa_icerigini_cek(session=session)
    html = onbellek["html"]

    if seri.tspb_tablo == "kredili":
        if seri.tspb_kategori not in KREDILI_KOLON_ETIKETLERI:
            raise RuntimeError(
                f"TSPB: {seri.id} — geçersiz tspb_kategori {seri.tspb_kategori!r} "
                f"(tablo='kredili', geçerli: {sorted(KREDILI_KOLON_ETIKETLERI)})"
            )
        satirlar = _kredili_satirlari(onbellek, html, session=session)
        kategori = seri.tspb_kategori
        noktalar = [
            (tarih, degerler[kategori]) for tarih, degerler in satirlar
            if degerler[kategori] is not None
        ]
    else:
        if seri.tspb_tablo not in PYS_TABLO_GRUP_BASLIGI:
            raise RuntimeError(f"TSPB: {seri.id} — geçersiz tspb_tablo {seri.tspb_tablo!r}")
        if seri.tspb_kategori not in PYS_KOLON_ETIKETLERI:
            raise RuntimeError(
                f"TSPB: {seri.id} — geçersiz tspb_kategori {seri.tspb_kategori!r} "
                f"(geçerli: {sorted(PYS_KOLON_ETIKETLERI)})"
            )
        satirlar = _pys_satirlari(onbellek, html, session=session)
        grup_etiketi = PYS_TABLO_GRUP_BASLIGI[seri.tspb_tablo]
        kategori_etiketi = PYS_KOLON_ETIKETLERI[seri.tspb_kategori]
        noktalar = [
            (tarih, gruplar[grup_etiketi][kategori_etiketi]) for tarih, gruplar in satirlar
            if gruplar[grup_etiketi][kategori_etiketi] is not None
        ]

    if not noktalar:
        raise RuntimeError(
            f"TSPB: {seri.id} için hiç veri noktası bulunamadı "
            f"(tablo={seri.tspb_tablo!r}, kategori={seri.tspb_kategori!r})"
        )
    df = (
        pd.DataFrame(noktalar, columns=["date", "value"])
        .drop_duplicates(subset="date", keep="last")
        .sort_values("date")
        .reset_index(drop=True)
    )
    if seri.start_date:
        df = df[df["date"] >= seri.start_date].reset_index(drop=True)
    return df
