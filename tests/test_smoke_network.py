"""Kaynakların sözleşmesini gerçek uçlara karşı doğrulayan smoke testler.

Bu testler varsayılan koşuda ve CI'da ATLANIR (`pyproject.toml` içinde
`addopts = "-m 'not network'"`). Elle çağrılır:

    set -a; . ./.env; set +a
    .venv/bin/python -m pytest -m network -v

Amaçları hata yakalamak değil, SÖZLEŞME KAYMASINI erken görmek: bir kaynak
alan adını değiştirir ya da bir ucu kaldırırsa, günlük ingest sessizce boş
seri yazmadan önce burada öğreniriz. Bu yüzden değerleri değil, yanıtın
ŞEKLİNİ doğrularlar.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest
import requests

pytestmark = pytest.mark.network


def _atla_kimlik_yoksa(*degiskenler: str) -> dict[str, str]:
    eksik = [d for d in degiskenler if not os.environ.get(d)]
    if eksik:
        pytest.skip(f"kimlik bilgisi yok: {', '.join(eksik)}")
    return {d: os.environ[d] for d in degiskenler}


@pytest.fixture(scope="module")
def pencere() -> tuple[date, date]:
    bitis = date.today() - timedelta(days=2)
    return bitis - timedelta(days=2), bitis


def test_epias_uclari_beklenen_alanlari_donduruyor(pencere):
    """UCLAR'daki her uç yaşıyor ve katalogdaki alanları (tekil ya da bileşen) taşıyor.

    Bir uca birden çok seri bağlanabilir (ör. `uretim` hem tekil `total`
    alanlı `elektrik/uretim` serisine hem bileşen alanlı
    `elektrik/uretim-kompozisyon` serisine bağlıdır) — bu yüzden uç başına
    tek bir beklenen alan yerine, o ucu kullanan TÜM serilerin beklediği
    alanlar kontrol edilir.
    """
    from core.catalog import seri_listele
    from ingest.epias import TABAN, UCLAR, ZAMAN_ASIMI, tgt_al

    kimlik = _atla_kimlik_yoksa("EPIAS_USERNAME", "EPIAS_PASSWORD")
    baslangic, bitis = pencere

    seriler = seri_listele("elektrik")
    assert {s.epias_ucu for s in seriler} == set(UCLAR), "katalog ile UCLAR ayrışmış"

    with requests.Session() as oturum:
        tgt = tgt_al(kimlik["EPIAS_USERNAME"], kimlik["EPIAS_PASSWORD"], session=oturum)
        assert tgt.startswith("TGT-")

        for uc, yol in UCLAR.items():
            yanit = oturum.post(
                TABAN + yol,
                headers={"Content-Type": "application/json", "TGT": tgt},
                json={
                    "startDate": f"{baslangic.isoformat()}T00:00:00+03:00",
                    "endDate": f"{bitis.isoformat()}T00:00:00+03:00",
                },
                timeout=ZAMAN_ASIMI,
            )
            assert yanit.status_code == 200, f"{uc}: HTTP {yanit.status_code}"

            kayitlar = yanit.json().get("items")
            assert kayitlar, f"{uc}: 'items' boş ya da yok"
            ilk = kayitlar[0]
            assert "date" in ilk, f"{uc}: 'date' alanı kaybolmuş"

            # `total` ve `importExport` zarfta hep bulunur ama hiçbir grubun
            # parçası değildir (bkz. bilesen_noktalari_ayikla): türetilmiş
            # toplam ve ticaret kalemi, üretim kaynağı değil.
            bilinen_alanlar = {"total", "importExport"}
            for seri in seriler:
                if seri.epias_ucu != uc:
                    continue
                if seri.epias_bilesenler:
                    beklenen_alanlar = {
                        alan
                        for alanlar in seri.epias_bilesenler.values()
                        for alan in alanlar
                    }
                    bilinen_alanlar |= beklenen_alanlar
                    eksik = beklenen_alanlar - set(ilk)
                    assert not eksik, (
                        f"{seri.id}: bileşen alanları yanıtta yok: {sorted(eksik)} "
                        f"(mevcut alanlar: {sorted(ilk)})"
                    )
                else:
                    bilinen_alanlar.add(seri.epias_alani)
                    assert seri.epias_alani in ilk, (
                        f"{seri.id}: katalogun beklediği '{seri.epias_alani}' alanı "
                        f"yanıtta yok (mevcut alanlar: {sorted(ilk)})"
                    )

            # TERS YÖN: yanıttaki her alan katalogda tanınmalı — ama yalnızca
            # bu ucu BİLEŞENLİ (composition) bir serinin kullandığı durumda.
            # Risk yalnızca orada var: `paylara_cevir` grup toplamlarından
            # pay hesaplar, yeni bir alan hiçbir gruba girmeden sessizce
            # kaybolabilir (bkz. I1, Akkuyu/nuclear senaryosu). Tekil-alanlı
            # bir seri (ör. ptf → yalnızca `price` okunur) adıyla seçtiği
            # tek alanı okur; yanıttaki ilgisiz ek alanlar (ör. `priceEur`,
            # `priceUsd`) onun için risk taşımaz — bunları da zorunlu kılmak
            # sahte kırmızıya yol açar. `date` ve `hour` sayısal değildir,
            # karşılaştırma dışı tutulur.
            uc_bilesenli_mi = any(
                s.epias_ucu == uc and s.epias_bilesenler for s in seriler
            )
            if uc_bilesenli_mi:
                fazlalik = (set(ilk) - {"date", "hour"}) - bilinen_alanlar
                assert not fazlalik, (
                    f"{uc}: yanıtta katalogda tanınmayan yeni alan(lar) var: "
                    f"{sorted(fazlalik)} — EPİAŞ yeni bir üretim kaynağı eklemiş "
                    "olabilir; kataloğa (epias_bilesenler) ekleyin"
                )


def test_evds_serisi_nokta_donduruyor(pencere):
    from core.catalog import seri_getir
    from ingest.evds import seri_cek

    kimlik = _atla_kimlik_yoksa("EVDS_API_KEY")
    seri = seri_getir("enflasyon/tufe-genel")

    df = seri_cek(seri, kimlik["EVDS_API_KEY"])
    assert not df.empty
    assert list(df.columns) == ["date", "value"]


def test_yahoo_serisi_nokta_donduruyor():
    """Yahoo resmi bir API değil; uç sessizce değişebilir."""
    from core.catalog import seri_getir
    from ingest.yahoo import seri_cek

    df = seri_cek(seri_getir("emtia-enerji/brent"))
    assert not df.empty
    assert list(df.columns) == ["date", "value"]
