"""İstanbul Ticaret Borsası (İTB) haftalık tescil bülteni istemcisi.

Kaynak: `https://bulten.istib.org.tr/Default/BultenlerAlt` — borsanın haftalık
tescil bültenini (ürün tesciline dayalı alım-satım işlemlerinin borsa
kaydı) döndüren sunucu taraflı AJAX ucu. Sayfa
`https://bulten.istib.org.tr/` üzerindeki "Tescil Bültenleri" formu bu ucu
şu JS ile çağırıyor (ölçüldü 2026-09-18, `Default/BultenlerAlt` ile aynı
origin):

    $("#partial").load('.../Default/BultenlerAlt?tur=' + tur +
        "&Yil=" + yil + "&ay=" + ay + "&gun=" + gun + "&hafta=" + hafta +
        "&ilkgun=" + ilkgun + "&songun=" + songun);

`tur=2` "Haftalık Bülten" seçer; `hafta` o haftanın PAZARTESİ tarihidir
(`YYYY-MM-DD`, seçenek listesinde "14.09.2026 - 18.09.2026" gibi
gösteriliyor, value="2026-09-14"). Sunucu `ay`/`Yil`/`gun`/`ilkgun`/`songun`
boş string geldiğinde ASP.NET tarih ayrıştırma hatasıyla 500 döndürüyor
(ölçüldü) — JS bunları hiç temizlemediği (yalnızca CSS ile gizlediği) için
tarayıcıda hep dolu gider; bu adaptör de aynı şekilde TÜM parametreleri
hedef haftanın değerleriyle doldurur.

Yanıt, borsanın o haftaki TÜM tescilli ürünlerini "Cins ve Nev'leri" grup
başlıkları altında listeleyen tam bir HTML tablosudur (`id="tablo"`).
"KÜMES HAYVANI ETİ" grubu altında hedef 4 ürün satır olarak görünür — ama
yalnızca o hafta gerçekten işlem GÖRMÜŞSE (borsa sıfır işlemli satırı hiç
yazmıyor, EPDK'nın sıfır satırı dinamik atmasıyla aynı desen, bkz.
`epdk.py` docstring'i): bazı haftalarda satır hiç yok, bazı haftalarda AYNI
ürün birden çok "cins" (ör. "(HTS)" vadeli/peşin, "(HTA)") satırı olarak
tekrar edebilir. `seri_cek` bu yüzden bir ürünün o haftaki TÜM satırlarını
Tutar/Miktar ağırlıklı ortalamayla tek noktaya indirger (`urun_agirlikli_fiyat`).

Referans doğrulaması (ölçüldü 2026-09-18, hafta=2026-09-07): "HİNDİ ETİ
KEMİKLİ (HTS)" Ortalama Fiyat 237,69 TL/kg ve "PİLİÇ KANAT (HTS)" 460,00
TL/kg, commodity_poultry.html kartlarıyla BİREBİR eşleşti. "PİLİÇ ETİ
KEMİKSİZ" için haftalık okuma (143,69 / 177,25 — hafta yorumuna göre)
referansın 149,5 değeriyle tam örtüşmedi; muhtemel neden referansın birden
çok haftayı/cinsi farklı ağırlıklandırması — üç ürün birebir eşleştiği için
kaynak doğru kabul edildi, dördüncüsü olduğu gibi (ağırlıklı ortalama)
bırakıldı.

Sayılar Türkçe biçimde gelir (`1.234,56`) — TUTAR/MİKTAR ayrıştırması bunu
`ondalik_cevir` ile çözer. HTML yanıtı entity-kodlu (`&#199;` = Ç) geliyor;
`html.unescape` olmadan ürün adı eşleşmesi Türkçe karakterlerde sessizce
başarısız olur.
"""

from __future__ import annotations

import html as html_modul
import re
from datetime import date, timedelta

import pandas as pd
import requests

from core.catalog import GECERLI_ISTIB_URUNLERI, Seri

UC = "https://bulten.istib.org.tr/Default/BultenlerAlt"
ZAMAN_ASIMI = 60

# Bültendeki taban ürün adı -> katalogdaki `istib_urun` (GECERLI_ISTIB_
# URUNLERI ile birebir eşleşmeli). Satırdaki parantez içi cins eki
# ("(HTS)", "(Vadeli Kg HTA)" gibi) `_taban_ad` ile atılır.
URUN_ESLEME = {
    "PİLİÇ ETİ KEMİKSİZ": "piliç-eti-kemiksiz",
    "HİNDİ ETİ KEMİKLİ": "hindi-eti-kemikli",
    "HİNDİ ETİ KEMİKSİZ": "hindi-eti-kemiksiz",
    "PİLİÇ KANAT": "piliç-kanat",
}
assert set(URUN_ESLEME.values()) == GECERLI_ISTIB_URUNLERI

GRUP_BASLIGI = "KÜMES HAYVANI ETİ"
# Backfill penceresi: borsa geçmişi en az 2017'ye gider ama her hafta ağır
# bir HTML sayfası (~300KB) gerektirir; iki yıllık pencere (104 hafta)
# mevsimsellik/YoY göstermeye yeter ve koşu süresini makul tutar (bkz.
# `bddk.py`'nin ~14 aylık AZAMI_GERI_AY kısıtıyla aynı gerekçe).
AZAMI_GERI_HAFTA = 104

_SATIR_RE = re.compile(
    r'<td[^>]*>\s*([A-ZÇĞİÖŞÜ][^<]*?)\s*</td>\s*'
    r'<td[^>]*>[^<]*</td>\s*'  # Muamele Adedi + cins (ör. "5 Vadeli")
    r'<td[^>]*>([\d.,]+)</td>\s*'  # En Az Fiyat
    r'<td[^>]*>([\d.,]+)</td>\s*'  # En Çok
    r'<td[^>]*>([\d.,]+)</td>\s*'  # Ortalama Fiyat
    r'<td[^>]*>([\d.,]+)</td>\s*'  # Miktar
    r'<td[^>]*>([^<]*)</td>\s*'  # Birim
    r'<td[^>]*>([\d.,]+)</td>',  # Tutar (TL)
)


def ondalik_cevir(ham: str) -> float:
    """Türkçe biçimi (`1.234,56`) `float`'a çevirir."""
    return float(ham.strip().replace(".", "").replace(",", "."))


def _taban_ad(satir_adi: str) -> str:
    """Satırın parantez içi cins ekini atar: 'PİLİÇ KANAT (HTS)' -> 'PİLİÇ KANAT'."""
    return re.sub(r"\s*\([^)]*\)?\s*$", "", satir_adi).strip()


def kumes_hayvani_satirlarini_cikar(yanit_html: str) -> dict[str, list[dict]]:
    """Bültenin `KÜMES HAYVANI ETİ` grubundan hedef 4 ürünün satırlarını çıkarır.

    Dönüş: `{istib_urun: [{"ortalama": float, "miktar": float}, ...]}` — bir
    üründen o hafta birden çok cins satırı varsa liste birden fazla eleman
    taşır (ağırlıklı ortalama `urun_agirlikli_fiyat` içinde alınır). Bültenin
    kendi "Ortalama Fiyat" sütunu kullanılır — bu, Tutar/Miktar'a EŞİT
    DEĞİLDİR (ölçüldü: HİNDİ ETİ KEMİKLİ HTS 2026-09-07 haftası Ortalama
    237,69 iken Tutar/Miktar 258,61 çıkıyor — borsa büyük olasılıkla işlem
    bazlı basit ortalama kullanıyor, hacim ağırlıklı değil); referans
    kartların 237,69/326,93/460,00 değerleriyle birebir eşleşen sütun bu
    yüzden doğrudan "Ortalama Fiyat", Tutar/Miktar değil.
    """
    metin = html_modul.unescape(yanit_html)
    baslangic = metin.find(GRUP_BASLIGI)
    if baslangic < 0:
        return {}
    # Bir sonraki grup başlığına (`group-title` div'i) ya da tablo sonuna kadar.
    sonraki = metin.find('class="group-title"', baslangic + len(GRUP_BASLIGI))
    blok = metin[baslangic:sonraki] if sonraki > 0 else metin[baslangic:]

    sonuc: dict[str, list[dict]] = {}
    for satir_adi, _en_az, _en_cok, ortalama, miktar, _birim, _tutar in _SATIR_RE.findall(blok):
        taban = _taban_ad(satir_adi)
        istib_urun = URUN_ESLEME.get(taban)
        if istib_urun is None:
            continue  # borsanın izlediği ama kartlarımızın kapsamadığı bir ürün
        sonuc.setdefault(istib_urun, []).append({
            "ortalama": ondalik_cevir(ortalama),
            "miktar": ondalik_cevir(miktar),
        })
    return sonuc


def urun_agirlikli_fiyat(satirlar: list[dict]) -> float:
    """Bir ürünün o haftaki (birden çok cins olabilen) satırlarını, her
    satırın KENDİ Ortalama Fiyatını Miktar ile ağırlıklandırarak tek fiyata
    indirger. Tek satırlı (çoğunluk) haftada bu doğrudan o satırın Ortalama
    Fiyatına eşittir."""
    toplam_miktar = sum(s["miktar"] for s in satirlar)
    if toplam_miktar <= 0:
        raise RuntimeError("İTB: sıfır miktarlı satırdan ağırlıklı fiyat hesaplanamaz")
    return sum(s["ortalama"] * s["miktar"] for s in satirlar) / toplam_miktar


def pazartesileri_uret(bugun: date, adet: int = AZAMI_GERI_HAFTA) -> list[date]:
    """`bugun`den geriye, en son geçmiş Pazartesi dahil, `adet` haftalık Pazartesi."""
    son_pazartesi = bugun - timedelta(days=bugun.weekday())
    return [son_pazartesi - timedelta(weeks=i) for i in range(adet)][::-1]


def haftalik_bulten_cek(pazartesi: date, session=None) -> str:
    http = session or requests
    parametreler = {
        "tur": "2",
        "Yil": str(pazartesi.year),
        "ay": f"{pazartesi.year}-{pazartesi.month}",
        "gun": pazartesi.isoformat(),
        "hafta": pazartesi.isoformat(),
        "ilkgun": pazartesi.isoformat(),
        "songun": pazartesi.isoformat(),
    }
    yanit = http.get(UC, params=parametreler, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"İTB HTTP {yanit.status_code} (hafta={pazartesi})")
    return yanit.text


def _tum_noktalari_getir(onbellek: dict, bugun: date, session=None) -> dict[str, list[tuple[str, float]]]:
    """Tüm hafta pencerelerini bir kez çeker; 4 ürün aynı haftalık bülteni paylaşır."""
    if "noktalar" in onbellek:
        return onbellek["noktalar"]

    noktalar: dict[str, list[tuple[str, float]]] = {urun: [] for urun in GECERLI_ISTIB_URUNLERI}
    for pazartesi in pazartesileri_uret(bugun):
        yanit_html = haftalik_bulten_cek(pazartesi, session=session)
        urun_satirlari = kumes_hayvani_satirlarini_cikar(yanit_html)
        for istib_urun, satirlar in urun_satirlari.items():
            fiyat = urun_agirlikli_fiyat(satirlar)
            noktalar[istib_urun].append((pazartesi.isoformat(), fiyat))

    onbellek["noktalar"] = noktalar
    return noktalar


def seri_cek(seri: Seri, onbellek: dict | None = None, session: requests.Session | None = None,
             bugun: date | None = None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `date` o haftanın Pazartesi'sidir; ürün o hafta hiç işlem görmediyse
    satır yoktur (borsa sıfır satırı yazmadığından sessizce atlanır, sıfır
    değer YAZILMAZ).
    """
    if onbellek is None:
        onbellek = {}
    bugun = bugun or date.today()

    tum_noktalar = _tum_noktalari_getir(onbellek, bugun, session=session)
    noktalar = tum_noktalar.get(seri.istib_urun, [])
    if not noktalar:
        raise RuntimeError(f"İTB: '{seri.istib_urun}' için hiç veri yok (pencere: {AZAMI_GERI_HAFTA} hafta)")

    df = pd.DataFrame(noktalar, columns=["date", "value"])
    return df.reset_index(drop=True)
