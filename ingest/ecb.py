"""ECB Data Portal (SDMX REST) istemcisi — anahtar gerektirmeyen, genel amaçlı.

Kaynak: `data-api.ecb.europa.eu/service/data/<akış>/<anahtar>?format=csvdata`.
Katalogda `ecb_akis` (SDMX dataflow kodu, ör. "CAR") ve `ecb_anahtar` (nokta
ayraçlı boyut kodları dizisi, ör. "M.I10.N.CREG.PC0000.4Z1.N.PN") sabitlenir;
FRED istemcisiyle (`ingest/fred.py`) aynı ilke: kod yanlışsa yanıt boş/hatalı
döner ve regresyon testi bunu yakalar. Bu istemci ECB'nin herhangi bir
dataflow'u için genel amaçlıdır — yeni bir Avrupa serisi eklemek yalnızca
akış/anahtar çiftini bulmayı gerektirir, kod değişikliği gerektirmez.

Ölçüldü (2026-09-18, canlı): CAR akışının `M.I10.N.CREG.PC0000.4Z1.N.PN`
anahtarı (Euro Bölgesi 21 sabit kompozisyon, mevsimsellikten arındırılmamış,
ACEA kaynaklı yeni otomobil tescili) Haziran 2026 = 979.505 adet — referans
platformun "Aylık Yeni Otomobil Tescilleri" kartıyla birebir eşleşti. Aynı
akışta yalnızca binek otomobil (PC0000) verisi var; CAR_CLASS=CV0000/
CVH000/CVL000 (ticari araç) için ECB'de hiç seri yayımlanmamış (ölçüldü).
"""

from __future__ import annotations

import pandas as pd
import requests

from core.catalog import Seri

TABAN = "https://data-api.ecb.europa.eu/service/data"
ZAMAN_ASIMI = 60


def seri_cek(seri: Seri, session=None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı)."""
    http = session or requests
    url = f"{TABAN}/{seri.ecb_akis}/{seri.ecb_anahtar}"
    yanit = http.get(
        url, params={"format": "csvdata"}, headers={"Accept": "text/csv"},
        timeout=ZAMAN_ASIMI,
    )
    if yanit.status_code == 404:
        raise RuntimeError(
            f"ECB'de seri bulunamadı: {seri.ecb_akis}/{seri.ecb_anahtar} "
            f"(HTTP 404) — ecb_akis/ecb_anahtar yanlış olabilir"
        )
    if yanit.status_code != 200:
        raise RuntimeError(
            f"ECB HTTP {yanit.status_code} ({seri.ecb_akis}/{seri.ecb_anahtar})"
        )
    df = pd.read_csv(pd.io.common.StringIO(yanit.text))
    if "TIME_PERIOD" not in df.columns or "OBS_VALUE" not in df.columns:
        raise RuntimeError(
            f"ECB CSV beklenen sütunları taşımıyor ({seri.ecb_akis}/{seri.ecb_anahtar}): "
            f"{list(df.columns)} — SDMX biçimi değişmiş olabilir"
        )
    df = df.rename(columns={"TIME_PERIOD": "date", "OBS_VALUE": "value"})[["date", "value"]]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"]).sort_values("date")
    if df.empty:
        raise RuntimeError(
            f"ECB'de {seri.ecb_akis}/{seri.ecb_anahtar} için hiç gözlem yok"
        )
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)
