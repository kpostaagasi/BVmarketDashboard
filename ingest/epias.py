"""EPİAŞ Şeffaflık Platformu 2.0 istemcisi.

Kimlik doğrulama TGT (ticket granting ticket) ile yapılır: kullanıcı adı ve
parola bir kez gönderilip ticket alınır, sonraki isteklere `TGT` başlığında
eklenir. Ticket ~2 saat geçerlidir; ingest koşusu dakikalar sürdüğü için
tazeleme mantığı yoktur.

Endpoint yolları UCLAR sözlüğünde toplanmıştır: EPİAŞ yol değiştirirse tek
yerde düzelir. Baraj doluluk `seri_cek`'in saatlik-alan-indirgeme desenine
UYMAZ (bkz. `baraj_doluluk_cek`): doğru yol `/v1/dams/data/active-fullness`
değil (önceki not "dams-active-fullness" 404 veriyor diyordu — yanlış yol
denenmişti); gerçek uç canlı ölçüldü ve 200 döndü, ama `date` gövde alanını
YOK SAYIYOR — her istekte yalnızca bugünün anlık görüntüsünü veriyor,
geriye dönük veri yok. Havza/ülke toplamı da yayınlamıyor: 80-116 barajlık
ham liste dönüyor, kapasite ağırlıklı toplam `baraj_doluluk_cek` içinde
`active-volume` + `dam-volume` uçlarıyla hesaplanıyor.

Yanıt zarfı `{"items": [...]}`; her kayıt "date" (ISO, +03:00 ofsetli) ve
seriye özgü bir değer alanı taşır (PTF için "price", üretim için "total").
Veri saatliktir; günlüğe indirgeme `seri_cek` içinde yapılır.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import requests

from core.catalog import Seri

TGT_URL = "https://giris.epias.com.tr/cas/v1/tickets"
TABAN = "https://seffaflik.epias.com.tr"
# evds ve yahoo ile aynı: ölçümde istek başına ~9s görüldü, 30s'lik pay dardı.
ZAMAN_ASIMI = 60

UCLAR = {
    "uretim": "/electricity-service/v1/generation/data/realtime-generation",
    "ptf": "/electricity-service/v1/markets/dam/data/mcp",
}

# Baraj doluluk `UCLAR`e girmiyor: `seri_cek`in tek-uç/hourly-alan deseni
# yerine `baraj_doluluk_cek` iki uçtan (hacim + kapasite) canlı anlık
# görüntüyü çekip kendi başına birleştiriyor (bkz. modül docstring'i).
BARAJ_AKTIF_HACIM_YOLU = "/electricity-service/v1/dams/data/active-volume"
BARAJ_HACIM_YOLU = "/electricity-service/v1/dams/data/dam-volume"
HAVZA_LISTESI_YOLU = "/electricity-service/v1/dams/data/basin-list"

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

# Türkiye 2016'dan beri sabit UTC+3 kullanıyor (DST yok) — bu yüzden TAM bir
# gün her zaman tam 24 saatlik kayıt içerir. Bu sabit, günlük indirgemeden
# önce eksik saatli günleri elemek için kullanılır (bkz. seri_cek).
SAAT_SAYISI_TAM_GUN = 24


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


def bilesen_noktalari_ayikla(
    yanit: dict, gruplar: dict[str, tuple[str, ...]]
) -> list[dict]:
    """Saatlik kayıtları grup toplamlarına indirger.

    `importExport` bilerek hiçbir gruba girmez: üretim kaynağı değil,
    ticaret kalemidir ve negatif olabilir (net ihracat). Paydaya karışırsa
    paylar %100'ü aşar. `total` da alınmaz — grup toplamlarından türetilir.

    Bilinmeyen alan adı sessizce sıfır sayılmaz; KeyError yükselir, çünkü
    EPİAŞ bir alanı yeniden adlandırırsa o grup sessizce boşalır ve grafik
    yanlış çizilir. `kayit[alan]` (`.get` değil) kasıtlı: bu, "alan hiç yok"
    (KeyError) ile "alan var ama değeri null" (aşağıdaki None kontrolü)
    ayrımını korur.

    Bir kaydın gruplara giren alanlarından HERHANGİ BİRİ `None` ise o SAAT
    tamamen atlanır — `None`'ı 0 saymak o kaynağın üretimini sessizce sıfır
    gösterir ve grup toplamını eksik raporlar (kardeş `noktalari_ayikla` ile
    aynı "veri uydurma" karşıtı davranış). Atlanan saat, aşağı akışta zaten
    `seri_cek`'in eksik-saat filtresine (`SAAT_SAYISI_TAM_GUN`) düşer: o gün
    24 saati tamamlayamaz ve günlük indirgemeden önce elenir.
    """
    noktalar = []
    for kayit in yanit.get("items") or []:
        degerler = {
            alan: kayit[alan] for alanlar in gruplar.values() for alan in alanlar
        }
        if any(deger is None for deger in degerler.values()):
            continue
        nokta = {"date": kayit["date"][:10]}
        for grup, alanlar in gruplar.items():
            nokta[grup] = float(sum(degerler[alan] for alan in alanlar))
        noktalar.append(nokta)
    return noktalar


def seri_cek(seri: Seri, tgt: str, session: requests.Session | None = None,
             bugun: date | None = None,
             onbellek: dict | None = None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    Pencere `pencereleri_bol` ile EPİAŞ'ın kabul ettiği azami dilimlere
    bölünür ve her dilim ayrı bir istekle çekilir (bkz. AZAMI_PENCERE_GUN);
    tüm dilimlerin ham noktaları birleştirildikten SONRA tek seferde
    günlüğe indirgenir — dilim başına değil. Dilimler tarih
    sınırında ayrıldığı için (bir gün asla iki dilime bölünmez) bu, tek
    istekli eski davranışla birebir aynı sonucu verir; sadece istek sayısı
    artar. Bir dilim HTTP 200 ile boş `items` dönerse (regresyon: tek
    istekli eski hâlde bu zaten hataydı) o dilim sessizce atlanmaz —
    hangi dilimin boş olduğu belirtilerek RuntimeError yükselir; aksi
    halde o dilimin kapsadığı günler sessizce kaybolur ve `seriyi_yaz`
    dosyanın tamamını delikli veriyle üzerine yazar.

    Günlüğe indirgemeden ÖNCE, TAM 24 saatlik kaydı olmayan günler
    düşülür (bkz. SAAT_SAYISI_TAM_GUN). EPİAŞ, henüz yayınlanmamış
    saatler için o güne ait eksik veri döner — özellikle son dilimin
    `endDate`'i bugünse, gün cron'un koştuğu saate kadar yalnızca kısmen
    yayınlanmış olur. Böyle bir günü toplam/ortalamaya dahil etmek, günün
    bir kesrini günlük değer gibi göstererek KPI'ları ve YoY
    karşılaştırmalarını (yön dahil) yanlış üretir. Kural yalnızca son güne
    özel değildir — ilk gün de `start_date` gün ortasına denk gelirse
    eksik olabilir. Türkiye 2016'dan beri sabit UTC+3 kullandığından
    (DST yok) her sağlıklı gün zaten tam 24 saat içerir; bu filtre yalnızca
    uçtaki kesik günleri atar, iç veriyi kırpmaz.

    Saatlik veri günlüğe indirgenir: `seri.monthly_agg == "sum"` ise günlük
    TOPLAM (üretim gibi akış büyüklükleri için — ortalama alınırsa değer
    24'te birine düşer), aksi halde günlük ORTALAMA (PTF gibi fiyat/seviye
    büyüklükleri için). Katalog `olcek`i BURADA uygulanmaz — indirgenmiş
    çerçeve ham birimiyle döner ve ölçekleme orchestrator'da
    (`ingest.run.olcekle`) tek noktadan yapılır. Sıra korunur: indirgeme
    bu fonksiyonda bittiği için orchestrator'ın uyguladığı ölçek yine
    indirgemeden SONRA devreye girer.
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
        # Aynı ucu aynı pencereyle paylaşan seriler (ör. elektrik/uretim ile
        # elektrik/uretim-kompozisyon) koşu başına tek dict paylaşırsa yanıt
        # bir kez çekilir — 42 istek yerine 21. Önbellek isteğe bağlıdır;
        # verilmezse davranış eskisiyle birebir aynı.
        anahtar = (seri.epias_ucu, cur_baslangic, cur_bitis)
        if onbellek is not None and anahtar in onbellek:
            govde = onbellek[anahtar]
        else:
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
            govde = yanit.json()
            if onbellek is not None:
                onbellek[anahtar] = govde
        if seri.epias_bilesenler:
            dilim_noktalari = bilesen_noktalari_ayikla(
                govde, seri.epias_bilesenler
            )
        else:
            dilim_noktalari = noktalari_ayikla(govde, seri.epias_alani)
        if not dilim_noktalari:
            raise RuntimeError(
                f"EPİAŞ dilimi boş döndü ({seri.id}, "
                f"{cur_baslangic.isoformat()}–{cur_bitis.isoformat()})"
            )
        tum_noktalar.extend(dilim_noktalari)

    if seri.epias_bilesenler:
        df = pd.DataFrame(tum_noktalar)
        gruplar = list(seri.epias_bilesenler)
    else:
        df = pd.DataFrame(tum_noktalar, columns=["date", "value"])
        gruplar = ["value"]

    # Eksik saatli günler düşer (Faz 3b C1): bir günün kesri, günlük değer
    # gibi gösterilirse KPI ve YoY yönü yanlış çıkar.
    gun_basina_saat = df.groupby("date")[gruplar[0]].transform("size")
    df = df[gun_basina_saat == SAAT_SAYISI_TAM_GUN]

    toplama = "sum" if seri.monthly_agg == "sum" else "mean"
    gunluk = df.groupby("date", as_index=False)[gruplar].agg(toplama)
    gunluk = gunluk.sort_values("date").reset_index(drop=True)
    return gunluk


def havza_listesi_cek(tgt: str, session: requests.Session | None = None) -> list[str]:
    """Saf GET: EPİAŞ'ın tanıdığı havza adlarını döner (bkz. HAVZA_LISTESI_YOLU).

    Canlı ölçüldü (2026-09-18): 17 havza. Katalog doğrulaması
    `core.catalog.GECERLI_EPIAS_HAVZALARI` ile bu listeyi statik tutuyor —
    EPİAŞ yeni bir havza eklerse bu fonksiyon onu görür ama katalog sabiti
    de elle güncellenmeli (sessiz uyuşmazlık yerine `_dogrula` hata verir).
    """
    http = session or requests
    yanit = http.get(
        TABAN + HAVZA_LISTESI_YOLU,
        headers={"TGT": tgt, "Accept": "application/json"},
        timeout=ZAMAN_ASIMI,
    )
    if yanit.status_code != 200:
        raise RuntimeError(f"EPİAŞ havza listesi HTTP {yanit.status_code}")
    return yanit.json()


def _kapasite_agirlikli_doluluk(
    aktif_hacimler: dict, kapasiteler: dict, havza_by_id: dict, havza: str | None
) -> float:
    """Saf: Σ(aktif hacim) / Σ(aktif kapasite) * 100 — istenirse tek havzaya
    süzülür (`havza=None` → Türkiye geneli, tüm barajlar).

    Kapasite ağırlıklı ortalama, her barajın doluluk yüzdesini kendi
    kapasitesiyle tartmakla matematiksel olarak özdeştir (doluluk% =
    hacim/kapasite*100 olduğundan); toplamları bölmek tek barajlık
    yuvarlama hatalarını biriktirmeden aynı sonucu verir.

    Kapasitesi (dam-volume'da) olmayan bir baraj varsa o baraj sessizce
    atlanır — hacmi olup kapasitesi olmayan bir baraj payda dışı kalırsa
    payı da dışarıda tutulmalı, aksi halde pay/payda tutarsızlaşır.
    """
    toplam_hacim = 0.0
    toplam_kapasite = 0.0
    for dam_id, hacim in aktif_hacimler.items():
        if havza is not None and havza_by_id.get(dam_id) != havza:
            continue
        kapasite = kapasiteler.get(dam_id)
        if kapasite is None:
            continue
        toplam_hacim += hacim
        toplam_kapasite += kapasite
    if toplam_kapasite <= 0:
        etiket = havza or "Türkiye geneli"
        raise RuntimeError(f"EPİAŞ baraj doluluk: '{etiket}' için kapasite verisi yok")
    return toplam_hacim / toplam_kapasite * 100


def baraj_doluluk_cek(
    seri: Seri, tgt: str, session: requests.Session | None = None,
    bugun: date | None = None, onbellek: dict | None = None,
) -> pd.DataFrame:
    """EPİAŞ'ın baraj doluluk ucundan CANLI anlık görüntüyü çeker.

    `seri_cek`teki pencereli-yeniden-çekme deseni burada UYGULANAMAZ:
    `active-volume`/`dam-volume` `date` gövde alanını yok sayar — canlı
    ölçümde 5 farklı tarihle (bugün, dün, ay başı, geçen yıl bugün) hepsi
    aynı "bugün" anlık görüntüsünü döndürdü. Bu yüzden bu fonksiyon TEK bir
    günlük satır döner; çok günlük geçmiş oluşturmak yalnızca bu fonksiyonu
    her gün ayrı çalıştırıp sonucu birikimli biçimde saklamakla mümkündür
    (mevcut `seriyi_yaz`in tam-üzerine-yazma sözleşmesiyle UYUŞMAZ — bu
    yüzden `ingest.run`'a henüz bağlanmadı; bkz. rapor).

    Türkiye geneli (kapasite ağırlıklı) = Σ(aktif hacim) / Σ(aktif kapasite)
    * 100 (`seri.epias_havza is None`); havza verilmişse yalnızca o
    havzanın barajları toplanır. Kapasite = maksimum işletme hacmi -
    minimum işletme hacmi (`dam-volume`); aktif hacim `active-volume`'dan.

    Aynı koşuda 18 seri (17 havza + ülke geneli) aynı iki uçtan aynı yanıtı
    paylaşır — `onbellek` verilirse (uretim/uretim-kompozisyon ile aynı
    desen) 36 istek yerine 2 istek yapılır.
    """
    bugun = bugun or date.today()
    http = session or requests
    govdeler = {}
    for anahtar, yol in (
        ("aktif_hacim", BARAJ_AKTIF_HACIM_YOLU), ("kapasite", BARAJ_HACIM_YOLU),
    ):
        if onbellek is not None and yol in onbellek:
            govdeler[anahtar] = onbellek[yol]
            continue
        yanit = http.post(
            TABAN + yol,
            headers={"Content-Type": "application/json", "TGT": tgt},
            json={"date": f"{bugun.isoformat()}T00:00:00+03:00"},
            timeout=ZAMAN_ASIMI,
        )
        if yanit.status_code != 200:
            raise RuntimeError(f"EPİAŞ HTTP {yanit.status_code} ({seri.id})")
        govde = yanit.json()
        govdeler[anahtar] = govde
        if onbellek is not None:
            onbellek[yol] = govde

    aktif_hacimler = {
        kayit["damId"]: float(kayit["activeVolume"])
        for kayit in govdeler["aktif_hacim"].get("items") or []
    }
    kapasiteler = {}
    havza_by_id = {}
    for kayit in govdeler["kapasite"].get("items") or []:
        havza_by_id[kayit["id"]] = kayit["basinName"]
        kapasiteler[kayit["id"]] = float(kayit["maxVolume"]) - float(kayit["minVolume"])
    if not aktif_hacimler:
        raise RuntimeError(f"EPİAŞ baraj doluluk boş döndü ({seri.id})")

    deger = _kapasite_agirlikli_doluluk(
        aktif_hacimler, kapasiteler, havza_by_id, seri.epias_havza
    )
    return pd.DataFrame({"date": [bugun.isoformat()], "value": [deger]})
