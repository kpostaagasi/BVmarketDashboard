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

# EPİAŞ elektrik uçları tek istekte en fazla 3 aylık pencereye izin veriyor
# (canlı API'de doğrulandı: pencere aşılınca HTTP 400 "(BUS)SEF1117 —
# Verilen tarihler tanımlanmış aralıktan (3 MONTH) fazla olamaz!"). Varsayılan
# pencere bu sınırın altında kalmalı, aksi halde start_date verilmeyen her
# istek başarısız olur. `bugun`e göre hesaplandığı için otomatik koşularda
# pencere her zaman güncel kalır — sabit bir tarih gibi zamanla sınırı aşmaz.
VARSAYILAN_PENCERE_GUN = 89


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

    Saatlik veri günlüğe indirgenir: `seri.monthly_agg == "sum"` ise günlük
    TOPLAM (üretim gibi akış büyüklükleri için — ortalama alınırsa değer
    24'te birine düşer), aksi halde günlük ORTALAMA (PTF gibi fiyat/seviye
    büyüklükleri için). Ardından `seri.olcek` ile çarpılır (ör. üretim MWh
    döner, GWh olarak gösterilir: olcek=0.001); ölçekleme indirgemeden SONRA
    uygulanır, aksi halde toplama öncesi ölçeklenmiş saatlik değerlerin
    toplamı yine doğru sonucu verirdi ama ortalamada anlamı değişirdi.
    """
    bugun = bugun or date.today()
    baslangic = (
        date.fromisoformat(seri.start_date)
        if seri.start_date
        else bugun - timedelta(days=VARSAYILAN_PENCERE_GUN)
    )
    http = session or requests

    yanit = http.post(
        TABAN + UCLAR[seri.epias_ucu],
        headers={"Content-Type": "application/json", "TGT": tgt},
        json={
            "startDate": f"{baslangic.isoformat()}T00:00:00+03:00",
            "endDate": f"{bugun.isoformat()}T00:00:00+03:00",
        },
        timeout=ZAMAN_ASIMI,
    )
    if yanit.status_code != 200:
        raise RuntimeError(
            f"EPİAŞ HTTP {yanit.status_code} ({seri.id})"
        )

    noktalar = noktalari_ayikla(yanit.json(), seri.epias_alani)
    if not noktalar:
        raise RuntimeError(f"EPİAŞ boş seri döndürdü ({seri.id})")

    df = pd.DataFrame(noktalar, columns=["date", "value"])
    if seri.monthly_agg == "sum":
        gunluk = df.groupby("date", as_index=False)["value"].sum()
    else:
        gunluk = df.groupby("date", as_index=False)["value"].mean()
    gunluk["value"] = gunluk["value"] * seri.olcek
    return gunluk
