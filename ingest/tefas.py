"""TEFAS (Takasbank Elektronik Fon Alım Satım Platformu) istemcisi.

Kaynak gerçekleri 2026-09-08'de canlı ölçüldü (sıfırdan yeniden
keşfetmeye çalışmayın):

- Eski `POST /api/DB/BindHistoryInfo` ucu KAPATILDI (`ERR-006 Method not
  found or disabled`). Yeni site Next.js ve veriyi
  `POST /api/funds/fonGnlBlgSiraliGetir` ucundan JSON gövdeyle çekiyor:
  `{fonTipi, fonKodu, basTarih, bitTarih, basSira, bitSira, dil, ...}`.
- Tarih biçimi `YYYYMMDD`. `29.08.2026` gibi noktalı biçim
  "could not be parsed" hatası veriyor.
- İKİ SERT SINIR: (1) tarih aralığı 1 ayı aşamaz, (2) başlangıç tarihi 5
  yıldan eski olamaz. Bu yüzden bu adaptör AY SONU ANLIK GÖRÜNTÜSÜ çeker:
  her ayın son iş günü için tek istek, tüm fonlar (`bitSira` büyük).
  Günlük tam geçmiş 5 yıl × 250 gün = 1250 istek olurdu; aylık 60 istek.
- Veri olmayan bir gün (hafta sonu/tatil) `resultList: null` ve
  `errorMessage: "Index 0 out of bounds for length 0"` döndürür — boş liste
  değil. Bu yüzden ay sonundan geriye doğru iş günü aranır.
- Yanıt satırı: `{fonKodu, fonUnvan, tarih, fiyat, tedPaySayisi,
  kisiSayisi, portfoyBuyukluk}`. **Satırda fon TÜRÜ yok**; tür kırılımı
  ancak istek başına `sfonTurKod` ile alınabilir (her tür için ayrı istek),
  o yüzden bu dilim tür kırılımı içermiyor.
- `fonTipi`: `YAT` menkul kıymet yatırım fonları, `EMK` emeklilik fonları.
  Ölçüm (2026-07-31): YAT 2.029 fon / 9.345,5 milyar TL / 10,9 mn hesap;
  EMK 399 fon / 2.418,6 milyar TL / 55,7 mn hesap.
- `kisiSayisi` FON BAZINDA hesap adedidir: aynı yatırımcı iki fondaysa iki
  kez sayılır. Katalog başlıkları bu yüzden "yatırımcı" değil "hesap" der.
"""

from __future__ import annotations

import json
import time
from calendar import monthrange
from datetime import date, timedelta

import pandas as pd
import requests

from core.catalog import GECERLI_TEFAS_OLCUTLERI, GECERLI_TEFAS_TIPLERI

UC = "https://www.tefas.gov.tr/api/funds/fonGnlBlgSiraliGetir"
ZAMAN_ASIMI = 90
AZAMI_GECMIS_YIL = 3
# Bir günde 2.037 fon döndü; tavan bolca üstünde tutuluyor ki fon sayısı
# arttığında sessizce kırpılmasın (kırpılma sessiz eksik veri demek).
SAYFA_TAVANI = 5000
# Ay sonu iş günü araması: en uzun resmi tatil zinciri + hafta sonu.
AZAMI_GERI_GUN = 8
# Ölçülen hız sınırı: 7 saniye aralık kesintisiz geçiyor, hızlı ardışık
# istekler 429 (ERR-224) alıyor ve ~50 saniye kapalı kalıyor.
ISTEK_ARALIGI = 7.0
GERI_CEKILME_SANIYE = 45.0
AZAMI_DENEME = 3

_son_istek: float | None = None

BASLIKLAR = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Referer": "https://www.tefas.gov.tr/tr/fon-verileri",
    "Origin": "https://www.tefas.gov.tr",
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
}

# Geçerli tip/ölçüt kümeleri katalogda tanımlıdır (core, ingest'i import
# etmez; ters yön serbest) ve `_dogrula` katalog yüklenirken uygular.
GECERLI_TIPLER = GECERLI_TEFAS_TIPLERI
GECERLI_OLCUTLER = GECERLI_TEFAS_OLCUTLERI


def ay_sonlari(bugun: date, gecmis_yil: int = AZAMI_GECMIS_YIL) -> list[date]:
    """Çekilecek ay sonları: 5 yıllık sınırın içinde kalan her ayın son günü.

    Cari ay için ayın son günü henüz gelmemiş olabilir; o durumda bugün
    kullanılır ve iş günü araması geriye doğru yürür.
    """
    baslangic_yil = bugun.year - gecmis_yil
    aylar: list[date] = []
    yil, ay = baslangic_yil, bugun.month
    # 5 yıl sınırı gün bazlıdır; bir ay pay bırakılır ki sınırın kenarındaki
    # istek "5 yıldan eski olamaz" hatasına düşmesin.
    ay += 1
    if ay == 13:
        yil, ay = yil + 1, 1
    while (yil, ay) <= (bugun.year, bugun.month):
        son = date(yil, ay, monthrange(yil, ay)[1])
        aylar.append(min(son, bugun))
        ay += 1
        if ay == 13:
            yil, ay = yil + 1, 1
    return aylar


def toplulastir(satirlar: list[dict]) -> dict[str, float]:
    """Bir günün tüm fon satırlarını sektör toplamlarına indirger."""
    if not satirlar:
        raise RuntimeError("TEFAS anlık görüntüsü boş")
    buyukluk = sum(float(s["portfoyBuyukluk"] or 0) for s in satirlar)
    hesap = sum(float(s["kisiSayisi"] or 0) for s in satirlar)
    adet = float(len(satirlar))
    return {
        "buyukluk": buyukluk,
        "hesap": hesap,
        "fon-sayisi": adet,
        # Fon başına ortalama büyüklük: konsolidasyon/parçalanma göstergesi.
        "ortalama-buyukluk": buyukluk / adet,
    }


def _istek_govdesi(tip: str, gun: date) -> str:
    tarih = gun.strftime("%Y%m%d")
    return json.dumps({
        "fonTipi": tip,
        "fonKodu": None,
        "aramaMetni": None,
        "fonTurKod": None,
        "fonGrubu": None,
        "sfonTurKod": None,
        "basTarih": tarih,
        "bitTarih": tarih,
        "basSira": 1,
        "bitSira": SAYFA_TAVANI,
        "fonTurAciklama": None,
        "dil": "TR",
        "kurucuKod": None,
    })


def _bekle() -> None:
    """İki istek arasında en az `ISTEK_ARALIGI` saniye bırakır.

    Ölçüm: hız sınırı dolduğunda uç `ERR-224 Because of reaching Throttling
    limit, message is BLOCKED!` ile 429 döndürüyor ve `Retry-After`
    vermiyor; ~50 saniye sonra açılıyor. 7 saniye aralıkla 8 istek
    kesintisiz geçti, bu yüzden ritim ölçüme dayanıyor.
    """
    global _son_istek
    if _son_istek is not None:
        gecen = time.monotonic() - _son_istek
        if gecen < ISTEK_ARALIGI:
            time.sleep(ISTEK_ARALIGI - gecen)
    _son_istek = time.monotonic()


def _gun_cek(tip: str, gun: date, session=None) -> list[dict] | None:
    """Tek günün tüm fonları. Veri yoksa None (hafta sonu/tatil).

    429'da `GERI_CEKILME_SANIYE` beklenip yeniden denenir; deneme hakkı
    biterse hata yükselir — sessizce eksik ay bırakmak, o ayın toplamını
    seriden düşürüp grafikte delik açardı.
    """
    http = session or requests
    yanit = None
    for deneme in range(AZAMI_DENEME):
        _bekle()
        try:
            yanit = http.post(
                UC, data=_istek_govdesi(tip, gun), headers=BASLIKLAR,
                timeout=ZAMAN_ASIMI,
            )
        except requests.exceptions.RequestException as hata:
            # Uç sınıra yaklaşıldığında 429 yerine yanıtı hiç vermiyor
            # (okuma zaman aşımı); bu da hız sınırının bir yüzü, kalıcı
            # hata değil.
            if deneme == AZAMI_DENEME - 1:
                raise RuntimeError(
                    f"TEFAS bağlantı hatası ({tip} {gun}, {AZAMI_DENEME} "
                    f"deneme): {hata}"
                ) from hata
            time.sleep(GERI_CEKILME_SANIYE)
            continue
        if yanit.status_code == 429:
            if deneme == AZAMI_DENEME - 1:
                raise RuntimeError(
                    f"TEFAS hız sınırı aşılamadı ({tip} {gun}): "
                    f"{AZAMI_DENEME} deneme"
                )
            time.sleep(GERI_CEKILME_SANIYE)
            continue
        if yanit.status_code != 200:
            raise RuntimeError(f"TEFAS HTTP {yanit.status_code} ({tip} {gun})")
        break
    govde = yanit.json()
    satirlar = govde.get("resultList")
    if not satirlar:
        mesaj = govde.get("errorMessage") or ""
        if "out of bounds" in mesaj or "bulunamadı" in mesaj.lower():
            return None  # o gün yayın yok
        raise RuntimeError(f"TEFAS beklenmeyen yanıt ({tip} {gun}): {mesaj}")
    if len(satirlar) >= SAYFA_TAVANI:
        # Tavana dayanmak sessiz eksik veridir: toplamlar kırpılmış olurdu.
        raise RuntimeError(
            f"TEFAS sayfa tavanına dayandı ({len(satirlar)} satır) — "
            "SAYFA_TAVANI yükseltilmeli"
        )
    return satirlar


def _anlik_getir(tip: str, ay_sonu: date, onbellek: dict, session=None):
    """Ay sonundan geriye doğru ilk yayın günü. Bulunamazsa None."""
    anahtar = (tip, ay_sonu.isoformat())
    if anahtar in onbellek:
        return onbellek[anahtar]
    for geri in range(AZAMI_GERI_GUN):
        gun = ay_sonu - timedelta(days=geri)
        satirlar = _gun_cek(tip, gun, session)
        if satirlar is not None:
            onbellek[anahtar] = toplulastir(satirlar)
            return onbellek[anahtar]
    onbellek[anahtar] = None
    return None


def seri_cek(seri, onbellek: dict | None = None, session=None,
             bugun: date | None = None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    Her ay sonu için tek istek atılır ve sonuç `onbellek`te paylaşılır:
    aynı `tefas_tip`i kullanan dört ölçüt (büyüklük, hesap, fon sayısı,
    ortalama büyüklük) tek yanıttan üretilir, yoksa istek sayısı dörde
    katlanırdı.

    Tarih olarak ayın BİRİ yazılır (aylık seri sözleşmesi), değer o ayın
    son yayın gününün anlık görüntüsüdür — yani ay sonu stoku.
    """
    bugun = bugun or date.today()
    onbellek = {} if onbellek is None else onbellek

    noktalar: dict[str, float] = {}
    for ay_sonu in ay_sonlari(bugun):
        toplam = _anlik_getir(seri.tefas_tip, ay_sonu, onbellek, session)
        if toplam is None:
            continue
        noktalar[f"{ay_sonu.year}-{ay_sonu.month:02d}-01"] = toplam[
            seri.tefas_olcut
        ]

    if not noktalar:
        raise RuntimeError(f"TEFAS hiç nokta döndürmedi: {seri.id}")

    df = pd.DataFrame(sorted(noktalar.items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)
