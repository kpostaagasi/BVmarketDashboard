"""TürkÇimento (Türkiye Çimento Sanayicileri Birliği) aylık bölgesel çimento
ve klinker istatistikleri istemcisi.

Kaynak: `turkcimento.org.tr/tr/istatistikler/aylik-veriler` — her YIL için
tek bir eski biçim Excel dosyası (`.xls`, BIFF) yayımlanır, adı
`Yeni-<yıl>_Aylik-rev<N>.xls`. Revizyon numarası (`rev<N>`) öngörülemez
biçimde artıyor (ör. 2026 için "rev2", 2022 için "rev8"), bu yüzden dosya
adı sabitlenmez — listeleme sayfası HER ÇALIŞTIRMADA taze taranır. Dosyanın
kendisi (aynı köke `/uploads/pdf/...xls` altında) WAF/oturum gerektirmeden
düz `requests.get` ile erişilebilir (ölçüldü 2026-09-18); yalnızca liste
sayfası taranarak dosya adı bulunur.

Her yılın dosyasında 12 sayfa var (`ocak`..`aralik`, Türkçe küçük harf ay
adı, Türkçe karakter yok). Her sayfa o AYA ait bölgesel (Marmara/Ege/
Akdeniz/Karadeniz/İç Anadolu/Doğu Anadolu/G.Doğu Anadolu) + TOPLAM
kırılımını beş ÇİMENTO ölçütü (Üretim/İç Satış/İhracat/Toplam Satış/Stok)
ve dört KLİNKER ölçütü (Üretim/İthalat/İhracat/Stok) için taşır. Her ölçüt
6 satırlık bir blok: `{yıl-1} Aylık`, `{yıl} Aylık`, `%`, `{yıl-1} Devre`
(yılbaşından kümülatif), `{yıl} Devre`, `%`. Yalnızca `{yıl} Aylık` TOPLAM
sütunu okunur (aylık akım, kümülatif değil). Satır/ürün etiketleri sabit
satır numarasıyla değil METİN eşleştirmesiyle bulunur (2018-2026 arası
dosyalarda satır düzeni birebir sabit ölçüldü ama taşıma şablon
değişikliğine karşı kırılmaz).

Henüz yayımlanmamış ayların sayfası dosyada zaten var (ör. 2026 dosyasında
Eylül'e kadar tüm ay sayfaları mevcut) ama TOPLAM = 0.0 — ulusal düzeyde
gerçek üretim/satış hiçbir ay için tam sıfır olamayacağından bu, "henüz
yayımlanmadı" sinyali olarak güvenle kullanılır.

Değerler tondan bin tona (`/1000`) çevrilir — referans platform "Bin Ton"
birimiyle gösteriyor.

Ölçüldü (2026-09-18, canlı, Nisan 2026): Çimento Üretim TOPLAM = 8.107.646,6
ton → 8107,6 bin ton (referans platform: 8107,6) ve Çimento Stoğu = 844,4
bin ton (referans: 844,4) birebir eşleşti. Klinker İhracatı Nisan 2026 canlı
okumada 593,8 bin ton çıkıyor; referans platformun daha önceki bir anlık
görüntüsü 541,1 gösteriyor — TürkÇimento'nun ticaret verisini revize etmesiyle
tutarlı (bu istemci her çalıştırmada TÜM pencereyi yeniden çeker, tam da bu
tür revizyonları yakalamak için; bkz. diğer istemcilerin aynı ilkesi).
"""

from __future__ import annotations

import re

import pandas as pd
import requests
import xlrd

LISTE_URL = "https://www.turkcimento.org.tr/tr/istatistikler/aylik-veriler"
ZAMAN_ASIMI = 60

AY_SAYFALARI = (
    "ocak", "subat", "mart", "nisan", "mayis", "haziran",
    "temmuz", "agustos", "eylul", "ekim", "kasim", "aralik",
)

_DOSYA_DESENI = re.compile(
    r'href="(https://www\.turkcimento\.org\.tr/uploads/pdf/Yeni-(\d{4})_Aylik-rev\d+\.xls)"'
)

# Kart adı -> (ÇİMENTO/KLİNKER üst etiketi, ölçüt alt etiketi). Sayfadaki
# metinle (sütun B/C) birebir aynı yazılmalı — bkz. modül docstring'i.
METRIK_ESLEME = {
    "cimento-uretim": ("ÇİMENTO", "Üretim"),
    "cimento-ic-satis": ("ÇİMENTO", "İç Satış"),
    "cimento-ihracat": ("ÇİMENTO", "İhracat"),
    "cimento-toplam-satis": ("ÇİMENTO", "Toplam Satış"),
    "cimento-stok": ("ÇİMENTO", "Stok"),
    "klinker-uretim": ("KLİNKER", "Üretim"),
    "klinker-ihracat": ("KLİNKER", "İhracat"),
    "klinker-stok": ("KLİNKER", "Stok"),
}


def _yil_dosyalari(session=None) -> dict[int, str]:
    """Liste sayfasından `{yıl: xls_url}` eşlemesini çıkarır."""
    http = session or requests
    yanit = http.get(LISTE_URL, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"TürkÇimento liste sayfası HTTP {yanit.status_code}")
    eslesme = {int(yil): url for url, yil in _DOSYA_DESENI.findall(yanit.text)}
    if not eslesme:
        raise RuntimeError(
            f"TürkÇimento liste sayfasında ({LISTE_URL}) hiç yıllık dosya "
            "linki bulunamadı — sayfa yapısı değişmiş olabilir"
        )
    return eslesme


def _xls_indir(url: str, session=None) -> bytes:
    http = session or requests
    yanit = http.get(url, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"TürkÇimento dosya indirme başarısız ({url}): HTTP {yanit.status_code}")
    return yanit.content


def aylik_toplam(kitap: xlrd.book.Book, ay_sayfa: str, yil: int, ust: str, alt: str) -> float | None:
    """Bir ay sayfasından `{yıl} Aylık` TOPLAM değerini çıkarır.

    Blok (ust/alt eşleşmesi) sayfada hiç bulunamazsa None döner — çağıran
    bunu şablon değişikliği ihtimaline karşı ayrıca doğrulamalı (bkz.
    `seri_cek`). Blok bulunur ama değer 0.0 ise bu "ay henüz yayımlanmadı"
    demektir (yine None döner, ayrım çağıranda `blok_bulundu` bayrağıyla
    yapılır).
    """
    sh = kitap.sheet_by_name(ay_sayfa)
    hedef = f"{yil} Aylık"
    mevcut_ust: str | None = None
    mevcut_alt: str | None = None
    for satir in range(sh.nrows):
        ust_hucre = str(sh.cell_value(satir, 1)).strip()
        alt_hucre = str(sh.cell_value(satir, 2)).strip()
        if ust_hucre:
            mevcut_ust = ust_hucre
        if alt_hucre:
            mevcut_alt = alt_hucre
        etiket = str(sh.cell_value(satir, 3)).strip()
        if etiket == hedef and mevcut_ust == ust and mevcut_alt == alt:
            return float(sh.cell_value(satir, sh.ncols - 1))
    return None


def seri_cek(seri, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `onbellek` verilirse yıl->URL eşlemesi ve her yılın açılmış `xlrd`
    kitabı koşu boyunca paylaşılır — 8 ölçüt aynı ~9 yıllık dosya kümesini
    okur, önbelleksiz her seri kendi dosyalarını yeniden indirirdi.
    """
    onbellek = {} if onbellek is None else onbellek
    ust, alt = METRIK_ESLEME[seri.turkcimento_metrik]

    if "yillar" not in onbellek:
        onbellek["yillar"] = _yil_dosyalari(session)
    yillar = onbellek["yillar"]

    blok_bulundu = False
    noktalar: dict[str, float] = {}
    for yil, url in sorted(yillar.items()):
        anahtar = f"kitap_{yil}"
        if anahtar not in onbellek:
            onbellek[anahtar] = xlrd.open_workbook(file_contents=_xls_indir(url, session))
        kitap = onbellek[anahtar]
        for ay_no, ay_adi in enumerate(AY_SAYFALARI, start=1):
            deger = aylik_toplam(kitap, ay_adi, yil, ust, alt)
            if deger is None:
                continue
            blok_bulundu = True
            if deger == 0.0:
                continue  # henüz yayımlanmamış ay
            noktalar[f"{yil}-{ay_no:02d}-01"] = deger / 1000  # ton -> bin ton

    if not blok_bulundu:
        raise RuntimeError(
            f"TürkÇimento'da '{ust}/{alt}' bloğu hiçbir sayfada bulunamadı "
            f"({seri.id}) — şablon değişmiş olabilir"
        )
    if not noktalar:
        raise RuntimeError(f"TürkÇimento'da '{ust}/{alt}' için hiç yayımlanmış veri yok ({seri.id})")

    df = pd.DataFrame(sorted(noktalar.items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)
