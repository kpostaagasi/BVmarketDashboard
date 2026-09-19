"""TAİD (Ağır Ticari Araçlar Derneği) aylık "Perakende Satışlar Yerli/İthal
Dağılımı" basın bülteni istemcisi.

Bülten listesi sayfalanmış bir JSON uçtan gelir: `GET .../server-api/
frontend/bultenler?page=N` — her kayıt `baslik` ("BASIN BÜLTENİ (AY YIL)")
ve `icerik` (HTML gövde, `<a href="/belgeler/<uuid>.pdf">Raporu
görüntülemek...` bağlantısı gömülü) taşır. Bültenler en yeniden en eskiye
sıralı geldiğinden, istenen geçmiş penceresinin gerisine düşülünce tarama
durur (aksi halde koşu başına onlarca sayfa gezilir).

Bültenin PDF'indeki "PERAKENDE SATIŞLAR YERLİ/İTHAL DAĞILIMI (<AY YIL>)"
tablosu (TEK AY — hemen ardından gelen "(OCAK-<AY> YIL)" KÜMÜLATİF tablosuyla
KARIŞTIRILMAMALI, bkz. `_tek_ay_bolumunu_ayikla`) marka × {YERLİ, İTHAL,
TOPLAM} kırılımı verir; kartın istediği tek sayı `TOPLAM` sütunudur. Öz-
doğrulama: her markada YERLİ+İTHAL=TOPLAM VE markaların TOPLAM'ı tablonun
kendi "TOPLAM" satırıyla tutmalı (canlı bültende ikisi de hep tutuyor);
tutmazsa RuntimeError — PDF şablonu değiştiğinde sessizce yanlış sayı
üretmektense ingest'in kırılması istenir.

Ölçüldü (2026-09-19): Ağustos 2026 bülteni FORD TRUCKS TOPLAM = 464 —
marketvisuals.net'in "FROTO - Perakende - Kamyon (TAID)" kartıyla (464)
BİREBİR eşleşti.

Sözleşme: seri_cek(seri, *, onbellek=None, session=None) -> DataFrame[date,value]
"""

from __future__ import annotations

import io
import re
from datetime import date

import pandas as pd
import pdfplumber
import requests

from core.catalog import GECERLI_TAID_MARKALARI

TABAN = "https://www.taid.org.tr"
LISTE_URL = f"{TABAN}/server-api/frontend/bultenler"
ZAMAN_ASIMI = 60
VARSAYILAN_GECMIS_YIL = 5

AY_ADLARI = (
    "OCAK", "ŞUBAT", "MART", "NİSAN", "MAYIS", "HAZİRAN", "TEMMUZ",
    "AĞUSTOS", "EYLÜL", "EKİM", "KASIM", "ARALIK",
)
_AY_INDEKS = {ad: i + 1 for i, ad in enumerate(AY_ADLARI)}

_BASLIK_DESENI = re.compile(
    r"BASIN B[ÜU]LTEN[İI]\s*\(?(" + "|".join(AY_ADLARI) + r")\s+(\d{4})\)?"
)
_PDF_DESENI = re.compile(r'href="(/belgeler/[^"]+\.pdf)"')
_TABLO_BASLIGI = "PERAKENDE SATIŞLAR YERLİ/İTHAL DAĞILIMI"


def bulten_listesini_cek(bugun: date, session=None) -> dict[str, str]:
    """Tüm sayfaları en yeniden eskiye gezip `"YYYY-MM-01" -> pdf_url`
    eşlemesi çıkarır; `VARSAYILAN_GECMIS_YIL` gerisine düşülünce durur."""
    http = session or requests
    en_eski = bugun.replace(year=bugun.year - VARSAYILAN_GECMIS_YIL)
    eslesme: dict[str, str] = {}
    sayfa = 1
    while True:
        yanit = http.get(LISTE_URL, params={"page": sayfa}, timeout=ZAMAN_ASIMI)
        if yanit.status_code != 200:
            raise RuntimeError(f"TAİD bülten listesi HTTP {yanit.status_code} (sayfa {sayfa})")
        govde = yanit.json()
        bultenler = govde.get("bultenler") or []
        if not bultenler:
            break
        gerideyiz = False
        for kayit in bultenler:
            eslesen = _BASLIK_DESENI.search(kayit.get("baslik", ""))
            if not eslesen:
                continue
            ay, yil = eslesen.group(1), int(eslesen.group(2))
            tarih = f"{yil}-{_AY_INDEKS[ay]:02d}-01"
            if date.fromisoformat(tarih) < en_eski:
                gerideyiz = True
                continue
            pdf_eslesen = _PDF_DESENI.search(kayit.get("icerik", ""))
            if pdf_eslesen:
                eslesme.setdefault(tarih, TABAN + pdf_eslesen.group(1))
        if gerideyiz or sayfa >= govde.get("totalPage", sayfa):
            break
        sayfa += 1
    if not eslesme:
        raise RuntimeError("TAİD bülten listesinde hiç bülten bulunamadı")
    return eslesme


def _sayi_parse(ham: str) -> float:
    return float(ham.replace(".", "").replace(",", "."))


def _tek_ay_bolumunu_ayikla(pdf_baytlari: bytes) -> str:
    """PDF'in TÜM sayfalarını tarar, tablo başlığını içeren sayfayı bulur;
    başlıktan hemen sonraki "TOPLAM" satırına kadar olan METNİ döner.

    Başlıktan sonraki İLK tabloyla sınırlı: çoğu ay başlık İKİ kez geçer
    (tek ay + "(OCAK-<AY>)" kümülatif) ama OCAK bültenlerinde kümülatif
    tablo yoktur (tek ay zaten Ocak-Ocak'la özdeş) — bu yüzden ikinci
    başlığın varlığına güvenmek yerine doğrudan bu tablonun kendi TOPLAM
    satırında durulur; kümülatif tablo (varsa) sınırın dışında kalır.
    """
    with pdfplumber.open(io.BytesIO(pdf_baytlari)) as pdf:
        for sayfa in pdf.pages:
            metin = sayfa.extract_text() or ""
            baslangic = metin.find(_TABLO_BASLIGI)
            if baslangic == -1:
                continue
            sonra = metin[baslangic + len(_TABLO_BASLIGI):]
            toplam_eslesen = re.search(r"\nTOPLAM\n", sonra)
            if not toplam_eslesen:
                raise RuntimeError(
                    f"TAİD PDF'inde '{_TABLO_BASLIGI}' başlığından sonra "
                    "TOPLAM satırı bulunamadı"
                )
            return sonra[: toplam_eslesen.end()]
    raise RuntimeError(f"TAİD PDF'inde '{_TABLO_BASLIGI}' tablosu bulunamadı")


def marka_toplamlarini_ayikla(bolum_metni: str) -> dict[str, float]:
    """Tek aylık bölüm metninden `{marka: toplam}` çıkarır ve öz-doğrular.

    Tablo satırı sırası PDF metin çıkarımında "<yerli> <ithal> <toplam>"
    satırının HEMEN ARDINDAN marka adı satırı gelecek şekildedir (hücre
    sırası değil, pdfplumber'ın metin akışı böyle). "TOPLAM" satırı da aynı
    desenle yakalanır ve markaların toplamıyla çapraz doğrulanır.
    """
    satirlar = [s.strip() for s in bolum_metni.strip().splitlines() if s.strip()]
    uc_sayi = re.compile(r"^[\d.,]+ [\d.,]+ [\d.,]+$")
    bekleyen: tuple[float, float, float] | None = None
    marka_satirlari: dict[str, tuple[float, float, float]] = {}
    genel_toplam: tuple[float, float, float] | None = None
    for satir in satirlar:
        if uc_sayi.match(satir):
            bekleyen = tuple(_sayi_parse(p) for p in satir.split())
            continue
        if bekleyen is None:
            continue
        if satir in GECERLI_TAID_MARKALARI:
            marka_satirlari[satir] = bekleyen
        elif satir == "TOPLAM":
            genel_toplam = bekleyen
        bekleyen = None

    if genel_toplam is None:
        raise RuntimeError("TAİD tablosunda TOPLAM satırı bulunamadı")
    for marka, (yerli, ithal, toplam) in marka_satirlari.items():
        if abs(yerli + ithal - toplam) > 0.5:
            raise RuntimeError(
                f"TAİD öz-doğrulama: {marka} YERLİ({yerli:g})+İTHAL({ithal:g}) "
                f"!= TOPLAM({toplam:g})"
            )
    toplanan = tuple(sum(v[i] for v in marka_satirlari.values()) for i in range(3))
    if any(abs(toplanan[i] - genel_toplam[i]) > 0.5 for i in range(3)):
        raise RuntimeError(
            f"TAİD öz-doğrulama: marka toplamları {toplanan} genel TOPLAM "
            f"satırıyla {genel_toplam} tutmuyor"
        )
    return {marka: toplam for marka, (_, _, toplam) in marka_satirlari.items()}


def seri_cek(seri, *, onbellek: dict | None = None, session=None,
             bugun: date | None = None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `seri.start_date` verilmişse o tarihten ÖNCEKİ bültenler İNDİRİLMEDEN
    atlanır — yalnızca bir verimlilik kısayolu değil: TAİD Ocak 2025'ten
    ÖNCEKİ bültenlerde "PERAKENDE SATIŞLAR YERLİ/İTHAL DAĞILIMI" tablosunu
    farklı bir sayfa düzeninde basıyor (etiket-sonra-değer yerine
    değer-sonra-etiket; "TOPLAM" satırı hemen ardından değer taşımıyor),
    bu da `_tek_ay_bolumunu_ayikla`'yı kırıyor (ölçüldü 2026-09-20: Ekim
    2023 – Aralık 2024 arası 15 bültenin 15'i de bu hatayla düşüyor, Ocak
    2025 – Ağustos 2026 arası 19 bültenin 19'u da sorunsuz). Katalogda bu
    seri için `start_date: "2025-01-01"` VERİLMELİDİR.
    """
    onbellek = {} if onbellek is None else onbellek
    bugun = bugun or date.today()
    marka = seri.taid_marka
    if marka not in GECERLI_TAID_MARKALARI:
        raise RuntimeError(f"Geçersiz taid_marka: {marka!r}")

    if "liste" not in onbellek:
        onbellek["liste"] = bulten_listesini_cek(bugun, session=session)
    liste = onbellek["liste"]

    satirlar = []
    for tarih, pdf_url in liste.items():
        if seri.start_date and tarih < seri.start_date:
            continue
        anahtar = f"{tarih}:markalar"
        if anahtar not in onbellek:
            http = session or requests
            yanit = http.get(pdf_url, timeout=ZAMAN_ASIMI)
            if yanit.status_code != 200:
                raise RuntimeError(f"TAİD bülten PDF HTTP {yanit.status_code} ({pdf_url})")
            bolum = _tek_ay_bolumunu_ayikla(yanit.content)
            onbellek[anahtar] = marka_toplamlarini_ayikla(bolum)
        deger = onbellek[anahtar].get(marka)
        if deger is not None:
            satirlar.append((tarih, deger))

    if not satirlar:
        raise RuntimeError(f"TAİD bültenlerinde '{marka}' için hiç veri yok")

    df = pd.DataFrame(satirlar, columns=["date", "value"]).sort_values("date")
    return df.reset_index(drop=True)
