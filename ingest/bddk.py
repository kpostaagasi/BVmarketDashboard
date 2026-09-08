"""BDDK Aylık Bülten (Gelişmiş Gösterim) istemcisi.

Kaynak gerçekleri 2026-09-08'de canlı ölçüldü (sıfırdan yeniden
keşfetmeye çalışmayın):

- Veri kaynağı, bültenin "Gelişmiş Gösterim" ekranının JSON ucudur:
  `POST /BultenAylik/tr/Home/GelismisRaporGetir`, gövde form-encoded:
  `baslangicYil, baslangicAy, bitisYil, bitisAy, periyot=1, paraBirimi=TL,
  taraf, kalemSutun, gosterimTuru=grid`. TEK istekte çok yıllı seri döner
  (2019-01 → cari ay: 91 nokta), yani ay ay ya da yıl yıl gezmek gerekmez.
- `kalemSutun` bültendeki kalem kimliğidir ve çoğu zaman virgüllü bir
  listedir (`167,121` = Net Faiz Geliri): BDDK zaman içinde şema
  değiştirdiği için aynı kalemin eski ve yeni kimlikleri birlikte
  gönderilir. Katalogdaki `bddk_kalem` bu dizeyi olduğu gibi taşır.
- `taraf` banka GRUBUdur, tek tek banka değil: 10001 Sektör, 10002 Mevduat
  bankaları, 10003 Katılım, 10004 Kalkınma ve Yatırım, 10005 Yerli Özel,
  10008/10009/10010 Mevduat-Yerli Özel/Kamu/Yabancı. Banka bazlı veri bu
  bültende yok (FinTürk ayrı bir ürün).
- Yanıt jqGrid biçimindedir: `Json.colNames` sütun adları,
  `Json.data.rows[i].cell` = [Banka, Yıl, Ay, ...değerler, Sıra]. Kar/zarar
  kalemlerinde üç değer sütunu (TP, YP, Toplam), rasyolarda tek sütun var.
- **KAR/ZARAR KALEMLERİ YILBAŞINDAN KÜMÜLATİFTİR**: 2026-01 = 201.706,
  2026-02 = 390.766 … 2026-07 = 1.471.532 (milyon TL). Aylık akımı görmek
  için yıl içinde fark alınır (Ocak olduğu gibi kalır). Bilanço stokları ve
  rasyolar kümülatif DEĞİLDİR — katalogdaki `bddk_kumulatif` bunu ayırır.
- **TLS: BDDK eksik sertifika zinciri gönderiyor.** Sunucu yalnızca kendi
  sertifikasını veriyor, imzalayan GlobalSign ara sertifikasını vermiyor;
  tarayıcı/curl bunu kendi deposundan tamamladığı için sorun görünmüyor ama
  `requests` `SSLError: unable to get local issuer certificate` veriyor.
  Çözüm: ara sertifika indirilip certifi paketinin sonuna eklenir
  (`_ca_paketi`). `verify=False` KULLANILMAZ — ara sertifika yine certifi
  içindeki GlobalSign köküne kadar doğrulanır, yani zincir kırılırsa hata
  yükselir. BDDK sertifika sağlayıcısını değiştirirse burası gürültülü
  şekilde kırılır ve `ARA_SERTIFIKA_URL` güncellenir.
"""

from __future__ import annotations

import ssl
import tempfile
from datetime import date

import certifi
import pandas as pd
import requests

UC = "https://www.bddk.org.tr/BultenAylik/tr/Home/GelismisRaporGetir"
ARA_SERTIFIKA_URL = "http://secure.globalsign.com/cacert/gsrsaovsslca2018.crt"
ZAMAN_ASIMI = 90
ILK_YIL = 2019
VARSAYILAN_TARAF = "10001"  # Sektör

BASLIKLAR = {
    # Uç, tarayıcıdaki jqGrid çağrısını taklit eder; XHR başlığı olmadan da
    # yanıt veriyor ama sözleşmeyi olduğu gibi taşımak daha güvenli.
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "X-Requested-With": "XMLHttpRequest",
}

_ca_yolu: str | None = None


def _ca_paketi(session=None) -> str:
    """certifi + BDDK'nın göndermediği ara sertifika. Süreç başına bir kez."""
    global _ca_yolu
    if _ca_yolu is not None:
        return _ca_yolu
    http = session or requests
    yanit = http.get(ARA_SERTIFIKA_URL, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(
            f"GlobalSign ara sertifikası indirilemedi: HTTP {yanit.status_code}"
        )
    ham = yanit.content
    pem = ham.decode() if ham.startswith(b"-----") else ssl.DER_cert_to_PEM_cert(ham)
    dosya = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
    dosya.write(certifi.contents() + "\n" + pem)
    dosya.close()
    _ca_yolu = dosya.name
    return _ca_yolu


def deger_sutunu(colNames: list[str]) -> int:
    """Değerin hangi sütunda olduğunu sütun ADINDAN bulur, konumdan değil.

    Kar/zarar kalemlerinde [Banka, Yıl, Ay, TP, YP, Toplam, Sıra] gelir ve
    "Toplam" istenir; rasyolarda tek değer sütunu (ör. "Rasyo") vardır.
    Konumsal (`cell[-2]`) okuma iki şeklin ikisinde de bugün doğru sonucu
    verir ama BDDK bir sütun eklediğinde sessizce yanlış sütunu okurdu.
    """
    if "Toplam" in colNames:
        return colNames.index("Toplam")
    kalanlar = [
        i for i, ad in enumerate(colNames)
        if ad not in ("Banka", "Yıl", "Ay", "Sira", "Sıra")
    ]
    if len(kalanlar) != 1:
        raise RuntimeError(
            f"BDDK yanıtında değer sütunu belirsiz: {colNames}"
        )
    return kalanlar[0]


def noktalari_ayikla(yanit: dict) -> dict[str, float]:
    """jqGrid yanıtından `{"YYYY-MM-01": değer}` çıkarır."""
    if not yanit.get("success"):
        raise RuntimeError(f"BDDK raporu başarısız döndü: {str(yanit)[:200]}")
    govde = yanit["Json"]
    sutun = deger_sutunu(list(govde["colNames"]))
    noktalar: dict[str, float] = {}
    for satir in govde["data"]["rows"]:
        hucreler = satir["cell"]
        yil, ay = int(hucreler[1]), int(hucreler[2])
        deger = hucreler[sutun]
        if deger is None or deger == "":
            continue
        noktalar[f"{yil}-{ay:02d}-01"] = float(deger)
    if not noktalar:
        raise RuntimeError("BDDK raporu hiç nokta döndürmedi")
    return noktalar


def kumulatifi_ayliga_cevir(noktalar: dict[str, float]) -> dict[str, float]:
    """Yılbaşından kümülatif kar/zarar kalemini aylık akıma çevirir.

    Ocak zaten tek aylıktır; sonraki aylar önceki aydan farkla bulunur.
    Bir ay eksikse (yayın atlanmışsa) o ay ATLANIR: eksik ayın üstüne
    fark almak iki ayı tek aya yığar ve sessizce yanlış değer üretir.
    """
    aylik: dict[str, float] = {}
    for tarih in sorted(noktalar):
        yil, ay = int(tarih[:4]), int(tarih[5:7])
        if ay == 1:
            aylik[tarih] = noktalar[tarih]
            continue
        onceki = f"{yil}-{ay - 1:02d}-01"
        if onceki in noktalar:
            aylik[tarih] = noktalar[tarih] - noktalar[onceki]
    return aylik


# Uç, henüz veri olmayan bir bitiş ayı istenirse HTTP 200 + `success: false`
# ve "2026 yılının en son 7 ayına ait veri bulunmaktadır!" döndürür. Mesajı
# ayrıştırmak yerine bitiş ayı geriye yürütülür: mesaj metni değişse de
# çalışır. Bültenin gecikmesi tipik olarak 1–2 ay, bu yüzden üst sınır
# geniş tutuluyor (yıl sınırını da geçebilir).
AZAMI_GERI_AY = 14


def _istek_govdesi(kalem: str, taraf: str, bitis: tuple[int, int]) -> dict:
    yil, ay = bitis
    return {
        "baslangicYil": ILK_YIL,
        "baslangicAy": 1,
        "bitisYil": yil,
        "bitisAy": ay,
        "periyot": 1,
        "paraBirimi": "TL",
        "taraf": taraf,
        "kalemSutun": kalem,
        "gosterimTuru": "grid",
    }


def geriye_aylar(bugun: date, adet: int = AZAMI_GERI_AY) -> list[tuple[int, int]]:
    """`bugun`den başlayarak geriye doğru (yıl, ay) çiftleri."""
    aylar = []
    yil, ay = bugun.year, bugun.month
    for _ in range(adet):
        aylar.append((yil, ay))
        ay -= 1
        if ay == 0:
            yil, ay = yil - 1, 12
    return aylar


def _rapor_cek(kalem: str, taraf: str, bugun: date, session=None,
               onbellek: dict | None = None) -> dict:
    """Yayımlanmış son döneme kadar olan seriyi çeker.

    Bulunan bitiş dönemi `onbellek["bitis"]`e yazılır: ilk seri geri
    yürüyerek dönemi bulur, kalan seriler tek istekte çeker.
    """
    http = session or requests
    onbellek = {} if onbellek is None else onbellek
    bilinen = onbellek.get("bitis")
    denenecek = [bilinen] if bilinen else geriye_aylar(bugun)

    son_hata = None
    for bitis in denenecek:
        yanit = http.post(
            UC,
            data=_istek_govdesi(kalem, taraf, bitis),
            headers=BASLIKLAR,
            timeout=ZAMAN_ASIMI,
            verify=_ca_paketi(session),
        )
        if yanit.status_code != 200:
            raise RuntimeError(f"BDDK HTTP {yanit.status_code} (kalem {kalem})")
        govde = yanit.json()
        if govde.get("success"):
            onbellek["bitis"] = bitis
            return govde
        son_hata = govde.get("error")
    raise RuntimeError(
        f"BDDK son {AZAMI_GERI_AY} ayın hiçbiri için veri döndürmedi "
        f"(kalem {kalem}); son yanıt: {son_hata}"
    )


def seri_cek(seri, onbellek: dict | None = None, session=None,
             bugun: date | None = None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `onbellek` verilirse aynı (kalem, taraf) çifti koşu başına bir kez
    çekilir; ayrıca yayımlanmış son dönem `onbellek["bitis"]`te paylaşılır,
    böylece geri yürüme (bkz. `_rapor_cek`) yalnızca ilk seride koşar.
    """
    bugun = bugun or date.today()
    onbellek = {} if onbellek is None else onbellek
    taraf = seri.bddk_taraf or VARSAYILAN_TARAF
    anahtar = (seri.bddk_kalem, taraf)

    if anahtar not in onbellek:
        onbellek[anahtar] = noktalari_ayikla(
            _rapor_cek(seri.bddk_kalem, taraf, bugun, session, onbellek)
        )
    noktalar = onbellek[anahtar]

    if seri.bddk_kumulatif:
        noktalar = kumulatifi_ayliga_cevir(noktalar)

    df = pd.DataFrame(sorted(noktalar.items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)
