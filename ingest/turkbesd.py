"""TÜRKBESD (Türkiye Beyaz Eşya Sanayicileri Derneği) yıllık ürün kırılımı
istemcisi.

Kaynak: `https://www.turkbesd.org/turkbesd-son-5-yilin-rakamlari/`. Sayfa,
dört ölçüt (İç Satış / Üretim / İhracat / İthalat) için birer "İNDİR"
bağlantısı taşıyan tek bir HTML gövdesi — her bağlantı, o ölçütün son 5
yılını ürün bazında (Buzdolabı, Derin Dondurucu, Çamaşır Makinesi, Bulaşık
Makinesi, Fırın, Kurutucu, Toplam) veren küçük bir XLSX dosyasına gider.

Ölçüm (2026-09-18):
- Sayfa `requests` varsayılan UA'sıyla HTTP 200 dönüyor, oturum/Cloudflare
  engeli yok.
- Dört XLSX bağlantısı (`/upload/menu/document/<kod>-<olcut>-<kod2>.xlsx`)
  DETERMİNİSTİK DEĞİL — dosya adındaki sayısal kod, TÜRKBESD içerik
  yönetim sisteminin yükleme zaman damgasından geliyor ve her güncellemede
  değişiyor (13.02.2026 tarihli üretim/ihracat/ithalat dosyaları "1322026"
  taşıyor, 24.03.2026 tarihli iç satış dosyası "2432026" taşıyor — aynı gün
  yüklenmemişler). Bu yüzden adaptör URL'yi HER KOŞUDA ana sayfadan
  kazır, sabit bir XLSX URL'si varsaymaz (bkz. `_baglantilari_cikar`).
- XLSX içeriği 2021-2025 (5 yıl) taşıyor; sayfa her yıl sonunda/başında
  yeni sütun ekleyerek güncelleniyor (2025 sütunu Şubat 2026'daki bir
  güncellemede eklendi — indirme kodundaki tarih bunu doğruluyor).
- Parite: sayfadaki 2025 değerleri marketvisuals.net/turkbesd_whitegood
  referans kartlarının `summary.latestVal` alanlarıyla birebir eşleşiyor
  (örn. İç Satış/Buzdolabı 2025 = 2.284.338, Üretim/Buzdolabı 2025 =
  6.193.140, İhracat/Buzdolabı 2025 = 4.019.144, İthalat/Buzdolabı 2025 =
  118.584 — dördü de bu modülün ayrıştırdığı XLSX hücreleriyle aynı).

BİLİNÇLİ KAPSAM DIŞI — AYLIK/ÇEYREKSEL TOPLAM KARTLARI: Referans sayfada
ayrıca "İç Satış/Üretim/İhracat/İthalat - Aylık" ve "Çeyreksel" kartları
var (toplam, ürün kırılımsız). TÜRKBESD bu aylık toplamları hiçbir
deterministik, tam geçmişli kaynaktan yayımlamıyor:
- `/raporlar--beyaz-dunya/` sayfası "Beyaz Dünya" bültenlerini listeler
  ama bunlar salt anlatı PDF'leri (yalnızca % değişim ve kümülatif YTD
  cümleleri, mutlak aylık rakam tablosu YOK) ve liste yalnızca en son
  ~5 ayı gösteriyor — 2024 Ocak'tan bugüne 30+ ayın tamamı asla birden
  erişilebilir değil.
- `/haber/turkbesd-beyaz-dunya-*` ve `turkbesd-basin-bulteni*` haber
  sayfaları da aynı türde anlatı metni; URL deseni tahmin edilebilir
  değil (yalnızca `agustos-2026`, `haziran-2026`, `ekim-2025` canlı
  ölçüldü — 200 döndü; aradaki aylar için hiçbir URL varyasyonu 200
  vermedi) ve site `sitemap.xml`'i de bu haberlerin çoğunu içermiyor.
- Bu nedenle aylık/çeyreksel toplam kartları BLOKE: gerçek, tam geçmişli
  bir kaynak yok; senteziklerini üretmek yasak (bkz. görev kısıtları).

Katalog kalemleri: `turkbesd_olcut` (ic-satis/uretim/ihracat/ithalat) ve
`turkbesd_urun` (buzdolabi/derin-dondurucu/camasir-makinesi/
bulasik-makinesi/firin/kurutucu). `TOPLAM` satırı şablon doğrulaması için
okunur ama hiçbir seriye eşlenmez (kataloğun ihtiyacı yok).
"""

from __future__ import annotations

import io
import re
from datetime import date

import openpyxl
import pandas as pd
import requests

from core.catalog import GECERLI_TURKBESD_OLCUTLERI, GECERLI_TURKBESD_URUNLERI

SAYFA_URL = "https://www.turkbesd.org/turkbesd-son-5-yilin-rakamlari/"
ZAMAN_ASIMI = 30

# Sayfadaki ölçüt anchor id'si -> XLSX'in A1 hücresindeki başlık metni.
# Şablon kayması (TÜRKBESD sütun adını değiştirirse) burada yakalanır.
OLCUT_BASLIKLARI = {
    "ic-satis": "İÇ SATIŞ",
    "uretim": "ÜRETİM",
    "ihracat": "İHRACAT",
    "ithalat": "İTHALAT",
}
assert set(OLCUT_BASLIKLARI) == GECERLI_TURKBESD_OLCUTLERI

# XLSX satır adı (BÜYÜK harfli, Türkçe) -> katalog ürün kalemi.
URUN_ESLEME = {
    "BUZDOLABI": "buzdolabi",
    "DERİN DONDURUCU": "derin-dondurucu",
    "ÇAMAŞIR MAKİNESİ": "camasir-makinesi",
    "BULAŞIK MAKİNESİ": "bulasik-makinesi",
    "FIRIN": "firin",
    "KURUTUCU": "kurutucu",
}
assert set(URUN_ESLEME.values()) == GECERLI_TURKBESD_URUNLERI
TOPLAM_SATIRI = "TOPLAM"

_ANCHOR_DESENI = re.compile(
    r"<div id='([a-z-]+)' title='[^']*'>\s*"
    r'<a class="downloadExcel" href="([^"]+)"'
)


def _baglantilari_cikar(html: str) -> dict[str, str]:
    """Ana sayfadan `{olcut: xlsx_url}` çıkarır.

    XLSX URL'si dosya yükleme zaman damgası taşıdığından deterministik
    DEĞİL (bkz. modül docstring'i) — bu yüzden her koşuda burada kazınır.
    """
    bulunan = {
        anchor: url
        for anchor, url in _ANCHOR_DESENI.findall(html)
        if anchor in OLCUT_BASLIKLARI
    }
    eksik = set(OLCUT_BASLIKLARI) - bulunan.keys()
    if eksik:
        raise RuntimeError(
            f"TÜRKBESD: sayfada şu ölçütlerin İNDİR bağlantısı bulunamadı: "
            f"{sorted(eksik)} — sayfa şablonu değişmiş olabilir"
        )
    return bulunan


def yil_verisini_ayikla(baytlar: bytes, olcut: str) -> dict[str, dict[int, float]]:
    """Bir ölçütün XLSX baytlarından `{urun: {yil: değer}}` çıkarır.

    Şablon: A1 ölçüt başlığı, B1:F1 yıllar, A2:A7 ürün adları + TOPLAM,
    B:F o ürünün yıllık rakamı. Herhangi biri kaymışsa (başlık, eksik
    ürün satırı, eksik TOPLAM) sessizce yarım veri döndürmek yerine patlar.
    """
    kitap = openpyxl.load_workbook(io.BytesIO(baytlar), data_only=True)
    sayfa = kitap[kitap.sheetnames[0]]
    satirlar = list(sayfa.iter_rows(values_only=True))
    if not satirlar or satirlar[0][0] != OLCUT_BASLIKLARI[olcut]:
        raise RuntimeError(
            f"TÜRKBESD {olcut}: XLSX A1 başlığı beklenenden farklı "
            f"({satirlar[0][0] if satirlar else None!r} != "
            f"{OLCUT_BASLIKLARI[olcut]!r}) — şablon değişmiş olabilir"
        )
    yillar = [int(y) for y in satirlar[0][1:] if y is not None]
    if not yillar:
        raise RuntimeError(f"TÜRKBESD {olcut}: XLSX'te yıl sütunu bulunamadı")

    urunler: dict[str, dict[int, float]] = {}
    gorulen_etiketler: set[str] = set()
    for satir in satirlar[1:]:
        etiket = satir[0]
        if etiket is None:
            continue
        etiket = str(etiket).strip()
        gorulen_etiketler.add(etiket)
        if etiket == TOPLAM_SATIRI:
            continue
        urun = URUN_ESLEME.get(etiket)
        if urun is None:
            continue
        degerler = satir[1 : 1 + len(yillar)]
        urunler[urun] = {
            yil: float(deger)
            for yil, deger in zip(yillar, degerler)
            if deger is not None
        }

    eksik_urunler = GECERLI_TURKBESD_URUNLERI - urunler.keys()
    if eksik_urunler:
        raise RuntimeError(
            f"TÜRKBESD {olcut}: XLSX'te şu ürün satırları bulunamadı: "
            f"{sorted(eksik_urunler)} — şablon değişmiş olabilir"
        )
    if TOPLAM_SATIRI not in gorulen_etiketler:
        raise RuntimeError(
            f"TÜRKBESD {olcut}: XLSX'te TOPLAM satırı bulunamadı — "
            "şablon değişmiş olabilir"
        )
    return urunler


def _sayfa_cek(session=None) -> str:
    http = session or requests
    yanit = http.get(SAYFA_URL, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"TÜRKBESD sayfası HTTP {yanit.status_code}")
    return yanit.text


def _dosya_indir(url: str, session=None) -> bytes:
    http = session or requests
    yanit = http.get(url, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"TÜRKBESD XLSX indirme HTTP {yanit.status_code} ({url})")
    return yanit.content


def _olcut_verisini_getir(
    olcut: str, onbellek: dict, session=None
) -> dict[str, dict[int, float]]:
    """`onbellek` içinde ölçüt bazında paylaşılır: 24 seri (6 ürün × 4
    ölçüt) aynı 4 XLSX dosyasını (ölçüt başına 1) paylaşır — önbelleksiz
    her seri kendi XLSX'ini yeniden indirirdi.
    """
    if "baglantilar" not in onbellek:
        onbellek["baglantilar"] = _baglantilari_cikar(_sayfa_cek(session))
    if olcut not in onbellek:
        url = onbellek["baglantilar"][olcut]
        tam_url = url if url.startswith("http") else f"https://www.turkbesd.org{url}"
        baytlar = _dosya_indir(tam_url, session)
        onbellek[olcut] = yil_verisini_ayikla(baytlar, olcut)
    return onbellek[olcut]


def seri_cek(seri, *, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    Veri YILLIKTIR (sayfa son 5 yılı taşır); her nokta o yılın 1 Ocak'ına
    tarihlenir. Ürün, ölçütün XLSX'inde hiç bulunamazsa (yazım hatası
    koruması, `yil_verisini_ayikla` zaten şablon kaymasını yakalıyor)
    RuntimeError.
    """
    onbellek = {} if onbellek is None else onbellek
    olcut = seri.turkbesd_olcut
    urun = seri.turkbesd_urun

    urunler = _olcut_verisini_getir(olcut, onbellek, session)
    yillik = urunler.get(urun)
    if not yillik:
        raise RuntimeError(
            f"TÜRKBESD {olcut}/{urun} için hiç veri bulunamadı ({seri.id})"
        )

    noktalar = {f"{yil}-01-01": deger for yil, deger in yillik.items()}
    df = pd.DataFrame(sorted(noktalar.items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)
