"""EPİAŞ Şeffaflık Platformu 2.0 istemcisi.

Kimlik doğrulama TGT (ticket granting ticket) ile yapılır: kullanıcı adı ve
parola bir kez gönderilip ticket alınır, sonraki isteklere `TGT` başlığında
eklenir. Ticket ~2 saat geçerlidir; ingest koşusu dakikalar sürdüğü için
tazeleme mantığı yoktur.

Endpoint yolları UCLAR sözlüğünde toplanmıştır: EPİAŞ yol değiştirirse tek
yerde düzelir. Baraj doluluk serisi bu istemcinin kapsamı dışındadır: ilgili
uç ("dams-active-fullness") 404 dönüyor ve zaten baraj/havza bazlı veriyor,
ulusal toplam yayınlamıyor.

Yanıt zarfı `{"items": [...]}`; her kayıt "date" (ISO, +03:00 ofsetli) ve
seriye özgü bir değer alanı taşır (PTF için "price", üretim için "total").
Veri saatliktir; günlüğe indirgeme `seri_cek` içinde yapılır.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import requests

TGT_URL = "https://giris.epias.com.tr/cas/v1/tickets"
TABAN = "https://seffaflik.epias.com.tr"
ZAMAN_ASIMI = 30

UCLAR = {
    "uretim": "/electricity-service/v1/generation/data/realtime-generation",
    "ptf": "/electricity-service/v1/markets/dam/data/mcp",
}

# EPİAŞ elektrik uçları TEK istekte en fazla 3 aylık pencereye izin veriyor
# (canlı API'de doğrulandı: pencere aşılınca HTTP 400 "(BUS)SEF1117 —
# Verilen tarihler tanımlanmış aralıktan (3 MONTH) fazla olamaz!"). Bu yüzden
# çok-yıllık pencereler `pencereleri_bol` ile bu sınırın altında ardışık
# dilimlere bölünüp ayrı isteklerle çekilir (bkz. seri_cek).
AZAMI_PENCERE_GUN = 89

# start_date verilmeyen seriler için varsayılan geçmiş: EVDS 15 yıl, Yahoo
# Finance 15 yıllık aralık kullanıyor; EPİAŞ Şeffaflık Platformu'nun saatlik
# elektrik verileri için 5 yıl seçildi — mevsimsellik grafiğinin anlamlı
# olması için birden çok takvim yılını üst üste bindirmeye yeter, ve
# 5 yıl / 89 günlük dilim ≈ seri başına ~21 istek: makul bir hacim, EPİAŞ'ı
# tek seferde yıllarca geriye giden ağır bir sorguyla zorlamaz.
VARSAYILAN_GECMIS_YIL = 5


def pencereleri_bol(
    baslangic: date, bitis: date, azami_gun: int = AZAMI_PENCERE_GUN
) -> list[tuple[date, date]]:
    """Saf: `[baslangic, bitis]` aralığını EPİAŞ'a tek istekte gönderilebilir,
    ardışık, çakışmayan ve aralarında boşluk bırakmayan dilimlere böler.

    Her dilim en fazla `azami_gun` gün sürer (`bitis - baslangic <= azami_gun`).
    Bir sonraki dilim, öncekinin bittiği günün ertesi günü başlar — EPİAŞ'ın
    `endDate`'i o günü dahil ettiği için (aksi halde sınır günü iki dilimde
    de görülür ve günlük toplam/ortalama iki katına çıkar).
    """
    if baslangic > bitis:
        raise ValueError("baslangic, bitişten sonra olamaz")
    pencereler: list[tuple[date, date]] = []
    cur_baslangic = baslangic
    while cur_baslangic <= bitis:
        cur_bitis = min(cur_baslangic + timedelta(days=azami_gun), bitis)
        pencereler.append((cur_baslangic, cur_bitis))
        cur_baslangic = cur_bitis + timedelta(days=1)
    return pencereler


def tgt_al(kullanici: str, parola: str,
           session: requests.Session | None = None) -> str:
    """Ticket alır. Parola yalnızca burada kullanılır, hiçbir yere yazılmaz."""
    http = session or requests
    yanit = http.post(
        TGT_URL,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/plain",
        },
        data={"username": kullanici, "password": parola},
        timeout=ZAMAN_ASIMI,
    )
    if yanit.status_code not in (200, 201):
        raise RuntimeError(f"EPİAŞ giriş başarısız: HTTP {yanit.status_code}")
    ticket = yanit.text.strip()
    if not ticket.startswith("TGT-"):
        raise RuntimeError("EPİAŞ giriş yanıtında TGT bulunamadı")
    return ticket


def noktalari_ayikla(yanit: dict, alan: str) -> list[tuple[str, float]]:
    """Saf: zarf sözlüğünden (tarih, değer) listesi çıkarır.

    Boş değerli kayıtlar atlanır — EPİAŞ yayınlanmamış saatleri null döner.
    Alan hiç yoksa KeyError yükselir: sessizce boş seri döndürmek, kırık bir
    ingest'i sağlıklı göstermekten kötüdür.
    """
    noktalar = []
    for kayit in yanit.get("items") or []:
        ham = kayit[alan]
        if ham is None:
            continue
        noktalar.append((kayit["date"][:10], float(ham)))
    return noktalar


def seri_cek(seri, tgt: str, session: requests.Session | None = None,
             bugun: date | None = None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    Pencere `pencereleri_bol` ile EPİAŞ'ın kabul ettiği azami dilimlere
    bölünür ve her dilim ayrı bir istekle çekilir (bkz. AZAMI_PENCERE_GUN);
    tüm dilimlerin ham noktaları birleştirildikten SONRA tek seferde
    günlüğe indirgenir ve ölçeklenir — dilim başına değil. Dilimler tarih
    sınırında ayrıldığı için (bir gün asla iki dilime bölünmez) bu, tek
    istekli eski davranışla birebir aynı sonucu verir; sadece istek sayısı
    artar.

    Saatlik veri günlüğe indirgenir: `seri.monthly_agg == "sum"` ise günlük
    TOPLAM (üretim gibi akış büyüklükleri için — ortalama alınırsa değer
    24'te birine düşer), aksi halde günlük ORTALAMA (PTF gibi fiyat/seviye
    büyüklükleri için). Ardından `seri.olcek` ile çarpılır (ör. üretim MWh
    döner, GWh olarak gösterilir: olcek=0.001); ölçekleme indirgemeden SONRA
    uygulanır, aksi halde toplama öncesi ölçeklenmiş saatlik değerlerin
    toplamı yine doğru sonucu verirdi ama ortalamada anlamı değişirdi.
    """
    bugun = bugun or date.today()
    if seri.start_date:
        baslangic = date.fromisoformat(seri.start_date)
    else:
        try:
            baslangic = bugun.replace(year=bugun.year - VARSAYILAN_GECMIS_YIL)
        except ValueError:
            # 29 Şubat: hedef yıl artık yıl değil, 28'ine düşülür
            baslangic = bugun.replace(
                year=bugun.year - VARSAYILAN_GECMIS_YIL, day=28
            )
    http = session or requests

    tum_noktalar: list[tuple[str, float]] = []
    for cur_baslangic, cur_bitis in pencereleri_bol(baslangic, bugun):
        yanit = http.post(
            TABAN + UCLAR[seri.epias_ucu],
            headers={"Content-Type": "application/json", "TGT": tgt},
            json={
                "startDate": f"{cur_baslangic.isoformat()}T00:00:00+03:00",
                "endDate": f"{cur_bitis.isoformat()}T00:00:00+03:00",
            },
            timeout=ZAMAN_ASIMI,
        )
        if yanit.status_code != 200:
            raise RuntimeError(
                f"EPİAŞ HTTP {yanit.status_code} ({seri.id})"
            )
        tum_noktalar.extend(noktalari_ayikla(yanit.json(), seri.epias_alani))

    if not tum_noktalar:
        raise RuntimeError(f"EPİAŞ boş seri döndürdü ({seri.id})")

    df = pd.DataFrame(tum_noktalar, columns=["date", "value"])
    if seri.monthly_agg == "sum":
        gunluk = df.groupby("date", as_index=False)["value"].sum()
    else:
        gunluk = df.groupby("date", as_index=False)["value"].mean()
    gunluk = gunluk.sort_values("date").reset_index(drop=True)
    gunluk["value"] = gunluk["value"] * seri.olcek
    return gunluk
