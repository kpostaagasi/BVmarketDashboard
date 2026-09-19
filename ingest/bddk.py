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

import html
import re
import ssl
import tempfile
from datetime import date, timedelta

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


# --- BDDK Haftalık Bülten (Takipteki Alacaklar vb.) -----------------------
#
# Kaynak gerçekleri 2026-09-18'de canlı ölçüldü (sıfırdan yeniden
# keşfetmeye çalışmayın):
#
# - Sayfa `https://www.bddk.org.tr/BultenHaftalik/tr` bir MVC uygulaması;
#   satır bazlı "karşılaştırma" grafiği `POST
#   /BultenHaftalik/tr/Home/KiyaslamaJsonGetir` gövde form-encoded:
#   `dil=tr, tarih=DD.MM.YYYY, id, parabirimi=TRY, sutun, tarafKodu, gun`.
#   Bu uç antiforgery token GEREKTİRMEZ (yalnızca klasik tablo/form
#   POST'ları token ister); tek gereken oturum çerezidir.
# - `id` satırı, `sutun` değer sütununu (1=TP, 2=YP, 3=Toplam) seçer;
#   `tarafKodu` banka grubudur (Sektör=10001). `id` tabloya özel olsa da
#   ölçüldüğünde AKTİF TABLO SEÇİMİNDEN BAĞIMSIZ çalışıyor — tabloId
#   değiştirmeye gerek yok.
# - `gun` parametresi YOK SAYILIYOR: uç her zaman `tarih`de biten ~13
#   haftalık (13 nokta) sabit bir pencere döner. Tam geçmiş için `tarih`i
#   dönen pencerenin en erken tarihinden bir gün geriye çekip yeniden
#   istemek gerekir (haftalık sayfalama).
# - Tarihler `D.MM.YYYY` biçiminde (gün sıfır doldurmasız olabilir, örn.
#   `4.10.2024`), değerler İngilizce ondalık noktalı sayı.
# - TLS sorunu aylık bültenle aynıdır: `_ca_paketi` kullanılır.
UC_HAFTALIK = "https://www.bddk.org.tr/BultenHaftalik"
UC_HAFTALIK_JSON = f"{UC_HAFTALIK}/tr/Home/KiyaslamaJsonGetir"
HAFTALIK_PENCERE_GUN = 90
HAFTALIK_ILK_TARIH = "2019-01-01"




def _haftalik_tarih_str(d: date) -> str:
    return f"{d.day}.{d.month:02d}.{d.year}"


def _haftalik_tarih_parse(metin: str) -> str:
    gun, ay, yil = metin.split(".")
    return f"{int(yil):04d}-{int(ay):02d}-{int(gun):02d}"


def _haftalik_cari_tarih(session=None) -> str:
    """Bültenin cari (en son yayımlanan) tarihini ana sayfadan okur."""
    http = session or requests
    yanit = http.get(
        f"{UC_HAFTALIK}/tr", timeout=ZAMAN_ASIMI, verify=_ca_paketi(session),
    )
    if yanit.status_code != 200:
        raise RuntimeError(f"BDDK Haftalık Bülten HTTP {yanit.status_code}")
    eslesme = re.search(r'"tarih":\s*\x27([\d.]+)\x27', yanit.text)
    if not eslesme:
        raise RuntimeError("BDDK Haftalık Bülten cari tarihi bulunamadı")
    return eslesme.group(1)


def _haftalik_json_cek(id_: str, sutun: int, taraf: str, tarih: str,
                        session=None) -> dict:
    http = session or requests
    yanit = http.post(
        UC_HAFTALIK_JSON,
        data={
            "dil": "tr", "tarih": tarih, "id": id_, "parabirimi": "TRY",
            "sutun": sutun, "tarafKodu": taraf, "gun": HAFTALIK_PENCERE_GUN,
        },
        headers=BASLIKLAR, timeout=ZAMAN_ASIMI, verify=_ca_paketi(session),
    )
    if yanit.status_code != 200:
        raise RuntimeError(f"BDDK Haftalık HTTP {yanit.status_code} (id {id_})")
    return yanit.json()


def haftalik_noktalar_cek(id_: str, sutun: int, taraf: str, cari_tarih: str,
                           session=None) -> dict[str, float]:
    """`id`/`sutun`/`taraf` satırının tüm geçmişini geriye sayfalayarak toplar.

    Uç sabit ~13 haftalık pencere döndüğü için `tarih` her turda dönen
    pencerenin en erken noktasının bir günü öncesine çekilir; pencere artık
    ilerlemiyorsa (sunucu aynı aralığı tekrar döndürdüyse) durulur.
    """
    noktalar: dict[str, float] = {}
    tarih = cari_tarih
    en_erken: str | None = None
    while True:
        govde = _haftalik_json_cek(id_, sutun, taraf, tarih, session)
        etiketler = govde.get("XEkseni") or []
        degerler = govde.get("YEkseni") or []
        if not etiketler:
            break
        for etiket, deger in zip(etiketler, degerler):
            if deger is None:
                continue
            noktalar[_haftalik_tarih_parse(etiket)] = float(deger)
        ilk = min(_haftalik_tarih_parse(e) for e in etiketler)
        if en_erken is not None and ilk >= en_erken:
            break
        en_erken = ilk
        if ilk <= HAFTALIK_ILK_TARIH:
            break
        onceki_gun = date.fromisoformat(ilk) - timedelta(days=1)
        tarih = _haftalik_tarih_str(onceki_gun)
    return noktalar


def seri_cek_haftalik(seri, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """BDDK Haftalık Bülten'den tek bir satırın (id/sutun/taraf) tam geçmişi.

    `onbellek` verilirse cari bülten tarihi ve her (id, sutun, taraf) çifti
    koşu başına bir kez çekilir.
    """
    onbellek = {} if onbellek is None else onbellek
    id_ = seri.bddk_haftalik_id
    sutun = seri.bddk_haftalik_sutun or 3
    taraf = seri.bddk_haftalik_taraf or VARSAYILAN_TARAF
    anahtar = ("haftalik", id_, sutun, taraf)

    if anahtar not in onbellek:
        if "haftalik_cari_tarih" not in onbellek:
            onbellek["haftalik_cari_tarih"] = _haftalik_cari_tarih(session)
        onbellek[anahtar] = haftalik_noktalar_cek(
            id_, sutun, taraf, onbellek["haftalik_cari_tarih"], session,
        )
    noktalar = onbellek[anahtar]
    if not noktalar:
        raise RuntimeError(f"BDDK Haftalık Bülten hiç nokta döndürmedi (id {id_})")

    df = pd.DataFrame(sorted(noktalar.items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)


# --- BDMK (Finansal Kiralama, Faktoring, Finansman Şirketleri) Bülteni ----
#
# Kaynak gerçekleri 2026-09-18'de canlı ölçüldü (sıfırdan yeniden
# keşfetmeye çalışmayın):
#
# - Ayrı bir BDDK ürünü: `https://www.bddk.org.tr/BultenAylikBdmk`.
#   Faktoring sayfası GET `/tr/Gosterim/Faktoring`, tablo POST
#   `/tr/Gosterim/FaktoringBasitRaporGetir`; Finansal Kiralama sayfası GET
#   `/tr/Gosterim/FinansalKiralama`, tablo POST
#   `/tr/Gosterim/FinansalKiralamaBasitRaporGetir`. Aylık bültenden farklı
#   olarak bu uç JSON değil TAM SAYFA HTML döner (tabloNo, yil, ay,
#   paraBirimi form alanları + antiforgery token gerekir) ve TEK AYLIK bir
#   tablo verir — tarih aralığı sorgusu yok, bu yüzden geçmiş ay ay
#   gezilerek toplanır.
# - `tabloNo=1` Bilanço (stok kalemler, ör. "5.1 Faktoring Alacakları"),
#   `tabloNo=2` Kâr Zarar (kalemler **yılbaşından kümülatiftir** — aylık
#   bültenle aynı desen, `kumulatifi_ayliga_cevir` ile aylığa çevrilir).
# - Tablo satırları "Toplam" (TP+YP) sütunuyla eşlenir; kalem adı satırın
#   ikinci hücresidir (ör. "XXI. DÖNEM NET KARI/ZARARI (XV+XX)",
#   "I. ESAS FAALİYET GELİRLERİ"). Sayılar Türk biçimidir (`.` binlik
#   ayraç, `,` ondalık).
# - Henüz yayımlanmamış bir ay istenirse tablo yalnızca başlık satırıyla
#   (veri satırı yok) döner — bu, "ay henüz yok" sinyalidir.
UC_BDMK = "https://www.bddk.org.tr/BultenAylikBdmk"
BDMK_ILK_YIL = 2019
_BDMK_SATIR_RE = re.compile(r"<tr>(.*?)</tr>", re.S)
_BDMK_HUCRE_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_BDMK_TABLO_RE = re.compile(r'<table id="TabloBasitGosterim".*?</table>', re.S)


def _bdmk_urun_url(urun: str) -> tuple[str, str]:
    if urun == "faktoring":
        return f"{UC_BDMK}/tr/Gosterim/Faktoring", f"{UC_BDMK}/tr/Gosterim/FaktoringBasitRaporGetir"
    if urun == "finansal_kiralama":
        return (
            f"{UC_BDMK}/tr/Gosterim/FinansalKiralama",
            f"{UC_BDMK}/tr/Gosterim/FinansalKiralamaBasitRaporGetir",
        )
    raise ValueError(f"Bilinmeyen bddk_bdmk_urun: {urun}")


def _bdmk_metin_temizle(html_parcasi: str) -> str:
    metin = html.unescape(html_parcasi).replace("\xa0", " ")
    return re.sub(r"\s+", " ", metin).strip()


def _bdmk_sayi(metin: str) -> float | None:
    """Türk sayı biçimini (`.` binlik ayraç, `,` ondalık) çözer.

    "-" BDDK tablolarında "veri yok" işaretidir (sıfır değil) — sessizce
    0.0'a çevrilirse gerçek sıfırla karışır ve kalem yanlış okunur.
    """
    temiz = metin.strip()
    if not temiz or temiz == "-":
        return None
    temiz = temiz.replace(".", "").replace(",", ".")
    try:
        return float(temiz)
    except ValueError:
        return None


def bdmk_satirlari_ayikla(tablo_html: str) -> dict[str, float]:
    """`TabloBasitGosterim` HTML'inden `{kalem_adı: toplam_değer}` çıkarır."""
    kalemler: dict[str, float] = {}
    for satir in _BDMK_SATIR_RE.findall(tablo_html):
        hucreler = _BDMK_HUCRE_RE.findall(satir)
        if len(hucreler) < 5:
            continue
        etiket = _bdmk_metin_temizle(hucreler[1])
        if not etiket:
            continue
        toplam = _bdmk_sayi(_bdmk_metin_temizle(hucreler[4]))
        if toplam is None:
            continue
        kalemler[etiket] = toplam
    return kalemler


def _bdmk_token(sayfa_url: str, session=None) -> str:
    http = session or requests
    yanit = http.get(sayfa_url, timeout=ZAMAN_ASIMI, verify=_ca_paketi(session))
    if yanit.status_code != 200:
        raise RuntimeError(f"BDMK HTTP {yanit.status_code} ({sayfa_url})")
    eslesme = re.search(
        r'name="__RequestVerificationToken" type="hidden" value="([^"]+)"',
        yanit.text,
    )
    if not eslesme:
        raise RuntimeError(f"BDMK antiforgery token bulunamadı: {sayfa_url}")
    return eslesme.group(1)


def _bdmk_tablo_cek(rapor_url: str, token: str, tablo_no: int, yil: int, ay: int,
                     session=None) -> dict[str, float]:
    http = session or requests
    yanit = http.post(
        rapor_url,
        data={
            "__RequestVerificationToken": token, "tabloNo": str(tablo_no),
            "yil": str(yil), "ay": str(ay), "paraBirimi": "TL",
        },
        timeout=ZAMAN_ASIMI, verify=_ca_paketi(session),
    )
    if yanit.status_code != 200:
        raise RuntimeError(
            f"BDMK HTTP {yanit.status_code} (tablo {tablo_no}, {yil}-{ay:02d})"
        )
    eslesme = _BDMK_TABLO_RE.search(yanit.text)
    if not eslesme:
        return {}
    return bdmk_satirlari_ayikla(eslesme.group(0))




def bdmk_aylik_gecmis_cek(urun: str, tablo_no: int, bugun: date,
                           session=None) -> dict[str, dict[str, float]]:
    """Bir (ürün, tablo) çifti için `{YYYY-MM-01: {kalem: değer}}` tam geçmişi.

    Cari aydan geriye doğru aylık HTML tabloları çekilir; henüz yayımlanmamış
    aylar (boş tablo) atlanarak yayımlanmış son aya kadar geriye yürünür,
    sonra BDMK_ILK_YIL'e kadar toplanır. Ara sıra kaçan tek bir ay (boş
    dönen) döngüyü kesmez, atlanır.
    """
    sayfa_url, rapor_url = _bdmk_urun_url(urun)
    token = _bdmk_token(sayfa_url, session)

    yil, ay = bugun.year, bugun.month
    for _ in range(AZAMI_GERI_AY):
        if _bdmk_tablo_cek(rapor_url, token, tablo_no, yil, ay, session):
            break
        ay -= 1
        if ay == 0:
            yil, ay = yil - 1, 12
    else:
        raise RuntimeError(
            f"BDMK son {AZAMI_GERI_AY} ayın hiçbirinde veri yok "
            f"({urun}, tablo {tablo_no})"
        )

    aylik: dict[str, dict[str, float]] = {}
    bos_ardisik = 0
    while yil > BDMK_ILK_YIL or (yil == BDMK_ILK_YIL and ay >= 1):
        satirlar = _bdmk_tablo_cek(rapor_url, token, tablo_no, yil, ay, session)
        if satirlar:
            aylik[f"{yil}-{ay:02d}-01"] = satirlar
            bos_ardisik = 0
        else:
            bos_ardisik += 1
            if bos_ardisik >= 6:
                break
        ay -= 1
        if ay == 0:
            yil, ay = yil - 1, 12
    return aylik


def seri_cek_bdmk(seri, onbellek: dict | None = None, session=None,
                   bugun: date | None = None) -> pd.DataFrame:
    """BDMK (Faktoring/Finansal Kiralama) bülteninden tek bir kalemin geçmişi.

    `onbellek` verilirse aynı (ürün, tabloNo) çifti koşu başına bir kez
    çekilir — Kâr Zarar tablosundaki birden çok kalem (Net Kâr, Toplam
    Gelirler) tek indirmeyi paylaşır.
    """
    bugun = bugun or date.today()
    onbellek = {} if onbellek is None else onbellek
    urun, tablo_no = seri.bddk_bdmk_urun, seri.bddk_bdmk_tablo
    anahtar_tablo = ("bdmk", urun, tablo_no)

    if anahtar_tablo not in onbellek:
        onbellek[anahtar_tablo] = bdmk_aylik_gecmis_cek(urun, tablo_no, bugun, session)
    aylik = onbellek[anahtar_tablo]

    kalem = seri.bddk_bdmk_kalem
    noktalar = {
        tarih: satirlar[kalem] for tarih, satirlar in aylik.items() if kalem in satirlar
    }
    if not noktalar:
        raise RuntimeError(
            f"BDMK kalemi bulunamadı: '{kalem}' ({urun}, tablo {tablo_no})"
        )
    if seri.bddk_bdmk_kumulatif:
        noktalar = kumulatifi_ayliga_cevir(noktalar)

    df = pd.DataFrame(sorted(noktalar.items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)
