"""KTB (Kültür ve Turizm Bakanlığı) bülten istemcisi: Sınır İstatistikleri ve
Bakanlık Belgeli Konaklama İstatistikleri.

## Sınır İstatistikleri Bülteni (kaynak_tipi: ktb, varsayılan)

Kaynak: https://yigm.ktb.gov.tr/TR-249702/sinir-istatistikleri.html — güncel
ayın "Sınır Bülteni" .xls dosyasına bağlantı burada yayımlanır (dosya adı/ID
öngörülemez, ör. "150564,temm-z-2026-bultenixls.xls" — bu yüzden bağlantı
her koşuda sayfadan kazınır, TAV/OSD ile aynı desen). Bülten çok sayfalı;
"Gelen Yabancılar" sayfası "AYLAR" satırları × 3 YIL sütunu (bülten hangi
aya aitse, o yıl + önceki 2 yıl) taşıyan bir tablo içerir — TEK dosya
otomatik olarak ~3 yıllık aylık tarihçe verir. Değerler TAM AYLIKTIR
(kümülatif değil), fark alma gerekmez.

Ölçüldü (2026-09-18): Temmuz 2026 hücresi (7.096.564) marketvisuals.net
"Yabancı Ziyaretçi Sayısı" kartıyla (kaynak: Kültür ve Turizm Bakanlığı)
TAM eşleşiyor. Bu sayı TCMB EVDS'in `bie_sgegi` grubundaki "Çıkış Yapan
Yabancı Ziyaretçi Sayısı" (K6) alanından GELMEZ — o alan artık boş
(muhtemelen TCMB tablosu sadeleştirildi, yalnızca toplam/yerli-yabancı
ayrımsız K1/K3/K4/K11/K12/K13 kaldı); EVDS'te KTB'ninkine eşdeğer güncel
bir alan yok, bu yüzden ayrı adaptör gerekli (bkz. `ingest/evds.py` ile
birlikte katalog notu).

## Bakanlık Belgeli Konaklama İstatistikleri Bülteni (ktb_bulten: konaklama)

Kaynak: https://yigm.ktb.gov.tr/TR-201121/bakanlik-belgeli-tesis-konaklama-
istatistikleri.html — burada güncel AYLIK bülten (ör. "151114,konaklama-aylik-
b-lten-2026-temm-z-03092026xlsx.xlsx") ve bir ÖNCEKİ YILIN YILLIK bülteni
(ör. "145670,konaklama-yillik-b-lten-2025-ver2xlsx.xlsx") yayımlanır. NOT:
`.../TR-249702/konaklama-istatistikleri.html` diye bir adres YOKTUR — TR-249702
sınır bülteninin sayfasıdır ve HTTP 200 dönse bile O SAYFA döner; gerçek
konaklama sayfası TR-201121'dir. Yayımlanma gecikmesi ~35-40 gündür, yani
bülten daima iki ay öncesinin verisini taşır.

Her iki bülten de makine-okunur .xlsx'tir (PDF yoktur) ve "Ay" sayfası aynı
şablonu taşır: 0. satır başlık (yıl buradan çözülür), 1. satır grup
başlıkları, 2. satır "YABANCI/YERLI/TOPLAM", 3.. satırlar OCAK..ARALIK ve
son satır TOPLAM. Doluluk oranı 10/11/12. sütunlarda (YABANCI, YERLI,
TOPLAM), yüzde, bir ondalıkta yayımlanır (dosyada tam hassasiyette). Aylık
bülten OCAK'tan yayımlanan aya kadar, Aralık bülteni ise tam yılı verir —
geçmiş yıl Aralık bülteni tek dosyada 12 ay verir. Yıllık bültenin "Ay"
sayfası da aynı 12 aydır (yıllık = toplamla birebir aynı aylık değerler).

Ölçüldü (2026-09-29): Temmuz 2026 doluluk — TOPLAM 67.9559, YABANCI
39.81941, YERLI 28.13649 — marketvisuals.net "otel_doluluk" kartlarının
(68.0 / 39.8 / 28.1) YUVARLAMASI. Sitenin kartlardaki "YoY" farkları
(+2.9 / -0.8 / +8.6 puan) KTB verisiyle UYUŞMUYOR: Temmuz 2025 KTB'de
66.04 / 40.13 / 25.91, yani gerçek yıl-üstü farkı +1.9 / -0.3 / +2.2. Kart
metinleri bir başka (muhtemelen eski) bülten sürümünden türetilmiş;
SEVİYEler birebir tutuyor, YoY sütununu kopyalamıyoruz.

Geçmiş yıl bültenleri güncel sayfada DEĞİLDİR; yıl arşiv sayfasında
(ör. 2024 → TR-367939/2024.html) durur, TR ID'leri öngörülemez. 2025 için
arşiv sayfası bulunamadığından o yılın yıllık bülteni kullanılıyor.
`ponytalt:` tavan — KTB 2027'de yıllık bülteni 2026'ya çevirdiğinde 2025
bağlantısı sayfadan düşer; o gün Aralık-2025 aylık bülteni URL'si
`KONAKLAMA_YIL_SAYFALARI`'na eklenmeli.

Konaklama DOLULUK ORANI, geceleme sayısından türetilemez: payda (yani
eldeki oda/yatak kapasitesi) sınır bülteninde yoktur. Bu yüzden
`turizm/geceleme-*` (Eurostat nights spent) veya ziyaretçi sayısı vekil
olarak KULLANILMAZ; KTB'nin kendi yüzdesi okunur.

Bu davranışlar tersine mühendislikle çıkarıldı, sıfırdan yeniden
keşfedilmemeli.

Sözleşme: seri_cek(seri, *, onbellek=None, session=None) -> DataFrame[date,value]
"""

from __future__ import annotations

import re
from io import BytesIO

import pandas as pd
import requests

SAYFA = "https://yigm.ktb.gov.tr/TR-249702/sinir-istatistikleri.html"
TABAN = "https://yigm.ktb.gov.tr"
ZAMAN_ASIMI = 60
SHEET = "Gelen Yabancılar"

# --- Bakanlık Belgeli Konaklama İstatistikleri ---------------------------
KONAKLAMA_SAYFA = (
    "https://yigm.ktb.gov.tr/TR-201121/bakanlik-belgeli-tesis-konaklama-istatistikleri.html"
)
# Geçmiş yılların aylık bültenleri yıl arşiv sayfasında; TR ID'leri
# öngörülemez, bulunduğunda buraya eklenir (yıl → arşiv sayfası).
KONAKLAMA_YIL_SAYFALARI = {2024: "https://yigm.ktb.gov.tr/TR-367939/2024.html"}
KONAKLAMA_SAYFA_ADI = "Ay"
_DOLULUK_SUTUN = {"yabancı": 10, "yerli": 11, "toplam": 12}
# Aynı "Ay" sayfasındaki GECELEME sütunları (4/5/6): doluluktan farklı olarak
# adet. Kapsam: yalnızca işletme ve basit belgeli tesisler; Eurostat/TÜİK
# (belediye belgeliler dahil) geceleme serileriyle birebir aynı DEĞİL.
_GECELEME_SUTUN = {"yabancı": 4, "yerli": 5, "toplam": 6}
_GOSTERGE_SUTUN = {"doluluk": _DOLULUK_SUTUN, "geceleme": _GECELEME_SUTUN}
_GOSTERGE_BASLIK = {"doluluk": ("DOLULUK ORANI", 10), "geceleme": ("GECELEME", 4)}
_EKLETI_DESENI = re.compile(r'href="(/Eklenti/(\d+),[^"?]+\.xlsx?)(?:\?[^"]*)?"', re.I)
_YIL_BASLIK = re.compile(r"\((\d{4})")

_AYLAR_TR = (
    "OCAK", "ŞUBAT", "MART", "NİSAN", "MAYIS", "HAZİRAN", "TEMMUZ",
    "AĞUSTOS", "EYLÜL", "EKİM", "KASIM", "ARALIK",
)

_DOSYA_DESENI = re.compile(r'href="(/Eklenti/\d+,[^"?]+\.xlsx?)')


def dosya_url(session=None) -> str:
    """Sayfada birden çok bülten bağlantısı olabiliyor (ör. eski bir
    "önceki döneme ait" bağlantısı güncel bültenin GÖRSEL bağlantısından
    DOM'da ÖNCE geçebiliyor, ölçüldü 2026-09-18) — bu yüzden ilk eşleşme
    değil, Eklenti ID'si EN BÜYÜK olan (en yeni yüklenen) bağlantı alınır.
    """
    http = session or requests
    yanit = http.get(SAYFA, timeout=ZAMAN_ASIMI)
    yanit.raise_for_status()
    eslesmeler = _DOSYA_DESENI.findall(yanit.text)
    if not eslesmeler:
        raise RuntimeError("KTB sınır bülteni bağlantısı sayfada bulunamadı")
    en_yeni = max(eslesmeler, key=lambda yol: int(yol.split("/")[-1].split(",")[0]))
    return TABAN + en_yeni


def _dosya_indir(url: str, onbellek: dict, session=None) -> bytes:
    if "bulten" not in onbellek:
        http = session or requests
        yanit = http.get(url, timeout=ZAMAN_ASIMI)
        yanit.raise_for_status()
        onbellek["bulten"] = yanit.content
    return onbellek["bulten"]


def _konaklama_dosya_url(sayfa_url: str, tur: str, session=None) -> str:
    """Sayfadaki konaklama bültenlerinden (`tur` = "aylik" / "yillik")
    Eklenti ID'si EN BÜYÜK olanın URL'si — en yeni yüklenen, yani en
    güncel bülten. Yıl arşiv sayfasında en büyük ID Aralık bültenidir ve o
    dosya yılın 12 ayını da taşır.
    """
    http = session or requests
    yanit = http.get(sayfa_url, timeout=ZAMAN_ASIMI)
    yanit.raise_for_status()
    eslesmeler = [
        yol
        for yol, _kimlik in _EKLETI_DESENI.findall(yanit.text)
        if "konaklama" in yol.lower() and tur in yol.lower()
    ]
    if not eslesmeler:
        raise RuntimeError(
            f"KTB konaklama '{tur}' bülteni bağlantısı bulunamadı: {sayfa_url}"
        )
    en_yeni = max(eslesmeler, key=lambda yol: int(yol.split("/")[-1].split(",")[0]))
    return TABAN + en_yeni


def _konaklama_indir(url: str, onbellek: dict, session=None) -> bytes:
    if url not in onbellek:
        http = session or requests
        yanit = http.get(url, timeout=ZAMAN_ASIMI)
        yanit.raise_for_status()
        onbellek[url] = yanit.content
    return onbellek[url]


def _konaklama_ay_tablosu(
    baytlar: bytes, gosterge: str = "doluluk"
) -> tuple[int, pd.DataFrame]:
    """'Ay' sayfası → (yıl, tablo). Yıl dosya adından değil, 0. satırdaki
    başlıktan okunur ("... (2026 OCAK-TEMMUZ)") — dosya adı Türkçe
    karakterleri çözüyor.
    """
    df = pd.read_excel(BytesIO(baytlar), sheet_name=KONAKLAMA_SAYFA_ADI, header=None)
    baslik = str(df.iat[0, 0])
    yil_eslesme = _YIL_BASLIK.search(baslik)
    if not yil_eslesme:
        raise RuntimeError(f"KTB konaklama bülteninde yıl çözülemedi: {baslik[:90]}")
    baslik_metni, baslik_sutunu = _GOSTERGE_BASLIK[gosterge]
    if str(df.iat[1, 0]).strip() != "AYLAR" or not str(
        df.iat[1, baslik_sutunu]
    ).strip().startswith(baslik_metni):
        raise RuntimeError(
            f"KTB konaklama '{KONAKLAMA_SAYFA_ADI}' sayfası şablonu değişmiş: "
            f"{list(df.iloc[1, :4])}"
        )
    if [str(df.iat[2, s]).strip() for s in _GOSTERGE_SUTUN[gosterge].values()] != [
        "YABANCI",
        "YERLI",
        "TOPLAM",
    ]:
        raise RuntimeError(
            f"KTB konaklama {gosterge} sütunları beklenmiyor: YABANCI/YERLI/TOPLAM"
        )
    return int(yil_eslesme.group(1)), df


def _konaklama_cek(seri, *, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """Bakanlık Belgeli Konaklama doluluk oranı: aylık %, üç ölçüt
    (toplam / yabancı / yerli). `seri.ktb_olcut` bu üçünden biri olmalı.
    """
    onbellek = {} if onbellek is None else onbellek
    olcut = getattr(seri, "ktb_olcut", None)
    gosterge = getattr(seri, "ktb_gosterge", None) or "doluluk"
    if gosterge not in _GOSTERGE_SUTUN:
        raise RuntimeError(f"KTB konaklama göstergesi geçersiz: {gosterge!r}")
    if olcut not in _DOLULUK_SUTUN:
        raise RuntimeError(f"KTB konaklama ölçütü geçersiz: {olcut!r}")
    sutun = _GOSTERGE_SUTUN[gosterge][olcut]

    dosyalar = [
        _konaklama_dosya_url(KONAKLAMA_SAYFA, "aylik", session=session),
        _konaklama_dosya_url(KONAKLAMA_SAYFA, "yillik", session=session),
    ] + [
        _konaklama_dosya_url(yil_sayfasi, "aylik", session=session)
        for yil_sayfasi in KONAKLAMA_YIL_SAYFALARI.values()
    ]

    satirlar = []
    for url in dosyalar:
        yil, df = _konaklama_ay_tablosu(
            _konaklama_indir(url, onbellek, session=session), gosterge
        )
        for i in range(3, len(df)):
            ay_adi = str(df.iat[i, 0]).strip()
            if ay_adi == "TOPLAM":
                break
            if ay_adi not in _AYLAR_TR:
                raise RuntimeError(f"KTB konaklama bülteni ay satırı beklenmiyor: {ay_adi!r}")
            ay_no = _AYLAR_TR.index(ay_adi) + 1
            deger = df.iat[i, sutun]
            if pd.isna(deger):
                raise RuntimeError(
                    f"KTB konaklama {gosterge} hücresi boş: {yil}-{ay_no:02d} {olcut}"
                )
            satirlar.append((f"{yil:04d}-{ay_no:02d}-01", float(deger)))
    if not satirlar:
        raise RuntimeError(f"KTB konaklama bülteninde {gosterge} satırı bulunamadı")

    sonuc = (
        pd.DataFrame(satirlar, columns=["date", "value"])
        .drop_duplicates("date", keep="last")
        .sort_values("date")
    )
    return sonuc.reset_index(drop=True)


def _sinir_cek(seri, *, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    onbellek = {} if onbellek is None else onbellek
    if "url" not in onbellek:
        onbellek["url"] = dosya_url(session=session)
    baytlar = _dosya_indir(onbellek["url"], onbellek, session=session)
    df = pd.read_excel(BytesIO(baytlar), sheet_name=SHEET, header=None)

    baslik = list(df.iloc[2])
    if str(baslik[0]).strip() != "AYLAR":
        raise RuntimeError(f"KTB '{SHEET}' sayfası şablonu değişmiş: {baslik[:4]}")

    yillar: list[int] = []
    for hucre in baslik[1:4]:
        try:
            yillar.append(int(hucre))
        except (TypeError, ValueError):
            break
    if not yillar:
        raise RuntimeError("KTB bülteninde yıl sütunu çözülemedi")

    satirlar = []
    for i in range(3, 3 + len(_AYLAR_TR)):
        ay_adi = str(df.iat[i, 0]).strip()
        if ay_adi not in _AYLAR_TR:
            raise RuntimeError(f"KTB '{SHEET}' ay satırı beklenmiyor: {ay_adi!r}")
        ay_no = _AYLAR_TR.index(ay_adi) + 1
        for j, yil in enumerate(yillar, start=1):
            deger = df.iat[i, j]
            if pd.isna(deger):
                continue
            satirlar.append((f"{yil:04d}-{ay_no:02d}-01", float(deger)))

    sonuc = pd.DataFrame(satirlar, columns=["date", "value"]).sort_values("date")
    return sonuc.reset_index(drop=True)


def seri_cek(seri, *, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """`seri.ktb_bulten` = "konaklama" ise doluluk oranı, aksi halde sınır
    istatistikleri (varsayılan) çekilir.
    """
    if getattr(seri, "ktb_bulten", None) == "konaklama":
        return _konaklama_cek(seri, onbellek=onbellek, session=session)
    return _sinir_cek(seri, onbellek=onbellek, session=session)
