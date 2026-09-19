"""Türk Telekom Yatırımcı İlişkileri çeyreklik "Özet Finansal ve Operasyonel
Veriler" Excel istemcisi.

Kaynak gerçekleri 2026-09-18'de canlı ölçüldü:

- Dosya yolu TÜRETİLEMEZ: her çeyrek rastgele bir hash dizini taşıyor
  (ör. `/media/j5jnipf0/ozet-finansal-ve-operasyonel-veriler-2c-26.xlsx`).
  `ARSIV_SAYFASI` (Çeyrek Dönem Sonuçları) sunucu tarafında render ediliyor
  ve YENİDEN-ESKİYE sıralı; ilk "Özet Finansal ve Operasyonel Veriler"
  bağlantısı en güncel çeyreğe ait.
- "Abone Verileri" sayfası TEK BAŞINA 2014 Ç1'den bugüne tüm abone
  geçmişini taşıyor (TAV'a benzer, dosya geçmişi birleştirilmez) — mobil
  toplam/sabit genişbant/TV/sabit ses abone sayıları burada.
- ARPU rakamları İKİ FARKLI (ve birbirine dönüştürülemeyen) sayfada:
  "ARPU (Tarihsel)" NOMİNAL değerleri taşır ama 2023 Ç4'te DONDURULMUŞ
  (şirket 2024'ten itibaren bu sayfayı güncellemeyi bırakmış); "Finansal&
  Oper. Veriler (TMS29)" sayfası TÜM çeyrekleri BU RAPORUN kendi
  döneminin (2026 Ç2) satın alma gücüne göre YENİDEN İFADE eder — yani bu
  sayfanın "2023 1Ç" sütunu 2023 Ç1'in o zamanki nominal değeri DEĞİLDİR.
  Sonuç: BLENDED (Genişbant+TV+Ses karması "Sabit Hat ARPU", Faturalı+
  Karma+Faturasız karması "Mobil ARPU") MUTLAK nominal ARPU kartları BU
  ADAPTÖRÜN KAPSAMI DIŞINDA bırakıldı — iki ayrı, birbirinden bağımsız
  neden var: (1) segment ARPU'larının ("Sabit Ses ARPU", "Genişbant ARPU",
  "Ev TV ARPU" / "Mobil Faturalı ARPU", "Mobil Karma ARPU", "Mobil Ön
  Ödemeli ARPU") ne şekilde ağırlıklandırılıp tek bir karma rakama
  indirgendiğini gösteren HAM bir "Sabit Hat ARPU"/"Mobil ARPU" satırı
  Excel'de YOK (ölçüldü: 'Finansal&Oper. Veriler (TMS29)' sayfasının B
  sütununu tam taradık, böyle bir etiket yok) — basit abone-sayısı ağırlıklı
  ortalama denemek ÇİFT SAYIM riski taşır (bir müşteri hem genişbant hem TV
  hem sabit ses abonesi olabilir, üçü de ayrı payda olarak toplanırsa aynı
  müşteri üç kez sayılır); (2) MUTLAK (nominal TL) kartlar zaten her
  çeyreğin KENDİ döneminin raporundan okunmalı (yukarıdaki TAS29 yeniden
  ifade sorunundan ötürü), N ayrı dosya indirmesi gerektirir. İkisi birden
  güvenilir bir hesaplama yolunu kapatıyor.
- **Abone PAYI (%) kartları GENİŞLETİLDİ** (2026-09-18 canlı ölçüldü):
  "Mobil Faturalı Abone Payı" ve "Sabit Genişbant Fiber Abone Payı" —
  ARPU'nun aksine bunlar için "Abone Verileri" sayfasında PAY hesaplamak
  için gereken HER İKİ ham abone-sayısı alanı da VAR ("Mobil Faturalı Abone
  Sayısı (mn)" / "Mobil Toplam Abone Sayısı (mn)"; "Fiber Abone Sayısı
  (mn)" / "Genişbant Toplam Abone Sayısı (mn)") — çift sayım riski yok
  (Faturalı, Toplam'ın alt kümesi; Fiber, Genişbant Toplam'ın alt kümesi,
  tanım gereği örtüşme yok). Basit oran = doğrudan gerçek veri, tahmini
  değil. Ölçüldü (2026 2Ç, referans marketvisuals.net'le karşılaştırıldı):
  Mobil Faturalı Payı hesap %80,32 (referans %80,4, fark 0,08 p); Fiber
  Payı hesap %94,07 (referans %94,1, fark 0,03 p) — küçük sapma muhtemelen
  şirketin kendi yuvarlama/anlık görüntü zamanlamasından, iki bağımsız
  ölçümde de 0,1 puanın altında.
- "Ortalama İndirme Hızı" (Mbps) kartı bu Excel'de HAM alan olarak YOK
  (her iki sayfa da tam tarandı, "hız"/"Mbps" içeren hiçbir satır etiketi
  yok) — katalog dışı. "Mobil Abone Pazar Payı" kartı (BTK + üç operatör
  verisi, yıllık/seçili çeyrek) bu Excel'de hiç yok ve düzensiz kadanslı;
  ayrıca dışarıda bırakıldı.
"""

from __future__ import annotations

import io
import re

import openpyxl
import pandas as pd
import requests

TABAN = "https://www.ttyatirimciiliskileri.com.tr"
ARSIV_SAYFASI = f"{TABAN}/tr-tr/mali-operasyonel-veriler/sayfalar/ceyrek-donem-sonuclari"
ZAMAN_ASIMI = 60
_BASLIKLAR = {"User-Agent": "Mozilla/5.0"}

_DOSYA_BAGLANTISI = re.compile(
    r'href="([^"]+\.xlsx)"[^>]*>\s*[^<]*zet Finansal ve Operasyonel Veriler', re.I
)
_CEYREK_TR = re.compile(r"^(\d{4}) ([1-4])Ç$")
_CEYREK_AY = {"1": "01", "2": "04", "3": "07", "4": "10"}

DOGRUDAN_METRIK_KAYNAK = {
    "mobil-toplam-abone": ("Abone Verileri", "Mobil Toplam Abone Sayısı (mn)"),
    "sabit-genisbant-abone": ("Abone Verileri", "Genişbant Toplam Abone Sayısı (mn)"),
    "tv-abone": ("Abone Verileri", "Toplam TV Abone Sayısı2 (mn)"),
    "sabit-ses-abone": ("Abone Verileri", "Sabit Ses Abone Sayısı¹ (mn)"),
}

# metrik -> ("ARPU (Tarihsel)" etiketi, "Finansal&Oper. Veriler (TMS29)" etiketi)
BUYUME_METRIK_KAYNAK = {
    "sabit-genisbant-arpu-buyume": ("Genişbant ARPU  (TL)", "Genişbant ARPU"),
    "mobil-karma-arpu-buyume": ("Mobil Karma ARPU (TL)", "Mobil Karma ARPU"),
}

# metrik -> ("Abone Verileri" pay etiketi, "Abone Verileri" toplam etiketi).
# Alt küme/toplam ilişkisi tanım gereği örtüşmez (çift sayım riski yok) —
# bkz. modül docstring'i.
ABONE_PAYI_KAYNAK = {
    "mobil-faturali-abone-payi": (
        "Mobil Faturalı Abone Sayısı (mn)", "Mobil Toplam Abone Sayısı (mn)",
    ),
    "sabit-genisbant-fiber-abone-payi": (
        "Fiber Abone Sayısı (mn)", "Genişbant Toplam Abone Sayısı (mn)",
    ),
}
# Bkz. modül docstring'i: 2025 Ç3'ten itibaren Mobil Karma ARPU büyümesi
# M2M HARİÇ hesaplanıyor.
_M2M_HARIC_GECISI = "2025 3Ç"
_M2M_HARIC_ETIKETI = "Mobil Karma ARPU (M2M hariç)"


def en_guncel_dosya_url(session=None) -> str:
    """Arşiv sayfasındaki EN GÜNCEL "Özet Finansal ve Operasyonel Veriler"
    xlsx bağlantısı (liste yeniden-eskiye sıralı, ilk eşleşme en güncel)."""
    http = session or requests
    yanit = http.get(ARSIV_SAYFASI, timeout=ZAMAN_ASIMI, headers=_BASLIKLAR)
    if yanit.status_code != 200:
        raise RuntimeError(f"TTKOM çeyrek sonuçları sayfası HTTP {yanit.status_code}")
    eslesme = _DOSYA_BAGLANTISI.search(yanit.text)
    if not eslesme:
        raise RuntimeError(
            "TTKOM çeyrek sonuçları sayfasında 'Özet Finansal ve Operasyonel "
            "Veriler' bağlantısı bulunamadı — sayfa yapısı değişmiş olabilir"
        )
    yol = eslesme.group(1)
    return yol if yol.startswith("http") else TABAN + yol


def _en_yakin_baslik_satiri(ws, satir_no: int) -> int:
    for r in range(satir_no, 0, -1):
        if sum(1 for h in ws[r] if isinstance(h.value, str) and _CEYREK_TR.match(h.value)) >= 2:
            return r
    raise RuntimeError(f"{ws.title}: {satir_no}. satır için çeyrek başlığı bulunamadı")


def _etiket_serisi(ws, etiket: str) -> dict[str, float]:
    """`etiket` metnini B sütununda taşıyan İLK satırı bulur; o satırın
    üstündeki en yakın çeyrek başlık satırına göre `{"2026 2Ç": değer}`
    döner. Bulunamazsa boş sözlük (şablon değişikliği çağıran tarafta
    RuntimeError'a düşer)."""
    for satir in ws.iter_rows():
        hucre = satir[1]  # B sütunu
        if hucre.value == etiket:
            baslik_satiri = _en_yakin_baslik_satiri(ws, hucre.row)
            sutunlar = {
                h.value: h.column for h in ws[baslik_satiri]
                if isinstance(h.value, str) and _CEYREK_TR.match(h.value)
            }
            return {
                donem: float(ws.cell(row=hucre.row, column=sutun).value)
                for donem, sutun in sutunlar.items()
                if isinstance(ws.cell(row=hucre.row, column=sutun).value, (int, float))
            }
    return {}


def _ceyrek_tarihi(etiket: str) -> str:
    yil, ceyrek = _CEYREK_TR.match(etiket).groups()
    return f"{yil}-{_CEYREK_AY[ceyrek]}-01"


def _onceki_yil(donem: str) -> str:
    yil, ceyrek = _CEYREK_TR.match(donem).groups()
    return f"{int(yil) - 1} {ceyrek}Ç"


def _buyume_serisi(kitap, metrik: str) -> dict[str, float]:
    """Yıllık % ARPU büyümesi: 2023 nominal ("ARPU (Tarihsel)"), 2024 Ç1+
    reel/TAS29 ("Finansal&Oper. Veriler (TMS29)") — bkz. modül docstring'i."""
    nominal_etiket, tas29_etiket = BUYUME_METRIK_KAYNAK[metrik]
    sonuc: dict[str, float] = {}

    nominal = _etiket_serisi(kitap["ARPU (Tarihsel)"], nominal_etiket)
    for donem, deger in nominal.items():
        onceki = _onceki_yil(donem)
        if nominal.get(onceki):
            sonuc[donem] = (deger / nominal[onceki] - 1) * 100

    tas29_sayfa = kitap["Finansal&Oper. Veriler (TMS29)"]
    tas29 = _etiket_serisi(tas29_sayfa, tas29_etiket)
    m2m_haric_mi = metrik == "mobil-karma-arpu-buyume"
    tas29_haric = _etiket_serisi(tas29_sayfa, _M2M_HARIC_ETIKETI) if m2m_haric_mi else {}

    for donem, deger in tas29.items():
        if m2m_haric_mi and donem >= _M2M_HARIC_GECISI:
            continue  # bu dönemler aşağıda M2M hariç seriden hesaplanır
        onceki = _onceki_yil(donem)
        if tas29.get(onceki):
            sonuc[donem] = (deger / tas29[onceki] - 1) * 100
    for donem, deger in tas29_haric.items():
        if donem < _M2M_HARIC_GECISI:
            continue
        onceki = _onceki_yil(donem)
        if tas29_haric.get(onceki):
            sonuc[donem] = (deger / tas29_haric[onceki] - 1) * 100

    return sonuc


def _payi_serisi(kitap, metrik: str) -> dict[str, float]:
    """Alt küme abone sayısının toplam içindeki payı (%) — bkz. modül
    docstring'indeki "Abone PAYI" notu."""
    pay_etiket, toplam_etiket = ABONE_PAYI_KAYNAK[metrik]
    ws = kitap["Abone Verileri"]
    pay = _etiket_serisi(ws, pay_etiket)
    toplam = _etiket_serisi(ws, toplam_etiket)
    return {
        donem: deger / toplam[donem] * 100
        for donem, deger in pay.items()
        if toplam.get(donem)
    }


def _kitabi_getir(onbellek: dict, session=None):
    if "kitap" in onbellek:
        return onbellek["kitap"]
    http = session or requests
    url = en_guncel_dosya_url(session)
    yanit = http.get(url, timeout=ZAMAN_ASIMI, headers=_BASLIKLAR)
    if yanit.status_code != 200:
        raise RuntimeError(f"TTKOM F&O Excel'i indirilemedi ({url}): HTTP {yanit.status_code}")
    onbellek["kitap"] = openpyxl.load_workbook(io.BytesIO(yanit.content), data_only=True)
    return onbellek["kitap"]


def seri_cek(seri, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `onbellek` verilirse tek dosya (6 serinin tamamı aynı çeyrek Excel'ini
    paylaşır) koşu boyunca bir kez indirilir/ayrıştırılır.
    """
    onbellek = {} if onbellek is None else onbellek
    kitap = _kitabi_getir(onbellek, session=session)
    metrik = seri.ttkom_metrik

    if metrik in DOGRUDAN_METRIK_KAYNAK:
        sayfa_adi, etiket = DOGRUDAN_METRIK_KAYNAK[metrik]
        ceyrekler = _etiket_serisi(kitap[sayfa_adi], etiket)
        if not ceyrekler:
            raise RuntimeError(f"TTKOM {sayfa_adi}: '{etiket}' satırı bulunamadı (seri={seri.id})")
    elif metrik in BUYUME_METRIK_KAYNAK:
        ceyrekler = _buyume_serisi(kitap, metrik)
        if not ceyrekler:
            raise RuntimeError(f"TTKOM: '{metrik}' büyüme serisi hesaplanamadı (seri={seri.id})")
    elif metrik in ABONE_PAYI_KAYNAK:
        ceyrekler = _payi_serisi(kitap, metrik)
        if not ceyrekler:
            raise RuntimeError(f"TTKOM: '{metrik}' payı hesaplanamadı (seri={seri.id})")
    else:
        raise RuntimeError(f"Bilinmeyen ttkom_metrik: {metrik!r}")

    noktalar = [(_ceyrek_tarihi(donem), deger) for donem, deger in ceyrekler.items()]
    df = pd.DataFrame(sorted(noktalar), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)
