"""Eurostat Dissemination API istemcisi — elektrik fiyatı istatistikleri
(`nrg_pc_204` hanehalkı, `nrg_pc_205` sanayi).

Anahtar GEREKTİRMEYEN kamuya açık REST uç noktası:
`https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/<dataset>`
JSON-stat 2.0 zarfı döner. `geo` parametresi TEKRARLANARAK (`geo=TR&geo=
EU27_2020`) birden çok coğrafyayı, `currency` verilmezse TÜM para birimlerini
(EUR/PPS/NAC) TEK istekte getirir — bu yüzden dataset başına TEK GET isteği
her (geo, currency) kombinasyonunun TÜM tarihçesini taşır (bkz. `_veri_getir`
onbellek anahtarı: yalnızca `dataset`).

`tax` (vergi/kesinti kapsamı) ve `nrg_cons` (tüketim bandı) katalogda EKSEN
DEĞİL — tüm serilerde SABİT: `tax=I_TAX` ("tüm vergi ve kesintiler dahil")
ve `nrg_cons=TOT_KWH` ("tüm bantların toplamı"). Bu, MarketVisuals'ın
eurostat_electricity_prices.html kartlarıyla CANLI ölçülerek birebir
doğrulandı: TR hanehalkı 2025-S2 = 6,79 cent EUR/kWh (kart: 6,79), TR
hanehalkı TL/kWh (currency=NAC) 2025-S2 = 3,2857 (kart: 3,29), TR sanayi
2025-S2 = 9,17 cent EUR/kWh (kart: 9,17), TR sanayi TL/kWh = 4,4411 (kart:
4,44) — dördü de BİREBİR eşleşti. EU27_2020 rakamları (2025-S1: bizim ölçüm
29,49 hane / 21,63 sanayi, kart 29,34 / 21,55) küçük (~%0,5) farkla eşleşti
— bu, Eurostat'ın EU27 toplamını üye ülke geç bildirimleriyle periyodik
REVİZE etmesinden kaynaklanıyor (TR'nin KENDİ bildirdiği rakam zaten kesin
olduğundan sabit kalıyor; EU27 AGREGASI ise yeniden hesaplanabiliyor) —
kodda düzeltilecek bir hata değil, canlı kaynağın doğal revizyon davranışı.

JSON-stat 2.0 "flat değer" biçimi: `value` sözlüğünün anahtarları, dizin
sırası `id` listesinden (ör. `[freq, siec, nrg_cons, unit, tax, currency,
geo, time]`) ve boyut uzunlukları `size` listesinden türeyen SATIR-ESAS
(row-major, SON boyut en hızlı değişen) düz bir ofsettir — bkz.
https://json-stat.org/full/#dimensionobject. `_noktalari_coz` bu geometriyi
yanıtın KENDİ `id`/`size` alanlarından okur (sabit sütun sırası varsaymaz),
bu yüzden Eurostat boyut sırasını değiştirse bile kırılmaz.

Yarıyıllık (S1/S2) veri: `time` ekseni "YYYY-S1"/"YYYY-S2" biçiminde gelir
(dataset etiketi: "bi-annual data (from 2007 onwards)"). Katalogda ayrı bir
"yarıyıllık" freq YOK; en yakın "quarterly" (yalnızca level grafiği
destekleyen, catalog._dogrula'nın zorunlu kıldığı) kovasına konur.

DÖNEM SONU damgası: yarıyıl, yarıyılı KAPATAN çeyreğin İLK gününe
damgalanır — S1 -> o yılın 1 Nisan'ı (1Ç+2Ç), S2 -> o yılın 1 Ekim'i
(3Ç+4Ç). Damga yarıyılın ilk ayına (S1->1 Ocak, S2->1 Temmuz) konulsaydı
`core.takvim.donem_sonu` "quarterly" kovasında S2'yi 3. çeyrek sanıp
2025-09-30'a çekerdi (yarım yılı çeyrek sayardı); doğrusu 2025-12-31'dir.
Ölçüt: `donem_sonu` dönemin BİTİŞ gününden tazelik eşiğini ölçer, ilk aya
damgalamak bu ölçümü 3 ay kaydırıyordu.

Bu, "quarterly" tazelik eşiğini (120 gün) yarıyıllık veri için biraz
iyimser bırakır (S2 verisi ancak 2026 başında yayımlanır). Tek yan etkisi
erken bir "gecikmiş" uyarısıdır; katalog tarafında `gecikme_gunu` ile
esnetilir, yanlış veri üretmez.

Değerler EUR/NAC HAM (EUR/kWh ya da TRY/kWh) gelir; "cent EUR/kWh" gösterimi
katalog `olcek: 100` ile (yalnızca `currency: EUR` serilerinde) EUR->cent
çevirir — AGENTS.md'deki "tek ölçekleme noktası" (`ingest.run.olcekle`)
ilkesiyle tutarlı, burada ölçeklenmez.
"""

from __future__ import annotations

import pandas as pd
import requests

from ingest.http import durum_kodu_yukselt

from core.catalog import Seri

TABAN = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
ZAMAN_ASIMI = 60

# Tüm eurostat serilerinde SABİT eksenler (bkz. modül docstring'i).
NRG_CONS_SABIT = "TOT_KWH"
TAX_SABIT = "I_TAX"

# Yarıyılı kapatan çeyreğin İLK günü (S1 -> 1 Nisan, S2 -> 1 Ekim), bkz.
# modül docstring'i.
YARIYIL_AY = {"S1": "04", "S2": "10"}


def _noktalari_coz(govde: dict) -> list[dict]:
    """JSON-stat 2.0 gövdesini düzleştirir: her nokta TÜM boyut kodlarını
    ve `value` değerini taşıyan bir sözlüktür.

    Geometri (`id` boyut sırası, `size` boyut uzunlukları) yanıtın KENDİSİNDEN
    okunur — sabit sütun/ofset varsayılmaz (bkz. modül docstring'i)."""
    boyut_adlari = govde["id"]
    boyutlar = govde["size"]
    kod_sirasi = {
        ad: [
            kod
            for kod, _ in sorted(
                govde["dimension"][ad]["category"]["index"].items(),
                key=lambda kv: kv[1],
            )
        ]
        for ad in boyut_adlari
    }
    noktalar = []
    for anahtar, deger in govde["value"].items():
        kalan = int(anahtar)
        konumlar = []
        for boyut in reversed(boyutlar):
            konumlar.append(kalan % boyut)
            kalan //= boyut
        konumlar.reverse()
        nokta = {ad: kod_sirasi[ad][konum] for ad, konum in zip(boyut_adlari, konumlar)}
        nokta["value"] = float(deger)
        noktalar.append(nokta)
    return noktalar


def _veri_getir(dataset: str, onbellek: dict, session=None) -> list[dict]:
    if dataset in onbellek:
        return onbellek[dataset]

    http = session or requests
    yanit = http.get(
        f"{TABAN}/{dataset}",
        params=[
            ("format", "JSON"),
            ("lang", "EN"),
            ("nrg_cons", NRG_CONS_SABIT),
            ("tax", TAX_SABIT),
            ("geo", "TR"),
            ("geo", "EU27_2020"),
        ],
        timeout=ZAMAN_ASIMI,
    )
    durum_kodu_yukselt(yanit)
    noktalar = _noktalari_coz(yanit.json())
    onbellek[dataset] = noktalar
    return noktalar


def _donem_tarihi(zaman: str) -> str:
    """'YYYY-S1'/'YYYY-S2' -> 'YYYY-04-01'/'YYYY-10-01' (yarıyılı kapatan
    çeyreğin ilk günü, bkz. modül docstring'i)."""
    yil, yariyil = zaman.split("-")
    return f"{yil}-{YARIYIL_AY[yariyil]}-01"


def seri_cek(seri: Seri, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `onbellek` verilirse dataset başına TEK istek koşu boyunca paylaşılır:
    6 seri (2 dataset × 3 geo/currency kombinasyonu) yalnızca 2 GET isteği
    kullanır (bkz. modül docstring'i, `_veri_getir`)."""
    onbellek = {} if onbellek is None else onbellek
    noktalar = _veri_getir(seri.eurostat_dataset, onbellek, session)

    eslesenler = [
        n
        for n in noktalar
        if n["geo"] == seri.eurostat_geo and n["currency"] == seri.eurostat_currency
    ]
    if not eslesenler:
        raise RuntimeError(
            f"Eurostat: {seri.eurostat_dataset}/{seri.eurostat_geo}/"
            f"{seri.eurostat_currency} için veri yok ({seri.id})"
        )

    df = (
        pd.DataFrame(
            {
                "date": [_donem_tarihi(n["time"]) for n in eslesenler],
                "value": [n["value"] for n in eslesenler],
            }
        )
        .sort_values("date")
        .drop_duplicates("date", keep="last")
        .reset_index(drop=True)
    )
    if seri.start_date:
        df = df[df["date"] >= seri.start_date].reset_index(drop=True)
    return df
