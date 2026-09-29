"""MKK Aylık Piyasa Bülteni yatırımcı/hesap sayısı istemcisi.

Kaynak gerçekleri 2026-09-29'da canlı ölçüldü (sıfırdan yeniden keşfetmeye
çalışmayın):

- **Doğru alan adı `www.mkk.com.tr`**. `www.mkk.gov.tr` ve `mkk.gov.tr` DNS'te
  YOK (ENOTFOUND). Yatırımcı/piyasa verisinin tamamı MKK'nın kendi Drupal
  sitesinde: bülten listesi `LISTE_SAYFASI`'nın DÜZ HTML'inde, JS'siz —
  `a[href$=".pdf"]` bağlantıları olarak gömülü. Ölçüldü: 2026-09-29'da listede
  **20 bülten**, Ocak 2025 → Ağustos 2026 arası (ay boşluğu YOK), sayfalama
  YOK. Dosya adı/ay klasörü **TÜRETİLEMEZ** (`Eylul.pdf` klasörsüz,
  `Aralik-2025_0.pdf`, `Temmuz-2025-1.pdf`), bu yüzden yalnızca kapaktan
  okunan `(<AY> <YYYY>)` tarihi kullanılır.
- **Her sayı GRAFİK ÜZERİNDE, tablo YOK.** Değerler PDF'in vektör
  grafiğine `pdfplumber` tarafından ~69°/90° DÖNDÜRÜLMÜŞ, harf harf (her
  `char` ayrı) olarak çizilmiştir. Sayfa metni (`extract_text`) bu yüzden
  okunamaz; ayrıştırma karakter KOORDİNATLARINDAN yapılır:
  - Değer etiketleri ~69°-90° arası döndürülmüş karakterlerdir (`char.matrix`
    0,1 bileşenlerinin açısı). Aynı sayfadaki diğer metinler 0° (yatay başlıklar,
    yatay y ekseni tık rakamları) veya 45° (x ekseni tarihleri) — hepsi
    dışlanır. Ölçüldü: Ağustos 2026 bülteninin sayfa 3'ündeki karakterler
    yalnızca 0° (415), 68,9° (260) ve 45° (130).
  - Bir etiket tek bir dikey dizidir: `x0` artarken `top` AZALIR. Etiketler
    önce 8pt'ten büyük `x0` boşluğuyla kümelenir (etiket içi adım ~2,7pt,
    etiketler arası ~48pt), SONRA aynı kümeye düşen iki serinin etiketleri
    15pt'ten büyük `top` boşluğuyla ayrılır (etiket içi `top` adımı ~7pt, seri
    bandı arası ≥40pt). Birleştirme yapılmazsa iki seri tek etikete girer.
  - Etiket metni `\\d{1,3}(\\.\\d{3})*` desene uymuyorsa atılır (y ekseni
    tıkları zaten döndürme filtresinden geçmez; bu ayrıca güvenlik ağıdır).
- **x ekseni TARİHLERİ FARKLI ŞABLONDADIR, HİÇBİR ZAMAN AYRIŞTIRILMAZ.**
  2025 bültenlerinde "31 Ocak 2024" (AY ADIYLA), 2026 bültenlerinde
  "31.08.2025" (sayısal, ve 68,9° değil 45° dönüşle) — ikisi de okunamaz.
  Bunun yerine tarih KAPAKTAN türetilir: bültenin ayı + grafikteki son nokta
  = o ayın AY SONU, diğerleri geriye doğru ay sonları. Ölçüldü: 2026
  bültenlerinde 13 nokta (örn. Ağustos 2026 → 31.08.2025 … 31.08.2026), 2025
  bültenlerinde de 13 (Şubat 2025 → 29.02.2024 … 28.02.2025).
- **Seri sırası = lejant sırası = etiket bandının üstten alta sırası.**
  "TOPLAM VE BAKİYELİ YATIRIMCI SAYISI" sayfasında üst bant "Kayıtlı Yatırımcı
  Sayısı" (siyah, beyaz çubuğun ÜSTÜNDE), alt bant "Bakiyeli Yatırımcı Sayısı"
  (yeşil, çubuğun İÇİNDE); lejant da aynı sırada. Sayfa başlığı 2025
  bültenlerinde "TOPLAM YATIRIMCI SAYISI", 2026'dan itibaren "TOPLAM VE
  BAKİYELİ YATIRIMCI SAYISI" — bu yüzden başlık DÜZEN İFADESİYLE eşleşir.
- **Ocak 2025 bülteninin grafik etiketleri OKUNAMAZ.** O sayfadaki döndürülmüş
  gliflerin ToUnicode eşlemesi bozuk: `pdfplumber` hepsini `(cid:1560)` gibi
  verir, hiçbiri rakam değildir. O bülten bu yüzden boş döner ve **atlanır**
  (uydurma değer yazılmaz); onun dışında tüm 20 bülte de iki sayfa sorunsuz
  okundu. Yan etki: en eski nokta 29.02.2024'tür (Ocak 2025'in taşıdığı
  31.01.2024 tek noktası kaybedilir).
- Bültenler **örtüşür ve tutarlıdır**: ölçüldü, ardışık bültenlerin ortak
  ayları BİREBİR aynı sayıyı taşır (örn. Nisan 2025'in sonu = Mayıs 2025'in
  13 noktasından 12.'si = 36.517.942). Birleştirme eskiden yeniye yapılır, yeni
  bülten eskisini ezer (revizyon kazanır).

`www.vap.org.tr` (MKK'nın Veri Analiz Platformu) AYNI verinin GÜNLÜK anlık
görüntüsünü sunar (kayıtlı/bakiyeli yatırımcı ve hesap sayısı, yerli/yabancı,
kadın/erkek, bireysel/kurumsal dağılımlar) ama **sunucu tarafında gömülü TEK
GÜN HTML'idir**: tarih parametresi, geçmiş sayfası, grafik ucu ve JSON API
YOK (2026-09-29'da `https://www.vap.org.tr/` HTML'i + Drupal `js_*.js` demeti
tarandı; özel bir uç/ayar bulunamadı). Bu yüzden günlük bir zaman serisi
KAYNAĞI DEĞİLDİR ve burada kullanılmaz — tersi, yani tarih parametresiyle
geçmişe gidilen bir uç, hiçbir yerde bulunamadı.
"""

from __future__ import annotations

import calendar
import io
import math
import re

import pdfplumber
import pandas as pd
import requests

from core.catalog import Seri

LISTE_SAYFASI = "https://www.mkk.com.tr/veri-hizmetleri/mkk-aylik-piyasa-bulteni"
ZAMAN_ASIMI = 120

# Katalogdaki `mkk_seri` değerleri (core/catalog.py'den tek kaynak olarak
# içe aktarılmalı). Her sayfanın serileri lejant sırasıyla, üstten alta.
SAYFA_SERILERI: dict[str, tuple[str, ...]] = {
    "TOPLAM YATIRIMCI SAYISI": ("kayitli_yatirimci", "bakiyeli_yatirimci"),
    "TOPLAM VE BAKİYELİ YATIRIMCI SAYISI": ("kayitli_yatirimci", "bakiyeli_yatirimci"),
    "BAKİYELİ HESAP SAYISI": ("bakiyeli_hesap",),
}
SERI_ADLARI = tuple(dict.fromkeys(s for v in SAYFA_SERILERI.values() for s in v))
assert SERI_ADLARI == ("kayitli_yatirimci", "bakiyeli_yatirimci", "bakiyeli_hesap")

# Kapak satırındaki ay adı -> ay no. Küçük/şerit varyantları ayrı tutulur
# (Python'un `.upper()`'ı 'i' harfini 'İ' değil 'I' yapar).
AY_NO = {
    "OCAK": 1, "ŞUBAT": 2, "SUBAT": 2, "MART": 3, "NİSAN": 4, "NISAN": 4,
    "MAYIS": 5, "HAZİRAN": 6, "HAZIRAN": 6, "TEMMUZ": 7, "AĞUSTOS": 8,
    "AGUSTOS": 8, "EYLÜL": 9, "EYLUL": 9, "EKİM": 10, "EKIM": 10,
    "KASIM": 11, "ARALIK": 12,
}

_DOSYA_RE = re.compile(r'href="([^"]*Aylik-Piyasa-Bulteni[^"]*\.pdf)"', re.I)
_KAPAK_RE = re.compile(r"([A-ZÇĞİÖŞÜ]+)\s+(\d{4})")
# 13 haneli Türkçe binlik ayırıcılı tam sayı: "10.531.423" / "45.000.000".
# Dört haneli grup (tarih) ve ondalık ayırıcı burada GEÇMEZ.
_DEGER_RE = re.compile(r"^\d{1,3}(?:\.\d{3})*$")

# Karakter tabanlı ölçüler (ölçülen değerler, bkz. modül docstring'i).
_X_BOSLUK_PT = 8  # etiketler arası ~48pt, etiket içi ~2,7pt
_TOP_BOSLUK_PT = 15  # seri bandı arası ≥40pt, etiket içi ~7pt
_BANT_BOSLUK_PT = 30  # aynı serinin etiketleri arası dikey açılma
_ACI_ARALIGI = (55.0, 95.0)  # değer etiketleri döndürmesi


def dosya_listesi(session=None) -> list[str]:
    """Liste sayfasını kazır, bülten PDF bağlantılarını mutlak URL olarak döner."""
    http = session or requests
    yanit = http.get(LISTE_SAYFASI, headers={"User-Agent": "Mozilla/5.0"}, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"MKK bülten listesi HTTP {yanit.status_code}: {LISTE_SAYFASI}")
    return [u if u.startswith("http") else "https://www.mkk.com.tr" + u
            for u in _DOSYA_RE.findall(yanit.text)]


def _kapak_tarihi(baytlar: bytes, ad: str) -> tuple[int, int]:
    """Kapak sayfasından bültenin (yıl, ay) bilgisini çözer."""
    with pdfplumber.open(io.BytesIO(baytlar)) as kitap:
        metin = (kitap.pages[0].extract_text() or "").upper()
    es = _KAPAK_RE.search(metin)
    if es is None or es.group(1) not in AY_NO:
        raise RuntimeError(f"MKK bülten kapağı okunamadı ({ad}): {metin[:120]!r}")
    return int(es.group(2)), AY_NO[es.group(1)]


def _donen_kareler(sayfa) -> list[dict]:
    """Sayfadaki döndürülmüş DEĞER etiketlerini `{"x", "ust", "deger"}` listesi
    olarak döner (yatay başlıklar ve 45° x ekseni tarihleri elenir)."""
    karakterler = []
    for c in sayfa.chars:
        if c["text"] not in "0123456789.,":
            continue
        aci = math.degrees(math.atan2(c["matrix"][1], c["matrix"][0])) % 180
        if _ACI_ARALIGI[0] <= aci <= _ACI_ARALIGI[1]:
            karakterler.append(c)
    karakterler.sort(key=lambda c: c["x0"])
    etiketler = []
    for kume in _kume_et(karakterler, _X_BOSLUK_PT):
        # İki seri aynı x bandına düşebilir; dikey boşluğa göre ayrılır.
        for dizi in _kume_dikey(kume, _TOP_BOSLUK_PT):
            metin = "".join(c["text"] for c in dizi)
            if not _DEGER_RE.match(metin):
                continue
            etiketler.append({"x": sum(c["x0"] for c in dizi) / len(dizi),
                              "ust": min(c["top"] for c in dizi),
                              "deger": float(metin.replace(".", ""))})
    return etiketler


def _kume_et(karakterler: list[dict], bosluk: float) -> list[list[dict]]:
    """`x0` sırasında, ardışık iki karakter arasındaki boşluk eşiği aşılıyorsa
    yeni kümeyi başlatır."""
    kumeler: list[list[dict]] = []
    for c in karakterler:
        if kumeler and c["x0"] - kumeler[-1][-1]["x0"] <= bosluk:
            kumeler[-1].append(c)
        else:
            kumeler.append([c])
    return kumeler


def _kume_dikey(kume: list[dict], bosluk: float) -> list[list[dict]]:
    """Bir kümeyi yukarıdan aşağı sıralar, `top` boşluğu eşine gelince böler."""
    out: list[list[dict]] = []
    for c in sorted(kume, key=lambda c: -c["top"]):
        if out and out[-1][-1]["top"] - c["top"] <= bosluk:
            out[-1].append(c)
        else:
            out.append([c])
    return out


def sayfa_noktalari(sayfa, ad: str) -> dict[str, list[float]] | None:
    """Bir bülten sayfasını `{seri_adi: [değerler]}` biçiminde çözer.

    Sayfa kayıtlı bir sayfa değilse `None`. Değer etiketleri okunamayan
    (Ocak 2025 bülteni) sayfa da `None` döner — uydurma sayı yazılmaz.
    """
    baslik = (sayfa.extract_text() or "").split("\n")[0].strip()
    if baslik not in SAYFA_SERILERI:
        return None
    seriler = SAYFA_SERILERI[baslik]
    bantlar: list[list[dict]] = []
    for e in sorted(_donen_kareler(sayfa), key=lambda e: e["ust"]):
        if bantlar and e["ust"] - bantlar[-1][-1]["ust"] <= _BANT_BOSLUK_PT:
            bantlar[-1].append(e)
        else:
            bantlar.append([e])
    if len(bantlar) != len(seriler):
        return None
    sirali = [[e["deger"] for e in sorted(b, key=lambda e: e["x"])] for b in bantlar]
    if len({len(x) for x in sirali}) != 1 or not sirali[0]:
        raise RuntimeError(f"MKK bülten sayfası tutarsız ({ad}, {baslik}): "
                           f"{[len(x) for x in sirali]}")
    # Değişmez: kayıtlı yatırımcı sayısı bakiyeli yatırımcı sayısından küçük
    # olamaz (bant sırası ters dönerse burada yakalanır).
    if len(sirali) == 2 and any(k < b for k, b in zip(*sirali)):
        raise RuntimeError(f"MKK bülten sayfasında seri sırası ters ({ad}, {baslik})")
    return dict(zip(seriler, sirali))


def ay_sonlari(yil: int, ay: int, adet: int) -> list[str]:
    """Bültenin ayı hariç, geriye doğru `adet` ayın AY SONU tarihleri."""
    return [f"{(yil + (ay - 1 - i) // 12):04d}-{(ay - 1 - i) % 12 + 1:02d}-"
            f"{calendar.monthrange(yil + (ay - 1 - i) // 12, (ay - 1 - i) % 12 + 1)[1]:02d}"
            for i in reversed(range(adet))]


def bulten_noktalari(baytlar: bytes, ad: str) -> dict[str, dict[str, float]]:
    """Tek bir bültenin kayıtlı sayfalarından `{tarih: değer}` noktaları çıkarır."""
    yil, ay = _kapak_tarihi(baytlar, ad)
    noktalar: dict[str, dict[str, float]] = {}
    with pdfplumber.open(io.BytesIO(baytlar)) as kitap:
        for sayfa in kitap.pages[2:]:  # 1: kapak, 2: içindekiler
            seriler = sayfa_noktalari(sayfa, ad)
            if not seriler:
                continue
            adet = len(next(iter(seriler.values())))
            tarihler = ay_sonlari(yil, ay, adet)
            for seri_adi, degerler in seriler.items():
                for tarih, deger in zip(tarihler, degerler):
                    noktalar.setdefault(seri_adi, {})[tarih] = deger
    return noktalar


def _tum_noktalar(onbellek: dict, session=None) -> dict[str, dict[str, float]]:
    """Tüm bültenleri bir kez indirir/çözer; seri sayısı ne olursa olsun tek
    indirme yapılır."""
    if "noktalar" not in onbellek:
        http = session or requests
        bultenler = []
        for yol in dosya_listesi(http):
            yanit = http.get(yol, headers={"User-Agent": "Mozilla/5.0"}, timeout=ZAMAN_ASIMI)
            if yanit.status_code != 200:
                raise RuntimeError(f"MKK bülteni HTTP {yanit.status_code}: {yol}")
            ad = yol.rsplit("/", 1)[-1]
            yil, ay = _kapak_tarihi(yanit.content, ad)
            bultenler.append(((yil, ay), yanit.content, ad))
        birlesik: dict[str, dict[str, float]] = {}
        # Liste sayfası KRONOLOJİK DEĞİLDİR (ay klasörü dosya adından türetilemez),
        # bu yüzden kapak tarihine göre eskiden yeniye sıralanır: yeni bülten
        # eskisini ezer, revizyon kazanır.
        for _, baytlar, ad in sorted(bultenler, key=lambda b: b[0]):
            for seri_adi, aylik in bulten_noktalari(baytlar, ad).items():
                birlesik.setdefault(seri_adi, {}).update(aylik)
        onbellek["noktalar"] = birlesik
    return onbellek["noktalar"]


def seri_cek(seri: Seri, onbellek: dict | None = None,
             session: requests.Session | None = None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `onbellek` verilirse indirilen PDF'ler ve çözülen noktalar koşu boyunca
    paylaşılır: üç seri aynı 20 bülteni okuduğu için yoksa 60 indirme olurdu.
    """
    onbellek = {} if onbellek is None else onbellek
    noktalar = _tum_noktalar(onbellek, session)
    adi = getattr(seri, "mkk_seri", None)
    if adi not in noktalar:
        raise RuntimeError(f"MKK bülteninde seri bulunamadı: {adi!r} ({seri.id})")
    df = pd.DataFrame(sorted(noktalar[adi].items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)


def _kendini_sina() -> None:  # pragma: no cover - elle çalıştırma içindir
    """Canlı bültenleri çeker ve elle ölçülmüş değerlerle karşılaştırır; bülten
    şablonu değişirse ya da bir sayfa okunamaz olursa patlar."""
    onbellek: dict = {}
    _tum_noktalar(onbellek)
    kayitli = onbellek["noktalar"]["kayitli_yatirimci"]
    # 2026-09-29'da Ağustos 2026 bülteninin son noktası (canlı ölçüldü).
    assert kayitli["2026-08-31"] == 39001729.0, sorted(kayitli.items())[-1]
    assert onbellek["noktalar"]["bakiyeli_hesap"]["2026-08-31"] == 16085627.0
    assert len(kayitli) >= 30, len(kayitli)
    print(f"{len(kayitli)} nokta, {min(kayitli)} … {max(kayitli)}")


if __name__ == "__main__":  # pragma: no cover
    _kendini_sina()
