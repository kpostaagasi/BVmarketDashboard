# Faz 3e: OSD Otomotiv Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** OSD aylık üretim bültenlerinden 13 firmanın aylık toplam üretimini çekip Otomotiv kategorisini açmak.

**Architecture:** `ingest/osd.py` saf katmanlarla kurulur — indeks HTML'inden bülten bağlantılarını çıkarma, çekilecek bültenleri seçme, firma adı normalizasyonu, PDF tablolarından firma×ay noktaları çıkarma, öz-doğrulama. Ağ yalnızca `seri_cek` kabuğunda. PDF baytları koşu başına önbelleklenir (Faz 3c EPİAŞ kalıbı); 13 seri aynı beş PDF'i paylaşır. `pdfplumber` yalnızca ingest'e ait olduğu için `requirements` ikiye ayrılır.

**Tech Stack:** Python 3.12 · Streamlit ≥1.49 · pandas · Plotly · PyYAML · requests · **pdfplumber (yalnızca ingest)** · pytest

**Spec:** `docs/superpowers/specs/2026-09-04-faz3e-osd-otomotiv-design.md`

## Global Constraints

- **Python 3.12.** Testler `.venv/bin/python -m pytest` ile koşar.
- **Arayüz dili Türkçe.** Tanımlayıcılar, fonksiyon adları, mesajlar, yorumlar ve docstring'ler Türkçe.
- **`requirements.txt` DEĞİŞMEZ.** Streamlit Cloud onu kurar; `pdfplumber` oraya girmez.
- **`core/` modülleri `ingest/`'i import etmez; `ingest/` Streamlit import etmez.**
- **`load_series`'in mevcut sözleşmesi bozulmaz.**
- **`importExport` benzeri alt toplam satırları seri olmaz:** `TOPLAM / TOTAL`, `Pay / Share %`, `... Toplam / ... Total`, `Toplam Pay / Total Share` firma değildir ve dışlanır.
- **Sessiz yanlış veri yasak.** Bülten şablonu değişirse ayrıştırıcı hata yükseltir; boş liste döndürüp devam etmez.
- **`st.dataframe` / `st.plotly_chart` `width="stretch"` kullanır.**

## Doğrulanmış OSD bilgileri

Canlı bültenlere karşı ölçüldü — uydurma değil.

**İndeks:** `https://www.osd.org.tr/osd-yayinlari/otomotiv-sanayii-uretim-bultenleri`

HTML'deki bağlantı biçimi (ters bölülü, düz bölüye çevrilmeli):

```
href="/saved-files\PDF\2023\01\16\Otomotiv_Sanayii_Uretim_Bulteni_2022.12.pdf"
href="/saved-files\PDF\2024\01\14\Otomotiv_Sanayii_Uretim_Bulteni-2023.12.pdf"
href="/saved-files\PDF\2026\08\17\Otomotiv_Sanayii_Uretim_Bulteni-2026.07.pdf"
```

2022 **alt çizgi**, 2023+ **tire** kullanıyor. İndekste bulunan modern-format bültenler: `2022.12`, `2023.12`, `2024.12`, `2025.12`, `2026.07`. (2006–2021 `Üretim Bülteni _YYYY.pdf` biçiminde ve kapsam dışı.)

**Bülten yapısı** (15 sayfa, hem 2022.12 hem 2026.07'de doğrulandı):

- **s2** (index 1): 15 satır × 19 sütun. Sütun 0 = firma, sütun 17 = `TOPLAM Total`. Bültenin AYI için.
- **s6–s9** (index 5–8): 26 satır × 14 sütun. Sütun 0 = tip/firma, sütun 1–12 = OCAK…ARALIK, sütun 13 = TOPLAM.

**s6 satır yapısı** (gerçek, Temmuz 2026):

```
 0 'Tipler\nTypes'                         ← başlık
 1 'FORD OTOSAN'                           ← FİRMA
 2 'Pay / Share %'                         ← atla
 3 'HYUNDAI MOTOR TÜRKİYE'                 ← FİRMA
 ...
11 'OTOMOBİL Toplam / Pass.Car Total'      ← atla
12 'Toplam Pay / Total Share'              ← atla
13 ''                                      ← atla
14 'A.I.O.S.'                              ← FİRMA (yeni bölüm)
```

**13 firma** (ham adlarıyla): `A.I.O.S.` · `FORD OTOSAN` · `HATTAT TRAKTÖR` · `HYUNDAI MOTOR TÜRKİYE` · `KARSAN` · `M. BENZ TÜRK` · `MAN TÜRKİYE` · `OTOKAR` · `OYAK RENAULT` · `TEMSA` · `TOFAŞ` · `TOYOTA` · `TÜRK TRAKTÖR`

**Sayı biçimi:** Türkçe — `36.548` (nokta binlik), `-` boş değer, `70,9` (virgül ondalık, yalnızca yüzde satırlarında).

**Öz-doğrulama kanıtı:** s6–s9'un firma toplamı, s2'nin `TOPLAM` sütunuyla 13 firmanın 13'ünde de fark 0 verdi.

---

### Task 1: `requirements` ayrımı ve `pdfplumber`

`pdfplumber` ingest'e girer, uygulamaya girmez.

**Files:**
- Create: `requirements-ingest.txt`
- Modify: `requirements-dev.txt`
- Modify: `.github/workflows/ingest.yml`
- Test: `tests/test_requirements.py`

**Interfaces:**
- Produces: `requirements-ingest.txt` (ingest bağımlılıkları), `pdfplumber` kurulu

- [ ] **Step 1: Testi yaz (başarısız olmalı)**

`tests/test_requirements.py` oluşturun:

```python
"""requirements ayrımı: pdfplumber ingest'e ait, uygulamaya değil.

Streamlit Cloud `requirements.txt`'i kurar. PDF kütüphanesi oraya girerse
uygulama gereksiz büyür ve çalışma zamanında hiç kullanılmaz.
"""

from pathlib import Path

KOK = Path(__file__).resolve().parent.parent


def _satirlar(ad: str) -> list[str]:
    return [
        s.strip()
        for s in (KOK / ad).read_text(encoding="utf-8").splitlines()
        if s.strip() and not s.strip().startswith("#")
    ]


def test_uygulama_requirements_pdfplumber_icermez():
    assert not any("pdfplumber" in s for s in _satirlar("requirements.txt"))


def test_ingest_requirements_pdfplumber_icerir():
    assert any("pdfplumber" in s for s in _satirlar("requirements-ingest.txt"))


def test_ingest_requirements_uygulamayi_kapsar():
    """Ingest, uygulamanın bağımlılıklarına da ihtiyaç duyar (pandas, requests)."""
    assert "-r requirements.txt" in _satirlar("requirements-ingest.txt")


def test_ingest_workflow_ingest_requirements_kurar():
    metin = (KOK / ".github/workflows/ingest.yml").read_text(encoding="utf-8")
    assert "requirements-ingest.txt" in metin
```

- [ ] **Step 2: Testi koştur, başarısız olduğunu gör**

Run: `.venv/bin/python -m pytest tests/test_requirements.py -q`
Expected: FAIL — `requirements-ingest.txt` yok (`FileNotFoundError`).

- [ ] **Step 3: `requirements-ingest.txt` oluştur**

```
-r requirements.txt
pdfplumber>=0.11
```

- [ ] **Step 4: `requirements-dev.txt`'i güncelle**

Mevcut içeriği `-r requirements.txt` + `pytest>=8.0`. Testler ingest modüllerini import ettiği için ingest bağımlılıkları da gerekir; ilk satırı değiştirin:

```
-r requirements-ingest.txt
pytest>=8.0
```

- [ ] **Step 5: Workflow'u güncelle**

`.github/workflows/ingest.yml` içindeki "Bağımlılıkları kur" adımını değiştirin:

```yaml
      - name: Bağımlılıkları kur
        run: pip install -r requirements-ingest.txt
```

`.github/workflows/test.yml`'e DOKUNMAYIN — o zaten `requirements-dev.txt` kuruyor ve Step 4 sayesinde ingest bağımlılıklarını da alacak.

- [ ] **Step 6: `pdfplumber`'ı yerel ortama kur**

Run: `.venv/bin/pip install -q 'pdfplumber>=0.11'`
Doğrula: `.venv/bin/python -c "import pdfplumber; print(pdfplumber.__version__)"`

- [ ] **Step 7: Testleri koştur, geçtiklerini gör**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — tümü (mevcut 238 + 4 yeni).

- [ ] **Step 8: Commit**

```bash
git add requirements-ingest.txt requirements-dev.txt .github/workflows/ingest.yml tests/test_requirements.py
git commit -m "chore: requirements ayrımı — pdfplumber yalnızca ingest'te"
```

---

### Task 2: Katalog — `osd` kaynak tipi

Katalog `osd` kaynak tipini ve `osd_firma` alanını tanır. Bu görev seri veya kategori EKLEMEZ.

**Files:**
- Modify: `core/catalog.py` (`GECERLI_KAYNAK_TIPLERI`, `Seri.osd_firma`, `KAYNAK_ALANLARI`, `serileri_yukle`)
- Test: `tests/test_catalog.py`

**Interfaces:**
- Produces:
  - `core.catalog.Seri.osd_firma: str | None = None`
  - `core.catalog.GECERLI_KAYNAK_TIPLERI` artık `"osd"` içerir
  - `core.catalog.KAYNAK_ALANLARI["osd"]`

- [ ] **Step 1: Testleri yaz (başarısız olmalı)**

`tests/test_catalog.py` sonuna ekleyin:

```python
def test_osd_gecerli_kaynak_tipi():
    from core.catalog import GECERLI_KAYNAK_TIPLERI, KAYNAK_ALANLARI

    assert "osd" in GECERLI_KAYNAK_TIPLERI
    assert "osd" in KAYNAK_ALANLARI


def test_osd_serisi_firma_ister():
    with pytest.raises(KatalogHatasi, match="osd_firma"):
        _dogrula_ham(
            _ham_seri(kaynak_tipi="osd", evds_code=None, evds_frequency=None)
        )


def test_osd_serisi_evds_alani_tasiyamaz():
    with pytest.raises(KatalogHatasi, match="evds_code"):
        _dogrula_ham(
            _ham_seri(kaynak_tipi="osd", osd_firma="FORD OTOSAN", evds_frequency=None)
        )


def test_evds_serisi_osd_firma_tasiyamaz():
    with pytest.raises(KatalogHatasi, match="osd_firma"):
        _dogrula_ham(_ham_seri(osd_firma="FORD OTOSAN"))
```

- [ ] **Step 2: Testleri koştur, başarısız olduklarını gör**

Run: `.venv/bin/python -m pytest tests/test_catalog.py -q`
Expected: FAIL — `"osd"` sette değil; `Seri` nesnesinin `osd_firma` özniteliği yok.

- [ ] **Step 3: `core/catalog.py`'yi güncelle**

`GECERLI_KAYNAK_TIPLERI` satırını değiştirin:

```python
GECERLI_KAYNAK_TIPLERI = {"evds", "yahoo", "epias", "osd"}
```

`KAYNAK_ALANLARI` sözlüğüne `"epias"` girdisinden sonra ekleyin:

```python
    "osd": {
        "zorunlu": ("osd_firma",),
        "istege_bagli": ("start_date",),
    },
```

`Seri` dataclass'ına `epias_bilesenler`'den sonra ekleyin:

```python
    osd_firma: str | None = None
```

`serileri_yukle()` içinde `Seri(...)` kurulumuna ekleyin:

```python
            osd_firma=ham.get("osd_firma"),
```

- [ ] **Step 4: Testleri koştur, geçtiklerini gör**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — tümü.

- [ ] **Step 5: Commit**

```bash
git add core/catalog.py tests/test_catalog.py
git commit -m "feat: katalog osd kaynak tipini tanısın"
```

---

### Task 3: `ingest/osd.py` — saf ayrıştırma katmanları

İndeks kazıma, bülten seçimi, ad normalizasyonu, nokta çıkarma ve öz-doğrulama. Bu görevde AĞA ÇIKILMAZ; hepsi saf fonksiyon ve fixture'la test edilir.

**Files:**
- Create: `ingest/osd.py`
- Test: `tests/test_osd.py`

**Interfaces:**
- Consumes: `core.catalog.Seri`
- Produces:
  - `ingest.osd.INDEKS_URL: str`
  - `ingest.osd.TABAN: str`
  - `ingest.osd.VARSAYILAN_GECMIS_YIL: int`
  - `ingest.osd.bulten_baglantilari(html: str) -> dict[str, str]`
  - `ingest.osd.cekilecek_bultenler(baglantilar: dict[str, str], bugun: date) -> list[str]`
  - `ingest.osd.firma_adini_normalize(ham: str) -> str`
  - `ingest.osd.sayi_parse(ham: str | None) -> float | None`
  - `ingest.osd.firma_aylik_noktalari(tablolar: list, yil: int) -> list[tuple[str, str, float]]`
  - `ingest.osd.ay_toplamlari(s2_tablosu: list) -> dict[str, float]`
  - `ingest.osd.dogrula(noktalar: list, toplamlar: dict, ay_tarihi: str) -> None`

- [ ] **Step 1: Testleri yaz (başarısız olmalı)**

`tests/test_osd.py` oluşturun:

```python
from datetime import date

import pytest

from ingest.osd import (
    ay_toplamlari,
    bulten_baglantilari,
    cekilecek_bultenler,
    dogrula,
    firma_adini_normalize,
    firma_aylik_noktalari,
    sayi_parse,
)

# --- İndeks kazıma ---

INDEKS_HTML = """
<a href="/saved-files\\PDF\\2023\\01\\16\\Otomotiv_Sanayii_Uretim_Bulteni_2022.12.pdf">2022</a>
<a href="/saved-files\\PDF\\2024\\01\\14\\Otomotiv_Sanayii_Uretim_Bulteni-2023.12.pdf">2023</a>
<a href="/saved-files\\PDF\\2026\\08\\17\\Otomotiv_Sanayii_Uretim_Bulteni-2026.07.pdf">2026</a>
<a href="/saved-files\\PDF\\2010\\01\\01\\Üretim Bülteni _2009.pdf">2009</a>
"""


def test_bulten_baglantilari_tire_ve_alt_cizgiyi_kabul_eder():
    """2022 alt çizgi, 2023+ tire kullanıyor — ikisi de bulunmalı."""
    b = bulten_baglantilari(INDEKS_HTML)
    assert set(b) == {"2022.12", "2023.12", "2026.07"}


def test_bulten_baglantilari_ters_boluyu_duzeltir():
    b = bulten_baglantilari(INDEKS_HTML)
    assert b["2026.07"] == (
        "https://www.osd.org.tr/saved-files/PDF/2026/08/17/"
        "Otomotiv_Sanayii_Uretim_Bulteni-2026.07.pdf"
    )


def test_bulten_baglantilari_eski_bicimi_yok_sayar():
    """`Üretim Bülteni _2009.pdf` farklı format; kapsam dışı."""
    assert "2009" not in bulten_baglantilari(INDEKS_HTML)


def test_bulten_baglantilari_hicbiri_yoksa_yukselir():
    """Site yapısı değişirse sessizce boş dönmemeli."""
    with pytest.raises(RuntimeError, match="bülten bağlantısı"):
        bulten_baglantilari("<html><body>hiçbir şey</body></html>")


# --- Bülten seçimi ---

BAGLANTILAR = {
    "2022.12": "u1", "2023.12": "u2", "2024.12": "u3",
    "2025.12": "u4", "2026.07": "u5",
}


def test_cekilecek_bultenler_aralik_ve_guncel_secer():
    secilen = cekilecek_bultenler(BAGLANTILAR, date(2026, 9, 4))
    assert secilen == ["2022.12", "2023.12", "2024.12", "2025.12", "2026.07"]


def test_cekilecek_bultenler_gecmis_yil_siniri_uygular():
    """VARSAYILAN_GECMIS_YIL=5 ise 2021 ve öncesi alınmaz."""
    genis = dict(BAGLANTILAR, **{"2019.12": "u0", "2020.12": "u0b"})
    secilen = cekilecek_bultenler(genis, date(2026, 9, 4))
    assert "2019.12" not in secilen and "2020.12" not in secilen


def test_cekilecek_bultenler_ocakta_tekrar_secmez():
    """Ocak'ta güncel bülten önceki yılın Aralık'ıdır; iki kez seçilmemeli."""
    ocak = {"2024.12": "u3", "2025.12": "u4"}
    secilen = cekilecek_bultenler(ocak, date(2026, 1, 10))
    assert secilen == sorted(set(secilen))
    assert len(secilen) == len(set(secilen))


# --- Ad ve sayı ayrıştırma ---

def test_firma_adini_normalize_null_bayti_temizler():
    """Eski PDF'lerde font kodlaması Türkçe karakterlerde \\x00 sızdırıyor."""
    assert firma_adini_normalize("T\x00pler") == "Tpler"


def test_firma_adini_normalize_satir_sonu_ve_bosluk_temizler():
    assert firma_adini_normalize("  FORD\nOTOSAN  ") == "FORD OTOSAN"


def test_sayi_parse_turkce_binlik_ayraci():
    assert sayi_parse("36.548") == 36548.0


def test_sayi_parse_bos_ve_tire_none_doner():
    assert sayi_parse("-") is None
    assert sayi_parse("") is None
    assert sayi_parse(None) is None


# --- Nokta çıkarma ---

def _tablo(*satirlar):
    """s6 biçimi: 14 sütun (tip/firma + 12 ay + toplam)."""
    basliklar = ["Tipler\nTypes"] + [f"AY{i}" for i in range(1, 13)] + ["TOPLAM"]
    return [basliklar, *satirlar]


def _firma_satiri(ad, *aylar):
    hucreler = list(aylar) + ["-"] * (12 - len(aylar))
    return [ad, *hucreler, "-"]


def test_firma_aylik_noktalari_firma_satirlarini_okur():
    tablo = _tablo(
        _firma_satiri("FORD OTOSAN", "100", "200"),
        ["Pay / Share %", *["1"] * 13],
        _firma_satiri("TOFAŞ", "10", "20"),
        ["Pay / Share %", *["1"] * 13],
        ["OTOMOBİL Toplam / Pass.Car Total", *["110"] * 13],
        ["Toplam Pay / Total Share", *["100"] * 13],
    )
    noktalar = firma_aylik_noktalari([tablo], 2026)
    assert ("FORD OTOSAN", "2026-01-01", 100.0) in noktalar
    assert ("FORD OTOSAN", "2026-02-01", 200.0) in noktalar
    assert ("TOFAŞ", "2026-02-01", 20.0) in noktalar


def test_firma_aylik_noktalari_alt_toplam_satirlarini_atlar():
    tablo = _tablo(
        _firma_satiri("FORD OTOSAN", "100"),
        ["Pay / Share %", *["1"] * 13],
        ["OTOMOBİL Toplam / Pass.Car Total", *["100"] * 13],
        ["Toplam Pay / Total Share", *["100"] * 13],
        ["", *[""] * 13],
    )
    adlar = {n[0] for n in firma_aylik_noktalari([tablo], 2026)}
    assert adlar == {"FORD OTOSAN"}


def test_firma_aylik_noktalari_ayni_firmayi_bolumler_arasi_toplar():
    """Bir firma birden çok araç tipi bölümünde görünür; toplanmalı."""
    t1 = _tablo(_firma_satiri("FORD OTOSAN", "100"))
    t2 = _tablo(_firma_satiri("FORD OTOSAN", "50"))
    noktalar = firma_aylik_noktalari([t1, t2], 2026)
    assert noktalar == [("FORD OTOSAN", "2026-01-01", 150.0)]


def test_firma_aylik_noktalari_bos_ayi_atlar():
    tablo = _tablo(_firma_satiri("KARSAN", "-", "5"))
    noktalar = firma_aylik_noktalari([tablo], 2026)
    assert noktalar == [("KARSAN", "2026-02-01", 5.0)]


# --- Öz-doğrulama ---

def _s2_tablosu(*satirlar):
    basliklar = ["FİRMALAR"] + [f"S{i}" for i in range(1, 17)] + ["TOPLAM Total", "%"]
    return [basliklar, *satirlar]


def _s2_satiri(ad, toplam):
    return [ad, *["-"] * 16, toplam, "-"]


def test_ay_toplamlari_toplam_sutununu_okur():
    tablo = _s2_tablosu(
        _s2_satiri("FORD OTOSAN", "36.548"),
        _s2_satiri("TOPLAM / TOTAL", "105.725"),
    )
    assert ay_toplamlari(tablo) == {"FORD OTOSAN": 36548.0}


def test_dogrula_tutan_toplamda_sessiz():
    noktalar = [("FORD OTOSAN", "2026-07-01", 36548.0)]
    dogrula(noktalar, {"FORD OTOSAN": 36548.0}, "2026-07-01")


def test_dogrula_tutmayan_toplamda_yukselir():
    """Şablon değişirse sessizce eksik veri üretmek yerine kırılmalı."""
    noktalar = [("FORD OTOSAN", "2026-07-01", 30000.0)]
    with pytest.raises(RuntimeError, match="FORD OTOSAN"):
        dogrula(noktalar, {"FORD OTOSAN": 36548.0}, "2026-07-01")


def test_dogrula_eksik_firmada_yukselir():
    with pytest.raises(RuntimeError, match="TOFAŞ"):
        dogrula([], {"TOFAŞ": 100.0}, "2026-07-01")
```

- [ ] **Step 2: Testleri koştur, başarısız olduklarını gör**

Run: `.venv/bin/python -m pytest tests/test_osd.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingest.osd'`.

- [ ] **Step 3: `ingest/osd.py`'yi yaz**

```python
"""OSD (Otomotiv Sanayii Derneği) aylık üretim bülteni istemcisi.

Bültenler yalnızca PDF olarak yayımlanıyor ve indirme URL'leri yükleme
tarihini gömdüğü için türetilemiyor — indeks sayfası kazınmak zorunda.

Firma aylık toplamı için 6–9. sayfalar okunur (firma × ay, araç tipi
bölümlerinde). Bir bülten o yılın tamamını taşıdığından tarihsel doldurma
yılda tek PDF ister; 2. sayfayı (tek ay) okumak aynı pencere için on kat
daha fazla indirme demek olurdu.

Öz-doğrulama: 6–9. sayfaların firma toplamı, 2. sayfanın TOPLAM sütunuyla
karşılaştırılır. Canlı bültende 13 firmanın 13'ünde de fark 0 ölçüldü.
Tutmazsa RuntimeError yükselir — OSD şablonu değiştiğinde sessizce eksik
veri üretmektense ingest'in kırılması istenir.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

TABAN = "https://www.osd.org.tr"
INDEKS_URL = f"{TABAN}/osd-yayinlari/otomotiv-sanayii-uretim-bultenleri"
VARSAYILAN_GECMIS_YIL = 5

# 2022 alt çizgi, 2023+ tire kullanıyor; ikisi de kabul edilir.
_BAGLANTI = re.compile(
    r'href="(/saved-files[^"]*?Otomotiv_Sanayii_Uretim_Bulteni[-_](\d{4}\.\d{2})\.pdf)"'
)

_ATLANACAK_ONEKLER = ("Pay /", "Toplam Pay", "Tipler")


def bulten_baglantilari(html: str) -> dict[str, str]:
    """İndeks HTML'inden `"YYYY.MM" -> tam URL` eşlemesi çıkarır.

    HTML'deki yollar ters bölülü (`/saved-files\\PDF\\2026\\...`); düz bölüye
    çevrilir. Hiç bağlantı bulunamazsa RuntimeError: site yapısı değiştiyse
    boş liste döndürüp sessizce devam etmek, veriyi sessizce kaybetmektir.
    """
    baglantilar = {
        anahtar: TABAN + yol.replace("\\", "/")
        for yol, anahtar in _BAGLANTI.findall(html)
    }
    if not baglantilar:
        raise RuntimeError(
            f"OSD indeksinde bülten bağlantısı bulunamadı ({INDEKS_URL}) — "
            "sayfa yapısı değişmiş olabilir"
        )
    return baglantilar


def cekilecek_bultenler(baglantilar: dict[str, str], bugun: date) -> list[str]:
    """Her yılın Aralık bülteni + en güncel bülten.

    Bir bülten o yılın tüm aylarını taşıdığı için yıl başına bir dosya yeter.
    Ocak'ta en güncel bülten zaten önceki yılın Aralık'ıdır; küme kullanımı
    tekrarı önler.
    """
    en_eski_yil = bugun.year - VARSAYILAN_GECMIS_YIL
    secilen = {
        a for a in baglantilar
        if a.endswith(".12") and int(a[:4]) >= en_eski_yil
    }
    guncel = max(baglantilar)
    if int(guncel[:4]) >= en_eski_yil:
        secilen.add(guncel)
    return sorted(secilen)


def firma_adini_normalize(ham: str) -> str:
    """Null baytı, satır sonlarını ve fazla boşluğu temizler.

    Eski bültenlerde font kodlaması Türkçe karakterlerde `\\x00` sızdırıyor
    (`"T\\x00pler"`); normalizasyon olmazsa firma katalogla eşleşmez.
    """
    return " ".join(ham.replace("\x00", "").split())


def sayi_parse(ham: str | None) -> float | None:
    """Türkçe biçimli tam sayı: `36.548` → 36548.0. `-` ve boş → None."""
    metin = (ham or "").strip()
    if not metin or metin == "-":
        return None
    try:
        return float(metin.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _firma_satiri_mi(ad: str) -> bool:
    if not ad or ad.startswith(_ATLANACAK_ONEKLER):
        return False
    # "OTOMOBİL Toplam / Pass.Car Total" gibi bölüm alt toplamları
    return "Toplam" not in ad and "Total" not in ad


def firma_aylik_noktalari(tablolar: list, yil: int) -> list[tuple[str, str, float]]:
    """6–9. sayfa tablolarından `(firma, "YYYY-MM-01", adet)` üretir.

    Bir firma birden çok araç tipi bölümünde görünür (Ford Otosan hem
    kamyonette hem minibüste); bölümler boyunca TOPLANIR — firma toplam
    üretimi budur ve 2. sayfanın TOPLAM sütunuyla birebir tutar.
    """
    toplam: dict[tuple[str, str], float] = defaultdict(float)
    for tablo in tablolar:
        for satir in tablo[1:]:
            ad = firma_adini_normalize(satir[0] or "")
            if not _firma_satiri_mi(ad):
                continue
            for ay in range(1, 13):
                deger = sayi_parse(satir[ay])
                if deger is not None:
                    toplam[(ad, f"{yil}-{ay:02d}-01")] += deger
    return [(ad, tarih, deger) for (ad, tarih), deger in toplam.items()]


def ay_toplamlari(s2_tablosu: list) -> dict[str, float]:
    """2. sayfanın `TOPLAM` sütunundan `firma -> adet` çıkarır (sütun 17)."""
    toplamlar = {}
    for satir in s2_tablosu[1:]:
        ad = firma_adini_normalize(satir[0] or "")
        if not _firma_satiri_mi(ad):
            continue
        deger = sayi_parse(satir[17])
        if deger is not None:
            toplamlar[ad] = deger
    return toplamlar


def dogrula(
    noktalar: list[tuple[str, str, float]],
    toplamlar: dict[str, float],
    ay_tarihi: str,
) -> None:
    """6–9. sayfa toplamını 2. sayfanın TOPLAM sütunuyla karşılaştırır."""
    ay_noktalari = {ad: deger for ad, tarih, deger in noktalar if tarih == ay_tarihi}
    for ad, beklenen in toplamlar.items():
        bulunan = ay_noktalari.get(ad)
        if bulunan is None:
            raise RuntimeError(
                f"OSD öz-doğrulama: {ad} 2. sayfada var ({beklenen:,.0f}) ama "
                f"6–9. sayfalarda {ay_tarihi} için hiç noktası yok"
            )
        if abs(bulunan - beklenen) > 0.5:
            raise RuntimeError(
                f"OSD öz-doğrulama: {ad} {ay_tarihi} — 6–9. sayfa toplamı "
                f"{bulunan:,.0f}, 2. sayfa TOPLAM {beklenen:,.0f}"
            )
```

- [ ] **Step 4: Testleri koştur, geçtiklerini gör**

Run: `.venv/bin/python -m pytest tests/test_osd.py -q`
Expected: PASS — 17 test.

- [ ] **Step 5: Tam suite'i koştur**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — tümü.

- [ ] **Step 6: Commit**

```bash
git add ingest/osd.py tests/test_osd.py
git commit -m "feat: OSD saf ayrıştırma katmanları ve öz-doğrulama"
```

---

### Task 4: `seri_cek`, katalog kayıtları ve gerçek veri

Ağ kabuğu, 13 seri, kategori, gerçek çekim ve tarayıcı doğrulaması.

**Files:**
- Modify: `ingest/osd.py` (`seri_cek`)
- Modify: `ingest/run.py` (`_cek` dördüncü dal, OSD önbelleği)
- Modify: `catalog/categories.yaml` (`otomotiv`)
- Modify: `catalog/series.yaml` (13 seri)
- Test: `tests/test_osd.py`, `tests/test_run.py`, `tests/test_catalog.py`

**Interfaces:**
- Consumes: Task 3'ün saf fonksiyonları
- Produces: `ingest.osd.seri_cek(seri, onbellek=None, session=None, bugun=None) -> pd.DataFrame`

- [ ] **Step 1: Testleri yaz (başarısız olmalı)**

`tests/test_osd.py` sonuna:

```python
def test_seri_cek_onbellegi_paylasir(monkeypatch):
    """13 seri aynı beş PDF'i paylaşır; ikinci seri hiç indirmemeli."""
    from types import SimpleNamespace

    from ingest import osd

    indirilenler = []

    def sahte_indir(url, session=None):
        indirilenler.append(url)
        return b"sahte-pdf"

    def sahte_ayristir(baytlar, anahtar):
        return [("FORD OTOSAN", "2026-01-01", 100.0),
                ("TOFAŞ", "2026-01-01", 50.0)]

    monkeypatch.setattr(osd, "_indeks_cek", lambda session=None: {"2026.07": "u"})
    monkeypatch.setattr(osd, "_pdf_indir", sahte_indir)
    monkeypatch.setattr(osd, "_bulteni_ayristir", sahte_ayristir)

    onbellek: dict = {}
    ford = SimpleNamespace(id="otomotiv/ford-otosan", osd_firma="FORD OTOSAN",
                           start_date=None)
    tofas = SimpleNamespace(id="otomotiv/tofas", osd_firma="TOFAŞ",
                            start_date=None)

    df1 = osd.seri_cek(ford, onbellek=onbellek, bugun=date(2026, 9, 4))
    df2 = osd.seri_cek(tofas, onbellek=onbellek, bugun=date(2026, 9, 4))

    assert len(indirilenler) == 1  # ikinci seri önbellekten
    assert list(df1.columns) == ["date", "value"]
    assert df1["value"].iloc[0] == 100.0
    assert df2["value"].iloc[0] == 50.0


def test_seri_cek_bilinmeyen_firmada_yukselir(monkeypatch):
    """Katalogdaki ad bültende yoksa sessizce boş seri yazılmamalı."""
    from types import SimpleNamespace

    from ingest import osd

    monkeypatch.setattr(osd, "_indeks_cek", lambda session=None: {"2026.07": "u"})
    monkeypatch.setattr(osd, "_pdf_indir", lambda url, session=None: b"x")
    monkeypatch.setattr(
        osd, "_bulteni_ayristir",
        lambda baytlar, anahtar: [("FORD OTOSAN", "2026-01-01", 100.0)],
    )

    seri = SimpleNamespace(id="otomotiv/yok", osd_firma="YOK BÖYLE FİRMA",
                           start_date=None)
    with pytest.raises(RuntimeError, match="YOK BÖYLE FİRMA"):
        osd.seri_cek(seri, onbellek={}, bugun=date(2026, 9, 4))
```

`tests/test_run.py` sonuna:

```python
def test_cek_osd_serisini_osd_modulune_yonlendirir(monkeypatch):
    import dataclasses

    from core.catalog import seri_getir
    from ingest import run

    cagrildi = {}

    def sahte_seri_cek(seri, onbellek=None, session=None):
        cagrildi["id"] = seri.id
        cagrildi["onbellek"] = onbellek
        return "DF"

    monkeypatch.setattr(run.osd, "seri_cek", sahte_seri_cek)
    seri = dataclasses.replace(
        seri_getir("enflasyon/tufe-genel"),
        kaynak_tipi="osd", osd_firma="FORD OTOSAN",
        evds_code=None, evds_frequency=None,
    )
    onbellek: dict = {}
    assert run._cek(seri, "ANAHTAR", None, None, None, onbellek) == "DF"
    assert cagrildi["onbellek"] is onbellek
```

`tests/test_catalog.py` sonuna:

```python
def test_otomotiv_kategorisi_on_uc_seri_icerir():
    from core.catalog import seri_listele

    seriler = seri_listele("otomotiv")
    assert len(seriler) == 13
    assert all(s.kaynak_tipi == "osd" for s in seriler)
    assert all(s.osd_firma for s in seriler)


def test_otomotiv_panosu_portfoy_firmalarini_gosterir():
    from core.catalog import kategorileri_yukle

    (kategori,) = [k for k in kategorileri_yukle() if k.slug == "otomotiv"]
    assert kategori.pano == (
        "otomotiv/ford-otosan", "otomotiv/tofas",
        "otomotiv/turk-traktor", "otomotiv/karsan",
    )
```

- [ ] **Step 2: Testleri koştur, başarısız olduklarını gör**

Run: `.venv/bin/python -m pytest tests/test_osd.py tests/test_run.py tests/test_catalog.py -q`
Expected: FAIL — `osd.seri_cek` yok; `run._cek` altı argüman almıyor; `otomotiv` kategorisi yok.

- [ ] **Step 3: `ingest/osd.py`'ye ağ kabuğunu ekle**

Dosyanın başındaki import satırlarına ekleyin:

```python
import io

import pandas as pd
import pdfplumber
import requests
```

Ve dosyanın sonuna:

```python
ZAMAN_ASIMI = 60
_SAYFA_FIRMA_AY = (5, 6, 7, 8)  # 6–9. sayfalar (0-tabanlı)
_SAYFA_AY_TOPLAM = 1            # 2. sayfa


def _indeks_cek(session=None) -> dict[str, str]:
    http = session or requests
    yanit = http.get(INDEKS_URL, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"OSD indeksi HTTP {yanit.status_code}")
    return bulten_baglantilari(yanit.text)


def _pdf_indir(url: str, session=None) -> bytes:
    http = session or requests
    yanit = http.get(url, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"OSD bülteni HTTP {yanit.status_code} ({url})")
    return yanit.content


def _bulteni_ayristir(baytlar: bytes, anahtar: str) -> list[tuple[str, str, float]]:
    """Bir bültenin firma×ay noktalarını çıkarır ve öz-doğrulamayı koşar."""
    yil, ay = int(anahtar[:4]), int(anahtar[5:7])
    with pdfplumber.open(io.BytesIO(baytlar)) as pdf:
        tablolar = [
            t for i in _SAYFA_FIRMA_AY for t in pdf.pages[i].extract_tables()
        ]
        noktalar = firma_aylik_noktalari(tablolar, yil)
        toplamlar = ay_toplamlari(pdf.pages[_SAYFA_AY_TOPLAM].extract_tables()[0])
    dogrula(noktalar, toplamlar, f"{yil}-{ay:02d}-01")
    return noktalar


def seri_cek(seri, onbellek: dict | None = None, session=None,
             bugun: date | None = None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `onbellek` verilirse indeks ve ayrıştırılmış bülten noktaları koşu
    boyunca paylaşılır: 13 seri aynı beş PDF'i okuduğu için yoksa 65
    indirme olurdu.
    """
    bugun = bugun or date.today()
    onbellek = {} if onbellek is None else onbellek

    if "indeks" not in onbellek:
        onbellek["indeks"] = _indeks_cek(session)
    baglantilar = onbellek["indeks"]

    tum_noktalar: list[tuple[str, str, float]] = []
    for anahtar in cekilecek_bultenler(baglantilar, bugun):
        if anahtar not in onbellek:
            baytlar = _pdf_indir(baglantilar[anahtar], session)
            onbellek[anahtar] = _bulteni_ayristir(baytlar, anahtar)
        tum_noktalar.extend(onbellek[anahtar])

    kendi = {
        tarih: deger
        for ad, tarih, deger in tum_noktalar
        if ad == seri.osd_firma
    }
    if not kendi:
        raise RuntimeError(
            f"OSD bültenlerinde firma bulunamadı: {seri.osd_firma!r} "
            f"({seri.id}) — katalogdaki ad bültenle eşleşmiyor olabilir"
        )

    df = pd.DataFrame(sorted(kendi.items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)
```

- [ ] **Step 4: `ingest/run.py`'yi güncelle**

Import satırını değiştirin:

```python
from ingest import epias, evds, osd, yahoo
```

`_cek()` imzasını ve gövdesini değiştirin:

```python
def _cek(seri: Seri, api_key: str | None, tgt: str | None, oturum,
         epias_onbellek: dict | None = None,
         osd_onbellek: dict | None = None):
    """Seriyi kaynak tipine göre doğru istemciye yönlendirir."""
    if seri.kaynak_tipi == "evds":
        return evds.seri_cek(seri, api_key, session=oturum)
    if seri.kaynak_tipi == "yahoo":
        return yahoo.seri_cek(seri, session=oturum)
    if seri.kaynak_tipi == "epias":
        return epias.seri_cek(seri, tgt, session=oturum, onbellek=epias_onbellek)
    if seri.kaynak_tipi == "osd":
        return osd.seri_cek(seri, onbellek=osd_onbellek, session=oturum)
    raise ValueError(f"Bilinmeyen kaynak tipi: {seri.kaynak_tipi}")
```

`epias_onbellek` tanımının yanına ekleyin:

```python
    # 13 OSD serisi aynı beş bülteni paylaşır (bkz. osd.seri_cek).
    osd_onbellek: dict = {}
```

Döngüdeki çağrıyı güncelleyin:

```python
                df = _cek(seri, api_key, tgt, oturum, epias_onbellek, osd_onbellek)
```

- [ ] **Step 5: Kategoriyi ve 13 seriyi katalogda tanımla**

`catalog/categories.yaml` sonuna ekleyin:

```yaml
- slug: otomotiv
  title: Otomotiv
  pano: [otomotiv/ford-otosan, otomotiv/tofas, otomotiv/turk-traktor, otomotiv/karsan]
  note: >-
    Üretim adetleri OSD aylık üretim bültenlerinden alınır; bülten genelde
    takip eden ayın 12–18'i arasında yayımlanır.
```

`catalog/series.yaml` sonuna 13 seriyi ekleyin. `osd_firma` değerleri bültendeki HAM adlardır ve birebir yazılmalıdır:

```yaml
- id: otomotiv/ford-otosan
  title: Ford Otosan Üretim
  category: otomotiv
  kaynak: { name: OSD, url: "https://www.osd.org.tr" }
  kaynak_tipi: osd
  osd_firma: FORD OTOSAN
  unit: "adet"
  freq: monthly
  monthly_agg: sum
  charts: [level, seasonality]

- id: otomotiv/tofas
  title: Tofaş Üretim
  category: otomotiv
  kaynak: { name: OSD, url: "https://www.osd.org.tr" }
  kaynak_tipi: osd
  osd_firma: TOFAŞ
  unit: "adet"
  freq: monthly
  monthly_agg: sum
  charts: [level, seasonality]

- id: otomotiv/turk-traktor
  title: Türk Traktör Üretim
  category: otomotiv
  kaynak: { name: OSD, url: "https://www.osd.org.tr" }
  kaynak_tipi: osd
  osd_firma: TÜRK TRAKTÖR
  unit: "adet"
  freq: monthly
  monthly_agg: sum
  charts: [level, seasonality]

- id: otomotiv/karsan
  title: Karsan Üretim
  category: otomotiv
  kaynak: { name: OSD, url: "https://www.osd.org.tr" }
  kaynak_tipi: osd
  osd_firma: KARSAN
  unit: "adet"
  freq: monthly
  monthly_agg: sum
  charts: [level, seasonality]

- id: otomotiv/otokar
  title: Otokar Üretim
  category: otomotiv
  kaynak: { name: OSD, url: "https://www.osd.org.tr" }
  kaynak_tipi: osd
  osd_firma: OTOKAR
  unit: "adet"
  freq: monthly
  monthly_agg: sum
  charts: [level, seasonality]

- id: otomotiv/anadolu-isuzu
  title: Anadolu Isuzu Üretim
  category: otomotiv
  kaynak: { name: OSD, url: "https://www.osd.org.tr" }
  kaynak_tipi: osd
  osd_firma: A.I.O.S.
  unit: "adet"
  freq: monthly
  monthly_agg: sum
  charts: [level, seasonality]

- id: otomotiv/oyak-renault
  title: Oyak Renault Üretim
  category: otomotiv
  kaynak: { name: OSD, url: "https://www.osd.org.tr" }
  kaynak_tipi: osd
  osd_firma: OYAK RENAULT
  unit: "adet"
  freq: monthly
  monthly_agg: sum
  charts: [level, seasonality]

- id: otomotiv/toyota
  title: Toyota Üretim
  category: otomotiv
  kaynak: { name: OSD, url: "https://www.osd.org.tr" }
  kaynak_tipi: osd
  osd_firma: TOYOTA
  unit: "adet"
  freq: monthly
  monthly_agg: sum
  charts: [level, seasonality]

- id: otomotiv/hyundai
  title: Hyundai Assan Üretim
  category: otomotiv
  kaynak: { name: OSD, url: "https://www.osd.org.tr" }
  kaynak_tipi: osd
  osd_firma: HYUNDAI MOTOR TÜRKİYE
  unit: "adet"
  freq: monthly
  monthly_agg: sum
  charts: [level, seasonality]

- id: otomotiv/mercedes-benz
  title: Mercedes-Benz Türk Üretim
  category: otomotiv
  kaynak: { name: OSD, url: "https://www.osd.org.tr" }
  kaynak_tipi: osd
  osd_firma: M. BENZ TÜRK
  unit: "adet"
  freq: monthly
  monthly_agg: sum
  charts: [level, seasonality]

- id: otomotiv/man
  title: MAN Türkiye Üretim
  category: otomotiv
  kaynak: { name: OSD, url: "https://www.osd.org.tr" }
  kaynak_tipi: osd
  osd_firma: MAN TÜRKİYE
  unit: "adet"
  freq: monthly
  monthly_agg: sum
  charts: [level, seasonality]

- id: otomotiv/temsa
  title: Temsa Üretim
  category: otomotiv
  kaynak: { name: OSD, url: "https://www.osd.org.tr" }
  kaynak_tipi: osd
  osd_firma: TEMSA
  unit: "adet"
  freq: monthly
  monthly_agg: sum
  charts: [level, seasonality]

- id: otomotiv/hattat-traktor
  title: Hattat Traktör Üretim
  category: otomotiv
  kaynak: { name: OSD, url: "https://www.osd.org.tr" }
  kaynak_tipi: osd
  osd_firma: HATTAT TRAKTÖR
  unit: "adet"
  freq: monthly
  monthly_agg: sum
  charts: [level, seasonality]
```

Seri sayısını sabitleyen İKİ test 27 → 40 güncellenir:

- `tests/test_catalog.py:31` — `assert len(serileri_yukle()) == 27`
- `tests/test_catalog.py:430` — `assert len(serileri_yukle()) == 27`

**DİKKAT:** `tests/test_takvim.py` içinde de `== 27` geçen bir satır var
(`assert satir.bekleme_gunu == 27`) ama o gün sayısıdır, seri sayısı DEĞİL —
DOKUNMAYIN. Körü körüne `grep`+`sed` yapmayın; yalnızca yukarıdaki iki satırı
değiştirin.

- [ ] **Step 6: Testleri koştur, geçtiklerini gör**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — tümü.

- [ ] **Step 7: Gerçek veriyi çek**

```bash
.venv/bin/python -m ingest.run --only otomotiv/ford-otosan
```

Bu tek seri bile beş PDF indirir (~3,5 MB) ve birkaç dakika sürebilir. ÖNPLANDA çalıştırın, bitmesini bekleyin.

Sonra tüm otomotiv serilerini çekmek için `--only` olmadan koşmak yerine tek tek çağırmayın — her çağrı önbelleği sıfırdan kurar. Bunun yerine tam koşu yapın:

```bash
set -a; . ./.env; set +a
.venv/bin/python -m ingest.run
```

Bu 40 serinin tamamını çeker; OSD önbelleği sayesinde bülten indirmesi beş kez olur.

- [ ] **Step 8: Veriyi doğrula**

```bash
.venv/bin/python -c "
import pandas as pd
from core.catalog import seri_listele
from core.data import seri_csv_oku, seri_yolu
toplam_ay = {}
for s in seri_listele('otomotiv'):
    d = seri_csv_oku(seri_yolu(s.id))
    print(f'{s.id:<30}{len(d):>5} nokta  {d.index.min().date()}→{d.index.max().date()}  '
          f'medyan {d.value.median():>9,.0f}')
    assert d.index.is_unique and d.index.is_monotonic_increasing, s.id
    for t, v in d.value.items():
        toplam_ay[t] = toplam_ay.get(t, 0) + v
print()
son = sorted(toplam_ay)[-3:]
for t in son:
    print(f'sektör toplamı {t.date()}: {toplam_ay[t]:,.0f} adet')
"
```

**Kabul ölçütleri:**
- 13 seri de nokta üretir; tarih aralığı 2022-01 → cari yılın son bülten ayı
- Tarihler tekil ve artan
- Ford Otosan medyanı ~20.000–45.000 adet
- Türk Traktör medyanı ~1.000–5.000 adet
- Aylık sektör toplamı ~80.000–150.000 adet bandında

Bir ölçüt tutmuyorsa DURUN, sebebini raporlayın, yanlış veriyi commit'lemeyin.

- [ ] **Step 9: Tarayıcıda doğrula**

```bash
.venv/bin/streamlit run app.py --server.headless true --server.port 8600 \
  > /tmp/bv-otomotiv.log 2>&1 &
```

`http://localhost:8600/_stcore/health` `ok` dönene kadar bekleyin, sonra `http://localhost:8600/otomotiv` adresinde doğrulayın:

1. Sol menüde "Otomotiv" görünüyor
2. Panoda dört kart: Ford Otosan, Tofaş, Türk Traktör, Karsan — bu sırada, hepsinde değer ve YoY dolu
3. On üç grafik kartı gerçek veriyle çiziliyor
4. Veri Takvimi otomotiv serilerini "güncel" ya da "bekleniyor" gösteriyor, "okunamadı" değil
5. Mevcut yedi kategori bozulmamış
6. `/tmp/bv-otomotiv.log` içinde traceback yok

Ekran görüntüsü alın, yolunu rapora yazın. Sunucuyu kapatın (`pkill -f "streamlit run app.py"`).

- [ ] **Step 10: Commit**

```bash
git add ingest/osd.py ingest/run.py catalog/ tests/ data/otomotiv
git commit -m "feat: OSD otomotiv serileri — 13 firma aylık üretim"
```

---

## Self-Review

**Spec coverage:**

| Spec gereksinimi | Karşılayan görev |
|---|---|
| `requirements` ayrımı, `pdfplumber` yalnızca ingest | Task 1 |
| `osd` kaynak tipi, `Seri.osd_firma`, `KAYNAK_ALANLARI` | Task 2 |
| İndeks kazıma, ters bölü düzeltme, tire/alt çizgi | Task 3 (`bulten_baglantilari`) |
| Aralık + güncel bülten seçimi, Ocak kenar durumu | Task 3 (`cekilecek_bultenler`) |
| `\x00` normalizasyonu | Task 3 (`firma_adini_normalize`) |
| 6–9. sayfa okuma, bölümler arası toplama | Task 3 (`firma_aylik_noktalari`) |
| Alt toplam satırlarının dışlanması | Task 3 (`_firma_satiri_mi`) |
| Öz-doğrulama (s2 TOPLAM karşılaştırması) | Task 3 (`dogrula`), Task 4 (`_bulteni_ayristir`) |
| Hiç bağlantı bulunamazsa RuntimeError | Task 3 (`bulten_baglantilari`) |
| PDF önbelleği, koşu başına paylaşım | Task 4 (`seri_cek`, `run.py`) |
| 13 seri, `otomotiv` kategorisi, pano | Task 4 Step 5 |
| Gerçek veri kabul ölçütleri | Task 4 Step 8 |
| Tarayıcı doğrulaması | Task 4 Step 9 |
| Ağ smoke testi | **BOŞLUK — aşağıya bakın** |

**Kapatılan boşluk:** Spec, `@pytest.mark.network` smoke testi istiyor. Task 4 Step 10'un commit'ine şu ek dahildir — `tests/test_smoke_network.py` sonuna:

```python
def test_osd_indeksi_bulten_baglantisi_donduruyor():
    """İndeks yapısı değişirse ingest kırılmadan önce burada görülür."""
    import requests

    from ingest.osd import INDEKS_URL, ZAMAN_ASIMI, bulten_baglantilari

    yanit = requests.get(INDEKS_URL, timeout=ZAMAN_ASIMI)
    assert yanit.status_code == 200

    baglantilar = bulten_baglantilari(yanit.text)
    assert baglantilar, "hiç bülten bağlantısı yok"
    assert all(u.endswith(".pdf") for u in baglantilar.values())
    assert all(u.startswith("https://www.osd.org.tr/") for u in baglantilar.values())
```

`git add tests/test_smoke_network.py` Task 4 Step 10 commit'ine eklenir.

**Placeholder taraması:** Yok. Task 4 Step 5'teki 13 seri tam olarak yazıldı (kısaltma veya "diğerleri benzer" yok); `osd_firma` değerleri canlı bültenden alınan ham adlardır.

**Type consistency:** Task 3'ün ürettiği `firma_aylik_noktalari`, `ay_toplamlari`, `dogrula` imzaları Task 4'ün `_bulteni_ayristir`'inde aynen çağrılıyor. `Seri.osd_firma` Task 2'de tanımlanıp Task 4'ün `seri_cek`'inde okunuyor. `run._cek` altı argümana çıkıyor ve tek çağrı yeri aynı adımda güncelleniyor; `tests/test_run.py`'deki yeni test bu imzayı kullanıyor. Mevcut epias testlerindeki `_cek` çağrıları beş argümanlıydı — `osd_onbellek` varsayılanlı olduğu için kırılmazlar.

**Bilinçli sapma:** `seri_cek` testleri `_indeks_cek`/`_pdf_indir`/`_bulteni_ayristir`'i monkeypatch'liyor; gerçek PDF fixture'ı repoya konmuyor (700 KB × 5). Ayrıştırma mantığı Task 3'te saf fonksiyonlar üzerinden zaten tam test edilmiş durumda; Task 4'ün testleri yalnızca önbellek paylaşımını ve firma eşleşmesini doğruluyor.
