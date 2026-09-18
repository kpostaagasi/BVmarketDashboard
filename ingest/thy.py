"""THY (Türk Hava Yolları) yatırımcı ilişkileri trafik bülteni istemcisi.

Kaynak gerçekleri 2026-09-18'de canlı ölçüldü:

- Dosya listesi TÜRETİLEMEZ: geçmiş yıllardaki xlsx bağlantıları düzensiz
  adlandırılmış (`turkish-airlines-trafik-ara_2025.xlsx`,
  `turkish-airlines-trafik-aralik-2022.xlsx`, biri `/trafik/` alt dizini
  olmadan `/documents/turkish-airlines-trafik-aralik_2024.xlsx`). Liste
  `TRAFIK_SAYFASI`dan kazınır; sayfa sunucu tarafında render edilir, JS
  gerekmez.
- BÜLTEN ŞABLONU YILA GÖRE DEĞİŞİYOR (iki farklı format ölçüldü):
  * Yeni şablon (cari yıl dosyasının kendi sayfaları, ör. 2026 dosyasının
    '2025' ve '2026' sayfaları): ay başlığı satır 2'de, segment adı
    ("Toplam"/"Yurt İçi"/"Yurt Dışı") metrik satırıyla AYNI satırda A
    sütununda, yalnızca segmentin ilk metrik satırında yazılı.
  * Eski şablon (yıl sonu arşiv dosyaları, ör. 2025/2024/2023/2022 dosyaları):
    segment adı ("TOPLAM"/"YURT İÇİ"/"YURT DIŞI", büyük harf) kendi başına
    bir satırda B sütununda, ay başlığı bir sonraki satırda; ayrıca bizim
    izlemediğimiz üç ek ölçüt var (Ücretli Yolcu Km, Uçulan Km, Dıştan Dışa
    Transfer Yolcu Sayısı) — bunlar sessizce atlanır (bilinmeyen ÖLÇÜT
    şablon farkıdır, hata değil; bilinmeyen SEGMENT hâlâ hatadır).
  Bu yüzden ayrıştırma satır pozisyonuna değil, hücre İÇERİĞİNE göre çalışır:
  her satırda hem A hem B sütunu segment sözlüğünde aranır (segment
  güncellenir), ay başlığı `AYLAR` ile birebir eşleşen satır olarak bulunur.
- HER DOSYA İKİ-DÖRT YIL SAYFASI TAŞIR (`Notlar`/`Notes` hariç, sayfa adı
  yılın kendisi, ör. `2022 dosyası → ['Notes','2019','2021','2022']`).
  2020 hiçbir dosyada yok (COVID döneminde bülten farklı yayımlanmış
  olabilir — kaynak sağlamıyor, sessizce atlanır çünkü sayfa hiç yok).
- Her sayfada satır 21 (yeni şablon) / 32 (eski şablon) civarında 'BÖLGESEL'
  başlıklı bir alt tablo var; bu tablo 'Yurt İçi'/'Toplam' gibi ana
  segment×ölçüt çiftlerini TEKRAR listeliyor (bölgesel kırılım öncesi özet
  satırı olarak). Ayrıştırma 'BÖLGESEL' satırında DURUR — durmazsa aynı
  (segment, ölçüt) anahtarı ikinci kez yazılmaya çalışılır ve
  `trafik_noktalari` hata verir.
- Ay hücresi boşsa (yayımlanmamış ay, cari yıl dosyasının gelecek ayları)
  hücre `None`; bu ay o (segment, ölçüt) sözlüğüne hiç eklenmez (sıfır
  uydurulmaz).
- Ölçüldü: Ağustos 2026 Toplam/Yurt İçi/Yurt Dışı Yolcu Sayısı sırasıyla
  10.001.394 / 3.591.405 / 6.409.989 (referans: marketvisuals.net/thy_traffic.html).
- Aynı yıl birden fazla dosyada geçebilir (ör. 2025 hem cari yıl dosyasının
  '2025' sayfasında hem 2025 arşiv dosyasında var); `dosya_listesi` sırası
  cari yıldan geçmişe doğru olduğu için birleştirme sırasında en son işlenen
  (en eski/arşiv) dosya kazanır — arşiv dosyası yıl sonu kesin rakamları
  taşır, cari yıl dosyasındaki devir değerleri küçük revizyonlar içerebilir.
"""

from __future__ import annotations

import io
import re

import openpyxl
import pandas as pd
import requests

TABAN = "https://investor.turkishairlines.com"
TRAFIK_SAYFASI = f"{TABAN}/tr/mali-ve-operasyonel-veriler/trafik"
ZAMAN_ASIMI = 60
_BASLIKLAR = {"User-Agent": "Mozilla/5.0"}

BOLGESEL_ETIKETI = "BÖLGESEL"

AYLAR = (
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
)

# Bültendeki tam ölçüt etiketi -> katalogdaki kısa ad (`thy_olcut`).
OLCUT_ESLEME = {
    "Konma Sayısı (Yolcu Seferleri)": "konma",
    "Arzedilen Koltuk Km ('000)": "ask",
    "Yolcu Doluluk Oranı (%)": "doluluk",
    "Yolcu Sayısı": "yolcu",
    "Kargo + Posta (Ton)": "kargo",
}

# Eski şablonun (2022-2025 arşiv dosyaları) bilinen ama katalogda karşılığı
# olmayan ek ölçütleri: gerçek şablon farkı, ayrıştırma hatası değil.
# Buradaki listede OLMAYAN bir etiket (yazım hatası, gerçek şablon
# bozulması) hâlâ RuntimeError'a düşer — sessizce atlanmaz.
OLCUT_IZLENMEYEN = {
    "Ücretli Yolcu Km ('000)",
    "Uçulan Km ('000)",
    "Dıştan Dışa Transfer Yolcu Sayısı",
}

# Bültendeki segment etiketi (iki şablonun iki farklı yazımı) -> katalogdaki
# ad (`thy_segment`). A sütunu (yeni şablon) YALNIZCA segment adı taşır —
# bu yüzden A sütunundaki her metin bu sözlükte olmak ZORUNDADIR (aksi hata).
SEGMENT_ESLEME = {
    "Toplam": "Toplam", "TOPLAM": "Toplam",
    "Yurt İçi": "Yurt İçi", "YURT İÇİ": "Yurt İçi",
    "Yurt Dışı": "Yurt Dışı", "YURT DIŞI": "Yurt Dışı",
}


def dosya_listesi(session=None) -> list[str]:
    """Trafik sayfasındaki xlsx bağlantılarını mutlak URL olarak döner.

    URL deseni yıldan yıla tutarsız olduğu için türetilemez; sayfa
    kazınmalı. Sayfa hiç xlsx bağlantısı içermiyorsa (şablon değişmiş,
    sayfa taşınmış) sessizce boş liste dönmek yerine hata verilir.
    """
    http = session or requests
    yanit = http.get(TRAFIK_SAYFASI, timeout=ZAMAN_ASIMI, headers=_BASLIKLAR)
    if yanit.status_code != 200:
        raise RuntimeError(f"THY trafik sayfası HTTP {yanit.status_code} döndü")
    html = yanit.content.decode("utf-8", errors="replace")
    baglantilar = re.findall(r'href="([^"]+\.xlsx)"', html)
    if not baglantilar:
        raise RuntimeError("THY trafik sayfasında xlsx bağlantısı bulunamadı")
    return [
        baglanti if baglanti.startswith("http") else f"{TABAN}{baglanti}"
        for baglanti in baglantilar
    ]


def _satiri_isle(
    satir: tuple, yil: int, mevcut_segment: str | None,
    gorulen: set[tuple[str, str]], noktalar: dict[tuple[str, str], dict[str, float]],
) -> tuple[str | None, bool]:
    """Bir veri satırını işler; `(güncel segment, BÖLGESEL'e ulaşıldı mı)` döner."""
    col0, col1 = satir[0], satir[1]
    veri_var = any(deger is not None for deger in satir[2:14])

    # A sütunu (yeni şablonda segmentin ilk metrik satırı) yalnızca segment
    # adı taşır; burada tanınmayan bir metin gerçek şablon bozulmasıdır.
    metin0 = str(col0).strip() if col0 is not None else ""
    if metin0:
        if metin0.upper() == BOLGESEL_ETIKETI:
            return mevcut_segment, True
        segment = SEGMENT_ESLEME.get(metin0)
        if segment is None:
            raise RuntimeError(f"THY bülteninde {yil}: bilinmeyen segment {metin0!r}")
        mevcut_segment = segment

    # B sütunu (eski şablonda segment başlığı, her iki şablonda ölçüt
    # etiketi ya da dipnot metni) — burada tanınmayan metin serbesttir,
    # aşağıda veri varsa ayrıca ölçüt olarak doğrulanır.
    metin1 = str(col1).strip() if col1 is not None else ""
    if metin1:
        if metin1.upper() == BOLGESEL_ETIKETI:
            return mevcut_segment, True
        segment = SEGMENT_ESLEME.get(metin1)
        if segment is not None:
            mevcut_segment = segment

    if not veri_var:
        # Segment-only başlık satırı (eski şablon), boş ayraç satırı ya da
        # dipnot metni (ör. "* Veriler tüm uçuşları içermektedir.") — hiçbiri
        # ölçüt verisi taşımaz.
        return mevcut_segment, False

    if not metin1:
        raise RuntimeError(f"THY bülteninde {yil}: ölçüt etiketi olmayan veri satırı")
    olcut = OLCUT_ESLEME.get(metin1)
    if olcut is None:
        if metin1 in OLCUT_IZLENMEYEN:
            return mevcut_segment, False
        raise RuntimeError(f"THY bülteninde {yil}: bilinmeyen ölçüt {metin1!r}")

    if mevcut_segment is None:
        raise RuntimeError(
            f"THY bülteninde {yil}: segment belirlenmeden ölçüt satırı geldi "
            f"({metin1!r})"
        )
    anahtar = (mevcut_segment, olcut)
    if anahtar in gorulen:
        raise RuntimeError(
            f"THY bülteninde {yil}: yinelenen segment/ölçüt anahtarı {anahtar} "
            "('BÖLGESEL' bloğu durdurulmadan okunmuş olabilir)"
        )
    gorulen.add(anahtar)

    aylik: dict[str, float] = {}
    for ay, hucre in enumerate(satir[2:14], start=1):
        if hucre is None:
            continue  # yayımlanmamış ay — sıfır uydurulmaz, atlanır
        if not isinstance(hucre, (int, float)):
            raise RuntimeError(
                f"THY bülteninde {yil}: sayısal olmayan hücre {metin1!r} "
                f"{yil}-{ay:02d}: {hucre!r}"
            )
        aylik[f"{yil}-{ay:02d}-01"] = float(hucre)
    noktalar.setdefault(anahtar, {}).update(aylik)
    return mevcut_segment, False


def trafik_noktalari(baytlar: bytes) -> dict[tuple[str, str], dict[str, float]]:
    """XLSX baytlarından `{(segment, ölçüt): {"YYYY-MM-01": değer}}` çıkarır.

    Dosyadaki `Notlar`/`Notes` dışında adı yıl olan TÜM sayfalar okunur
    (bir dosya 2-4 yıl taşıyabilir). Her sayfada 'BÖLGESEL' satırında durulur.
    """
    kitap = openpyxl.load_workbook(io.BytesIO(baytlar), data_only=True)
    try:
        noktalar: dict[tuple[str, str], dict[str, float]] = {}
        yil_sayfasi_var = False
        for ad in kitap.sheetnames:
            if not ad.isdigit():
                continue
            yil_sayfasi_var = True
            yil = int(ad)
            sayfa = kitap[ad]
            ay_basligi_bulundu = False
            mevcut_segment: str | None = None
            gorulen: set[tuple[str, str]] = set()
            for satir in sayfa.iter_rows(
                min_row=1, max_row=sayfa.max_row, min_col=1, max_col=14,
                values_only=True,
            ):
                if tuple(satir[2:14]) == AYLAR:
                    ay_basligi_bulundu = True
                    continue
                mevcut_segment, durduruldu = _satiri_isle(
                    satir, yil, mevcut_segment, gorulen, noktalar
                )
                if durduruldu:
                    break
            if not ay_basligi_bulundu:
                raise RuntimeError(f"THY bülteninde {yil}: ay başlığı bulunamadı")
        if not yil_sayfasi_var:
            raise RuntimeError("THY bülteninde yıl sayfası bulunamadı")
        return noktalar
    finally:
        kitap.close()


def _tum_noktalari_getir(
    onbellek: dict, session=None,
) -> dict[tuple[str, str], dict[str, float]]:
    """Dosya listesini ve her dosyanın ayrıştırılmış noktalarını önbellekler.

    15 seri (3 segment × 5 ölçüt) aynı dosya kümesini paylaşır; önbelleksiz
    her seri kendi dosyalarını yeniden indirir.
    """
    if "noktalar" in onbellek:
        return onbellek["noktalar"]

    http = session or requests
    birlesik: dict[tuple[str, str], dict[str, float]] = {}
    # Sıra `dosya_listesi`nin döndürdüğü sırayla (cari yıldan geçmişe);
    # aynı yıl birden fazla dosyada geçtiğinde en son işlenen (en eski,
    # dolayısıyla o yılın kendi yıl-sonu arşivi) kazanır — arşiv dosyası
    # kesin rakamları taşır.
    for url in dosya_listesi(session):
        yanit = http.get(url, timeout=ZAMAN_ASIMI, headers=_BASLIKLAR)
        if yanit.status_code != 200:
            raise RuntimeError(f"THY dosyası indirilemedi ({url}): HTTP {yanit.status_code}")
        for anahtar, aylik in trafik_noktalari(yanit.content).items():
            birlesik.setdefault(anahtar, {}).update(aylik)

    onbellek["noktalar"] = birlesik
    return birlesik


def seri_cek(seri, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """THY trafik bültenlerinden tek bir (segment, ölçüt) serisini çeker.

    `onbellek` verilirse dosya listesi ve ayrıştırılmış noktalar koşu
    boyunca paylaşılır: 15 seri aynı ~5 dosyayı okuduğu için yoksa 75
    indirme olurdu.
    """
    onbellek = {} if onbellek is None else onbellek
    tum_noktalar = _tum_noktalari_getir(onbellek, session=session)
    anahtar = (seri.thy_segment, seri.thy_olcut)
    aylik = tum_noktalar.get(anahtar)
    if not aylik:
        raise RuntimeError(
            f"THY bülteninde segment/ölçüt bulunamadı: {anahtar} ({seri.id})"
        )

    df = pd.DataFrame(sorted(aylik.items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)
