"""UAB (Ulaştırma ve Altyapı Bakanlığı) liman yük elleçleme istemcisi.

Kaynak: https://denizcilikistatistikleri.uab.gov.tr/yuk-istatistikleri-<yıl>
(liman başkanlığı bazında aylık yük elleçleme). Ana "/yuk-istatistikleri"
sayfası Next.js + ngx_pagespeed'e bağımlı bir istemci uygulamasıdır ve
ölçüldü (2026-09-18, tam tarayıcı oturumuyla) — hiçbir `web-api` isteği
TETİKLENMEDİ (mod_pagespeed JS'i erteliyor/satır içi ediyor); bu yüzden düz
`requests` ile o sayfa KAZINAMAZ. Ancak her yılın kendi alt sayfası
(`/yuk-istatistikleri-<yıl>`, 2019–2026 arası doğrulandı) STATİK HTML'DİR
ve doğrudan `liman-baskanliklari-bazinda-yuk-ellecleme-<hash>.xls`
bağlantılarını taşır — bu adaptör yalnızca bu alt sayfaları kullanır.

Her ay ayrı bir .xls yayımlanır ve bu dosya AYLIK DEĞİL — YIL BAŞINDAN
İLGİLİ AYA KADAR KÜMÜLATİFTİR (dosyanın kendi 0. satır başlığı, ör.
"...yük elleçleme istatistikleri, Ocak-Ağustos 2026"). AYLIK akış =
ardışık iki bültenin "Toplam Yük Elleçleme" sütunundaki farkı (Ocak
kümülatifi = Ocak'ın kendisi). Bağlantı dosya adları hash'lidir (tarih
sırasına güvenilmez); her dosyanın ait olduğu (yıl, ay) KENDİ başlık
satırından çözülür.

Ölçüldü (2026-09-18): Ağustos 2026 aylık farkı — Türkiye toplamı ve 9
"Liman Başkanlığı" (Aliağa, Trabzon, Kocaeli, Ambarlı, İzmir, İskenderun,
Mersin, Gemlik, Tekirdağ) — marketvisuals.net'in `uab_liman_ellecleme.html`
kartlarıyla TAM (kuruşuna kadar) eşleşiyor. "2025 - İlk 12 Liman" yıllık
sıralama kartı bu adaptörde YOK (bkz. `core/catalog.py` `denizcilik` notu):
tek yıla ait sabit bir sıralama, zaman serisi Seri şemasına uymuyor;
istenirse Aralık bülteninin (=tam yıl kümülatifi) ilgili satırından ayrı
bir mekanizmayla üretilebilir.

Sözleşme: seri_cek(seri, *, onbellek=None, session=None) -> DataFrame[date,value]
"""

from __future__ import annotations

import re
from datetime import date
from io import BytesIO

import pandas as pd
import requests

from core.catalog import GECERLI_UAB_LIMANLARI

TABAN = "https://denizcilikistatistikleri.uab.gov.tr"
ZAMAN_ASIMI = 60
# Kaç önceki yıl daha taranacak (cari yıl dahil toplam pencere).
GECMIS_YIL_SAYISI = 2

# Katalogdaki `uab_liman` değeri -> UAB dosyasındaki "Liman Başkanlığı" satır adı.
_LIMANLAR = {
    "toplam": "Toplam / Total",
    "aliaga": "Aliağa",
    "trabzon": "Trabzon",
    "kocaeli": "Kocaeli",
    "ambarli": "Ambarlı",
    "izmir": "İzmir",
    "iskenderun": "İskenderun",
    "mersin": "Mersin",
    "gemlik": "Gemlik",
    "tekirdag": "Tekirdağ",
}
assert set(_LIMANLAR) == GECERLI_UAB_LIMANLARI

_AYLAR_TR = (
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
    "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
)

_DOSYA_DESENI = re.compile(
    r'href="(https://denizcilikistatistikleri\.uab\.gov\.tr/uploads/pages/'
    r'yuk-istatistikleri-\d{4}/liman-baskanliklari-bazinda-yuk-ellecleme-[a-f0-9]+\.xls)"'
)


def dosya_listesi(yil: int, session=None) -> list[str]:
    """`<yıl>` alt sayfasını kazır, o yılın aylık .xls bağlantılarını döner."""
    http = session or requests
    yanit = http.get(f"{TABAN}/yuk-istatistikleri-{yil}", timeout=ZAMAN_ASIMI)
    yanit.raise_for_status()
    return sorted(set(_DOSYA_DESENI.findall(yanit.text)))


def _dosya_indir(url: str, onbellek: dict, session=None) -> bytes:
    if url not in onbellek:
        http = session or requests
        yanit = http.get(url, timeout=ZAMAN_ASIMI)
        yanit.raise_for_status()
        onbellek[url] = yanit.content
    return onbellek[url]

def _donem_coz(baslik: str) -> tuple[int, int]:
    """'...yük elleçleme istatistikleri, Ocak-Ağustos 2026\\n' -> (2026, 8).

    Yıl tamamlandığında son bülten ay adı taşımaz (yalnızca "...,
    2024\\n") — bu, o yılın TAM YIL (Ocak-Aralık) kümülatifidir; ay adı
    bulunamazsa Aralık (12) varsayılır. Ay adı(ları) metinde herhangi bir
    konumda aranır (regex ile konuma bağlı eşleşme aranmaz, ör. ", 2024"
    öncesinde noktalama işareti olabiliyor); bir aralıkta ("Ocak-Ağustos")
    metinde EN SAĞDAKİ (son) ay adı esas alınır.
    """
    yil_e = re.search(r"(\d{4})\s*$", baslik.strip())
    if not yil_e:
        raise RuntimeError(f"UAB dosya başlığından dönem çözülemedi: {baslik!r}")
    yil = int(yil_e.group(1))
    onceki_metin = baslik[: yil_e.start()]
    bulunan_aylar = [ay for ay in _AYLAR_TR if ay in onceki_metin]
    if not bulunan_aylar:
        return yil, 12
    son_ay = max(bulunan_aylar, key=lambda ay: onceki_metin.rfind(ay))
    return yil, _AYLAR_TR.index(son_ay) + 1


def _donem_ve_deger(baytlar: bytes, ham_ad: str) -> tuple[int, int, float]:
    df = pd.read_excel(BytesIO(baytlar), header=None)
    yil, ay = _donem_coz(str(df.iat[0, 0]))

    toplam_kolon = None
    for j in range(df.shape[1]):
        if "Toplam Yük Elleçleme" in str(df.iat[4, j]):
            toplam_kolon = j
            break
    if toplam_kolon is None:
        raise RuntimeError("UAB dosyasında 'Toplam Yük Elleçleme' sütunu bulunamadı")

    for i in range(6, len(df)):
        ad = df.iat[i, 0]
        if isinstance(ad, str) and ad.strip() == ham_ad:
            return yil, ay, float(df.iat[i, toplam_kolon])
    raise RuntimeError(f"UAB dosyasında '{ham_ad}' satırı yok")


def seri_cek(seri, *, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı)."""
    onbellek = {} if onbellek is None else onbellek
    ham_ad = _LIMANLAR[seri.uab_liman]
    bugunku_yil = date.today().year

    kumulatif: dict[int, dict[int, float]] = {}
    for yil in range(bugunku_yil - GECMIS_YIL_SAYISI, bugunku_yil + 1):
        anahtar = f"dosyalar-{yil}"
        if anahtar not in onbellek:
            try:
                onbellek[anahtar] = dosya_listesi(yil, session=session)
            except requests.HTTPError:
                # O yıla ait alt sayfa henüz yok/kaldırılmış — tarihçe bu
                # kadarıyla sınırlı kalır, diğer yıllar etkilenmez.
                onbellek[anahtar] = []
        for url in onbellek[anahtar]:
            baytlar = _dosya_indir(url, onbellek, session=session)
            y, ay, deger = _donem_ve_deger(baytlar, ham_ad)
            kumulatif.setdefault(y, {})[ay] = deger

    satirlar = []
    for yil, aylar in kumulatif.items():
        onceki = 0.0
        for ay in sorted(aylar):
            cari = aylar[ay]
            satirlar.append((f"{yil:04d}-{ay:02d}-01", cari - onceki))
            onceki = cari

    df = pd.DataFrame(satirlar, columns=["date", "value"]).sort_values("date")
    return df.reset_index(drop=True)
