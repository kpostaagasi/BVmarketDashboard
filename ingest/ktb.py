"""KTB (Kültür ve Turizm Bakanlığı) Sınır İstatistikleri Bülteni istemcisi.

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


def seri_cek(seri, *, onbellek: dict | None = None, session=None) -> pd.DataFrame:
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
