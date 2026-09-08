"""EUROCONTROL günlük uçuş verisi (Daily Traffic Variation) istemcisi.

Kaynak gerçekleri 2026-09-08'de canlı ölçüldü (sıfırdan yeniden
keşfetmeye çalışmayın):

- Veri, EUROCONTROL'ün "Daily Traffic Variation" panosunun beslediği üç
  statik JSON dosyasından gelir (Google Charts `DataTable` biçimi):
  `tfc_ct_data.json` ülkeler (43 varlık, "Türkiye" dahil),
  `tfc_ao_data.json` hava yolu şirketleri (52 varlık: "Turkish Airlines
  Group", "Pegasus", "SunExpress"), `tfc_apt_100_data.json` havalimanları
  (Türkiye: Istanbul, Istanbul Sabiha Gokcen, Antalya, Ankara, Izmir,
  Istanbul Ataturk). Panonun "Download" düğmesi aynı veriyi XLSX olarak
  veriyor; JSON daha ucuz ve ek bağımlılık istemiyor.
- Dosya biçimi: `[sütun adları, sütun tipleri, satır, satır, ...]` — ilk
  İKİ eleman veri değildir.
- Sayılar dizedir ve baştaki boşlukla gelir (`" 2441"`); yüzdeler bilimsel
  gösterimde (`2.841609e-01`).
- **DOSYALAR YALNIZCA CARİ YILI TAŞIR** (2026-01-01 → 2026-09-07). Ama her
  satır önceki yılın aynı gününü de veriyor: `Day Previous Year` +
  `Flights <önceki yıl> (Reference)`. Bu iki sütun kullanılarak seri bir yıl
  geriye uzatılır — böylece mevsimsellik grafiği iki yıl çizebilir.
  `Day 2019` + `Flights 2019 (Reference)` sütunları da var ama 2019 ile
  cari yıl arasında beş yıllık boşluk bırakırdı; bilinçli olarak
  kullanılmıyor (seviye grafiğinde kopuk çizgi, YoY'da anlamsız eşleşme).
- Referans sütununun adı her yıl değişir (`Flights 2025 (Reference)`), bu
  yüzden sütun adı REGEX'le bulunur; sabit indeks kullanmak yıl dönümünde
  sessizce yanlış sütunu okurdu.
"""

from __future__ import annotations

import json
import re
from datetime import date

import pandas as pd
import requests

from core.catalog import GECERLI_EC_KAYNAKLARI

TABAN = "https://www.eurocontrol.int/Economics"
ZAMAN_ASIMI = 120

DOSYALAR = {
    "ulke": "tfc_ct_data.json",
    "havayolu": "tfc_ao_data.json",
    "havalimani": "tfc_apt_100_data.json",
}
assert set(DOSYALAR) == GECERLI_EC_KAYNAKLARI

_REFERANS = re.compile(r"^Flights (\d{4}) \(Reference\)$")


def dosya_url(kaynak: str) -> str:
    return f"{TABAN}/{DOSYALAR[kaynak]}"


def sayi_parse(ham: object) -> float | None:
    """`" 2441"` → 2441.0. Boş ya da sayı olmayan → None."""
    if ham is None:
        return None
    metin = str(ham).strip()
    if not metin or metin in ("-", "null", "NaN"):
        return None
    try:
        return float(metin)
    except ValueError:
        return None


def referans_sutunu(basliklar: list[str], bugun: date) -> str | None:
    """Önceki yılın referans sütununun adı; yoksa None.

    2019 sütunu bilinçle atlanır (bkz. modül docstring'i): cari yılla
    arasında beş yıllık boşluk var.
    """
    yillar = []
    for ad in basliklar:
        eslesme = _REFERANS.match(ad)
        if eslesme:
            yillar.append((int(eslesme.group(1)), ad))
    onceki = [(y, ad) for y, ad in yillar if y == bugun.year - 1]
    return onceki[0][1] if onceki else None


def noktalari_ayikla(govde: list, varlik: str, bugun: date) -> dict[str, float]:
    """Bir varlığın günlük uçuş sayılarını çıkarır (cari + önceki yıl).

    `govde` Google Charts DataTable listesidir: ilk iki eleman sütun adları
    ve tipleridir, veri üçüncüden başlar.
    """
    if len(govde) < 3:
        raise RuntimeError("EUROCONTROL dosyası beklenen biçimde değil")
    basliklar = [str(b) for b in govde[0]]
    for gerekli in ("Entity", "Day", "Flights"):
        if gerekli not in basliklar:
            raise RuntimeError(
                f"EUROCONTROL dosyasında '{gerekli}' sütunu yok: {basliklar}"
            )
    i_varlik = basliklar.index("Entity")
    i_gun = basliklar.index("Day")
    i_ucus = basliklar.index("Flights")
    referans_ad = referans_sutunu(basliklar, bugun)
    i_ref = basliklar.index(referans_ad) if referans_ad else None
    i_ref_gun = (
        basliklar.index("Day Previous Year")
        if "Day Previous Year" in basliklar
        else None
    )

    noktalar: dict[str, float] = {}
    gorulen_varlik = False
    for satir in govde[2:]:
        if str(satir[i_varlik]).strip() != varlik:
            continue
        gorulen_varlik = True
        deger = sayi_parse(satir[i_ucus])
        gun = str(satir[i_gun]).strip()
        if deger is not None and gun:
            noktalar[gun] = deger
        if i_ref is not None and i_ref_gun is not None:
            onceki = sayi_parse(satir[i_ref])
            onceki_gun = str(satir[i_ref_gun]).strip()
            # Cari yıl değeri her zaman kazanır: aynı gün iki kaynaktan
            # gelirse (yıl dönümü kenarı) taze olan doğru olandır.
            if onceki is not None and onceki_gun and onceki_gun not in noktalar:
                noktalar[onceki_gun] = onceki
    if not gorulen_varlik:
        raise RuntimeError(
            f"EUROCONTROL dosyasında varlık bulunamadı: {varlik!r} — "
            "kaynak adlandırmayı değiştirmiş olabilir"
        )
    if not noktalar:
        raise RuntimeError(f"EUROCONTROL {varlik!r} için hiç nokta üretmedi")
    return noktalar


def _dosya_cek(kaynak: str, onbellek: dict, session=None) -> list:
    if kaynak in onbellek:
        return onbellek[kaynak]
    http = session or requests
    yanit = http.get(dosya_url(kaynak), timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(
            f"EUROCONTROL HTTP {yanit.status_code} ({DOSYALAR[kaynak]})"
        )
    onbellek[kaynak] = json.loads(yanit.text)
    return onbellek[kaynak]


def seri_cek(seri, onbellek: dict | None = None, session=None,
             bugun: date | None = None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    Üç dosya koşu başına bir kez indirilir ve `onbellek`te paylaşılır: yedi
    seri bu üç dosyayı okuduğu için yoksa yedi indirme olurdu (dosyalar
    2–5 MB).
    """
    bugun = bugun or date.today()
    onbellek = {} if onbellek is None else onbellek
    govde = _dosya_cek(seri.ec_kaynak, onbellek, session)
    noktalar = noktalari_ayikla(govde, seri.ec_varlik, bugun)

    df = pd.DataFrame(sorted(noktalar.items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)
