"""TMSD (Türkiye Makarna Sanayicileri Derneği) aylık sektör raporu istemcisi.

Kaynak XLSX/HTML değil — her ay yayımlanan bir PDF sektör raporu
(`https://www.makarna.org.tr/uploads/files/TMSD%20Sekt%C3%B6r%20Raporu%20
<Ay>%20<Yıl>.pdf`). Rapor KAPAK adı VERİ ayından BİR AY İLERİDE (ölçüldü,
2026-09-18, canlı): "Temmuz 2026" kapaklı rapor 1 Ağustos 2026'da
yayımlanır ama tablo ızgaraları hâlâ "HAZİRAN 2026" başlığı taşıyor ve
en son ay olarak Haziran'ı gösterir (`bulten_url`nin `ay` argümanı bu
yüzden İSTENEN VERİ AYI değil, İSTENEN KAPAK adı için kullanılan çağırma
sırası — `_en_son_bulteni_getir` bugünün ayından geriye doğru deneme
yaparak KAPAK adını bulur; tablonun KENDİ satır/sütun etiketleri gerçek
veri ayını belirler, URL'e güvenilmez). Doğrulandı: 7 kalemin TÜMÜ için
Haziran 2026 değerleri marketvisuals referans değerleriyle birebir
eşleşiyor (bkz. `tests/test_tmsd.py`); Temmuz 2026 marketvisuals'ta
görünüyor olsa da bu PDF'in hiçbir tablosunda (ne YIL/AY ne SEZON) henüz
yok — muhtemelen marketvisuals için ayrı/daha hızlı bir TÜİK ÖTS beslemesi
kullanılıyor; bu adaptör yalnızca TMSD'nin KENDİ yayımladığı en güncel
tabloyla sınırlı (bloke değil, ölçülen bir gecikme).

PDF'in içindeki tablolar (`pdfplumber` ile okunur, XLSX hücre ızgarası
YOK) her ürün için aynı şablonu tekrarlıyor: bir "YIL/AY" (takvim,
Ocak-Aralık) ya da "SEZON" (buğday/durum buğdayı — Temmuz-Haziran mahsul
yılı) satırı+sütunu ızgarası, ardından $/ton fiyat tablosu (İKİNCİ tablo,
kullanılmıyor). `pdfplumber.extract_tables()` bu tabloları GÜVENİLMEZ
şekilde (boş/karışık hücre dizileri) döndürüyor (ölçüldü); bu yüzden
`extract_words()` ile KONUM tabanlı ızgara yeniden inşa ediliyor:
- Sütun x0'ları başlık satırındaki ay etiketlerinden (Oca./Tem./...)
  okunur.
- Sayılar HÜCRE İÇİNDE SAĞA hizalı geliyor (başlıklar SOLA hizalı) —
  bu yüzden kelime EŞLEŞTİRMESİ `x0`ya en yakın sütun değil, kelimenin
  SAĞ kenarının (`x1`) hangi [sütun_x0, sonraki_sütun_x0] aralığına
  düştüğüne bakılarak yapılır (ölçüldü: `x0` bazlı eşleştirme bitişik
  sütunlara yanlış atama yapıyordu, ör. tek haneli "5" değeri "Tem."
  sütununa değil "Ağu." sütununa düşüyordu).
- Bazı ondalıklı değerler PDF'in kendi satır kırılımı yüzünden İKİ ayrı
  kelimeye bölünüyor (ölçüldü: "103.8" → "103." + "8", "8" ana satırın
  ~25pt altında farklı bir "top" ile geliyor). Her satır etiketinin
  (yıl/sezon) y-aralığı bir SONRAKİ satır etiketine kadar (ya da son
  satırsa +30pt) genişletilerek bu parçalar birleştirilir.

Buğday/durum buğdayı SEZON tabloları TAKVİM AYI değil MAHSUL YILI
(Temmuz-Haziran) bazında: "2023/24" satırı Temmuz 2023 - Haziran 2024'ü
kapsar, sütun sırası Tem./Ağu./.../Haz. `bulteni_ayikla` her (sezon,
sütun) çiftini doğrudan takvim (yıl, ay)'a çevirir (sütun Tem-Ara ise
sezonun İLK yılı, Oca-Haz ise sezonun İKİNCİ yılı).
Ölçüldü (2026-09-18, canlı): Temmuz 2026 raporunun "DURUM BUĞDAYI
İTHALATI" SEZON tablosunda 2023/24 satırı Tem-Ara = [5, 5, 9, 5, 6, 5]
— marketvisuals'ın 2023 takvim yılı Temmuz-Aralık değerleriyle
([5.0, 5.0, 9.0, 5.0, 6.0, 5.0]) birebir eşleşiyor.

Her aylık PDF'in tablo ızgarası GEÇMİŞİN TAMAMINI TAŞIMIYOR — yalnızca
son ~3 takvim yılını (ya da mahsul yılını) gösteriyor (TİM'in yıl başına
tek dosyasının aksine, tek bir PDF'te sınırlı bir kayan pencere var).
Bu yüzden bu adaptör TEK bir (en güncel yayımlanmış) PDF'i çeker ve o
PDF'in gösterdiği pencereyle sınırlı kalır (~3 yıl) — TİM'in çok-dosyalı
tam-geçmiş desenini burada uygulamak (aylık PDF'leri geriye doğru tek
tek indirip üst üste bindirmek) bilinçli olarak kapsam dışı bırakıldı;
mevcut pencere marketvisuals'ın gösterdiği 2023-2026 aralığının büyük
kısmını (2023 Temmuz'dan itibaren) kapsıyor.
"""

from __future__ import annotations

import io
import re
from datetime import date

import pandas as pd
import pdfplumber
import requests

TABAN = "https://www.makarna.org.tr/uploads/files"
ZAMAN_ASIMI = 60

AY_ADLARI_TR = {
    1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
    7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık",
}
# Takvim tablosu (YIL/AY) sütun sırası — ay 1 = Oca.
TAKVIM_SUTUNLARI = ["Oca.", "Şub.", "Mar.", "Nis.", "May.", "Haz.",
                     "Tem.", "Ağu.", "Eyl.", "Eki.", "Kas.", "Ara."]
# Mahsul yılı tablosu (SEZON) sütun sırası — Temmuz'dan başlar.
SEZON_SUTUNLARI = ["Tem.", "Ağu.", "Eyl.", "Eki.", "Kas.", "Ara.",
                    "Oca.", "Şub.", "Mar.", "Nis.", "May.", "Haz."]

KALEM_MAKARNA_EKMEKLIK = "makarna-ekmeklik"
KALEM_MAKARNA_DURUM = "makarna-durum"
KALEM_NOODLE = "noodle"
KALEM_IRMIK = "irmik"
KALEM_DURUM_BUGDAY_ITHALAT = "durum-bugday-ithalat"
KALEM_DURUM_BUGDAY_IHRACAT = "durum-bugday-ihracat"
KALEM_EKMEKLIK_BUGDAY_ITHALAT = "ekmeklik-bugday-ithalat"

GECERLI_TMSD_KALEMLERI = {
    KALEM_MAKARNA_EKMEKLIK, KALEM_MAKARNA_DURUM, KALEM_NOODLE, KALEM_IRMIK,
    KALEM_DURUM_BUGDAY_ITHALAT, KALEM_DURUM_BUGDAY_IHRACAT,
    KALEM_EKMEKLIK_BUGDAY_ITHALAT,
}

# Her kalemin PDF'teki sayfa başlığı (birebir, `extract_text()`'in ilk
# satırıyla karşılaştırılır) + tablo anahtar etiketi ("YIL/AY" takvim,
# "SEZON" mahsul yılı) + sütun sırası. Aynı başlık birden çok sayfada
# tekrar edebilir (miktar + fiyat tabloları, bazen yanlış başlıklı bir
# sayfa da — ölçüldü: "DURUM BUĞDAYI İTHALATI" başlığı İHRACAT fiyat
# sayfasında da tekrarlanıyor); İLK eşleşen sayfa her zaman miktar
# tablosunu taşıyor (ölçüldü, 2026-09-18).
_KALEM_TANIMLARI = {
    KALEM_MAKARNA_EKMEKLIK: ("MAKARNA İHRACATI (EKMEKLİK BUĞDAY İÇEREN)", "YIL/AY", TAKVIM_SUTUNLARI),
    KALEM_MAKARNA_DURUM: ("MAKARNA İHRACATI (DURUM)", "YIL/AY", TAKVIM_SUTUNLARI),
    KALEM_NOODLE: ("NOODLE İHRACATI", "YIL/AY", TAKVIM_SUTUNLARI),
    KALEM_IRMIK: ("İRMİK İHRACATI", "YIL/AY", TAKVIM_SUTUNLARI),
    KALEM_DURUM_BUGDAY_ITHALAT: ("DURUM BUĞDAYI İTHALATI", "SEZON", SEZON_SUTUNLARI),
    KALEM_DURUM_BUGDAY_IHRACAT: ("DURUM BUĞDAYI İHRACATI", "SEZON", SEZON_SUTUNLARI),
    KALEM_EKMEKLIK_BUGDAY_ITHALAT: ("EKMEKLİK BUĞDAYI İTHALATI", "SEZON", SEZON_SUTUNLARI),
}
assert set(_KALEM_TANIMLARI) == GECERLI_TMSD_KALEMLERI


def bulten_url(yil: int, ay: int) -> str:
    """Rapor KAPAK adı (bkz. modül docstring'i: veri ayından bir ay ileride);
    `_en_son_bulteni_getir` bunu bugünün ayından geriye deneyerek dolaylı
    kullanır — dönen verinin GERÇEK ayı tablonun kendi etiketinden gelir."""
    ay_adi = AY_ADLARI_TR[ay]
    return f"{TABAN}/TMSD%20Sekt%C3%B6r%20Raporu%20{ay_adi}%20{yil}.pdf"


def _sayfayi_bul(pdf: pdfplumber.PDF, baslik: str):
    """Metni tam olarak `baslik` ile başlayan İLK sayfayı döner."""
    for sayfa in pdf.pages:
        metin = (sayfa.extract_text() or "").strip()
        if metin.startswith(baslik):
            return sayfa
    raise RuntimeError(f"TMSD: '{baslik}' başlıklı sayfa bulunamadı — rapor şablonu değişmiş olabilir")


def _tabloyu_ayikla(sayfa, anahtar_etiket: str, sutun_sirasi: list[str]) -> dict[str, dict[str, str]]:
    """Bir sayfadaki İLK (miktar) YIL/AY ya da SEZON ızgarasını konum
    tabanlı olarak `{satir_etiketi: {sutun_etiketi: ham_metin}}` şeklinde okur.

    Bkz. modül docstring'i: sütun eşleştirmesi `x1` (sağ kenar) ile, satır
    aralığı bir sonraki satıra kadar genişletilerek bölünmüş ondalıklar
    birleştirilir.
    """
    kelimeler = sayfa.extract_words()
    ankorlar = sorted((k for k in kelimeler if k["text"] == anahtar_etiket), key=lambda k: k["top"])
    if not ankorlar:
        raise RuntimeError(f"TMSD: '{anahtar_etiket}' tablo başlığı bulunamadı")
    ankor = ankorlar[0]
    baslik_top = ankor["top"]

    baslik_satiri = [k for k in kelimeler if abs(k["top"] - baslik_top) < 2 and k is not ankor]
    kolon_x0 = []
    for etiket in sutun_sirasi:
        eslesen = [k for k in baslik_satiri if k["text"] == etiket]
        if not eslesen:
            raise RuntimeError(f"TMSD: '{etiket}' sütun başlığı bulunamadı — şablon değişmiş olabilir")
        kolon_x0.append(min(eslesen, key=lambda k: abs(k["top"] - baslik_top))["x0"])
    ust_sinirlar = kolon_x0[1:] + [kolon_x0[-1] + 90]

    # Sayfa aynı ızgarayı İKİ KEZ taşıyabilir (miktar + $/ton fiyat
    # tablosu, bkz. modül docstring'i); satır araması bir SONRAKİ
    # `anahtar_etiket` oluşumuna kadar sınırlanır — yoksa fiyat
    # tablosunun aynı x0'daki yıl/sezon etiketleri de yakalanıp
    # "yinelenen satır etiketi" hatasına düşer.
    alt_sinir_top = ankorlar[1]["top"] if len(ankorlar) > 1 else float("inf")
    satir_deseni = re.compile(r"^\d{4}(/\d{2})?$")
    satirlar = sorted(
        (k for k in kelimeler
         if satir_deseni.match(k["text"]) and abs(k["x0"] - ankor["x0"]) < 15
         and baslik_top < k["top"] < alt_sinir_top),
        key=lambda k: k["top"],
    )
    if not satirlar:
        raise RuntimeError("TMSD: tabloda satır etiketi (yıl/sezon) bulunamadı")

    sonuc: dict[str, dict[str, str]] = {}
    for i, satir in enumerate(satirlar):
        ust = satir["top"] - 1
        alt = satirlar[i + 1]["top"] - 1 if i + 1 < len(satirlar) else satir["top"] + 30
        satir_kelimeleri = [
            k for k in kelimeler
            if ust <= k["top"] < alt and k["x0"] > ankor["x0"] + 5 and k is not satir
        ]
        hucreler: dict[str, list] = {}
        for k in satir_kelimeleri:
            for j, (alt_sinir, ust_sinir) in enumerate(zip(kolon_x0, ust_sinirlar)):
                if alt_sinir < k["x1"] <= ust_sinir:
                    hucreler.setdefault(sutun_sirasi[j], []).append(k)
                    break
        deger: dict[str, str] = {}
        for etiket, parcalar in hucreler.items():
            parcalar.sort(key=lambda k: (k["top"], k["x0"]))
            deger[etiket] = "".join(p["text"] for p in parcalar)
        if satir["text"] in sonuc:
            raise RuntimeError(f"TMSD: yinelenen satır etiketi: {satir['text']!r}")
        sonuc[satir["text"]] = deger
    return sonuc


def _sayiya_cevir(ham: str, anahtar: str, konum: str) -> float:
    if not re.fullmatch(r"[\d,]+(\.\d+)?", ham):
        raise RuntimeError(f"TMSD {anahtar}: sayısal olmayan hücre ({konum}): {ham!r}")
    return float(ham.replace(",", ""))


def bulteni_ayikla(baytlar: bytes, anahtar: str) -> dict[str, dict[str, float]]:
    """Bir PDF'in tamamından yedi kalemin TAKVİM AYI bazlı serilerini çıkarır.

    Dönen değer `{kalem: {"YYYY-MM-01": değer}}`. Mahsul yılı (SEZON)
    tabloları burada `_sezon_karsiligi` ile takvim ayına çevrilmiş olarak
    döner — çağıran taraf (`seri_cek`) sezon/takvim farkını görmez.
    """
    with pdfplumber.open(io.BytesIO(baytlar)) as pdf:
        sonuc: dict[str, dict[str, float]] = {}
        for kalem, (baslik, anahtar_etiket, sutunlar) in _KALEM_TANIMLARI.items():
            sayfa = _sayfayi_bul(pdf, baslik)
            tablo = _tabloyu_ayikla(sayfa, anahtar_etiket, sutunlar)
            noktalar: dict[str, float] = {}
            if anahtar_etiket == "YIL/AY":
                for satir_etiketi, hucreler in tablo.items():
                    yil = int(satir_etiketi)
                    for ay, ay_etiketi in enumerate(TAKVIM_SUTUNLARI, start=1):
                        if ay_etiketi in hucreler:
                            konum = f"{kalem}/{satir_etiketi}/{ay_etiketi}"
                            noktalar[f"{yil}-{ay:02d}-01"] = _sayiya_cevir(hucreler[ay_etiketi], anahtar, konum)
            else:  # SEZON
                # Takvim ayı -> (sezon, sütun) eşlemesini TERSİNE çevirerek
                # tablo satırlarını (sezon etiketleri) dolaş.
                for satir_etiketi, hucreler in tablo.items():
                    ilk_yil = int(satir_etiketi.split("/")[0])
                    for ay_offset, ay_etiketi in enumerate(SEZON_SUTUNLARI):
                        if ay_etiketi not in hucreler:
                            continue
                        if ay_offset < 6:
                            yil, ay = ilk_yil, ay_offset + 7
                        else:
                            yil, ay = ilk_yil + 1, ay_offset - 5
                        konum = f"{kalem}/{satir_etiketi}/{ay_etiketi}"
                        noktalar[f"{yil}-{ay:02d}-01"] = _sayiya_cevir(hucreler[ay_etiketi], anahtar, konum)
            if not noktalar:
                raise RuntimeError(f"TMSD {anahtar}: '{kalem}' için hiç nokta okunamadı")
            sonuc[kalem] = noktalar
    return sonuc


def _bulten_indir(url: str, session=None) -> bytes | None:
    """404 → None (o ay henüz yayımlanmamış); diğer hatalar yükselir."""
    http = session or requests
    yanit = http.get(url, timeout=ZAMAN_ASIMI)
    if yanit.status_code == 404:
        return None
    if yanit.status_code != 200:
        raise RuntimeError(f"TMSD HTTP {yanit.status_code} ({url})")
    return yanit.content


def _en_son_bulteni_getir(bugun: date, onbellek: dict, session=None) -> dict[str, dict[str, float]]:
    """Bugünün ayından geriye giderek YAYIMLANMIŞ en güncel raporu bulur.

    Rapor kapak adı ile veri ayı arasında kayma olduğu için (bkz. modül
    docstring'i) `bugun`ın kapak adına denk gelen ay genelde henüz yok;
    birkaç ay geriye inilir.
    """
    if "sonuc" in onbellek:
        return onbellek["sonuc"]
    yil, ay = bugun.year, bugun.month
    for _ in range(6):
        baytlar = _bulten_indir(bulten_url(yil, ay), session)
        if baytlar is not None:
            sonuc = bulteni_ayikla(baytlar, f"{yil}.{ay:02d}")
            onbellek["sonuc"] = sonuc
            return sonuc
        yil, ay = (yil, ay - 1) if ay > 1 else (yil - 1, 12)
    raise RuntimeError("TMSD: son 6 ayda yayımlanmış bir rapor bulunamadı")


def seri_cek(seri, *, onbellek: dict | None = None, session=None,
             bugun: date | None = None):
    """En güncel (yayımlanmış) TMSD raporundan tek bir kalemin serisini çeker.

    Yedi kalem aynı PDF'i paylaşır (bkz. `_en_son_bulteni_getir`); rapor
    tek bir kayan pencereye (~3 takvim/mahsul yılı) sahiptir — bkz. modül
    docstring'inin son paragrafı.
    """
    if seri.tmsd_kalem not in GECERLI_TMSD_KALEMLERI:
        raise RuntimeError(f"TMSD: bilinmeyen kalem '{seri.tmsd_kalem}'")

    bugun = bugun or date.today()
    onbellek = {} if onbellek is None else onbellek
    tum_kalemler = _en_son_bulteni_getir(bugun, onbellek, session)
    noktalar = tum_kalemler[seri.tmsd_kalem]

    if not noktalar:
        raise RuntimeError(f"TMSD: '{seri.tmsd_kalem}' için hiç veri toplanamadı")

    tarihler = sorted(t for t in noktalar if seri.start_date is None or t >= seri.start_date)
    df = pd.DataFrame({"date": tarihler, "value": [noktalar[t] for t in tarihler]})
    return df.reset_index(drop=True)
