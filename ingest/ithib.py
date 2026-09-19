"""İTHİB (İstanbul Tekstil ve Hammaddeleri İhracatçıları Birliği) aylık
"Tekstil İhracat Değerlendirme Notu" PDF istemcisi.

Kaynak XLSX/HTML tablo değil — her ay yayımlanan bir PDF bülten
(`https://www.ithib.org.tr/bilgi-merkezi/istatistikler-raporlar/kategori/
aylik-ihracat-degerlendirme-bilgi-notlari-7` liste sayfasından bağlantı
alınır; dosya URL'i tahmin edilemeyen bir depolama kimliği taşıyor, ör.
`.../storage/38000/Tekstil-İhracat-Değerlendirme-Notu---2026-Ağustos-
Ayı.pdf` — bu yüzden ay→URL eşlemesi liste sayfasından KAZINIR, TİM'in
deterministik URL'lerinin aksine).

Bültenin "Ürün Grubu Bazında Tekstil Sektörü İhracatı" sayfasında YEDİ
ürün grubu (İplik, Teknik Tekstil, Dokuma Kumaş, Ev Tekstili, Örme
Kumaş, Elyaf, Konfeksiyon Yan Sanayi) için gruplu çubuk grafik var; her
grup İKİ değer taşır (aynı ay ÖNCEKİ yıl + BU yıl). Tablo YOK — çubuk
üstü sayı ETİKETLERİ `pdfplumber.extract_words()` ile KONUM tabanlı
okunuyor:
- Kategori etiketleri sabit bir "top" bandında (≈398-424, bazıları iki
  satırlı: "DOKUMA" + "KUMAŞ") — birbirine yakın (< 15pt) kelimeler AYNI
  kategoriye birleştirilir, x0-x1 aralığı o kategorinin sütun sınırını
  verir.
- Sayı etiketleri kategori bandının ÜSTÜNDE (top 95-375, grafik ekseni
  sabit olduğu için ay bağımsız) — her sayı,
  MERKEZ x'i (x0+x1)/2 en yakın kategori sınırına göre o kategoriye
  atanır (y-ekseni tik değerleri (250/200/150/.../0) kategorilerin SOL
  sınırından daha solda kaldığı için hariç tutulur).
- Kategori içinde SOL taraftaki sayı ÖNCEKİ yıl (aynı ay), SAĞ taraftaki
  BU YIL'dır (ölçüldü: standart gruplu çubuk grafik solda-eskiyi-önce
  çizim sırası, 2026-08 bülteninde İPLİK için sol=179 (2025 Ağustos),
  sağ=199 (2026 Ağustos) — marketvisuals'ın prevVal/latestVal
  alanlarıyla birebir eşleşiyor).

Her PDF İKİ nokta verir (bu ay + aynı ay bir önceki yıl) — TİM'in
"tek dosya = tüm geçmiş" ya da "tek dosya = kayan pencere" desenlerinin
İKİSİ de YOK. Bu yüzden liste sayfasındaki HER ayın kendi PDF'i çekilir
(TİM'in il/ülke bültenleriyle aynı "ay başına dosya" deseni) ve her
PDF'ten İKİ nokta (bu ay + 12 ay önceki karşılığı) toplanır — N ay
çekilirse ~2N aylık nokta elde edilir. Liste sayfası sayfalama/filtre
şeması karmaşık (yıl bazlı "years=" parametresi + sayfa numarası
birbirine bağlı, ölçüldü) ve tam çözülmedi; bu adaptör yalnızca
VARSAYILAN (parametresiz) liste sayfasının gösterdiği pencereyle
sınırlıdır (ölçüldü 2026-09-18: canlı Ağustos 2026'dan Eylül 2025'e 11
ay) — bu, ~22 aylık (2024-09'dan 2026-08'e) bir seri üretir.

"Tekstil Sektörü Toplam İhracat" (agregе) bu sayfada YOK; farklı bir
sayfadaki ("Aylar Bazında Tekstil Sektörü İhracatı") çubuk grafiğin
KENDİ etiket düzeni ölçülmedi ve yedi ürün grubunun toplamı bu değere
eşit DEĞİL (ölçüldü: 2026-08 için 7 grup toplamı 991, gerçek toplam
944 — kategoriler ayrık değil / örtüşüyor) — bilinçli olarak kapsam
dışı bırakıldı (bkz. görev raporundaki `bloke`).
"""

from __future__ import annotations

import io
import re
from html import unescape

import pandas as pd
import pdfplumber
import requests

LISTE_URL = "https://www.ithib.org.tr/bilgi-merkezi/istatistikler-raporlar/kategori/aylik-ihracat-degerlendirme-bilgi-notlari-7"
ZAMAN_ASIMI = 60

AY_ADLARI = {
    "Ocak": 1, "Şubat": 2, "Mart": 3, "Nisan": 4, "Mayıs": 5, "Haziran": 6,
    "Temmuz": 7, "Ağustos": 8, "Eylül": 9, "Ekim": 10, "Kasım": 11, "Aralık": 12,
}

KALEM_IPLIK = "iplik"
KALEM_TEKNIK_TEKSTIL = "teknik-tekstil"
KALEM_DOKUMA_KUMAS = "dokuma-kumas"
KALEM_EV_TEKSTILI = "ev-tekstili"
KALEM_ORME_KUMAS = "orme-kumas"
KALEM_ELYAF = "elyaf"
KALEM_KONFEKSIYON_YAN_SANAYI = "konfeksiyon-yan-sanayi"

GECERLI_ITHIB_KALEMLERI = {
    KALEM_IPLIK, KALEM_TEKNIK_TEKSTIL, KALEM_DOKUMA_KUMAS, KALEM_EV_TEKSTILI,
    KALEM_ORME_KUMAS, KALEM_ELYAF, KALEM_KONFEKSIYON_YAN_SANAYI,
}

# PDF'teki (BÜYÜK harfli, çok satırlı olabilen) kategori etiketi -> katalog kalemi.
_ETIKET_KALEM = {
    "İPLİK": KALEM_IPLIK,
    "TEKNİK TEKSTİL": KALEM_TEKNIK_TEKSTIL,
    "DOKUMA KUMAŞ": KALEM_DOKUMA_KUMAS,
    "EV TEKSTİLİ": KALEM_EV_TEKSTILI,
    "ÖRME KUMAŞ": KALEM_ORME_KUMAS,
    "ELYAF": KALEM_ELYAF,
    "KONFEKSİYON YAN SANAYİ": KALEM_KONFEKSIYON_YAN_SANAYI,
}
assert set(_ETIKET_KALEM.values()) == GECERLI_ITHIB_KALEMLERI

_LISTE_DESENI = re.compile(
    r'<a href="([^"]+\.pdf)"[^>]*>\s*<h3[^>]*>\s*'
    r'Tekstil İhracat Değerlendirme Notu - (\d{4}) ([A-Za-zÇŞĞÜÖİçşğüöı]+) Ayı\s*</h3>',
    re.DOTALL,
)


def liste_baglantilarini_cek(html: str) -> dict[tuple[int, int], str]:
    """Liste sayfasından `{(yıl, ay): pdf_url}` çıkarır.

    Dosya URL'i tahmin edilemeyen bir depolama kimliği taşıdığı için
    (bkz. modül docstring'i) bu KAZIMA zorunlu — TİM'in deterministik
    URL kalıbı burada yok.
    """
    sonuc: dict[tuple[int, int], str] = {}
    for url, yil_metni, ay_adi in _LISTE_DESENI.findall(html):
        if ay_adi not in AY_ADLARI:
            raise RuntimeError(f"İTHİB: liste sayfasında bilinmeyen ay adı: {ay_adi!r}")
        sonuc[(int(yil_metni), AY_ADLARI[ay_adi])] = unescape(url)
    if not sonuc:
        raise RuntimeError("İTHİB: liste sayfasında hiç rapor bağlantısı bulunamadı — sayfa yapısı değişmiş olabilir")
    return sonuc


_AYLAR_DESENI = "|".join(AY_ADLARI)
_TEK_AY_LEJANTI = re.compile(
    rf"(\d{{4}})\s+({_AYLAR_DESENI})\s+(\d{{4}})\s+({_AYLAR_DESENI})\b"
)


def _urun_grubu_sayfasini_bul(pdf: pdfplumber.PDF, beklenen_ay_adi: str):
    """"Ürün Grubu Bazında Tekstil Sektörü İhracatı" grafiğinin TEK AYLIK
    (çeyrek/kümülatif değil) karşılaştırma sayfasını bulur.

    Bazı aylarda (çeyrek sonu: Mart/Haziran/Eylül/Aralık) bültende AYNI
    başlıklı bir "Ocak-<Ay> Dönemi" kümülatif sayfa da yer alıyor
    (ölçüldü: 2026-03 bülteninde sayfa 12 "2025 Ocak-Mart 2026
    Ocak-Mart" kümülatif, sayfa 13 "2025 Mart 2026 Mart" tek aylık) —
    bu yüzden alt başlık metin eşleşmesi (bazı çeyrek baskılarında hiç
    yok, ölçüldü) yerine LEJANT satırındaki "<yıl> <ay> <yıl> <ay>"
    örüntüsü kullanılır: aynı ay adı TİRESİZ iki kez geçmeli (bir aralık
    olan "Ocak-Mart" tek kelime olarak eşleşmeyeceğinden kümülatif
    sayfa doğal olarak elenir).
    """
    for sayfa in pdf.pages:
        metin = sayfa.extract_text() or ""
        if "ÜRÜN GRUBU BAZINDA TEKSTİL SEKTÖRÜ İHRACATI" not in metin:
            continue
        eslesme = _TEK_AY_LEJANTI.search(metin)
        if eslesme and eslesme.group(2) == eslesme.group(4) == beklenen_ay_adi:
            return sayfa
    raise RuntimeError(
        "İTHİB: 'Ürün Grubu Bazında Tekstil Sektörü İhracatı' tek aylık karşılaştırma "
        f"sayfası bulunamadı (beklenen ay: {beklenen_ay_adi}) — bülten şablonu değişmiş olabilir"
    )


_KATEGORI_KELIMELERI = {
    "İPLİK", "TEKNİK", "TEKSTİL", "DOKUMA", "KUMAŞ", "EV", "TEKSTİLİ",
    "ÖRME", "ELYAF", "KONFEKSİYON", "YAN", "SANAYİ",
}


def _kategorileri_bul(sayfa) -> list[tuple[str, float, float]]:
    """Kategori etiketlerini (çok satırlı olabilen) birleştirip
    `[(BÜYÜK_ETİKET, x0, x1), ...]` döner (bkz. modül docstring'i).

    Etiket satırının düşey konumu (`top`) aya göre kayar (çubuk
    yüksekliği grafiğin toplam ölçeğini değiştirir) — bu yüzden sabit
    bir "top" bandı yerine bilinen kategori kelimelerinin GEÇTİĞİ en
    kalabalık satır (mod) bulunur; bu satırın altına (~30pt) sarkan
    ikinci satır kelimeleri (örn. "DOKUMA" altında "KUMAŞ") de dahil
    edilir.
    """
    adaylar = [k for k in sayfa.extract_words() if k["text"] in _KATEGORI_KELIMELERI]
    if not adaylar:
        raise RuntimeError("İTHİB: sayfada kategori etiketi bulunamadı")
    tepeler = [round(k["top"]) for k in adaylar]
    ana_tepe = max(set(tepeler), key=tepeler.count)
    kelimeler = [k for k in adaylar if ana_tepe - 2 <= k["top"] <= ana_tepe + 30]
    kelimeler.sort(key=lambda k: k["x0"])
    gruplar: list[list[dict]] = []
    for k in kelimeler:
        if gruplar and k["x0"] - gruplar[-1][-1]["x1"] < 15:
            gruplar[-1].append(k)
        else:
            gruplar.append([k])
    kategoriler = []
    for g in gruplar:
        etiket = " ".join(k["text"] for k in sorted(g, key=lambda k: (k["top"], k["x0"])))
        kategoriler.append((etiket, min(k["x0"] for k in g), max(k["x1"] for k in g)))
    beklenen = set(_ETIKET_KALEM)
    bulunan = {ad for ad, _, _ in kategoriler}
    if bulunan != beklenen:
        raise RuntimeError(
            f"İTHİB: kategori etiketleri beklenenle uyuşmuyor — bulunan: {sorted(bulunan)}, "
            f"beklenen: {sorted(beklenen)}"
        )
    return sorted(kategoriler, key=lambda t: t[1])


def _degerleri_ayikla(
    sayfa, kategoriler: list[tuple[str, float, float]], anahtar: str
) -> dict[str, tuple[float, float]]:
    """Her kategori için `(önceki_yıl_değeri, bu_yıl_değeri)` döner."""
    sol_sinir = min(x0 for _, x0, _ in kategoriler) - 30
    kelimeler = [
        k for k in sayfa.extract_words()
        if 95 <= k["top"] <= 375 and re.fullmatch(r"-?\d+(?:\.\d+)?", k["text"]) and k["x0"] > sol_sinir
    ]
    merkezler = [(x0 + x1) / 2 for _, x0, x1 in kategoriler]
    sinirlar = [(merkezler[i] + merkezler[i + 1]) / 2 for i in range(len(merkezler) - 1)]

    kova: dict[str, list[dict]] = {}
    for k in kelimeler:
        merkez = (k["x0"] + k["x1"]) / 2
        indeks = sum(1 for s in sinirlar if merkez > s)
        kova.setdefault(kategoriler[indeks][0], []).append(k)

    sonuc: dict[str, tuple[float, float]] = {}
    for etiket, _x0, _x1 in kategoriler:
        degerler = sorted(kova.get(etiket, []), key=lambda k: k["x0"])
        if len(degerler) != 2:
            raise RuntimeError(
                f"İTHİB {anahtar}: '{etiket}' için 2 değer bekleniyor, {len(degerler)} bulundu: "
                f"{[d['text'] for d in degerler]}"
            )
        sonuc[etiket] = (float(degerler[0]["text"]), float(degerler[1]["text"]))
    return sonuc


_AY_ADLARI_TERS = {v: k for k, v in AY_ADLARI.items()}


def bulteni_ayikla(baytlar: bytes, yil: int, ay: int) -> dict[str, tuple[float, float]]:
    """Bir bültenden `{kalem: (önceki_yıl_değeri, bu_yıl_değeri)}` çıkarır (Milyon USD)."""
    beklenen_ay_adi = _AY_ADLARI_TERS[ay]
    with pdfplumber.open(io.BytesIO(baytlar)) as pdf:
        sayfa = _urun_grubu_sayfasini_bul(pdf, beklenen_ay_adi)
        kategoriler = _kategorileri_bul(sayfa)
        ham = _degerleri_ayikla(sayfa, kategoriler, f"{yil}.{ay:02d}")
    return {_ETIKET_KALEM[etiket]: deger for etiket, deger in ham.items()}


def _liste_cek(onbellek: dict, session=None) -> dict[tuple[int, int], str]:
    if "liste" in onbellek:
        return onbellek["liste"]
    http = session or requests
    yanit = http.get(LISTE_URL, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"İTHİB HTTP {yanit.status_code} (liste sayfası)")
    liste = liste_baglantilarini_cek(yanit.text)
    onbellek["liste"] = liste
    return liste


def _bulteni_getir(yil: int, ay: int, url: str, onbellek: dict, session=None) -> dict[str, tuple[float, float]]:
    anahtar = (yil, ay)
    if anahtar in onbellek:
        return onbellek[anahtar]
    http = session or requests
    yanit = http.get(url, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"İTHİB HTTP {yanit.status_code} ({url})")
    sonuc = bulteni_ayikla(yanit.content, yil, ay)
    onbellek[anahtar] = sonuc
    return sonuc


def seri_cek(seri, *, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """Liste sayfasındaki HER ayın bülteninden tek bir ürün grubunun
    serisini çeker; her bülten İKİ noktaya (bu ay + 12 ay önceki karşılığı)
    katkı yapar (bkz. modül docstring'i).
    """
    if seri.ithib_kalem not in GECERLI_ITHIB_KALEMLERI:
        raise RuntimeError(f"İTHİB: bilinmeyen kalem '{seri.ithib_kalem}'")

    onbellek = {} if onbellek is None else onbellek
    liste = _liste_cek(onbellek, session)

    noktalar: dict[str, float] = {}
    for (yil, ay), url in liste.items():
        sonuc = _bulteni_getir(yil, ay, url, onbellek, session)
        onceki, bu_yil = sonuc[seri.ithib_kalem]
        noktalar[f"{yil}-{ay:02d}-01"] = bu_yil
        noktalar[f"{yil - 1}-{ay:02d}-01"] = onceki

    if not noktalar:
        raise RuntimeError(f"İTHİB: '{seri.ithib_kalem}' için hiç veri toplanamadı")

    tarihler = sorted(t for t in noktalar if seri.start_date is None or t >= seri.start_date)
    df = pd.DataFrame({"date": tarihler, "value": [noktalar[t] for t in tarihler]})
    return df.reset_index(drop=True)
