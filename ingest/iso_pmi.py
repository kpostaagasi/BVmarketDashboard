"""İSO (İstanbul Sanayi Odası) Türkiye Sektörel PMI + Türkiye İmalat PMI istemcisi.

Kaynak gerçekleri (canlı ölçüldü 2026-09-19, sıfırdan yeniden keşfetmeye
çalışmayın):

- İSO, S&P Global ile ortaklaşa İKİ AYRI aylık PDF raporu yayımlıyor; ikisi
  de ücretsiz, girişsiz, parola/API anahtarı gerektirmiyor:

  1) "Türkiye Sektörel PMI" — proje sayfası
     https://www.iso.org.tr/projeler/iso-turkiye-sektorel-pmi/. Sayfanın
     sunucu tarafında render edilen HTML'i (JS gerekmiyor, ölçüldü) bir
     "İstanbul Sanayi Odası Türkiye Sektörel PMI Raporları" indirme
     bağlantısı taşıyor (`/file/sektorel-PMI-<id>.zip`); bu ZIP SON ~12
     AYIN PDF raporunu içeriyor ve HER PDF KENDİ İÇİNDE son 6 ayın
     "Endeks Özeti" tablosunu taşıyor — dolayısıyla ZIP'teki dosyaları
     birleştirmek ~18 aya kadar tarihçe verir (ölçüldü: 2025.08–2026.08
     arası 11 dosya, aralarında 2025.10 eksik — TİM'in aylık bültenlerinde
     görülen "yayımlanmama" ile aynı doğa, sessizce atlanır).
  2) "Türkiye İmalat PMI" (manşet, tek rakamlı ulusal PMI) — proje sayfası
     https://www.iso.org.tr/projeler/iso-turkiye-imalat-pmi/, indirme
     bağlantısı `/file/PMI_turkiye-<id>.zip`. Bu ZIP SADECE SON 3 AYIN kısa
     ("_PR" = press release) bültenini taşır ve Sektörel PMI'nin aksine
     SAYISAL TABLO içermez — yalnızca başlık altındaki ilk cümleden manşet
     değeri ayrıştırılabilir (bkz. `_manset_degerini_ayikla`). Bu yüzden
     manşet PMI serisinin tarihçesi ZIP'teki dosya sayısıyla (3 ay) sınırlı
     kalır; Sektörel PMI'daki 6-ay-içi-tek-PDF avantajı burada YOK.

  Her iki ZIP'in dosya adı deseni de KARARSIZ (`.zip` dosya ID'si zamanla
  değişebilir, `TRSektörelPMI_YYYY.MM_TUR.pdf` içindeki Türkçe büyük İ bazı
  ay dosyalarında bozuk kodlanıyor — ör. `TRÿmalatPMI_2026.08_TUR_PR.pdf`).
  Bu yüzden URL'ler HER KOŞUDA proje sayfasından taze okunur (bkz.
  `ingest.worldbank.en_guncel_dosya_url` ile aynı desen) ve dosya eşleme
  yalnızca dosya adının SAYISAL kısmına (`\\d{4}\\.\\d{2}`) dayanır.

- "Endeks Özeti" tablosu (Sektörel PMI, ölçüldü Ağustos 2026 Gıda Ürünleri
  sayfası) 12 sütun taşır — sıra: PMI, Üretim, Yeni Siparişler, Yeni İhracat
  Siparişleri, Birikmiş İşler, İstihdam, Mal Stoku, Girdi Fiyatları, Ürün
  Fiyatları, Alım Miktarı, Teslim Süresi, Girdi Stoku. Satır biçimi
  `"MM-YY <12 Türkçe-ondalık sayı>"`.
  Referans platformun (marketvisuals) "Çıktı − Girdi Fiyatları" kartı =
  Ürün Fiyatları − Girdi Fiyatları (ölçüldü Ağustos 2026 Gıda: 52,2 − 64,7
  = −12,5, referans kart değeriyle birebir).
- 10 alt sektörün adı ve sırası İSO'nun proje sayfasında sabit listeleniyor
  (bkz. `SEKTOR_SIRASI`); PDF'teki fiziksel sayfa sırası da bunu izliyor
  ama eşleme sayfa İNDEKSİNE değil her sayfanın kendi başlığındaki sektör
  adına göre yapılıyor (bkz. `_sayfa_sektoru`) — daha dayanıklı.
- Manşet PMI'nin başlık cümlesi ay ay DEĞİŞİYOR ("PMI Haziran'da 47,1 olarak
  gerçekleşti" / "PMI 48,1 ile son üç ayın en yüksek düzeyine çıktı") ama
  ÜÇ ölçülen ayda da (2026-06/07/08) "PMI" kelimesinden sonraki İLK ondalık
  sayı her zaman cari ayın manşet değeriydi — S&P Global'in standart küresel
  PMI basın bülteni şablonunun (40+ ülke) parçası, tesadüfi değil.
"""

from __future__ import annotations

import io
import re
import zipfile

import pandas as pd
import pdfplumber
import requests

TABAN = "https://www.iso.org.tr"
SEKTOREL_PROJE_URL = f"{TABAN}/projeler/iso-turkiye-sektorel-pmi/"
MANSET_PROJE_URL = f"{TABAN}/projeler/iso-turkiye-imalat-pmi/"
ZAMAN_ASIMI = 60
_BASLIKLAR = {"User-Agent": "Mozilla/5.0"}

_ZIP_BAGLANTISI = re.compile(r'href="(/file/[^"]+\.zip)"')
_DOSYA_TARIHI = re.compile(r"(\d{4})\.(\d{2})")
_AY_SATIRI = re.compile(r"^(\d{2})-(\d{2})\s+(.+)$")
_SAYI = re.compile(r"^-?\d+,\d+$")
_MANSET_DEGER = re.compile(r"PMI[^\d]*?(\d+,\d+)")

# İSO'nun proje sayfasında (https://www.iso.org.tr/projeler/iso-turkiye-sektorel-pmi/)
# sabit listelenen 10 alt sektör; PDF sayfa başlıklarıyla birebir.
SEKTOR_SIRASI = (
    "Gıda Ürünleri",
    "Tekstil Ürünleri",
    "Giyim ve Deri Ürünleri",
    "Ağaç ve Kağıt Ürünleri",
    "Kimyasal, Plastik ve Kauçuk Ürünler",
    "Metalik Olmayan Mineral Ürünler",
    "Ana Metal Sanayi",
    "Makine ve Metal Ürünler",
    "Elektrikli ve Elektronik Ürünler",
    "Kara ve Deniz Taşıtları",
)

# "Endeks Özeti" tablosunun 12 sütunundan katalogda doğrudan seri olarak
# tutulan üçü (dördüncüsü — fiyat farkı — iki sütunun farkı, ayrı ele alınır).
METRIK_SUTUNU = {
    "pmi": 0,
    "yeni-siparisler": 2,
    "yeni-ihracat-siparisleri": 3,
}
GIRDI_FIYATLARI_SUTUNU = 7
URUN_FIYATLARI_SUTUNU = 8
GECERLI_METRIKLER = frozenset(METRIK_SUTUNU) | {"fiyat-farki"}


def _zip_baglantisini_bul(html_metni: str) -> str:
    eslesme = _ZIP_BAGLANTISI.search(html_metni)
    if not eslesme:
        raise RuntimeError(
            "İSO proje sayfasında .zip rapor bağlantısı bulunamadı — "
            "sayfa yapısı değişmiş olabilir"
        )
    return TABAN + eslesme.group(1)


def _zip_indir(proje_url: str, session=None) -> bytes:
    http = session or requests
    sayfa = http.get(proje_url, timeout=ZAMAN_ASIMI, headers=_BASLIKLAR)
    if sayfa.status_code != 200:
        raise RuntimeError(f"İSO proje sayfası HTTP {sayfa.status_code}: {proje_url}")
    zip_url = _zip_baglantisini_bul(sayfa.text)
    yanit = http.get(zip_url, timeout=ZAMAN_ASIMI, headers=_BASLIKLAR)
    if yanit.status_code != 200:
        raise RuntimeError(f"İSO ZIP indirilemedi HTTP {yanit.status_code}: {zip_url}")
    return yanit.content


def _pdf_dosyalarini_ayikla(zip_baytlari: bytes) -> list[tuple[tuple[int, int], bytes]]:
    """ZIP içindeki PDF'leri `(yıl, ay)` damgasına göre kronolojik sıralar.

    Dosya adının Türkçe kısmı bazı aylarda bozuk kodlanıyor (bkz. modül
    docstring'i) — yalnızca `\\d{4}\\.\\d{2}` deseni güvenilir kabul edilir.
    """
    sonuc = []
    with zipfile.ZipFile(io.BytesIO(zip_baytlari)) as z:
        for ad in z.namelist():
            if not ad.lower().endswith(".pdf"):
                continue
            eslesme = _DOSYA_TARIHI.search(ad)
            if not eslesme:
                continue
            yil, ay = int(eslesme.group(1)), int(eslesme.group(2))
            sonuc.append(((yil, ay), z.read(ad)))
    sonuc.sort(key=lambda t: t[0])
    return sonuc


def _sayfa_sektoru(sayfa_metni: str) -> str | None:
    """Sayfanın ilk birkaç satırından sektör başlığını bulur (sayfa
    indeksine değil, başlık METNİNE göre — kapak/genel bakış sayfaları
    hiçbir zaman ilk 6 satırda tam sektör adı taşımaz, ölçüldü)."""
    for satir in sayfa_metni.split("\n")[:6]:
        temiz = satir.strip()
        if temiz in SEKTOR_SIRASI:
            return temiz
    return None


def _satir_degerlerini_ayikla(sayfa_metni: str) -> dict[str, list[float]]:
    """`{"YYYY-MM-01": [12 değer]}` — sütun sırası `METRIK_SUTUNU` +
    `GIRDI_FIYATLARI_SUTUNU`/`URUN_FIYATLARI_SUTUNU` ile birebir."""
    sonuc: dict[str, list[float]] = {}
    for satir in sayfa_metni.split("\n"):
        eslesme = _AY_SATIRI.match(satir.strip())
        if not eslesme:
            continue
        ay, yil2, kalan = eslesme.groups()
        if not (1 <= int(ay) <= 12):
            continue
        sayilar_ham = kalan.split()
        if len(sayilar_ham) != 12 or not all(_SAYI.match(s) for s in sayilar_ham):
            continue
        tarih = f"20{yil2}-{ay}-01"
        sonuc[tarih] = [float(s.replace(",", ".")) for s in sayilar_ham]
    return sonuc


def sektorel_veriyi_topla(zip_baytlari: bytes) -> dict[str, dict[str, list[float]]]:
    """`{sektör: {tarih: [12 değer]}}` — ZIP'teki TÜM PDF'ler taranır;
    çakışan aylarda KRONOLOJİK OLARAK SONRAKİ dosya kazanır (revizyon
    yakalama; `_pdf_dosyalarini_ayikla` zaten eskiden yeniye sıralı döner)."""
    veri: dict[str, dict[str, list[float]]] = {ad: {} for ad in SEKTOR_SIRASI}
    dosyalar = _pdf_dosyalarini_ayikla(zip_baytlari)
    if not dosyalar:
        raise RuntimeError("İSO Sektörel PMI ZIP'inde PDF bulunamadı")
    for _, pdf_bayt in dosyalar:
        with pdfplumber.open(io.BytesIO(pdf_bayt)) as pdf:
            for sayfa in pdf.pages:
                metin = sayfa.extract_text() or ""
                sektor = _sayfa_sektoru(metin)
                if sektor is None:
                    continue
                veri[sektor].update(_satir_degerlerini_ayikla(metin))
    eksik = [s for s in SEKTOR_SIRASI if not veri[s]]
    if eksik:
        raise RuntimeError(
            "İSO Sektörel PMI şablonu değişmiş olabilir — hiç veri "
            f"bulunamayan sektör(ler): {', '.join(eksik)}"
        )
    return veri


def _manset_degerini_ayikla(sayfa0_metni: str) -> float:
    for satir in sayfa0_metni.split("\n")[:4]:
        eslesme = _MANSET_DEGER.search(satir)
        if eslesme:
            return float(eslesme.group(1).replace(",", "."))
    raise RuntimeError(
        "İSO Türkiye İmalat PMI basın bülteninde manşet değer satırı "
        "bulunamadı — şablon değişmiş olabilir"
    )


def manset_veriyi_topla(zip_baytlari: bytes) -> dict[str, float]:
    """`{tarih: manşet PMI}` — her PDF kendi ayının TEK değerini verir
    (Sektörel PMI'nin aksine çoklu-ay tablosu yok, bkz. modül docstring'i);
    pencere derinliği ZIP'teki dosya sayısıyla (ölçüldü: 3 ay) sınırlıdır."""
    veri: dict[str, float] = {}
    dosyalar = _pdf_dosyalarini_ayikla(zip_baytlari)
    if not dosyalar:
        raise RuntimeError("İSO Türkiye İmalat PMI ZIP'inde PDF bulunamadı")
    for (yil, ay), pdf_bayt in dosyalar:
        with pdfplumber.open(io.BytesIO(pdf_bayt)) as pdf:
            metin = pdf.pages[0].extract_text() or ""
        veri[f"{yil:04d}-{ay:02d}-01"] = _manset_degerini_ayikla(metin)
    return veri


def _sektorel_onbellegi_getir(onbellek: dict, session=None) -> dict[str, dict[str, list[float]]]:
    if "sektorel" not in onbellek:
        zip_baytlari = _zip_indir(SEKTOREL_PROJE_URL, session=session)
        onbellek["sektorel"] = sektorel_veriyi_topla(zip_baytlari)
    return onbellek["sektorel"]


def _manset_onbellegi_getir(onbellek: dict, session=None) -> dict[str, float]:
    if "manset" not in onbellek:
        zip_baytlari = _zip_indir(MANSET_PROJE_URL, session=session)
        onbellek["manset"] = manset_veriyi_topla(zip_baytlari)
    return onbellek["manset"]


def seri_cek(seri, *, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """`iso_pmi_sektor` verilmemişse (None) manşet Türkiye İmalat PMI;
    verilmişse Sektörel PMI'nin `iso_pmi_metrik` sütunu (`fiyat-farki` iki
    sütunun farkı olarak hesaplanır, bkz. modül docstring'i)."""
    onbellek = {} if onbellek is None else onbellek

    if seri.iso_pmi_sektor is None:
        if seri.iso_pmi_metrik != "pmi":
            raise RuntimeError(
                f"{seri.id}: manşet PMI serisi yalnızca iso_pmi_metrik='pmi' destekler"
            )
        veri = _manset_onbellegi_getir(onbellek, session=session)
        noktalar = sorted(veri.items())
    else:
        if seri.iso_pmi_sektor not in SEKTOR_SIRASI:
            raise RuntimeError(f"{seri.id}: bilinmeyen iso_pmi_sektor {seri.iso_pmi_sektor!r}")
        sektorel = _sektorel_onbellegi_getir(onbellek, session=session)
        sektor_verisi = sektorel[seri.iso_pmi_sektor]
        if seri.iso_pmi_metrik == "fiyat-farki":
            noktalar = sorted(
                (tarih, degerler[URUN_FIYATLARI_SUTUNU] - degerler[GIRDI_FIYATLARI_SUTUNU])
                for tarih, degerler in sektor_verisi.items()
            )
        elif seri.iso_pmi_metrik in METRIK_SUTUNU:
            sutun = METRIK_SUTUNU[seri.iso_pmi_metrik]
            noktalar = sorted((tarih, degerler[sutun]) for tarih, degerler in sektor_verisi.items())
        else:
            raise RuntimeError(f"{seri.id}: bilinmeyen iso_pmi_metrik {seri.iso_pmi_metrik!r}")

    if not noktalar:
        raise RuntimeError(f"{seri.id}: İSO PMI için veri noktası bulunamadı")
    df = pd.DataFrame(noktalar, columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)
