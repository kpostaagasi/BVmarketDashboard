"""EPDK Petrol Piyasası aylık sektör raporu "EK" (çok tablolu) XLSX istemcisi.

Kaynak sayfası (`https://www.epdk.gov.tr/Detay/Icerik/3-0-104-1008/
petrolaylik-sektor-raporu`) yıl bazında açılır bir liste gösteriyor; her ay
satırında BİR ana rapor (`word.png`/`pdf.png`) ve BİR ya da daha fazla
ek dosya (`excel.png`) linki var — bağlantılar `<a>` metninde değil
`/Detay/DownloadDocument?id=<opak-id>` sorgu parametresinde, bu yüzden
`a[href$=.xlsx]` gibi bir CSS seçiciyle bulunamıyor; `dosyalari_ayikla`
ham HTML'den `(yıl, ay, xlsx URL'i)` üçlülerini regex ile çıkarır.

**Format kırılması (ölçüldü 2026-09-18): EPDK bu çok tablolu "Tablo 1"–
"Tablo 24" EK formatını yalnızca Ocak 2026'dan itibaren yayımlıyor.**
Aralık 2025 ve öncesi ayların eki tamamen farklı bir dosya: "İl Bazında
Teslimler" (81 il × şirket matrisi, ürün grubu toplamı yok, "Tablo N"
sayfası hiç yok) — bu adaptör o eski formatı OKUMUYOR. Bu yüzden seriler
Ocak 2026'dan bugüne sınırlı bir geçmişle başlıyor; `havacilik` kategorisinin
EUROCONTROL notundaki "kaynak yalnızca cari yılı taşır" kısıtına benzer bir
durum (bkz. `catalog/categories.yaml`).

Her ayın EK dosyası kendi başına yeterli: "Aylık Bazda" tablolar (Tablo 1
rafineri üretimi, Tablo 5 ithalat, Tablo 11 ihracat) o yılın Ocak'tan o aya
kadarki TÜM ayları sütun taşır — ama Tablo 12 (yurt içi satış) TEK dönemlik
(yalnızca rapor ayı). Bu yüzden `seri_cek` tim.py/osd.py gibi AYRI ay
dosyalarını indirip HER birinden yalnızca KENDİ ayının sütununu okur — hem
dört tablo hem tüm ölçüt/ürün kombinasyonları arasında tutarlı, hem de
"en son dosyanın çok-aylık sütunlarına güven" riskini taşımaz (revizyonlar
farklı ay dosyalarında farklı görünebilir).

Şablon tek yıl içinde bile kararsız — üç ayrı çeşitlilik gözlemlendi ve
hepsi ele alınıyor:
- Yılın İLK ayında (Ocak) "Aylık Bazda" tablolar henüz tek ay taşıdığından
  ay-adı sütunu yerine tek bir "Miktar" sütunu kullanılıyor (bkz.
  `_ay_sutun_bul`), VE Tablo 11 satır/sütunu tamamen DEVRİK: satır=ay,
  sütun=ürün adı (diğer aylarda satır=ürün, sütun=ay) — bkz.
  `aylik_urun_tablosu`.
- Birleşik sayfa adları ay ay değişiyor: "Tablo2&6"/"Tablo7&8" (Oca–Mar),
  "Tablo 2-6"/"Tablo7-8" (Nis), "Tablo 2-6"/"Tablo 7-8" (May–). `_sayfa_bul`
  boşluk/tire/"&" farkını yok sayarak eşler.
- Başlık satırı yazımı kararsız: "Lisans Sahibinin Ünvanı" (Ü) vs "...Unvanı"
  (U), "ÜRÜN TÜRLERİ" (büyük harf, Ocak) vs "Ürün Türleri". Eşleştirmeler
  önek/büyük-küçük harf toleranslı.

Tablo 1'in ~40 granüler ürün satırı, kart başlıklarındaki 5 ürün grubuna
(Benzin, Motorin, Fuel Oil, Havacılık Yakıtları, Denizcilik Yakıtları)
EPDK_TABLO1_GRUPLARI ile toplanarak eşlenir — eşleme MarketVisuals'ın
epdk_satis_verileri.html kartlarındaki Temmuz 2026 değerleriyle (578,6 /
567,7 / 1.548,2 / -164,8 / 79,5 bin ton) BİREBİR doğrulandı. Bazı granüler
alt kalemler (ör. "Kurşunsuz Benzin 98 Oktan (E10)") o ay hiç hareket
görmediğinde satır tablodan TAMAMEN düşüyor (Temmuz'da 0 değerle mevcut,
Mart'ta satırın kendisi yok) — EPDK sıfır satırları dinamik attığından, bir
grubun eksik alt kalemi 0 sayılır; grubun kendisi (ör. "Ürün Türü" başlığı,
"Benzin Türleri" satırı/sütunu) eksikse RuntimeError hâlâ fırlar.

Tablo 5/11 (ithalat/ihracat) satırları zaten 5 ürün grubunun adını taşıyor,
toplama gerekmiyor. Tablo 12 (yurt içi satış) şirket bazlı; "Toplam" satırı
doğrudan okunur (kendi toplamları da MarketVisuals kartlarıyla birebir
eşleşti — Benzin 616,7, Fuel Oil 8,3, Havacılık 123,9, Denizcilik 2,3 bin
ton; Motorin'de küçük bir fark var: bizim 2.658,3 karşı kart 2.667,1 — EPDK
"Revizyon Tarihi" notlu dinamik veri revize ediyor, iki ölçüm farklı anda
alınmış olabilir).

Ham değerler TONDUR — "Bin ton" gösterime katalogdaki `olcek: 0.001` ile
çevrilir (AGENTS.md: "tek ölçekleme noktası" `ingest.run.olcekle`).
"""

from __future__ import annotations

import re
from io import BytesIO

import openpyxl
import pandas as pd
import requests

from core.catalog import (
    GECERLI_EPDK_DOGALGAZ_OLCUTLERI,
    GECERLI_EPDK_OLCUTLERI,
    GECERLI_EPDK_URUNLERI,
)

TABAN = "https://www.epdk.gov.tr"
LISTE_URL = f"{TABAN}/Detay/Icerik/3-0-104-1008/petrolaylik-sektor-raporu"
ZAMAN_ASIMI = 60

AY_ADLARI = (
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
)
AY_ADI_TO_NO = {ad: i + 1 for i, ad in enumerate(AY_ADLARI)}

# Çok tablolu "EK" formatının başladığı ilk dönem (bkz. modül docstring'i).
ILK_YIL = 2026
ILK_AY = 1

# Tablo 1'in granüler satır adları -> katalogdaki `epdk_urun` (GECERLI_
# EPDK_URUNLERI ile birebir eşleşmeli). Temmuz 2026 verisiyle doğrulandı
# (bkz. modül docstring'i).
EPDK_TABLO1_GRUPLARI = {
    "benzin": (
        "Kurşunsuz Benzin 95 Oktan",
        "Kurşunsuz Benzin 98 Oktan",
        "Kurşunsuz Benzin 98 Oktan (E10)",
    ),
    "motorin": ("Motorin", "Motorin (Biodizel ihtiva eden)"),
    "fuel-oil": (
        "Atmosferik Straight Run Fuel Oil",
        "Fuel Oil (Kükürt Oranı %0,1'i geçmeyenler)",
        "Fuel Oil (Kükürt Oranı %0,5'i geçen fakat %1'i geçmeyenler)",
        "Kalorifer Yakıtı (Kükürt Oranı %0,1'i geçen ancak %0,5'i geçmeyenler)",
        "Kalorifer Yakıtı (Kükürt Oranı %0,1'i geçmeyenler)",
        "Kalorifer Yakıtı (Kükürt Oranı %0,5'i geçen fakat %1'i geçmeyenler)",
        "Yüksek Kükürtlü Fuel Oil (Kükürt oranı %1'i geçenler)",
    ),
    "havacilik": ("Jet Yakıtı (Kerosen)", "Jet Yakıtı (Benzin)"),
    "denizcilik": ("Denizcilik Yakıtı (Artık)", "Denizcilik Yakıtı (Damıtık)"),
}
assert set(EPDK_TABLO1_GRUPLARI) == GECERLI_EPDK_URUNLERI

# Tablo 5/11/12'nin zaten grup adıyla gelen satır/sütun etiketleri.
EPDK_URUN_ETIKETLERI = {
    "benzin": "Benzin Türleri",
    "motorin": "Motorin Türleri",
    "fuel-oil": "Fuel Oil Türleri",
    "havacilik": "Havacılık Yakıtları",
    "denizcilik": "Denizcilik Yakıtları",
}
assert set(EPDK_URUN_ETIKETLERI) == GECERLI_EPDK_URUNLERI

# `ayin_tum_olculerini_cikar`'ın döndürdüğü dört ölçüt (GECERLI_EPDK_
# OLCUTLERI ile birebir eşleşmeli — bkz. pgsus.py'deki eşdeğer desen).
EPDK_OLCUT_ADLARI = ("rafineri-uretimi", "yurtici-satis", "ithalat", "ihracat")
assert set(EPDK_OLCUT_ADLARI) == GECERLI_EPDK_OLCUTLERI

_DOSYA_LISTESI_RE = re.compile(
    r'data-id="(\d+)"[^>]*onclick="ShowDetailList\(this\);"><i[^>]*></i>'
    r'(\d{4}) Y\w+ Petrol Piyasas\w+ (\w+) Ay\w+ .*?Sekt.{0,8}r Raporu',
    re.DOTALL,
)
_EXCEL_LINK_RE = re.compile(
    r'href="(/Detay/DownloadDocument\?id=[^"]+)"[^>]*title="[^"]*">'
    r"<img src ='/Content/img/excel\.png'"
)


def dosyalari_ayikla(html: str) -> list[dict]:
    """Ham liste sayfasından `{"yil", "ay", "url"}` girdileri çıkarır.

    Her ay girdisi TEK `<li>` bloğunda bir ana rapor linki (word/pdf) ve bir
    ya da daha fazla excel linki taşır; sıra ay ay değişebildiğinden
    (bazı aylarda excel önce, bazılarında sonra) her girdinin ARDINDAN gelen
    bir sonraki girdiye kadarki pencere içinde ilk excel linki alınır.
    """
    eslesmeler = list(_DOSYA_LISTESI_RE.finditer(html))
    sonuc = []
    for i, m in enumerate(eslesmeler):
        ay_no = AY_ADI_TO_NO.get(m.group(3))
        if ay_no is None:
            continue
        pencere_sonu = eslesmeler[i + 1].start() if i + 1 < len(eslesmeler) else len(html)
        excel_m = _EXCEL_LINK_RE.search(html, m.end(), pencere_sonu)
        if excel_m is None:
            continue  # o ay için henüz excel eki yayımlanmamış
        sonuc.append({"yil": int(m.group(2)), "ay": ay_no, "url": excel_m.group(1)})
    return sonuc


def cekilecek_dosyalar(dosya_listesi: list[dict]) -> list[dict]:
    """Yalnızca çok tablolu EK formatının geçerli olduğu (Ocak 2026+)
    dönemleri, eskiden yeniye sıralı döner."""
    return sorted(
        (d for d in dosya_listesi if (d["yil"], d["ay"]) >= (ILK_YIL, ILK_AY)),
        key=lambda d: (d["yil"], d["ay"]),
    )


def _ilk_dolu(row) -> tuple[int | None, str | None]:
    for i, v in enumerate(row):
        if v is not None and str(v).strip() != "":
            return i, str(v).strip()
    return None, None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _sayfa_bul(kitap, hedef: str):
    hedef_norm = _norm(f"Tablo{hedef}")
    for ad in kitap.sheetnames:
        if _norm(ad) == hedef_norm:
            return kitap[ad]
    raise RuntimeError(f"EPDK: 'Tablo {hedef}' sayfası bulunamadı (sayfalar: {kitap.sheetnames})")


def _ay_sutun_bul(baslik: list, ay_adi: str, tablo_no) -> int:
    if ay_adi in baslik:
        return baslik.index(ay_adi)
    if "Miktar" in baslik:
        # Yılın ilk ayı: tek ay olduğu için sütun adı ay adı değil "Miktar".
        return baslik.index("Miktar")
    raise RuntimeError(f"EPDK Tablo {tablo_no}: '{ay_adi}' sütunu bulunamadı ({baslik})")


def tablo1_uretim(satirlar: list, ay_adi: str) -> dict[str, float]:
    """Tablo 1'in (Aylık Bazda Rafineri Üretimi) granüler satırlarını 5 ürün
    grubuna toplar. Değerler HAM TONDUR (bin ton çevirisi katalog `olcek`i)."""
    baslik_idx = None
    for i, row in enumerate(satirlar):
        if row and row[0] and str(row[0]).strip() == "Ürün Türü":
            baslik_idx = i
            break
    if baslik_idx is None:
        raise RuntimeError("EPDK Tablo 1: 'Ürün Türü' başlık satırı bulunamadı")
    baslik = [str(c).strip() if c else c for c in satirlar[baslik_idx]]
    ay_col = _ay_sutun_bul(baslik, ay_adi, 1)

    deger_map: dict[str, float] = {}
    for row in satirlar[baslik_idx + 1:]:
        if not row or row[0] is None:
            continue
        ad = str(row[0]).strip()
        if ad in ("", "Genel Toplam") or ad.startswith("Tablo"):
            continue
        v = row[ay_col]
        deger_map[ad] = float(v) if isinstance(v, (int, float)) else 0.0

    sonuc = {}
    for urun, satir_adlari in EPDK_TABLO1_GRUPLARI.items():
        # Eksik alt kalem = 0 (bkz. modül docstring'i); grup adlarının HİÇBİRİ
        # yoksa da toplam sessizce 0 olur — bu, "Ürün Türü" başlığının ya da
        # tüm satırların birden kaybolduğu (şablon kırıldığı) durumdur ve
        # aşağı akışta seri_cek'in "hiç nokta yok" kontrolüyle yakalanır.
        sonuc[urun] = sum(deger_map.get(ad, 0.0) for ad in satir_adlari)
    return sonuc


def alt_tablo_satirlarini_bul(tum_satirlar: list, tablo_no: int) -> list:
    """Birleşik bir sayfada ('Tablo 2-6' gibi) 'Tablo N:' başlığından bir
    sonraki 'Tablo M:' başlığına (ya da sayfa sonuna) kadarki satırları döner."""
    baslangic = None
    for i, row in enumerate(tum_satirlar):
        col, val = _ilk_dolu(row)
        if val and val.startswith(f"Tablo {tablo_no}:"):
            baslangic = i
            break
    if baslangic is None:
        raise RuntimeError(f"EPDK: 'Tablo {tablo_no}:' başlığı bulunamadı")
    bitis = len(tum_satirlar)
    for i in range(baslangic + 1, len(tum_satirlar)):
        col, val = _ilk_dolu(tum_satirlar[i])
        if val and val.startswith("Tablo ") and ":" in val:
            bitis = i
            break
    return tum_satirlar[baslangic:bitis]


def aylik_urun_tablosu(satirlar: list, ay_adi: str, tablo_no: int) -> dict[str, float]:
    """Tablo 5/11 gibi satırları zaten ürün grubu adı olan 'Aylık Bazda'
    tabloları okur. Değerler HAM TONDUR."""
    baslik_idx = None
    for i, row in enumerate(satirlar):
        col, val = _ilk_dolu(row)
        if val and val.upper().startswith("ÜRÜN TÜR"):
            baslik_idx = i
            break

    if baslik_idx is not None:
        baslik = [str(c).strip() if c else c for c in satirlar[baslik_idx]]
        ay_col = _ay_sutun_bul(baslik, ay_adi, tablo_no)
        deger_map: dict[str, float] = {}
        for row in satirlar[baslik_idx + 1:]:
            col, ad = _ilk_dolu(row)
            if ad is None or ad.upper() in ("GENEL TOPLAM", "TOPLAM"):
                continue
            v = row[ay_col]
            deger_map[ad] = float(v) if isinstance(v, (int, float)) else 0.0
    else:
        # Yılın ilk ayı: tablo DEVRİK yayımlanıyor — satır=ay, sütun=ürün
        # (başlık ['Ay', 'Benzin Türleri', ...]).
        for i, row in enumerate(satirlar):
            col, val = _ilk_dolu(row)
            if val and val.upper() == "AY":
                baslik_idx = i
                break
        if baslik_idx is None:
            raise RuntimeError(f"EPDK Tablo {tablo_no}: ürün türü başlık satırı bulunamadı")
        baslik = [str(c).strip() if c else c for c in satirlar[baslik_idx]]
        veri_satiri = None
        for row in satirlar[baslik_idx + 1:]:
            col, ad = _ilk_dolu(row)
            if ad == ay_adi:
                veri_satiri = row
                break
        if veri_satiri is None:
            raise RuntimeError(f"EPDK Tablo {tablo_no}: '{ay_adi}' satırı bulunamadı")
        deger_map = {}
        for i, ad in enumerate(baslik):
            if ad and ad != "Ay":
                v = veri_satiri[i]
                deger_map[ad] = float(v) if isinstance(v, (int, float)) else 0.0

    sonuc = {}
    for urun, etiket in EPDK_URUN_ETIKETLERI.items():
        if etiket not in deger_map:
            raise RuntimeError(f"EPDK Tablo {tablo_no}: beklenen sütun/satır yok: '{etiket}'")
        sonuc[urun] = deger_map[etiket]
    return sonuc


def tablo12_yurtici_satis(satirlar: list) -> dict[str, float]:
    """Tablo 12'nin (o dönemin şirket bazlı yurt içi satışları) 'Toplam'
    satırını okur. Değerler HAM TONDUR."""
    baslik_idx = None
    for i, row in enumerate(satirlar):
        col, val = _ilk_dolu(row)
        if val and val.startswith("Lisans Sahibinin"):
            baslik_idx = i
            break
    if baslik_idx is None:
        raise RuntimeError("EPDK Tablo 12: başlık satırı bulunamadı")
    baslik = [str(c).strip() if c else c for c in satirlar[baslik_idx]]

    toplam_row = None
    for row in satirlar[baslik_idx + 1:]:
        col, val = _ilk_dolu(row)
        if val and val.upper() in ("TOPLAM", "GENEL TOPLAM"):
            toplam_row = row
            break
    if toplam_row is None:
        raise RuntimeError("EPDK Tablo 12: 'Toplam' satırı bulunamadı")

    sonuc = {}
    for urun, etiket in EPDK_URUN_ETIKETLERI.items():
        if etiket not in baslik:
            raise RuntimeError(f"EPDK Tablo 12: beklenen sütun yok: '{etiket}'")
        col = baslik.index(etiket)
        v = toplam_row[col]
        sonuc[urun] = float(v) if isinstance(v, (int, float)) else 0.0
    return sonuc


def ayin_tum_olculerini_cikar(baytlar: bytes, ay_adi: str) -> dict[str, dict[str, float]]:
    """Bir ayın EK dosyasından 4 ölçütün (rafineri-uretimi, yurtici-satis,
    ithalat, ihracat) 5'er ürün değerini çıkarır. Değerler HAM TONDUR."""
    kitap = openpyxl.load_workbook(BytesIO(baytlar), data_only=True, read_only=True)
    try:
        rows1 = list(_sayfa_bul(kitap, "1").iter_rows(values_only=True))
        rows26 = list(_sayfa_bul(kitap, "2-6").iter_rows(values_only=True))
        rows11 = list(_sayfa_bul(kitap, "11").iter_rows(values_only=True))
        rows12 = list(_sayfa_bul(kitap, "12").iter_rows(values_only=True))
    finally:
        kitap.close()

    tablo5 = alt_tablo_satirlarini_bul(rows26, 5)
    return {
        "rafineri-uretimi": tablo1_uretim(rows1, ay_adi),
        "ithalat": aylik_urun_tablosu(tablo5, ay_adi, 5),
        "ihracat": aylik_urun_tablosu(rows11, ay_adi, 11),
        "yurtici-satis": tablo12_yurtici_satis(rows12),
    }


def _dosya_listesi_cek(session=None) -> list[dict]:
    http = session or requests
    yanit = http.get(LISTE_URL, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"EPDK dosya listesi HTTP {yanit.status_code}")
    return cekilecek_dosyalar(dosyalari_ayikla(yanit.text))


def _dosya_indir(url: str, session=None) -> bytes:
    http = session or requests
    yanit = http.get(TABAN + url, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"EPDK aylık EK dosyası HTTP {yanit.status_code} ({url})")
    return yanit.content


def _tum_noktalari_getir(onbellek: dict, session=None) -> dict[tuple[str, str], dict[str, float]]:
    if "noktalar" in onbellek:
        return onbellek["noktalar"]

    dosyalar = _dosya_listesi_cek(session)
    if not dosyalar:
        raise RuntimeError(
            f"EPDK: {ILK_YIL}-{ILK_AY:02d} sonrası indirilecek aylık rapor bulunamadı"
        )

    noktalar: dict[tuple[str, str], dict[str, float]] = {}
    for d in dosyalar:
        ay_adi = AY_ADLARI[d["ay"] - 1]
        baytlar = _dosya_indir(d["url"], session)
        aylik = ayin_tum_olculerini_cikar(baytlar, ay_adi)
        tarih = f"{d['yil']:04d}-{d['ay']:02d}-01"
        for olcut, urun_degerleri in aylik.items():
            for urun, deger in urun_degerleri.items():
                noktalar.setdefault((olcut, urun), {})[tarih] = deger

    onbellek["noktalar"] = noktalar
    return noktalar


def seri_cek(seri, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `onbellek` verilirse dosya listesi ve her ayın ayrıştırılmış noktaları
    koşu boyunca paylaşılır: 20 seri (4 ölçüt × 5 ürün) aynı ~8 aylık dosya
    kümesini paylaşır, aksi halde seri başına 8 indirme olurdu.
    """
    onbellek = {} if onbellek is None else onbellek
    noktalar = _tum_noktalari_getir(onbellek, session)

    anahtar = (seri.epdk_olcut, seri.epdk_urun)
    if anahtar not in noktalar or not noktalar[anahtar]:
        raise RuntimeError(f"EPDK: ölçüt/ürün kombinasyonu bulunamadı: {anahtar!r} ({seri.id})")

    df = pd.DataFrame(sorted(noktalar[anahtar].items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)


# --- Doğal Gaz Piyasası aylık sektör raporu ---
#
# Kaynak sayfası PETROL'den FARKLI: `3-0-95-1007/dogal-gazaylik-sektor-
# raporu` (canlı ölçüldü — Google araması + site kazıması, sayfa `3-0-95`
# elektrik ağacı ALTINDA ama alt-yol `-1007` doğal gaza işaret ediyor).
# Liste HTML'i de farklı yazılmış: başlık "Doğal Gaz Piyasası Sektör
# Raporu <Ay> <Yıl>" (yıl SONDA; petrolde "<Yıl> Yılı Petrol Piyasası <Ay>
# Ayı Sektör Raporu" — yıl BAŞTA). `_EXCEL_LINK_RE` ve `cekilecek_dosyalar`/
# ILK_YIL/ILK_AY (2026-01) PETROLLE AYNI: doğal gaz eki de yalnızca Ocak
# 2026'dan itibaren yayımlanıyor — 2025 ve öncesi ay girdilerinde yalnızca
# `word.png` ana rapor var, excel eki hiç yok (canlı ölçüldü, Ağustos 2025
# girdisinde tek link).
#
# EK'in iç yapısı petrolden TAMAMEN FARKLI (ayrı XLSX şablonu, "Tablo-N "
# başlıkları TİRE+BOŞLUK ile yazılı — petrolün "Tablo N:" boşluk+iki nokta
# biçiminden farklı noktalama, bkz. `_dogalgaz_alt_tablo_bul`). Dokuz ölçüt
# üç farklı tablo TÜRÜNDEN okunuyor:
#   - Tablo-3 (şirket bazlı ithalat) ve Tablo-6 (depolama): petrolün Tablo 1
#     gibi "Aylık Bazda" ÇOK AYLIK sütunlu — her ay dosyası yalnızca KENDİ
#     ayının sütununu okur (aynı `_ay_sutun_bul` deseni).
#   - Tablo-8 (abone/serbest tüketici) ve Tablo-12 (şirket×sektör tüketim,
#     Tablo 11-12-13 birleşik sayfasında): TEK DÖNEMLİK — yalnızca rapor
#     ayını taşır, ay sütunu aranmaz.
#
# AHGAZ Grubu = Enerya (9 şirket) + Marmara (2 şirket) çatı markaları altında
# faaliyet gösteren 11 doğal gaz dağıtım şirketi. Tablo-8'de bir şirket
# BİRDEN FAZLA il satırında tekrarlanabiliyor (ör. MARMARA YALOVA hem
# Yalova hem Kocaeli hem Tekirdağ'da) — aynı ada ait TÜM il satırları
# toplanır. Temmuz 2026 verisiyle canlı ölçüldü ve MarketVisuals'ın
# epdk_dogalgaz_verileri.html kartlarıyla BİREBİR eşleşti: toplam abone
# 2.174.051, serbest tüketici 79.304 (Tablo-8 toplamı), toplam tüketim
# 97.064.499,84 Sm³ ≈ 97,06 milyon Sm³ (Tablo-12 "Genel Toplam" toplamı).
# NTGAZ (NATURELGAZ SANAYİ VE TİCARET A.Ş.) Tablo-12'de İKİ lisans tipi
# satırına (İthalat + Sıkıştırılmış Doğalgaz) bölünmüş — toplamı 14,87
# milyon Sm³ karta birebir uydu; AYGAZ tek satır, 8,65 milyon Sm³ birebir.
# BOTAŞ Tablo-3'te tek satır, Temmuz 2026 = 3,06 milyar Sm³ birebir. Özel
# ithalatçılar (AKFEL+BOSPHORUS+KİBAR) Mayıs-Temmuz 2026 hücrelerinde BOŞ
# (None) — MarketVisuals kartı bu yüzden "Nisan 2026"yı en son dönem
# gösteriyor (sıfır/boş ayları göstermeme tercihi). Bu adaptör petrol.py
# Tablo 1 ile AYNI ilkeyi izler ("EPDK sıfır satırları dinamik attığından,
# bir grubun eksik alt kalemi 0 sayılır"): boş hücre grubun o ay için 0
# Sm³ ithalat yaptığı biçiminde YORUMLANIR (veri UYDURULMAZ, yalnızca
# gerçek boş hücre 0 sayılır) — bu yüzden bizim seri Mayıs-Temmuz için de
# gerçek (0'a yakın) gözlemler taşıyabilir; kart yalnızca son SIFIR OLMAYAN
# noktayı öne çıkarıyor, veri kümesi farklı değil.
DOGALGAZ_LISTE_URL = f"{TABAN}/Detay/Icerik/3-0-95-1007/dogal-gazaylik-sektor-raporu"

_DOGALGAZ_DOSYA_LISTESI_RE = re.compile(
    r'data-id="(\d+)"[^>]*onclick="ShowDetailList\(this\);"><i[^>]*></i>'
    r'Do\w+ Gaz Piyasas\w+ Sekt.{0,8}r Raporu (\w+) (\d{4})',
)

AHGAZ_SIRKET_ONEKLERI = ("ENERYA", "MARMARA")
BOTAS_SIRKET_ADI = "BOTAŞ BORU HATLARI İLE PETROL TAŞIMA ANONİM ŞİRKETİ"
OZEL_ITHALATCI_SIRKETLERI = (
    "AKFEL GAZ SANAYİ VE TİCARET ANONİM ŞİRKETİ",
    "BOSPHORUS GAZ CORPORATİON ANONİM ŞİRKETİ",
    "KİBAR ENERJİ ANONİM ŞİRKETİ",
)
NTGAZ_SIRKET_ADI = "NATURELGAZ SANAYİ VE TİCARET ANONİM ŞİRKETİ"
AYGAZ_SIRKET_ADI = "AYGAZ DOĞAL GAZ TOPTAN SATIŞ ANONİM ŞİRKETİ"

# `dogalgaz_ayin_tum_olculerini_cikar`'ın döndürdüğü dokuz ölçüt
# (GECERLI_EPDK_DOGALGAZ_OLCUTLERI ile birebir eşleşmeli).
DOGALGAZ_OLCUT_ADLARI = (
    "ahgaz-tuketim", "ahgaz-abone", "ahgaz-serbest",
    "ntgaz-hacim", "aygaz-hacim",
    "botas-ithalat", "ozel-ithalatci-ithalat",
    "depolama-borugazi", "depolama-lng",
)
assert set(DOGALGAZ_OLCUT_ADLARI) == GECERLI_EPDK_DOGALGAZ_OLCUTLERI


def dogalgaz_dosyalari_ayikla(html: str) -> list[dict]:
    """Doğal gaz liste sayfasından `{"yil", "ay", "url"}` girdileri çıkarır.

    Petrolün `dosyalari_ayikla`'sıyla aynı "pencere içinde ilk excel linki"
    deseni; yalnızca başlık regex'i ve ay/yıl grup SIRASI farklı (bkz.
    modül docstring'i)."""
    eslesmeler = list(_DOGALGAZ_DOSYA_LISTESI_RE.finditer(html))
    sonuc = []
    for i, m in enumerate(eslesmeler):
        ay_no = AY_ADI_TO_NO.get(m.group(2))
        if ay_no is None:
            continue
        pencere_sonu = eslesmeler[i + 1].start() if i + 1 < len(eslesmeler) else len(html)
        excel_m = _EXCEL_LINK_RE.search(html, m.end(), pencere_sonu)
        if excel_m is None:
            continue  # o ay için henüz excel eki yayımlanmamış
        sonuc.append({"yil": int(m.group(3)), "ay": ay_no, "url": excel_m.group(1)})
    return sonuc


def _dogalgaz_alt_tablo_bul(tum_satirlar: list, tablo_no: int) -> list:
    """Birleşik bir sayfada ('Tablo 3-4' gibi) 'Tablo-N ' başlığından bir
    sonraki 'Tablo-M ' başlığına (ya da sayfa sonuna) kadarki satırları
    döner. Petrolün `alt_tablo_satirlarini_bul`'undan TEK farkı noktalama:
    doğal gaz EK'i "Tablo-3 ..." (tire+boşluk) yazıyor, petrol "Tablo 3: ..."
    (boşluk+iki nokta) — canlı ölçülen iki farklı EPDK şablon biçimi."""
    baslangic = None
    for i, row in enumerate(tum_satirlar):
        col, val = _ilk_dolu(row)
        if val and val.startswith(f"Tablo-{tablo_no} "):
            baslangic = i
            break
    if baslangic is None:
        raise RuntimeError(f"EPDK Doğal Gaz: 'Tablo-{tablo_no} ' başlığı bulunamadı")
    bitis = len(tum_satirlar)
    for i in range(baslangic + 1, len(tum_satirlar)):
        col, val = _ilk_dolu(tum_satirlar[i])
        if val and re.match(r"^Tablo-\d+ ", val):
            bitis = i
            break
    return tum_satirlar[baslangic:bitis]


def _dogalgaz_ay_baslik_satiri_bul(satirlar: list, tablo_no) -> list:
    """Ay adı (ör. 'Ocak') ya da tek aylık dosyalarda 'Miktar' taşıyan
    başlık satırını arar (bkz. `_ay_sutun_bul`)."""
    for row in satirlar:
        hucreler = [str(c).strip() if c else c for c in row]
        if any(h in AY_ADLARI or h == "Miktar" for h in hucreler if h):
            return hucreler
    raise RuntimeError(f"EPDK Doğal Gaz Tablo {tablo_no}: ay başlık satırı bulunamadı")


def _dogalgaz_sirket_deger_haritasi(satirlar: list, ay_sutun: int) -> dict[str, float]:
    """İlk sütundaki şirket adı -> o ayın sütunundaki HAM Sm3 değeri.
    'Genel Toplam'/'Toplam' satırı atlanır. Aynı şirket adı birden fazla
    satırda (il bazlı ya da lisans tipi bazlı) tekrarlanıyorsa değerler
    TOPLANIR (bkz. modül docstring'i)."""
    harita: dict[str, float] = {}
    for row in satirlar:
        ad = row[0]
        if ad is None:
            continue
        ad = str(ad).strip()
        if ad.upper() in ("GENEL TOPLAM", "TOPLAM") or ad.startswith("Tablo-"):
            continue
        if ay_sutun >= len(row):
            continue
        v = row[ay_sutun]
        harita[ad] = harita.get(ad, 0.0) + (float(v) if isinstance(v, (int, float)) else 0.0)
    return harita


def dogalgaz_ithalat_cek(tablo3: list, ay_adi: str) -> dict[str, float]:
    """Tablo-3'ün (şirket bazlı ithalat) BOTAŞ ve üç özel ithalatçının
    (AKFEL+BOSPHORUS+KİBAR) o ayki Sm3 hacmini okur. Ham değerler Sm3'TÜR."""
    baslik = _dogalgaz_ay_baslik_satiri_bul(tablo3, 3)
    sutun = _ay_sutun_bul(baslik, ay_adi, 3)
    harita = _dogalgaz_sirket_deger_haritasi(tablo3, sutun)
    if BOTAS_SIRKET_ADI not in harita:
        raise RuntimeError("EPDK Doğal Gaz Tablo 3: BOTAŞ satırı bulunamadı")
    if not any(ad in harita for ad in OZEL_ITHALATCI_SIRKETLERI):
        raise RuntimeError(
            "EPDK Doğal Gaz Tablo 3: özel ithalatçı satırlarından hiçbiri bulunamadı"
        )
    ozel_toplam = sum(harita.get(ad, 0.0) for ad in OZEL_ITHALATCI_SIRKETLERI)
    return {"botas-ithalat": harita[BOTAS_SIRKET_ADI], "ozel-ithalatci-ithalat": ozel_toplam}


def dogalgaz_depolama_cek(tablo6: list, ay_adi: str) -> dict[str, float]:
    """Tablo-6'nın (depolama aylık gelişimi) Boru Gazı ve LNG hacmini okur.
    Ham değerler Sm3'TÜR.

    Satır etiketi kararsız: çoğu ay düz "Boru Gazı"/"LNG", ama Haziran
    2026'da "DPF-34 - Boru Gazı"/"DPF-34 - LNG" (tesis kodu önekli) —
    canlı ölçüldü. `endswith` ile önek farkına dayanıklı eşleşilir."""
    baslik = _dogalgaz_ay_baslik_satiri_bul(tablo6, 6)
    sutun = _ay_sutun_bul(baslik, ay_adi, 6)
    sonuc = {}
    for etiket, alan in (("Boru Gazı", "depolama-borugazi"), ("LNG", "depolama-lng")):
        satir = next(
            (row for row in tablo6 if row[0] and str(row[0]).strip().endswith(etiket)),
            None,
        )
        if satir is None:
            raise RuntimeError(f"EPDK Doğal Gaz Tablo 6: '{etiket}' satırı bulunamadı")
        v = satir[sutun]
        sonuc[alan] = float(v) if isinstance(v, (int, float)) else 0.0
    return sonuc


def dogalgaz_abone_cek(tablo8: list) -> dict[str, float]:
    """Tablo-8'in (İl/Şirket bazlı abone, TEK dönemlik) AHGAZ grubu
    (Enerya+Marmara) toplam abone ve serbest tüketici sayısını okur.
    İl satırları (ör. 'ADANA') önek eşleşmediği için otomatik atlanır."""
    baslik_idx = None
    for i, row in enumerate(tablo8):
        col, val = _ilk_dolu(row)
        if val == "İl/Şirket":
            baslik_idx = i
            break
    if baslik_idx is None:
        raise RuntimeError("EPDK Doğal Gaz Tablo 8: başlık satırı bulunamadı")
    baslik = [str(c).strip() if c else c for c in tablo8[baslik_idx]]
    for etiket in ("Abone Sayısı", "Serbest Tüketici Sayısı"):
        if etiket not in baslik:
            raise RuntimeError(f"EPDK Doğal Gaz Tablo 8: '{etiket}' sütunu bulunamadı")
    abone_sutun = baslik.index("Abone Sayısı")
    serbest_sutun = baslik.index("Serbest Tüketici Sayısı")

    abone_toplam = 0.0
    serbest_toplam = 0.0
    for row in tablo8[baslik_idx + 1:]:
        ad = row[0]
        if ad is None or not any(
            str(ad).upper().startswith(onek) for onek in AHGAZ_SIRKET_ONEKLERI
        ):
            continue
        v_abone = row[abone_sutun]
        v_serbest = row[serbest_sutun]
        abone_toplam += float(v_abone) if isinstance(v_abone, (int, float)) else 0.0
        serbest_toplam += float(v_serbest) if isinstance(v_serbest, (int, float)) else 0.0
    return {"ahgaz-abone": abone_toplam, "ahgaz-serbest": serbest_toplam}


def dogalgaz_sirket_tuketim_cek(tablo12: list) -> dict[str, float]:
    """Tablo-12'nin (şirket×sektör aylık tüketim, TEK dönemlik — yalnızca
    rapor ayı) AHGAZ grubu toplamını, NTGAZ'ı ve AYGAZ'ı okur. Bir şirketin
    birden fazla lisans tipi satırı olabilir (ör. NATURELGAZ hem İthalat
    hem Sıkıştırılmış Doğalgaz lisansıyla ayrı satırda, ilk sütun ikinci
    satırda BOŞ olabilir) — aynı ada ait TÜM satırlar toplanır."""
    baslik_idx = None
    for i, row in enumerate(tablo12):
        col, val = _ilk_dolu(row)
        if val == "TÜRKİYE":
            baslik_idx = i
            break
    if baslik_idx is None:
        raise RuntimeError("EPDK Doğal Gaz Tablo 12: başlık satırı bulunamadı")
    baslik = [str(c).strip() if c else c for c in tablo12[baslik_idx]]
    if "Genel Toplam" not in baslik:
        raise RuntimeError("EPDK Doğal Gaz Tablo 12: 'Genel Toplam' sütunu bulunamadı")
    toplam_sutun = baslik.index("Genel Toplam")

    harita: dict[str, float] = {}
    guncel_ad: str | None = None
    for row in tablo12[baslik_idx + 1:]:
        ad = row[0]
        if ad is not None:
            guncel_ad = str(ad).strip()
        if guncel_ad is None:
            continue
        v = row[toplam_sutun] if toplam_sutun < len(row) else None
        harita[guncel_ad] = harita.get(guncel_ad, 0.0) + (
            float(v) if isinstance(v, (int, float)) else 0.0
        )

    ahgaz_toplam = sum(
        v for ad, v in harita.items()
        if any(ad.upper().startswith(onek) for onek in AHGAZ_SIRKET_ONEKLERI)
    )
    if NTGAZ_SIRKET_ADI not in harita:
        raise RuntimeError("EPDK Doğal Gaz Tablo 12: NATURELGAZ satırı bulunamadı")
    if AYGAZ_SIRKET_ADI not in harita:
        raise RuntimeError("EPDK Doğal Gaz Tablo 12: AYGAZ satırı bulunamadı")
    return {
        "ahgaz-tuketim": ahgaz_toplam,
        "ntgaz-hacim": harita[NTGAZ_SIRKET_ADI],
        "aygaz-hacim": harita[AYGAZ_SIRKET_ADI],
    }


def dogalgaz_ayin_tum_olculerini_cikar(baytlar: bytes, ay_adi: str) -> dict[str, float]:
    """Bir ayın doğal gaz EK dosyasından DOGALGAZ_OLCUT_ADLARI'ndaki dokuz
    ölçütü çıkarır. Ham değerler ölçüte göre Sm3/abone/tüketici SAYISIDIR."""
    kitap = openpyxl.load_workbook(BytesIO(baytlar), data_only=True, read_only=True)
    try:
        rows_34 = list(_sayfa_bul(kitap, "3-4").iter_rows(values_only=True))
        rows_6 = list(_sayfa_bul(kitap, "6").iter_rows(values_only=True))
        rows_8 = list(_sayfa_bul(kitap, "8").iter_rows(values_only=True))
        rows_11_12_13 = list(_sayfa_bul(kitap, "11-12-13").iter_rows(values_only=True))
    finally:
        kitap.close()

    tablo3 = _dogalgaz_alt_tablo_bul(rows_34, 3)
    tablo12 = _dogalgaz_alt_tablo_bul(rows_11_12_13, 12)

    sonuc: dict[str, float] = {}
    sonuc.update(dogalgaz_ithalat_cek(tablo3, ay_adi))
    sonuc.update(dogalgaz_depolama_cek(rows_6, ay_adi))
    sonuc.update(dogalgaz_abone_cek(rows_8))
    sonuc.update(dogalgaz_sirket_tuketim_cek(tablo12))
    return sonuc


def _dogalgaz_dosya_listesi_cek(session=None) -> list[dict]:
    http = session or requests
    yanit = http.get(DOGALGAZ_LISTE_URL, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"EPDK Doğal Gaz dosya listesi HTTP {yanit.status_code}")
    return cekilecek_dosyalar(dogalgaz_dosyalari_ayikla(yanit.text))


def _dogalgaz_tum_noktalari_getir(onbellek: dict, session=None) -> dict[str, dict[str, float]]:
    if "dogalgaz_noktalar" in onbellek:
        return onbellek["dogalgaz_noktalar"]

    dosyalar = _dogalgaz_dosya_listesi_cek(session)
    if not dosyalar:
        raise RuntimeError(
            f"EPDK Doğal Gaz: {ILK_YIL}-{ILK_AY:02d} sonrası indirilecek aylık rapor bulunamadı"
        )

    noktalar: dict[str, dict[str, float]] = {}
    for d in dosyalar:
        ay_adi = AY_ADLARI[d["ay"] - 1]
        baytlar = _dosya_indir(d["url"], session)
        aylik = dogalgaz_ayin_tum_olculerini_cikar(baytlar, ay_adi)
        tarih = f"{d['yil']:04d}-{d['ay']:02d}-01"
        for olcut, deger in aylik.items():
            noktalar.setdefault(olcut, {})[tarih] = deger

    onbellek["dogalgaz_noktalar"] = noktalar
    return noktalar


def dogalgaz_seri_cek(seri, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `onbellek` verilirse dosya listesi ve her ayın ayrıştırılmış noktaları
    koşu boyunca paylaşılır: 9 seri aynı ~7-8 aylık dosya kümesini paylaşır
    (petrolün `_tum_noktalari_getir`'iyle aynı desen, `onbellek` içinde AYRI
    anahtar altında — petrol ve doğal gaz seri_cek'leri aynı `epdk_onbellek`
    dict'ini paylaşabilir, çakışmazlar)."""
    onbellek = {} if onbellek is None else onbellek
    noktalar = _dogalgaz_tum_noktalari_getir(onbellek, session)

    olcut = seri.epdk_dogalgaz_olcut
    if olcut not in noktalar or not noktalar[olcut]:
        raise RuntimeError(f"EPDK Doğal Gaz: ölçüt bulunamadı: {olcut!r} ({seri.id})")

    df = pd.DataFrame(sorted(noktalar[olcut].items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)
