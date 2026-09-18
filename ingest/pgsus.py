"""Pegasus Yatırımcı İlişkileri aylık trafik bülteni istemcisi.

Tek XLSX dosyası 2019'dan bugüne TÜM geçmişi taşıyor (TİM/OSD'nin aksine
yıl/ay başına ayrı dosya yok) — bu yüzden `seri_cek` her koşuda dosyayı
BİR KEZ indirip ayrıştırır; 18 seri (3 segment × 6 ölçüt) aynı önbelleği
paylaşır, aksi halde 18 indirme olurdu.

`TRAFİK` sayfasının AYLIK bloğu (satır 2 yıl, satır 3 ay başlığı, satır
4-21 üç segment × altı ölçüt) okunur; segment etiketi (A sütunu) yalnızca
o segmentin İLK satırında yazılıdır, sonraki beş satırda boştur — bu
yüzden "son görülen segment" satır satır taşınır. KÜMÜLATİF blok (satır
25'ten itibaren) ve satır 3'teki AYLIK bloğun ardından gelen yıllık %
değişim sütunu (tamamen boş bir ayraç sütunundan sonra gelir) okunmaz.

Ölçüldü (2026-09-18): Ağustos 2026 Toplam/İç Hat/Dış Hat misafir sayısı
4.51 / 1.61 / 2.90 mn — pegasusyatirimciiliskileri.com kart özetiyle
birebir eşleşiyor.
"""

from __future__ import annotations

import io

import openpyxl
import pandas as pd
import requests

from core.catalog import GECERLI_PGSUS_OLCUTLERI, GECERLI_PGSUS_SEGMENTLERI

UC = (
    "https://www.pegasusyatirimciiliskileri.com/medium/image/"
    "pegasus-trafik-karbon-emisyonu-verileri-2019-2026-excel_1571/view.aspx"
)
ZAMAN_ASIMI = 60
SAYFA_ADI = "TRAFİK"

AY_ADLARI = (
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
)

# Ham ölçüt etiketi -> katalogdaki kısa anahtar (core.catalog'daki
# GECERLI_PGSUS_OLCUTLERI ile birebir eşleşmeli).
OLCUT_ESLEME = {
    "Misafir sayısı, mn": "misafir",
    "Konma": "konma",
    "Koltuk sayısı, mn": "koltuk",
    "Doluluk Oranı": "doluluk",
    "ASK (mln km)": "ask",
    "Konma başına Misafir": "konma-basina-misafir",
}
assert set(OLCUT_ESLEME.values()) == GECERLI_PGSUS_OLCUTLERI


def _ay_sutunlarini_bul(satir_yil: tuple, satir_ay: tuple) -> dict[int, str]:
    """C sütunundan başlayıp ilk tamamen boş (yıl, ay) çiftinde duran
    yıl×ay ızgarasını `{sütun indeksi: "YYYY-MM-01"}` olarak döner.

    AYLIK bloğunun ardından bir ayraç (tamamen boş) sütun gelip, onun
    ardından yıllık % değişim gibi türetilmiş bir özet sütunu geliyor —
    ayraç görülünce taramak durur, o özet sütunu hiç okunmaz.
    """
    sutunlar: dict[int, str] = {}
    onceki: tuple[int, int] | None = None
    for sutun in range(2, len(satir_yil)):
        yil, ay_adi = satir_yil[sutun], satir_ay[sutun]
        if yil is None and ay_adi is None:
            break
        if yil is None or ay_adi is None:
            raise RuntimeError(
                f"Pegasus trafik bülteni: eksik yıl/ay başlığı (sütun {sutun})"
            )
        if ay_adi not in AY_ADLARI:
            raise RuntimeError(
                f"Pegasus trafik bülteni: bilinmeyen ay adı {ay_adi!r} (sütun {sutun})"
            )
        if not isinstance(yil, int) or isinstance(yil, bool):
            raise RuntimeError(
                f"Pegasus trafik bülteni: yıl sayı değil {yil!r} (sütun {sutun})"
            )
        ay = AY_ADLARI.index(ay_adi) + 1
        simdiki = (yil, ay)
        if onceki is not None and simdiki <= onceki:
            raise RuntimeError(
                f"Pegasus trafik bülteni: yıl/ay sırası bozuk (sütun {sutun}: "
                f"{simdiki} <= {onceki})"
            )
        onceki = simdiki
        sutunlar[sutun] = f"{yil}-{ay:02d}-01"
    if not sutunlar:
        raise RuntimeError("Pegasus trafik bülteni: yıl/ay ızgarası bulunamadı")
    return sutunlar


def trafik_noktalari(baytlar: bytes) -> dict[tuple[str, str], dict[str, float]]:
    """XLSX baytlarından `{(segment, ölçüt): {"YYYY-MM-01": değer}}` çıkarır.

    Yalnızca AYLIK blok (satır 4-21) okunur; KÜMÜLATİF blok (satır 25+)
    dokunulmaz. Boş hücre (henüz yayımlanmamış ay) sıfıra çevrilmeden
    atlanır.
    """
    kitap = openpyxl.load_workbook(io.BytesIO(baytlar), data_only=True)
    try:
        if SAYFA_ADI not in kitap.sheetnames:
            raise RuntimeError(
                f"Pegasus trafik bülteninde '{SAYFA_ADI}' sayfası yok: {kitap.sheetnames}"
            )
        sayfa = kitap[SAYFA_ADI]
        satirlar = list(sayfa.iter_rows(values_only=True))
        if len(satirlar) < 3 or satirlar[2][0] != "AYLIK":
            raise RuntimeError(
                "Pegasus trafik bülteni: A3 hücresi 'AYLIK' değil — şablon değişmiş olabilir"
            )
        sutunlar = _ay_sutunlarini_bul(satirlar[1], satirlar[2])

        noktalar: dict[tuple[str, str], dict[str, float]] = {}
        mevcut_segment: str | None = None
        for satir in satirlar[3:]:
            segment_ham, olcut_ham = satir[0], satir[1]
            if segment_ham is None and olcut_ham is None:
                break  # AYLIK blok bitti (KÜMÜLATİF başlığından önceki boş satırlar)
            if segment_ham is not None:
                if segment_ham not in GECERLI_PGSUS_SEGMENTLERI:
                    raise RuntimeError(
                        f"Pegasus trafik bülteni: bilinmeyen segment {segment_ham!r}"
                    )
                mevcut_segment = segment_ham
            if mevcut_segment is None:
                raise RuntimeError(
                    "Pegasus trafik bülteni: segment etiketinden önce ölçüt satırı geldi"
                )
            if olcut_ham not in OLCUT_ESLEME:
                raise RuntimeError(
                    f"Pegasus trafik bülteni: bilinmeyen ölçüt {olcut_ham!r} "
                    f"(segment {mevcut_segment!r})"
                )
            olcut = OLCUT_ESLEME[olcut_ham]
            aylik: dict[str, float] = {}
            for sutun, tarih in sutunlar.items():
                hucre = satir[sutun]
                if hucre is None:
                    continue  # yayımlanmamış ay — sıfır değil, atlanır
                if isinstance(hucre, bool) or not isinstance(hucre, (int, float)):
                    raise RuntimeError(
                        f"Pegasus trafik bülteni: sayısal olmayan hücre "
                        f"{mevcut_segment}/{olcut}/{tarih}: {hucre!r}"
                    )
                aylik[tarih] = float(hucre)
            anahtar = (mevcut_segment, olcut)
            if anahtar in noktalar:
                raise RuntimeError(
                    f"Pegasus trafik bülteni: yinelenen segment/ölçüt satırı {anahtar!r}"
                )
            noktalar[anahtar] = aylik

        beklenen = {
            (segment, olcut)
            for segment in GECERLI_PGSUS_SEGMENTLERI
            for olcut in GECERLI_PGSUS_OLCUTLERI
        }
        if set(noktalar) != beklenen:
            eksik = beklenen - set(noktalar)
            raise RuntimeError(
                f"Pegasus trafik bülteni: eksik segment/ölçüt satırı {sorted(eksik)}"
            )
        return noktalar
    finally:
        kitap.close()


def _dosya_indir(session=None) -> bytes:
    http = session or requests
    yanit = http.get(UC, headers={"User-Agent": "Mozilla/5.0"}, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"Pegasus trafik bülteni HTTP {yanit.status_code}")
    return yanit.content


def seri_cek(seri, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `onbellek` verilirse dosya indirme + ayrıştırma koşu boyunca
    paylaşılır: 18 seri aynı tek dosyayı okuduğu için yoksa 18 indirme
    olurdu.
    """
    onbellek = {} if onbellek is None else onbellek
    if "noktalar" not in onbellek:
        baytlar = _dosya_indir(session)
        onbellek["noktalar"] = trafik_noktalari(baytlar)
    noktalar = onbellek["noktalar"]

    anahtar = (seri.pgsus_segment, seri.pgsus_olcut)
    if anahtar not in noktalar:
        raise RuntimeError(
            f"Pegasus trafik bülteninde segment/ölçüt bulunamadı: {anahtar!r} ({seri.id})"
        )

    df = pd.DataFrame(sorted(noktalar[anahtar].items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)
