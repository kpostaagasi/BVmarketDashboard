# Faz 1: Streamlit İskeleti + EVDS Dilimi — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `BVmarketDashboard` repo'sunu Next.js'ten Streamlit'e çevirip, TCMB EVDS'ten gelen 13 makro serisini katalog-sürümlü dört kategori sayfasında hazır istatistikli grafik kartlarıyla yayına almak.

**Architecture:** Katalog (`catalog/*.yaml`) tek doğruluk kaynağıdır; sayfalar ondan üretilir. Veri repoda CSV olarak yaşar (`data/<kategori>/<seri>.csv`), GitHub Actions cron'u günlük çeker ve commit'ler; Streamlit uygulaması yalnızca okur ve runtime'da hiç secret kullanmaz. Tüm okuma tek bir `load_series()` kapısından geçer, böylece ileride harici veritabanına geçiş sayfaları etkilemez.

**Tech Stack:** Python 3.12 · Streamlit ≥1.49 · pandas ≥2.2 · Plotly ≥5.24 · PyYAML · requests · pytest · GitHub Actions · Streamlit Community Cloud

**Spec:** `docs/superpowers/specs/2026-08-27-streamlit-dashboard-design.md`

## Global Constraints

- **Python 3.12.** Actions ve Community Cloud aynı sürümü kullanır.
- **Streamlit ≥ 1.49** — `st.navigation` 1.36'da, `st.segmented_control` 1.40'ta geldi; floor, final review sırasında `use_container_width`'in kaldırılma tarihi geçtiği için 1.49'a çıkarıldı.
- **Arayüz dili Türkçe.** Başlıklar, etiketler, hata mesajları Türkçe. Kod içi isimler ve fonksiyon adları da Türkçe (mevcut repo bu geleneği izliyor).
- **Veri dosyaları yalnızca `date,value` içerir.** Metadata katalogda yaşar, veri dosyasında asla.
- **CSV yazımı `float_format="%.5f"`** — EVDS `decimal: 5` döndürüyor; sabit format diff gürültüsünü engeller.
- **Tarih penceresi:** katalogdaki opsiyonel `start_date`, tanımlı değilse bugünden 15 yıl geriye.
- **Her ingest koşusu tam pencereyi yeniden çeker.** Artımlı ekleme yok — revizyonlar yakalanmalı.
- **Renk paleti** (doğrulanmış, `theme.py`'de sabit): seri renkleri `#3987e5`, `#d95926`, `#199e70`; kart yüzeyi `#16273F`; sayfa zemini `#0F1E33`. Bu değerler değiştirilmemeli — dataviz doğrulayıcısından geçmiş bir settir.
- **Dual-axis grafik yasak.** İki farklı ölçekteki büyüklük iki ayrı grafiktir.
- **Runtime'da secret yok.** `EVDS_API_KEY` yalnızca `ingest/` tarafında ve yalnızca Actions ortamında okunur. Streamlit kodunda geçmez.

---

### Task 1: Repo pivotu ve katalog katmanı

Next.js uygulaması silinir, Python iskeleti kurulur, katalog okuyucu ve doğrulayıcı yazılır. Bu görevin sonunda `pytest` yeşil ve katalog 13 seriyi doğrulanmış olarak veriyor.

**Files:**
- Delete: `src/`, `.next/`, `public/`, `scripts/`, `package.json`, `package-lock.json`, `next.config.ts`, `tsconfig.json`, `next-env.d.ts`, `eslint.config.mjs`, `postcss.config.mjs`, `.github/workflows/update.yml`
- Create: `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`, `.gitignore`, `.streamlit/config.toml`
- Create: `catalog/categories.yaml`, `catalog/series.yaml`
- Create: `core/__init__.py`, `core/catalog.py`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Consumes: hiçbir şey (ilk görev)
- Produces:
  - `core.catalog.Kaynak(name: str, url: str)` — frozen dataclass
  - `core.catalog.Seri(id, title, category, kaynak: Kaynak, unit, freq, evds_code, evds_frequency, charts: tuple[str, ...], monthly_agg: str = "mean", start_date: str | None = None)` — frozen dataclass
  - `core.catalog.Kategori(slug: str, title: str)` — frozen dataclass
  - `core.catalog.KatalogHatasi(Exception)`
  - `core.catalog.kategorileri_yukle() -> list[Kategori]`
  - `core.catalog.serileri_yukle() -> list[Seri]`
  - `core.catalog.seri_listele(kategori: str | None = None) -> list[Seri]`
  - `core.catalog.seri_getir(seri_id: str) -> Seri`
  - `core.catalog.KOK: pathlib.Path` — repo kökü

- [ ] **Step 1: Next.js uygulamasını sil ve Python iskeletini kur**

Bu adım geri dönüşü zor; kullanıcı onayı spec'te kayıtlı (`Kapsam kararları` → Repo).

```bash
git rm -r --cached .next 2>/dev/null || true
rm -rf src .next public scripts node_modules
git rm -r -q --ignore-unmatch src public scripts
git rm -q --ignore-unmatch package.json package-lock.json next.config.ts \
  tsconfig.json next-env.d.ts eslint.config.mjs postcss.config.mjs \
  .github/workflows/update.yml
rm -rf data          # eski kategori yolları (tufe/, kur/, faiz/…) artık geçersiz
git rm -r -q --ignore-unmatch data
mkdir -p catalog core ingest tests .streamlit .github/workflows
```

`data/` de siliniyor: eski dosyalar `tufe/genel.json` gibi eski kategori yollarında ve JSON formatında; Task 4 onları yeni yollarda CSV olarak yeniden üretecek. Veri kaybı yok — git history'de duruyorlar.

- [ ] **Step 2: Bağımlılık ve proje dosyalarını yaz**

`requirements.txt` (Streamlit Cloud bunu kurar — pytest buraya girmez):

```
streamlit>=1.49
pandas>=2.2
plotly>=5.24
PyYAML>=6.0
requests>=2.32
```

`requirements-dev.txt`:

```
-r requirements.txt
pytest>=8.0
```

`pyproject.toml` — `pythonpath` olmadan `core`/`ingest` importları testlerde çözülmez:

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

`.gitignore`:

```
__pycache__/
*.pyc
.pytest_cache/
.venv/
venv/
.DS_Store
.streamlit/secrets.toml
```

`.streamlit/config.toml`:

```toml
[theme]
base = "dark"
primaryColor = "#E8B54D"
backgroundColor = "#0F1E33"
secondaryBackgroundColor = "#16273F"
textColor = "#E6EDF5"

[server]
headless = true
```

- [ ] **Step 3: Kategori katalogunu yaz**

`catalog/categories.yaml`:

```yaml
- slug: ekonomi-makro
  title: Ekonomi & Makro
- slug: enflasyon
  title: Enflasyon Verileri
- slug: insaat
  title: İnşaat
- slug: kredi-karti
  title: Kredi Kartı Harcamaları
```

- [ ] **Step 4: Seri katalogunu yaz**

`catalog/series.yaml` — 13 serinin tamamı. EVDS kodları `categories/withDatagroups` + `serieList` taramasıyla doğrulanmıştır, tahmin değildir; değiştirmeyin.

```yaml
- id: enflasyon/tufe-genel
  title: TÜFE Genel Endeks
  category: enflasyon
  kaynak: { name: TCMB EVDS, url: "https://evds3.tcmb.gov.tr" }
  unit: "Endeks (2025=100)"
  freq: monthly
  evds_code: TP.TUKFIY2025.GENEL
  evds_frequency: "5"
  charts: [seasonality, level]

- id: enflasyon/tufe-gida
  title: TÜFE Gıda ve Alkolsüz İçecekler
  category: enflasyon
  kaynak: { name: TCMB EVDS, url: "https://evds3.tcmb.gov.tr" }
  unit: "Endeks (2025=100)"
  freq: monthly
  evds_code: TP.TUKFIY2025.01
  evds_frequency: "5"
  charts: [seasonality, level]

- id: ekonomi-makro/usd-try
  title: USD/TRY (TCMB Alış)
  category: ekonomi-makro
  kaynak: { name: TCMB EVDS, url: "https://evds3.tcmb.gov.tr" }
  unit: "TL"
  freq: daily
  evds_code: TP.DK.USD.A.YTL
  evds_frequency: "1"
  monthly_agg: last
  charts: [level, seasonality]

- id: ekonomi-makro/eur-try
  title: EUR/TRY (TCMB Alış)
  category: ekonomi-makro
  kaynak: { name: TCMB EVDS, url: "https://evds3.tcmb.gov.tr" }
  unit: "TL"
  freq: daily
  evds_code: TP.DK.EUR.A.YTL
  evds_frequency: "1"
  monthly_agg: last
  charts: [level, seasonality]

- id: ekonomi-makro/politika-faizi
  title: TCMB Ağırlıklı Ortalama Fonlama Maliyeti
  category: ekonomi-makro
  kaynak: { name: TCMB EVDS, url: "https://evds3.tcmb.gov.tr" }
  unit: "%"
  freq: daily
  evds_code: TP.APIFON4
  evds_frequency: "1"
  monthly_agg: last
  charts: [level]

- id: ekonomi-makro/mevduat-faizi-tl
  title: TL Mevduat Faizi (3 Aya Kadar, Stok)
  category: ekonomi-makro
  kaynak: { name: TCMB EVDS, url: "https://evds3.tcmb.gov.tr" }
  unit: "%"
  freq: monthly
  evds_code: TP.MT210AGS.TRY.MT02
  evds_frequency: "5"
  charts: [level, seasonality]

- id: ekonomi-makro/tuketici-guven
  title: Tüketici Güven Endeksi
  category: ekonomi-makro
  kaynak: { name: TCMB EVDS, url: "https://evds3.tcmb.gov.tr" }
  unit: "Endeks"
  freq: monthly
  evds_code: TP.TG2.Y01
  evds_frequency: "5"
  charts: [seasonality, level]

- id: ekonomi-makro/yabanci-hisse
  title: Yabancı Yatırımcı Hisse Senedi Net Alım-Satım
  category: ekonomi-makro
  kaynak: { name: TCMB EVDS, url: "https://evds3.tcmb.gov.tr" }
  unit: "Milyon USD"
  freq: weekly
  evds_code: TP.MKNETHAR.M7
  evds_frequency: "2"
  monthly_agg: sum
  charts: [level, seasonality]

- id: ekonomi-makro/yabanci-dibs
  title: Yabancı Yatırımcı DİBS Net Alım-Satım
  category: ekonomi-makro
  kaynak: { name: TCMB EVDS, url: "https://evds3.tcmb.gov.tr" }
  unit: "Milyon USD"
  freq: weekly
  evds_code: TP.MKNETHAR.M8
  evds_frequency: "2"
  monthly_agg: sum
  charts: [level, seasonality]

- id: insaat/konut-fiyat-endeksi
  title: Konut Fiyat Endeksi (Türkiye)
  category: insaat
  kaynak: { name: TCMB EVDS, url: "https://evds3.tcmb.gov.tr" }
  unit: "Endeks (2010=100)"
  freq: monthly
  evds_code: TP.KFE.TR
  evds_frequency: "5"
  charts: [level, seasonality]

- id: insaat/konut-satis-toplam
  title: Toplam Konut Satışları
  category: insaat
  kaynak: { name: TCMB EVDS, url: "https://evds3.tcmb.gov.tr" }
  unit: "Adet"
  freq: monthly
  evds_code: TP.AKONUTSAT1.KTRTOPLAM
  evds_frequency: "5"
  charts: [seasonality, level]

- id: insaat/konut-satis-ipotekli
  title: İpotekli Konut Satışları
  category: insaat
  kaynak: { name: TCMB EVDS, url: "https://evds3.tcmb.gov.tr" }
  unit: "Adet"
  freq: monthly
  evds_code: TP.AKONUTSAT2.KTRTOPLAM
  evds_frequency: "5"
  charts: [seasonality, level]

- id: kredi-karti/harcama-toplam
  title: Kredi Kartı Harcamaları (Toplam)
  category: kredi-karti
  kaynak: { name: TCMB EVDS, url: "https://evds3.tcmb.gov.tr" }
  unit: "Bin TL"
  freq: weekly
  evds_code: TP.KKHARTUT.KT1
  evds_frequency: "2"
  monthly_agg: sum
  charts: [level, seasonality]
```

- [ ] **Step 5: Katalog testlerini yaz (başarısız olmalı)**

`tests/test_catalog.py`:

```python
import pytest

from core.catalog import (
    KatalogHatasi,
    Seri,
    kategorileri_yukle,
    seri_getir,
    seri_listele,
    serileri_yukle,
)


def test_dort_kategori_yuklenir():
    kategoriler = kategorileri_yukle()
    assert [k.slug for k in kategoriler] == [
        "ekonomi-makro",
        "enflasyon",
        "insaat",
        "kredi-karti",
    ]


def test_onuc_seri_yuklenir():
    assert len(serileri_yukle()) == 13


def test_seri_alanlari_dogru_tiplerde():
    seri = seri_getir("enflasyon/tufe-genel")
    assert isinstance(seri, Seri)
    assert seri.title == "TÜFE Genel Endeks"
    assert seri.category == "enflasyon"
    assert seri.kaynak.name == "TCMB EVDS"
    assert seri.evds_code == "TP.TUKFIY2025.GENEL"
    assert seri.evds_frequency == "5"
    assert seri.charts == ("seasonality", "level")
    assert seri.monthly_agg == "mean"
    assert seri.start_date is None


def test_kategoriye_gore_filtreleme():
    idler = [s.id for s in seri_listele("insaat")]
    assert idler == [
        "insaat/konut-fiyat-endeksi",
        "insaat/konut-satis-toplam",
        "insaat/konut-satis-ipotekli",
    ]


def test_bilinmeyen_seri_hata_verir():
    with pytest.raises(KatalogHatasi):
        seri_getir("yok/boyle-bir-seri")


def test_her_seri_id_si_kendi_kategorisiyle_baslar():
    for seri in serileri_yukle():
        assert seri.id.startswith(f"{seri.category}/"), seri.id


def test_her_seri_bilinen_bir_kategoriye_ait():
    sluglar = {k.slug for k in kategorileri_yukle()}
    for seri in serileri_yukle():
        assert seri.category in sluglar, seri.id


def test_idler_tekil():
    idler = [s.id for s in serileri_yukle()]
    assert len(idler) == len(set(idler))


def test_alan_degerleri_gecerli_kumelerde():
    for seri in serileri_yukle():
        assert seri.freq in {"daily", "weekly", "monthly"}, seri.id
        assert seri.evds_frequency in {"1", "2", "5"}, seri.id
        assert seri.monthly_agg in {"mean", "last", "sum"}, seri.id
        assert seri.charts, seri.id
        assert set(seri.charts) <= {"seasonality", "level"}, seri.id
        assert seri.evds_code, seri.id
```

- [ ] **Step 6: Testleri koştur, başarısız olduklarını gör**

Run: `pytest tests/test_catalog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.catalog'`

- [ ] **Step 7: `core/catalog.py`'yi yaz**

`core/__init__.py` boş dosya olarak oluşturulur.

`core/catalog.py`:

```python
"""Katalog: serilerin ve kategorilerin tek doğruluk kaynağı.

Metadata burada yaşar; veri dosyaları yalnızca `date,value` içerir.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

KOK = Path(__file__).resolve().parent.parent
KATALOG_DIZINI = KOK / "catalog"

GECERLI_FREKANSLAR = {"daily", "weekly", "monthly"}
GECERLI_EVDS_FREKANSLARI = {"1", "2", "5"}
GECERLI_GRAFIKLER = {"seasonality", "level"}
GECERLI_AYLIK_AGG = {"mean", "last", "sum"}


class KatalogHatasi(Exception):
    """Katalog dosyaları tutarsız ya da eksik."""


@dataclass(frozen=True)
class Kaynak:
    name: str
    url: str


@dataclass(frozen=True)
class Kategori:
    slug: str
    title: str


@dataclass(frozen=True)
class Seri:
    id: str
    title: str
    category: str
    kaynak: Kaynak
    unit: str
    freq: str
    evds_code: str
    evds_frequency: str
    charts: tuple[str, ...]
    monthly_agg: str = "mean"
    start_date: str | None = None


def _yaml_oku(ad: str) -> list[dict]:
    yol = KATALOG_DIZINI / ad
    if not yol.exists():
        raise KatalogHatasi(f"Katalog dosyası bulunamadı: {yol}")
    icerik = yaml.safe_load(yol.read_text(encoding="utf-8"))
    if not isinstance(icerik, list) or not icerik:
        raise KatalogHatasi(f"{ad} boş ya da liste değil")
    return icerik


@lru_cache(maxsize=1)
def kategorileri_yukle() -> tuple[Kategori, ...]:
    kategoriler = []
    gorulen: set[str] = set()
    for ham in _yaml_oku("categories.yaml"):
        slug = ham["slug"]
        if slug in gorulen:
            raise KatalogHatasi(f"Kategori slug'ı tekrar ediyor: {slug}")
        gorulen.add(slug)
        kategoriler.append(Kategori(slug=slug, title=ham["title"]))
    return tuple(kategoriler)


@lru_cache(maxsize=1)
def serileri_yukle() -> tuple[Seri, ...]:
    sluglar = {k.slug for k in kategorileri_yukle()}
    seriler = []
    gorulen: set[str] = set()

    for ham in _yaml_oku("series.yaml"):
        seri = Seri(
            id=ham["id"],
            title=ham["title"],
            category=ham["category"],
            kaynak=Kaynak(**ham["kaynak"]),
            unit=ham["unit"],
            freq=ham["freq"],
            evds_code=ham["evds_code"],
            evds_frequency=str(ham["evds_frequency"]),
            charts=tuple(ham["charts"]),
            monthly_agg=ham.get("monthly_agg", "mean"),
            start_date=ham.get("start_date"),
        )
        _dogrula(seri, sluglar, gorulen)
        gorulen.add(seri.id)
        seriler.append(seri)

    return tuple(seriler)


def _dogrula(seri: Seri, kategori_sluglari: set[str], gorulen: set[str]) -> None:
    if seri.id in gorulen:
        raise KatalogHatasi(f"Seri id'si tekrar ediyor: {seri.id}")
    if seri.category not in kategori_sluglari:
        raise KatalogHatasi(
            f"{seri.id}: '{seri.category}' kategorisi categories.yaml'da yok"
        )
    if not seri.id.startswith(f"{seri.category}/"):
        raise KatalogHatasi(
            f"{seri.id}: id, kategori adıyla başlamalı ('{seri.category}/')"
        )
    if seri.freq not in GECERLI_FREKANSLAR:
        raise KatalogHatasi(f"{seri.id}: geçersiz freq '{seri.freq}'")
    if seri.evds_frequency not in GECERLI_EVDS_FREKANSLARI:
        raise KatalogHatasi(
            f"{seri.id}: geçersiz evds_frequency '{seri.evds_frequency}'"
        )
    if seri.monthly_agg not in GECERLI_AYLIK_AGG:
        raise KatalogHatasi(f"{seri.id}: geçersiz monthly_agg '{seri.monthly_agg}'")
    if not seri.charts:
        raise KatalogHatasi(f"{seri.id}: en az bir grafik tanımlı olmalı")
    if not set(seri.charts) <= GECERLI_GRAFIKLER:
        raise KatalogHatasi(f"{seri.id}: bilinmeyen grafik türü {seri.charts}")
    if not seri.evds_code:
        raise KatalogHatasi(f"{seri.id}: evds_code boş")


def seri_listele(kategori: str | None = None) -> list[Seri]:
    seriler = serileri_yukle()
    if kategori is None:
        return list(seriler)
    return [s for s in seriler if s.category == kategori]


def seri_getir(seri_id: str) -> Seri:
    for seri in serileri_yukle():
        if seri.id == seri_id:
            return seri
    raise KatalogHatasi(f"Katalogda böyle bir seri yok: {seri_id}")
```

- [ ] **Step 8: Testleri koştur, geçtiklerini gör**

Run: `pip install -r requirements-dev.txt && pytest tests/test_catalog.py -v`
Expected: PASS — 9 test

`kategorileri_yukle()` `tuple` döndürüyor ama test `[k.slug for k in ...]` ile listeye çeviriyor; `lru_cache` hashable dönüş tipi gerektirdiği için tuple zorunlu.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat: repo pivotu ve katalog katmanı

Next.js uygulaması kaldırıldı, Python iskeleti kuruldu.
catalog/*.yaml 13 EVDS serisini ve 4 kategoriyi tanımlıyor;
core/catalog.py yükleme + doğrulama yapıyor."
```

---

### Task 2: İstatistik katmanı

Grafik kartındaki hazır istatistikleri (son değer, MoM, YoY, 12 aylık aralık) ve YoY%/MoM% görünüm dönüşümlerini üreten saf pandas fonksiyonları. Streamlit'e hiç bağımlılığı yok, tamamı test edilebilir.

**Files:**
- Create: `core/stats.py`
- Test: `tests/test_stats.py`

**Interfaces:**
- Consumes: hiçbir şey (saf pandas)
- Produces:
  - `core.stats.son_tarih(df: pd.DataFrame) -> pd.Timestamp`
  - `core.stats.son_deger(df: pd.DataFrame) -> float`
  - `core.stats.mom(df: pd.DataFrame) -> float | None` — yüzde, ör. `-12.7`
  - `core.stats.yoy(df: pd.DataFrame) -> float | None`
  - `core.stats.aralik_12a(df: pd.DataFrame) -> tuple[float, float] | None`
  - `core.stats.seri_yoy(df: pd.DataFrame) -> pd.DataFrame`
  - `core.stats.seri_mom(df: pd.DataFrame) -> pd.DataFrame`
  - `core.stats.gorunum_uygula(df: pd.DataFrame, gorunum: str) -> pd.DataFrame` — `gorunum` ∈ {`"Varsayılan"`, `"YoY %"`, `"MoM %"`}

Tüm fonksiyonlar `DatetimeIndex`'li ve tek `value` sütunlu DataFrame alır (Task 3'ün `load_series()` çıktısı).

- [ ] **Step 1: Testleri yaz (başarısız olmalı)**

`tests/test_stats.py`:

```python
import pandas as pd
import pytest

from core.stats import (
    aralik_12a,
    gorunum_uygula,
    mom,
    seri_mom,
    seri_yoy,
    son_deger,
    son_tarih,
    yoy,
)


def aylik_df(degerler, baslangic="2024-01-01"):
    idx = pd.date_range(baslangic, periods=len(degerler), freq="MS", name="date")
    return pd.DataFrame({"value": degerler}, index=idx)


def test_son_tarih_ve_son_deger():
    df = aylik_df([10.0, 20.0, 30.0])
    assert son_tarih(df) == pd.Timestamp("2024-03-01")
    assert son_deger(df) == 30.0


def test_mom_bir_onceki_aya_gore_yuzde():
    df = aylik_df([100.0, 110.0])
    assert mom(df) == pytest.approx(10.0)


def test_yoy_on_iki_ay_oncesine_gore_yuzde():
    df = aylik_df([100.0] + [0.0] * 11 + [125.0])
    assert yoy(df) == pytest.approx(25.0)


def test_yoy_yeterli_gecmis_yoksa_none():
    df = aylik_df([100.0, 110.0, 120.0])
    assert yoy(df) is None


def test_mom_tek_nokta_varsa_none():
    df = aylik_df([100.0])
    assert mom(df) is None


def test_sifir_taban_none_dondurur():
    df = aylik_df([0.0, 50.0])
    assert mom(df) is None


def test_aralik_12a_son_on_iki_ayin_min_maksi():
    # 24 ay: ilk 12 ay 1..12, sonraki 12 ay 100..111
    df = aylik_df([float(v) for v in range(1, 13)] + [float(v) for v in range(100, 112)])
    assert aralik_12a(df) == (100.0, 111.0)


def test_gunluk_seride_mom_bir_ay_oncesine_bakar():
    idx = pd.date_range("2026-01-01", periods=60, freq="D", name="date")
    df = pd.DataFrame({"value": [float(i) for i in range(60)]}, index=idx)
    # son gün 2026-03-01 (değer 59); bir ay öncesi 2026-02-01 (değer 31)
    assert mom(df) == pytest.approx((59 / 31 - 1) * 100)


def test_seri_yoy_her_nokta_icin_yuzde_uretir():
    df = aylik_df([100.0] * 12 + [110.0] * 12)
    sonuc = seri_yoy(df)
    assert sonuc.loc[pd.Timestamp("2025-01-01"), "value"] == pytest.approx(10.0)
    assert pd.isna(sonuc.loc[pd.Timestamp("2024-01-01"), "value"])


def test_seri_mom_her_nokta_icin_yuzde_uretir():
    df = aylik_df([100.0, 110.0, 121.0])
    sonuc = seri_mom(df)
    assert sonuc.loc[pd.Timestamp("2024-02-01"), "value"] == pytest.approx(10.0)
    assert sonuc.loc[pd.Timestamp("2024-03-01"), "value"] == pytest.approx(10.0)


def test_gorunum_uygula_varsayilan_ayni_dfyi_dondurur():
    df = aylik_df([1.0, 2.0])
    pd.testing.assert_frame_equal(gorunum_uygula(df, "Varsayılan"), df)


def test_gorunum_uygula_bilinmeyen_gorunumde_hata_verir():
    df = aylik_df([1.0, 2.0])
    with pytest.raises(ValueError):
        gorunum_uygula(df, "Haftalık %")
```

- [ ] **Step 2: Testleri koştur, başarısız olduklarını gör**

Run: `pytest tests/test_stats.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.stats'`

- [ ] **Step 3: `core/stats.py`'yi yaz**

```python
"""Grafik kartlarındaki hazır istatistikler ve görünüm dönüşümleri.

Tüm fonksiyonlar DatetimeIndex'li, tek `value` sütunlu DataFrame alır.
Değişim hesapları konumsal kaydırma (`shift`) değil tarih tabanlı `asof`
mantığı kullanır: aylık, haftalık ve günlük seriler aynı kodla doğru
sonuç verir.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

VARSAYILAN = "Varsayılan"
YOY = "YoY %"
MOM = "MoM %"
GORUNUMLER = (VARSAYILAN, YOY, MOM)


def son_tarih(df: pd.DataFrame) -> pd.Timestamp:
    return df.index.max()


def son_deger(df: pd.DataFrame) -> float:
    return float(df.loc[son_tarih(df), "value"])


def _asof(df: pd.DataFrame, hedef: pd.Timestamp) -> float | None:
    """`hedef` tarihinde ya da ondan önceki en son değer."""
    uygun = df.index[df.index <= hedef]
    if len(uygun) == 0:
        return None
    return float(df.loc[uygun.max(), "value"])


def _degisim(df: pd.DataFrame, offset: pd.DateOffset) -> float | None:
    if df.empty:
        return None
    simdi = son_tarih(df)
    hedef = simdi - offset
    onceki = _asof(df, hedef)
    if onceki is None or onceki == 0:
        return None
    # _asof, hedeften önce hiç nokta yoksa None döner; ama hedef ilk
    # noktadan sonraysa ve seri kısaysa aynı noktayı döndürebilir.
    if df.index.min() > hedef:
        return None
    return (son_deger(df) / onceki - 1) * 100


def mom(df: pd.DataFrame) -> float | None:
    return _degisim(df, pd.DateOffset(months=1))


def yoy(df: pd.DataFrame) -> float | None:
    return _degisim(df, pd.DateOffset(years=1))


def aralik_12a(df: pd.DataFrame) -> tuple[float, float] | None:
    if df.empty:
        return None
    pencere = df[df.index > son_tarih(df) - pd.DateOffset(months=12)]
    if len(pencere) < 2:
        return None
    return (float(pencere["value"].min()), float(pencere["value"].max()))


def _onceki_degerler(df: pd.DataFrame, offset: pd.DateOffset) -> np.ndarray:
    """Her nokta için `offset` kadar önceki (ya da ondan önceki en son) değer."""
    hedefler = df.index - offset
    konum = df.index.searchsorted(hedefler, side="right") - 1
    degerler = df["value"].to_numpy()
    sonuc = np.where(konum >= 0, degerler[konum.clip(min=0)], np.nan)
    # Hedef, serinin ilk noktasından öndeyse karşılaştırma yapılamaz.
    return np.where(hedefler < df.index.min(), np.nan, sonuc)


def _seri_degisim(df: pd.DataFrame, offset: pd.DateOffset) -> pd.DataFrame:
    onceki = _onceki_degerler(df, offset)
    with np.errstate(divide="ignore", invalid="ignore"):
        yuzde = (df["value"].to_numpy() / np.where(onceki == 0, np.nan, onceki) - 1) * 100
    return pd.DataFrame({"value": yuzde}, index=df.index)


def seri_yoy(df: pd.DataFrame) -> pd.DataFrame:
    return _seri_degisim(df, pd.DateOffset(years=1))


def seri_mom(df: pd.DataFrame) -> pd.DataFrame:
    return _seri_degisim(df, pd.DateOffset(months=1))


def gorunum_uygula(df: pd.DataFrame, gorunum: str) -> pd.DataFrame:
    if gorunum == VARSAYILAN:
        return df
    if gorunum == YOY:
        return seri_yoy(df)
    if gorunum == MOM:
        return seri_mom(df)
    raise ValueError(f"Bilinmeyen görünüm: {gorunum}")
```

- [ ] **Step 4: Testleri koştur, geçtiklerini gör**

Run: `pytest tests/test_stats.py -v`
Expected: PASS — 12 test

- [ ] **Step 5: Commit**

```bash
git add core/stats.py tests/test_stats.py
git commit -m "feat: istatistik katmanı (MoM, YoY, 12A aralık, görünüm dönüşümleri)

Değişim hesapları tarih tabanlı asof mantığı kullanır; aylık, haftalık
ve günlük seriler aynı kodla doğru sonuç verir."
```

---

### Task 3: Veri okuma katmanı

Repodaki CSV'leri okuyan tek kapı. Saf okuma fonksiyonu test edilir, Streamlit önbelleği onun etrafına sarılır — böylece testler Streamlit runtime'ı olmadan koşar.

**Files:**
- Create: `core/data.py`
- Test: `tests/test_data.py`

**Interfaces:**
- Consumes: `core.catalog.KOK`
- Produces:
  - `core.data.VERI_DIZINI: pathlib.Path`
  - `core.data.VeriYokHatasi(FileNotFoundError)`
  - `core.data.seri_csv_oku(yol: pathlib.Path) -> pd.DataFrame` — saf, test edilebilir
  - `core.data.load_series(seri_id: str) -> pd.DataFrame` — Streamlit önbellekli kapı
  - `core.data.seri_var_mi(seri_id: str) -> bool`

- [ ] **Step 1: Testleri yaz (başarısız olmalı)**

`tests/test_data.py`:

```python
import pandas as pd
import pytest

from core.data import VeriYokHatasi, seri_csv_oku


def csv_yaz(tmp_path, icerik):
    yol = tmp_path / "seri.csv"
    yol.write_text(icerik, encoding="utf-8")
    return yol


def test_csv_datetimeindexli_df_verir(tmp_path):
    yol = csv_yaz(tmp_path, "date,value\n2024-01-01,10.5\n2024-02-01,11.25\n")
    df = seri_csv_oku(yol)
    assert list(df.columns) == ["value"]
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.name == "date"
    assert df.loc[pd.Timestamp("2024-02-01"), "value"] == 11.25


def test_satirlar_tarihe_gore_siralanir(tmp_path):
    yol = csv_yaz(tmp_path, "date,value\n2024-03-01,3\n2024-01-01,1\n2024-02-01,2\n")
    df = seri_csv_oku(yol)
    assert list(df["value"]) == [1.0, 2.0, 3.0]


def test_bos_degerler_atilir(tmp_path):
    yol = csv_yaz(tmp_path, "date,value\n2024-01-01,1\n2024-02-01,\n2024-03-01,3\n")
    df = seri_csv_oku(yol)
    assert len(df) == 2


def test_dosya_yoksa_turkce_hata(tmp_path):
    with pytest.raises(VeriYokHatasi, match="ingest.run"):
        seri_csv_oku(tmp_path / "olmayan.csv")
```

- [ ] **Step 2: Testleri koştur, başarısız olduklarını gör**

Run: `pytest tests/test_data.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.data'`

- [ ] **Step 3: `core/data.py`'yi yaz**

```python
"""Veri okuma: repodaki CSV'lere açılan tek kapı.

Bugün veri repoda CSV olarak duruyor. İleride harici bir veritabanına
geçilirse yalnızca `load_series()`'in içi değişir; sayfalar etkilenmez.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from core.catalog import KOK

VERI_DIZINI = KOK / "data"


class VeriYokHatasi(FileNotFoundError):
    """Seri katalogda var ama veri dosyası üretilmemiş."""


def seri_yolu(seri_id: str) -> Path:
    return VERI_DIZINI / f"{seri_id}.csv"


def seri_var_mi(seri_id: str) -> bool:
    return seri_yolu(seri_id).exists()


def seri_csv_oku(yol: Path) -> pd.DataFrame:
    if not yol.exists():
        raise VeriYokHatasi(
            f"Veri dosyası yok: {yol}\n"
            "Veriyi üretmek için `python -m ingest.run` çalıştırın."
        )
    df = pd.read_csv(yol, parse_dates=["date"])
    df = df.dropna(subset=["value"]).sort_values("date").set_index("date")
    df.index.name = "date"
    return df[["value"]].astype({"value": "float64"})


@st.cache_data(show_spinner=False)
def load_series(seri_id: str) -> pd.DataFrame:
    """Katalogdaki bir serinin verisini döndürür (önbellekli)."""
    return seri_csv_oku(seri_yolu(seri_id))
```

- [ ] **Step 4: Testleri koştur, geçtiklerini gör**

Run: `pytest tests/test_data.py -v`
Expected: PASS — 4 test

Testler `seri_csv_oku`'yu doğrudan çağırıyor; `st.cache_data` sarmalayıcısına dokunmuyorlar, bu yüzden Streamlit runtime'ı gerekmiyor.

- [ ] **Step 5: Commit**

```bash
git add core/data.py tests/test_data.py
git commit -m "feat: veri okuma katmanı

load_series() tek okuma kapısı; saf seri_csv_oku() test edilebilir
kalsın diye önbellek ayrı sarmalayıcıda."
```

---

### Task 4: EVDS ingest

Mevcut `evds.ts`'teki doğrulanmış EVDS3 kontratının Python karşılığı. Parse fonksiyonları ağa çıkmadan test edilir; sonra gerçek EVDS'e karşı bir kez koşturulup `data/` doldurulur.

**Files:**
- Create: `ingest/__init__.py`, `ingest/evds.py`, `ingest/run.py`
- Test: `tests/test_evds.py`
- Generate: `data/<kategori>/<seri>.csv` × 13

**Interfaces:**
- Consumes: `core.catalog.Seri`, `core.catalog.seri_listele`, `core.catalog.KOK`, `core.data.seri_yolu`
- Produces:
  - `ingest.evds.ENDPOINT: str`
  - `ingest.evds.alan_adi(evds_code: str) -> str`
  - `ingest.evds.tarih_parse(tarih: str) -> str | None` — ISO `YYYY-MM-DD` ya da None
  - `ingest.evds.deger_parse(ham: object) -> float | None`
  - `ingest.evds.tarih_formatla(d: datetime.date) -> str` — EVDS'in beklediği `DD-MM-YYYY`
  - `ingest.evds.istek_govdesi(evds_code: str, evds_frequency: str, baslangic: str, bitis: str) -> dict`
  - `ingest.evds.noktalari_ayikla(yanit: dict, evds_code: str) -> list[tuple[str, float]]`
  - `ingest.evds.seri_cek(seri: Seri, api_key: str, session=None) -> pd.DataFrame`
  - `ingest.run.main() -> int` — exit kodu

- [ ] **Step 1: Parse testlerini yaz (başarısız olmalı)**

`tests/test_evds.py`:

```python
from datetime import date

import pytest

from ingest.evds import (
    alan_adi,
    deger_parse,
    istek_govdesi,
    noktalari_ayikla,
    tarih_formatla,
    tarih_parse,
)


def test_alan_adi_noktalari_alt_cizgiye_cevirir():
    assert alan_adi("TP.TUKFIY2025.GENEL") == "TP_TUKFIY2025_GENEL"


def test_aylik_tarih_ayin_ilk_gunune_cevrilir():
    # EVDS aylık serilerde dokümantasyona aykırı olarak "YYYY-MM" döndürüyor
    assert tarih_parse("2026-07") == "2026-07-01"


def test_gunluk_tarih_gun_ay_yil_sirasindan_isoya_cevrilir():
    assert tarih_parse("05-08-2026") == "2026-08-05"


def test_taninmayan_tarih_none_dondurur():
    assert tarih_parse("2026/08/05") is None
    assert tarih_parse("") is None


def test_deger_binlik_ayraci_temizlenir():
    # groupSeperator:true yüzünden değerler "139,411.00000" gibi geliyor
    assert deger_parse("139,411.00000") == pytest.approx(139411.0)


def test_deger_bos_ve_gecersizler_none():
    assert deger_parse(None) is None
    assert deger_parse("") is None
    assert deger_parse("   ") is None
    assert deger_parse("yok") is None


def test_tarih_formatla_evds_bicimini_verir():
    assert tarih_formatla(date(2026, 8, 5)) == "05-08-2026"


def test_istek_govdesi_seri_kodunu_tire_ile_gonderir():
    govde = istek_govdesi("TP.APIFON4", "1", "01-01-2011", "27-08-2026")
    assert govde["series"] == "-TP.APIFON4"
    assert govde["frequency"] == "1"
    assert govde["startDate"] == "01-01-2011"
    assert govde["endDate"] == "27-08-2026"
    assert govde["decimalSeperator"] == "."
    assert govde["groupSeperator"] is True


def test_noktalari_ayikla_siralar_ve_gecersizleri_atar():
    yanit = {
        "items": [
            {"Tarih": "2026-03", "TP_TUKFIY2025_GENEL": "102,50000"},
            {"Tarih": "2026-01", "TP_TUKFIY2025_GENEL": "100.00000"},
            {"Tarih": "2026-02", "TP_TUKFIY2025_GENEL": None},
            {"Tarih": "bozuk", "TP_TUKFIY2025_GENEL": "999"},
        ]
    }
    assert noktalari_ayikla(yanit, "TP.TUKFIY2025.GENEL") == [
        ("2026-01-01", 100.0),
        ("2026-03-01", 102.5),
    ]


def test_noktalari_ayikla_bos_yanitta_bos_liste():
    assert noktalari_ayikla({}, "TP.APIFON4") == []
```

- [ ] **Step 2: Testleri koştur, başarısız olduklarını gör**

Run: `pytest tests/test_evds.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingest.evds'`

- [ ] **Step 3: `ingest/evds.py`'yi yaz**

`ingest/__init__.py` boş dosya olarak oluşturulur.

```python
"""TCMB EVDS3 istemcisi.

Dokümante edilmemiş davranışlar (repo'daki eski TypeScript modülünde
keşfedilip doğrulanmıştır — sıfırdan yeniden keşfetmeye çalışmayın):

- Endpoint resmi evds2 REST'i değil; POST /igmevdsms-dis/fe, key HTTP
  header'ında gider.
- Tarih alanı frekansa göre iki farklı biçimde döner: aylık "YYYY-MM"
  (gün yok), günlük/haftalık "DD-MM-YYYY".
- Yanıttaki değer alanının adı, seri kodunun noktalarının alt çizgiye
  çevrilmiş halidir.
- groupSeperator:true istendiği için değerler binlik ayraç içerir.
"""

from __future__ import annotations

import math
import re
from datetime import date

import pandas as pd
import requests

from core.catalog import Seri

ENDPOINT = "https://evds3.tcmb.gov.tr/igmevdsms-dis/fe"
ZAMAN_ASIMI = 60

_AYLIK = re.compile(r"^(\d{4})-(\d{2})$")
_GUNLUK = re.compile(r"^(\d{2})-(\d{2})-(\d{4})$")


def alan_adi(evds_code: str) -> str:
    return evds_code.replace(".", "_")


def tarih_parse(tarih: str) -> str | None:
    metin = str(tarih).strip()
    aylik = _AYLIK.match(metin)
    if aylik:
        return f"{aylik.group(1)}-{aylik.group(2)}-01"
    gunluk = _GUNLUK.match(metin)
    if gunluk:
        return f"{gunluk.group(3)}-{gunluk.group(2)}-{gunluk.group(1)}"
    return None


def deger_parse(ham: object) -> float | None:
    if ham is None:
        return None
    metin = str(ham).replace(",", "").strip()
    if not metin:
        return None
    try:
        deger = float(metin)
    except ValueError:
        return None
    return deger if math.isfinite(deger) else None


def tarih_formatla(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def istek_govdesi(
    evds_code: str, evds_frequency: str, baslangic: str, bitis: str
) -> dict:
    return {
        "type": "json",
        "series": f"-{evds_code}",
        "aggregationTypes": "-avg",
        "formulas": "-0",
        "startDate": baslangic,
        "endDate": bitis,
        "frequency": evds_frequency,
        "decimalSeperator": ".",
        "decimal": "5",
        "dateFormat": "0",
        "lang": "TR",
        "yon": "1",
        "sira": "1",
        "ozelFormuller": [],
        "groupSeperator": True,
        "isRaporSayfasi": False,
    }


def noktalari_ayikla(yanit: dict, evds_code: str) -> list[tuple[str, float]]:
    alan = alan_adi(evds_code)
    noktalar: list[tuple[str, float]] = []
    for satir in yanit.get("items") or []:
        tarih = tarih_parse(satir.get("Tarih", ""))
        deger = deger_parse(satir.get(alan))
        if tarih is None or deger is None:
            continue
        noktalar.append((tarih, deger))
    noktalar.sort(key=lambda n: n[0])
    return noktalar


def _pencere(seri: Seri, bugun: date) -> tuple[str, str]:
    if seri.start_date:
        baslangic = date.fromisoformat(seri.start_date)
    else:
        baslangic = bugun.replace(year=bugun.year - 15)
    return tarih_formatla(baslangic), tarih_formatla(bugun)


def seri_cek(seri: Seri, api_key: str, session: requests.Session | None = None,
             bugun: date | None = None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı)."""
    bugun = bugun or date.today()
    baslangic, bitis = _pencere(seri, bugun)
    http = session or requests

    yanit = http.post(
        ENDPOINT,
        headers={"key": api_key, "Content-Type": "application/json"},
        json=istek_govdesi(seri.evds_code, seri.evds_frequency, baslangic, bitis),
        timeout=ZAMAN_ASIMI,
    )
    if yanit.status_code != 200:
        raise RuntimeError(
            f"EVDS HTTP {yanit.status_code} ({seri.evds_code})"
        )

    noktalar = noktalari_ayikla(yanit.json(), seri.evds_code)
    if not noktalar:
        raise RuntimeError(f"EVDS boş seri döndürdü ({seri.evds_code})")

    return pd.DataFrame(noktalar, columns=["date", "value"])
```

- [ ] **Step 4: Testleri koştur, geçtiklerini gör**

Run: `pytest tests/test_evds.py -v`
Expected: PASS — 10 test

- [ ] **Step 5: `ingest/run.py`'yi yaz**

```python
"""Ingest orchestrator.

Bir serinin başarısızlığı diğerlerini düşürmez: başarılı seriler yine
yazılır, hatalar toplanıp raporlanır, en az bir hata varsa exit kodu 1
olur ki Actions kırmızıya dönsün.
"""

from __future__ import annotations

import argparse
import os
import sys

import requests

from core.catalog import Seri, seri_listele
from core.data import seri_yolu
from ingest.evds import seri_cek


def seriyi_yaz(seri: Seri, df) -> int:
    yol = seri_yolu(seri.id)
    yol.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(yol, index=False, float_format="%.5f")
    return len(df)


def main() -> int:
    ayristirici = argparse.ArgumentParser(description="EVDS verilerini çeker")
    ayristirici.add_argument(
        "--only", help="Yalnızca bu seri id'sini çek (hata ayıklama için)"
    )
    args = ayristirici.parse_args()

    api_key = os.environ.get("EVDS_API_KEY")
    if not api_key:
        print("HATA: EVDS_API_KEY tanımlı değil", file=sys.stderr)
        return 2

    seriler = seri_listele()
    if args.only:
        seriler = [s for s in seriler if s.id == args.only]
        if not seriler:
            print(f"HATA: katalogda yok: {args.only}", file=sys.stderr)
            return 2

    basarili: list[str] = []
    hatalar: list[tuple[str, str]] = []

    with requests.Session() as oturum:
        for seri in seriler:
            try:
                df = seri_cek(seri, api_key, session=oturum)
                adet = seriyi_yaz(seri, df)
                basarili.append(f"{seri.id} ({adet} nokta)")
                print(f"  ✓ {seri.id} — {adet} nokta")
            except Exception as hata:  # noqa: BLE001 — modül bazlı izolasyon
                hatalar.append((seri.id, str(hata)))
                print(f"  ✗ {seri.id} — {hata}", file=sys.stderr)

    print(f"\n{len(basarili)}/{len(seriler)} seri başarılı")
    if hatalar:
        print(f"{len(hatalar)} seri başarısız:", file=sys.stderr)
        for seri_id, mesaj in hatalar:
            print(f"  - {seri_id}: {mesaj}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Gerçek EVDS'e karşı bir kez koştur**

API key `evds2.tcmb.gov.tr`'den alınır (ücretsiz kayıt). Lokal koşu:

```bash
EVDS_API_KEY=<key> python -m ingest.run
```

Expected: 13/13 seri başarılı, `data/` altında 13 CSV. Aylık seriler ~180 nokta (15 yıl), günlük seriler ~3900 nokta.

Bir seri boş dönerse önce `--only` ile izole edin:

```bash
EVDS_API_KEY=<key> python -m ingest.run --only enflasyon/tufe-genel
```

`TP.TUKFIY2025.*` kodları 2025 bazlı endeksin başlangıcından öncesini döndürmeyebilir; o durumda katalogda o seriye `start_date: "2025-01-01"` ekleyin — kod değişikliği gerekmez.

- [ ] **Step 7: Üretilen veriyi gözle doğrula**

```bash
head -3 data/enflasyon/tufe-genel.csv
wc -l data/*/*.csv
```

Expected: başlık satırı `date,value`; tarihler ISO ve artan sırada; 13 dosya.

- [ ] **Step 8: Commit**

```bash
git add ingest tests/test_evds.py data
git commit -m "feat: EVDS3 ingest modülü ve ilk veri çekimi

Endpoint, tarih formatı tutarsızlığı ve binlik ayraç davranışı eski
TypeScript modülünden taşındı. Pencere 15 yıla çıkarıldı; her koşu tam
pencereyi yeniden çekiyor ki revizyonlar diff'te görünsün."
```

---

### Task 5: Tema ve grafik üreticileri

Plotly figürlerini üreten saf fonksiyonlar. Renk paleti dataviz doğrulayıcısından geçmiştir; değerleri değiştirmeyin.

**Files:**
- Create: `core/theme.py`, `core/charts.py`
- Test: `tests/test_charts.py`

**Interfaces:**
- Consumes: `core.stats` (dolaylı — çağıran taraf dönüşümü uygular)
- Produces:
  - `core.theme.RENKLER: dict[str, str | list[str]]`
  - `core.theme.TR_AYLAR: list[str]`
  - `core.charts.aylige_cevir(df: pd.DataFrame, agg: str = "mean") -> pd.DataFrame`
  - `core.charts.mevsimsellik_figuru(df, birim: str, agg: str = "mean", yil_sayisi: int = 3) -> go.Figure`
  - `core.charts.seviye_figuru(df, birim: str) -> go.Figure`

- [ ] **Step 1: `core/theme.py`'yi yaz**

Bu dosyanın testi yok — sabit tanımları. Renkler `scripts/validate_palette.js` ile `--mode dark --surface "#16273F" --pairs all` altında doğrulanmıştır (CVD ΔE 9.4, normal görüş ΔE 20.9, kontrast ≥3:1, tüm kontroller PASS).

```python
"""Görsel kimlik sabitleri.

RENKLER["seri"] dataviz doğrulayıcısından geçmiş bir settir; slotlar
yıla değil *güncelliğe* atanır (0 = cari yıl, 1 = geçen yıl, 2 = iki yıl
önce). Böylece takvim yılı döndüğünde renkler yeniden dağılmaz.

Cari yıl vurgusu renkle değil çizgi kalınlığıyla verilir: aynı hue'nun
iki tonu koyu tema açıklık bandına sıkıştığında normal görüşte bile
ayırt edilemiyor (ΔE 14.4 < 15 tabanı).

RENKLER["artis"]/["dusus"] durum renkleridir; yalnızca ▲/▼ işaretiyle
birlikte istatistik satırlarında kullanılır, grafiğin içinde asla.
"""

RENKLER = {
    "sayfa_zemini": "#0F1E33",
    "kart_zemini": "#16273F",
    "metin": "#E6EDF5",
    "metin_soluk": "#9FB3CC",
    "izgara": "#22354F",
    "vurgu": "#E8B54D",
    "artis": "#199e70",
    "dusus": "#e66767",
    "seri": ["#3987e5", "#d95926", "#199e70"],
}

TR_AYLAR = [
    "Oca", "Şub", "Mar", "Nis", "May", "Haz",
    "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara",
]
```

- [ ] **Step 2: Grafik testlerini yaz (başarısız olmalı)**

`tests/test_charts.py`:

```python
import pandas as pd
import pytest

from core.charts import aylige_cevir, mevsimsellik_figuru, seviye_figuru
from core.theme import RENKLER, TR_AYLAR


def gunluk_df(baslangic, periyot, deger=1.0):
    idx = pd.date_range(baslangic, periods=periyot, freq="D", name="date")
    return pd.DataFrame({"value": [deger] * periyot}, index=idx)


def aylik_df(baslangic, periyot):
    idx = pd.date_range(baslangic, periods=periyot, freq="MS", name="date")
    return pd.DataFrame({"value": [float(i) for i in range(periyot)]}, index=idx)


def test_aylige_cevir_ortalama_alir():
    idx = pd.date_range("2026-01-01", periods=31, freq="D", name="date")
    df = pd.DataFrame({"value": [10.0] * 30 + [41.0]}, index=idx)
    sonuc = aylige_cevir(df, "mean")
    assert len(sonuc) == 1
    assert sonuc.iloc[0]["value"] == pytest.approx(11.0)


def test_aylige_cevir_son_degeri_alir():
    idx = pd.date_range("2026-01-01", periods=3, freq="D", name="date")
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0]}, index=idx)
    assert aylige_cevir(df, "last").iloc[0]["value"] == 3.0


def test_aylige_cevir_toplar():
    idx = pd.date_range("2026-01-01", periods=3, freq="D", name="date")
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0]}, index=idx)
    assert aylige_cevir(df, "sum").iloc[0]["value"] == 6.0


def test_mevsimsellik_uc_yil_icin_uc_iz_uretir():
    df = aylik_df("2022-01-01", 60)  # 2022-01 .. 2026-12
    fig = mevsimsellik_figuru(df, "Adet")
    assert len(fig.data) == 3


def test_mevsimsellik_ilk_iz_cari_yil_ve_kalin():
    df = aylik_df("2022-01-01", 60)
    fig = mevsimsellik_figuru(df, "Adet")
    ilk = fig.data[0]
    assert ilk.name == "2026"
    assert ilk.line.color == RENKLER["seri"][0]
    assert ilk.line.width == 3
    assert fig.data[1].line.width == 2


def test_mevsimsellik_x_ekseni_ay_numaralari():
    df = aylik_df("2022-01-01", 60)
    fig = mevsimsellik_figuru(df, "Adet")
    assert list(fig.data[0].x) == list(range(1, 13))
    assert list(fig.layout.xaxis.ticktext) == TR_AYLAR


def test_mevsimsellik_kisa_seride_mevcut_yillari_verir():
    df = aylik_df("2026-01-01", 6)
    fig = mevsimsellik_figuru(df, "Adet")
    assert len(fig.data) == 1
    assert fig.data[0].name == "2026"


def test_seviye_tek_iz_ve_legendsiz():
    df = aylik_df("2024-01-01", 24)
    fig = seviye_figuru(df, "TL")
    assert len(fig.data) == 1
    assert fig.layout.showlegend is False
    assert fig.data[0].line.color == RENKLER["seri"][0]


def test_seviye_y_ekseni_birimi_gosterir():
    df = aylik_df("2024-01-01", 24)
    fig = seviye_figuru(df, "TL")
    assert fig.layout.yaxis.title.text == "TL"
```

- [ ] **Step 3: Testleri koştur, başarısız olduklarını gör**

Run: `pytest tests/test_charts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.charts'`

- [ ] **Step 4: `core/charts.py`'yi yaz**

```python
"""Plotly figür üreticileri.

İki form yeterli:
- mevsimsellik: yıl başına bir çizgi, x ekseni Oca→Ara. "Bu ay normal mi?"
- seviye: tüm geçmiş, tek çizgi. "Nereden nereye geldik?"

Çift y-eksenli grafik üretilmez; farklı ölçekteki iki büyüklük iki ayrı
grafiktir.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from core.theme import RENKLER, TR_AYLAR

_AGG_FONKSIYONLARI = {"mean": "mean", "last": "last", "sum": "sum"}


def aylige_cevir(df: pd.DataFrame, agg: str = "mean") -> pd.DataFrame:
    """Günlük/haftalık seriyi ay başlangıcına indirger."""
    if agg not in _AGG_FONKSIYONLARI:
        raise ValueError(f"Bilinmeyen toplama: {agg}")
    seri = df["value"].resample("MS").agg(_AGG_FONKSIYONLARI[agg])
    return seri.dropna().to_frame("value")


def _temayi_uygula(fig: go.Figure, birim: str) -> go.Figure:
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=RENKLER["metin_soluk"], size=12),
        margin=dict(l=8, r=8, t=8, b=8),
        height=280,
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            bgcolor="rgba(0,0,0,0)",
        ),
    )
    fig.update_xaxes(
        showgrid=False,
        linecolor=RENKLER["izgara"],
        tickfont=dict(color=RENKLER["metin_soluk"]),
    )
    fig.update_yaxes(
        gridcolor=RENKLER["izgara"],
        zeroline=False,
        title=dict(text=birim, font=dict(color=RENKLER["metin_soluk"], size=11)),
        tickfont=dict(color=RENKLER["metin_soluk"]),
    )
    return fig


def mevsimsellik_figuru(
    df: pd.DataFrame, birim: str, agg: str = "mean", yil_sayisi: int = 3
) -> go.Figure:
    aylik = aylige_cevir(df, agg)
    fig = go.Figure()

    if aylik.empty:
        return _temayi_uygula(fig, birim)

    son_yil = int(aylik.index.year.max())
    ilk_yil = int(aylik.index.year.min())
    yillar = [y for y in range(son_yil, son_yil - yil_sayisi, -1) if y >= ilk_yil]

    for sira, yil in enumerate(yillar):
        alt = aylik[aylik.index.year == yil]
        if alt.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=list(alt.index.month),
                y=list(alt["value"]),
                name=str(yil),
                mode="lines+markers",
                line=dict(color=RENKLER["seri"][sira], width=3 if sira == 0 else 2),
                marker=dict(size=8 if sira == 0 else 6),
                hovertemplate=f"{yil}: %{{y:,.2f}} {birim}<extra></extra>",
            )
        )

    fig.update_xaxes(
        tickmode="array",
        tickvals=list(range(1, 13)),
        ticktext=TR_AYLAR,
        range=[0.5, 12.5],
    )
    _temayi_uygula(fig, birim)
    fig.update_layout(showlegend=len(fig.data) >= 2)
    return fig


def seviye_figuru(df: pd.DataFrame, birim: str) -> go.Figure:
    fig = go.Figure(
        go.Scatter(
            x=list(df.index),
            y=list(df["value"]),
            mode="lines",
            line=dict(color=RENKLER["seri"][0], width=2),
            hovertemplate=f"%{{y:,.2f}} {birim}<extra></extra>",
        )
    )
    _temayi_uygula(fig, birim)
    fig.update_layout(showlegend=False)
    return fig
```

Tek seride legend yoktur — kart başlığı seriyi zaten adlandırıyor. İki ve üzeri seride legend her zaman açıktır, böylece kimlik yalnızca renge bağlı kalmaz.

- [ ] **Step 5: Testleri koştur, geçtiklerini gör**

Run: `pytest tests/test_charts.py -v`
Expected: PASS — 9 test

- [ ] **Step 6: Commit**

```bash
git add core/theme.py core/charts.py tests/test_charts.py
git commit -m "feat: tema ve Plotly grafik üreticileri

Renk paleti dataviz doğrulayıcısından geçti (koyu lacivert yüzeyde
CVD ΔE 9.4, normal görüş ΔE 20.9). Cari yıl vurgusu renkle değil
çizgi kalınlığıyla veriliyor."
```

---

### Task 6: Sayfa bileşenleri ve navigasyon

Grafik kartı, KPI satırı, kategori sayfası ve `st.navigation` girişi. Bu görevin sonunda uygulama tarayıcıda gerçek veriyle çalışıyor.

**Files:**
- Create: `core/components.py`, `core/page.py`, `app.py`
- Test: manuel tarayıcı doğrulaması (Streamlit render'ı birim testine uygun değil; figür üreticileri Task 5'te zaten test edildi)

**Interfaces:**
- Consumes: `core.catalog.Seri`, `core.catalog.Kategori`, `core.catalog.kategorileri_yukle`, `core.catalog.seri_listele`, `core.data.load_series`, `core.data.seri_var_mi`, `core.data.VeriYokHatasi`, `core.stats.*`, `core.charts.mevsimsellik_figuru`, `core.charts.seviye_figuru`, `core.theme.RENKLER`
- Produces:
  - `core.components.yuzde_rozeti(deger: float | None) -> str` — ▲/▼ işaretli markdown
  - `core.components.sayi_bicimle(deger: float | None, birim: str = "") -> str`
  - `core.components.kpi_satiri(seriler: list[Seri]) -> None`
  - `core.components.grafik_karti(seri: Seri, gorunum: str) -> None`
  - `core.page.kategori_sayfasi_yap(kategori: Kategori) -> Callable[[], None]`

- [ ] **Step 1: `core/components.py`'yi yaz**

```python
"""Streamlit bileşenleri: KPI satırı ve grafik kartı.

grafik_karti() tek fonksiyondur; sitedeki tüm kartlar onun bir örneğidir.
"""

from __future__ import annotations

import streamlit as st

from core.catalog import Seri
from core.charts import mevsimsellik_figuru, seviye_figuru
from core.data import VeriYokHatasi, load_series
from core.stats import (
    VARSAYILAN,
    aralik_12a,
    gorunum_uygula,
    mom,
    son_deger,
    son_tarih,
    yoy,
)
from core.theme import RENKLER

_SIKLIK_ETIKETLERI = {"daily": "GÜNLÜK", "weekly": "HAFTALIK", "monthly": "AYLIK"}


def sayi_bicimle(deger: float | None, birim: str = "") -> str:
    if deger is None:
        return "—"
    metin = f"{deger:,.2f}".replace(",", " ")
    return f"{metin} {birim}".strip()


def yuzde_rozeti(deger: float | None) -> str:
    """Durum rengi yalnızca ▲/▼ işaretiyle birlikte kullanılır."""
    if deger is None:
        return ":gray[—]"
    isaret = "▲" if deger >= 0 else "▼"
    renk = RENKLER["artis"] if deger >= 0 else RENKLER["dusus"]
    return f"<span style='color:{renk}'>{isaret} %{deger:,.1f}</span>"


def kpi_satiri(seriler: list[Seri]) -> None:
    gosterilecek = seriler[:4]
    if not gosterilecek:
        return
    sutunlar = st.columns(len(gosterilecek))
    for sutun, seri in zip(sutunlar, gosterilecek):
        with sutun, st.container(border=True):
            st.caption(seri.title)
            try:
                df = load_series(seri.id)
            except VeriYokHatasi:
                st.markdown("**—**")
                st.caption("veri yok")
                continue
            st.markdown(f"### {sayi_bicimle(son_deger(df), seri.unit)}")
            st.markdown(
                f"YoY {yuzde_rozeti(yoy(df))} · {son_tarih(df):%Y-%m}",
                unsafe_allow_html=True,
            )


def _istatistik_satiri(df, seri: Seri) -> None:
    aralik = aralik_12a(df)
    aralik_metni = (
        f"{sayi_bicimle(aralik[0])} – {sayi_bicimle(aralik[1])}" if aralik else "—"
    )
    sol, sag = st.columns(2)
    with sol:
        st.markdown(
            f"**{sayi_bicimle(son_deger(df), seri.unit)}**  \n"
            f"MoM {yuzde_rozeti(mom(df))}",
            unsafe_allow_html=True,
        )
    with sag:
        st.markdown(
            f"YoY {yuzde_rozeti(yoy(df))}  \n"
            f"<span style='color:{RENKLER['metin_soluk']}'>12A aralık "
            f"{aralik_metni}</span>",
            unsafe_allow_html=True,
        )


def grafik_karti(seri: Seri, gorunum: str) -> None:
    with st.container(border=True):
        baslik, kaynak = st.columns([4, 1])
        baslik.markdown(f"**{seri.title}**")
        kaynak.markdown(
            f"<div style='text-align:right;color:{RENKLER['metin_soluk']};"
            f"font-size:0.8em'>"
            f"<a href='{seri.kaynak.url}' style='color:inherit'>"
            f"{seri.kaynak.name}</a></div>",
            unsafe_allow_html=True,
        )

        try:
            df = load_series(seri.id)
        except VeriYokHatasi as hata:
            st.warning(str(hata))
            return

        etiket = _SIKLIK_ETIKETLERI[seri.freq]
        st.caption(f"Son Dönem: {son_tarih(df):%Y-%m} · {etiket}")
        _istatistik_satiri(df, seri)

        gosterilecek = gorunum_uygula(df, gorunum)
        birim = seri.unit if gorunum == VARSAYILAN else "%"

        for grafik in seri.charts:
            if grafik == "seasonality":
                fig = mevsimsellik_figuru(gosterilecek, birim, agg=seri.monthly_agg)
            else:
                fig = seviye_figuru(gosterilecek, birim)
            st.plotly_chart(fig, use_container_width=True, key=f"{seri.id}-{grafik}")

        with st.expander("Veri tablosu"):
            st.dataframe(gosterilecek, use_container_width=True)
```

`st.expander` içindeki veri tablosu, dataviz erişilebilirlik gereğidir: kontrastı düşük kalan bir işaret varsa okuyucunun sayıya ulaşabileceği bir yol her zaman bulunur.

**Bilinen sürüm tuzağı:** `use_container_width` Streamlit 1.49'dan itibaren `width="stretch"` lehine deprecate edildi ama hâlâ çalışıyor. Community Cloud en güncel sürümü kurduğu için deploy sırasında deprecation uyarısı görebilirsiniz; işlevsel bir sorun değil. Uyarı rahatsız ederse `st.plotly_chart(fig, width="stretch", key=...)` ve `st.dataframe(gosterilecek, width="stretch")` olarak değiştirin — bu, requirements floor'unu 1.49'a çıkarır.

- [ ] **Step 2: `core/page.py`'yi yaz**

```python
"""Kategori sayfası üreticisi.

Sayfalar bildirimseldir: katalogdaki her kategori için bir kapanış
üretilir, içerik katalogdan okunur.
"""

from __future__ import annotations

from typing import Callable

import streamlit as st

from core.catalog import Kategori, seri_listele
from core.components import grafik_karti, kpi_satiri
from core.stats import GORUNUMLER, VARSAYILAN


def _kategoriyi_ciz(kategori: Kategori) -> None:
    seriler = seri_listele(kategori.slug)

    st.title(kategori.title)
    kaynaklar = sorted({s.kaynak.name for s in seriler})
    st.caption(f"{len(seriler)} seri · Kaynak: {', '.join(kaynaklar)}")

    gorunum = st.segmented_control(
        "Görünüm",
        GORUNUMLER,
        default=VARSAYILAN,
        key=f"gorunum_{kategori.slug}",
        label_visibility="collapsed",
    )
    gorunum = gorunum or VARSAYILAN

    kpi_satiri(seriler)
    st.divider()

    sutunlar = st.columns(2)
    for sira, seri in enumerate(seriler):
        with sutunlar[sira % 2]:
            grafik_karti(seri, gorunum)


def kategori_sayfasi_yap(kategori: Kategori) -> Callable[[], None]:
    def sayfa() -> None:
        _kategoriyi_ciz(kategori)

    sayfa.__name__ = f"sayfa_{kategori.slug.replace('-', '_')}"
    return sayfa
```

`st.segmented_control` seçim temizlendiğinde `None` döndürür; `gorunum or VARSAYILAN` bunu karşılar.

- [ ] **Step 3: `app.py`'yi yaz**

```python
"""BV Market Dashboard — giriş noktası.

Sol menü katalogdan üretilir; yeni bir kategori eklemek için
catalog/categories.yaml'a bir satır eklemek yeterlidir.
"""

import streamlit as st

from core.catalog import kategorileri_yukle
from core.page import kategori_sayfasi_yap

st.set_page_config(
    page_title="BV Market Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

sayfalar = [
    st.Page(
        kategori_sayfasi_yap(kategori),
        title=kategori.title,
        url_path=kategori.slug,
        default=(sira == 0),
    )
    for sira, kategori in enumerate(kategorileri_yukle())
]

st.navigation({"Veri Sayfaları": sayfalar}).run()
```

- [ ] **Step 4: Uygulamayı çalıştır ve tarayıcıda doğrula**

```bash
streamlit run app.py
```

Her dört sayfayı da gezin ve şunları doğrulayın:

1. Sol menüde dört kategori görünüyor: Ekonomi & Makro, Enflasyon Verileri, İnşaat, Kredi Kartı Harcamaları
2. Her sayfada KPI satırı gerçek sayılar gösteriyor (`—` değil)
3. Her grafik kartında veri render oluyor; mevsimsellik grafiğinde x ekseni `Oca … Ara`, cari yıl çizgisi diğerlerinden kalın
4. `YoY %` ve `MoM %` görünümlerine geçince grafikler yüzdeye dönüyor, y ekseni başlığı `%` oluyor
5. "Veri tablosu" açılır bölümü tarihleri ve değerleri gösteriyor
6. Tarayıcı konsolunda hata yok

Ekran görüntüsü alın; sonraki adımın commit mesajı bu doğrulamaya dayanıyor.

Bir sayfa boşsa: `python -m ingest.run --only <seri-id>` ile o serinin verisinin üretilip üretilmediğini kontrol edin.

- [ ] **Step 5: Tüm test paketini koştur**

Run: `pytest -v`
Expected: PASS — 44 test (9 katalog + 12 stats + 4 data + 10 evds + 9 charts)

- [ ] **Step 6: Commit**

```bash
git add app.py core/components.py core/page.py
git commit -m "feat: sayfa bileşenleri ve navigasyon

Dört kategori sayfası katalogdan üretiliyor; grafik kartı tek
fonksiyon. Tarayıcıda dört sayfa da gerçek veriyle doğrulandı."
```

---

### Task 7: Actions workflow, README ve deploy

Günlük veri tazeliğini kuran cron ve deploy dokümantasyonu.

**Files:**
- Create: `.github/workflows/ingest.yml`
- Rewrite: `README.md`

**Interfaces:**
- Consumes: `ingest.run.main()` (Task 4)
- Produces: yok (son görev)

- [ ] **Step 1: Workflow'u yaz**

`.github/workflows/ingest.yml`:

```yaml
name: Veri güncelle

on:
  schedule:
    # 06:00 UTC = 09:00 TSİ
    - cron: "0 6 * * *"
  workflow_dispatch:

permissions:
  contents: write

jobs:
  ingest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Bağımlılıkları kur
        run: pip install -r requirements.txt

      - name: EVDS verilerini çek
        env:
          EVDS_API_KEY: ${{ secrets.EVDS_API_KEY }}
        run: python -m ingest.run

      - name: Değişiklikleri commit'le
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data
          if git diff --staged --quiet; then
            echo "Veride değişiklik yok."
          else
            git commit -m "data: EVDS güncelleme $(date -u +%Y-%m-%d)"
            git push
          fi
```

Ingest adımı `ingest.run` non-zero dönerse workflow kırmızıya döner, ama "Değişiklikleri commit'le" adımı çalışmaz — başarısız bir koşuda kısmi veri commit'lenmez. Kısmi veriyi yine de yayınlamak isterseniz o adıma `if: always()` ekleyin; varsayılan olarak eklenmiyor çünkü sessizce eksik veri yayınlamak, gürültülü bir hatadan kötüdür.

- [ ] **Step 2: Test paketini CI'a ekle**

Aynı dosyaya ikinci bir job:

```yaml
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install -r requirements-dev.txt
      - run: pytest -v
```

- [ ] **Step 3: README'yi yeniden yaz**

`README.md`:

````markdown
# BV Market Dashboard

Türkiye ekonomisi için veri ve grafikler — BV Portföy iç kullanımı.
Resmi kaynaklardan otomatik veri çekme, normalize etme, hazır
istatistikli grafik sayfaları olarak sunma.

## Mimari

```
app.py                    # st.navigation — sol menü katalogdan üretilir
catalog/series.yaml       # tek doğruluk kaynağı: seri tanımları
catalog/categories.yaml   # menü ağacı
core/                     # catalog, data, stats, charts, components, page
ingest/                   # evds.py + run.py (orchestrator)
data/<kategori>/<seri>.csv
.github/workflows/ingest.yml   # günlük cron: ingest → commit → push
```

Veri repoda yaşar; uygulama yalnızca okur ve **runtime'da hiç secret
kullanmaz**. `EVDS_API_KEY` sadece GitHub Actions ortamında geçer.

## Komutlar

```bash
pip install -r requirements-dev.txt
streamlit run app.py                       # geliştirme sunucusu
EVDS_API_KEY=<key> python -m ingest.run    # veriyi tazele
pytest                                     # test paketi
```

Tek bir seriyi hata ayıklamak için: `python -m ingest.run --only enflasyon/tufe-genel`

## Yeni seri ekleme

`catalog/series.yaml`'a bir kayıt ekleyin; kod değişikliği gerekmez:

```yaml
- id: <kategori>/<ad>
  title: Görünen Ad
  category: <kategori>          # categories.yaml'da tanımlı olmalı
  kaynak: { name: TCMB EVDS, url: "https://evds3.tcmb.gov.tr" }
  unit: "Birim"
  freq: monthly                 # daily | weekly | monthly
  evds_code: TP.XXX.YYY
  evds_frequency: "5"           # 1=günlük, 2=haftalık, 5=aylık
  monthly_agg: mean             # mean | last | sum (günlük/haftalık için)
  charts: [seasonality, level]
```

Sonra `python -m ingest.run --only <yeni-id>` ile veriyi üretin.

## Deploy

Streamlit Community Cloud, private repo. Erişim viewer allowlist'i ile
BV Portföy e-postalarına kısıtlıdır.

Uygulama hareketsizlik sonrası uykuya dalar; günün ilk kullanıcısı
~30 saniye soğuk başlangıç bekler.

## Ön koşul

[TCMB EVDS](https://evds2.tcmb.gov.tr)'ten ücretsiz API key alıp GitHub
repo secret'ına `EVDS_API_KEY` olarak ekleyin.

## Yol haritası

| Faz | İçerik | Durum |
|---|---|---|
| 1 | Streamlit iskeleti + EVDS dilimi (13 seri, 4 kategori) | ✅ |
| 2 | Emtia (~11 sayfa) + günlük seriler için parquet geçişi | Sırada |
| 3 | Sektör sayfaları + Veri Takvimi | Planlandı |
| 4 | Hisse sayfaları | Planlandı |
| 5 | Arama, favoriler, AI raporları | Planlandı |

Tasarım detayları: `docs/superpowers/specs/2026-08-27-streamlit-dashboard-design.md`
````

- [ ] **Step 4: Commit ve push**

```bash
git add .github/workflows/ingest.yml README.md
git commit -m "ci: günlük EVDS ingest workflow'u ve README

Ingest başarısız olursa kısmi veri commit'lenmez."
git push -u origin feat/streamlit-dashboard
```

- [ ] **Step 5: Workflow'u elle tetikle ve yeşil gör**

GitHub'da repo secret'ı ekleyin (Settings → Secrets and variables → Actions → `EVDS_API_KEY`), sonra:

```bash
gh workflow run "Veri güncelle" --ref feat/streamlit-dashboard
gh run watch
```

Expected: her iki job da yeşil. Ingest job'ı "Veride değişiklik yok" der (veri Task 4'te zaten güncel çekildi) ya da yeni bir data commit'i push'lar.

- [ ] **Step 6: Streamlit Community Cloud'a deploy et**

Bu adım tarayıcıda elle yapılır:

1. [share.streamlit.io](https://share.streamlit.io) → GitHub ile giriş
2. New app → repo `BVmarketDashboard`, branch `main` (merge sonrası), main file `app.py`
3. Advanced settings → Python 3.12
4. Deploy sonrası app ayarlarından erişimi kısıtlayın (viewer allowlist'e BV Portföy e-postaları)

**Doğrulanacak:** allowlist'in ücretsiz katmandaki güncel davranışı burada yerinde görülecek. Beklenen şekilde çalışmazsa spec'teki risk 2'ye düşün — çare bulut VM + reverse proxy auth.

---

## Self-Review

**Spec coverage:**

| Spec gereksinimi | Karşılayan görev |
|---|---|
| Katalog-merkezli tasarım (`series.yaml`, `categories.yaml`) | Task 1 |
| CSV veri formatı, metadata katalogda | Task 1 (format), Task 4 (yazım) |
| `load_series()` tek okuma kapısı | Task 3 |
| Hazır istatistikler (son değer, MoM, YoY, 12A aralık) | Task 2 |
| Varsayılan / YoY% / MoM% toggle | Task 2 (dönüşüm), Task 6 (kontrol) |
| `chart_card()` tek fonksiyon | Task 6 (`grafik_karti`) |
| Mevsimsellik + seviye grafikleri, Plotly | Task 5 |
| Koyu tema, doğrulanmış palet | Task 5 |
| EVDS3 kontratı (endpoint, tarih formatları, alan adı, binlik ayraç) | Task 4 |
| 13 seri, 4 kategori | Task 1 (katalog), Task 4 (veri) |
| 15 yıllık pencere, tam yeniden çekim | Task 4 |
| Hata izolasyonu, non-zero exit | Task 4 (`run.py`) |
| Actions cron → commit → push | Task 7 |
| Runtime'da secret yok | Task 3/6 (Streamlit tarafı `EVDS_API_KEY` okumaz), Task 7 (yalnız Actions env) |
| Next.js silinmesi | Task 1 |
| `st.navigation` sol menü | Task 6 |
| pytest kapsamı | Task 1–5 |
| Tarayıcı doğrulaması, ekran görüntüsü | Task 6 Step 4 |
| Community Cloud deploy + allowlist doğrulaması | Task 7 Step 6 |

Boşluk yok.

**Kapsam dışı bırakılanlar (spec'te v1'de değil):** ilgili veri çipleri (`related:` alanı), arama kutusu, favoriler, Veri Takvimi bileşeni, sektör sayfaları. Bunlar Faz 2+ kapsamında.

**Type consistency:** `Seri.kaynak` alanı katalog YAML'ında da `kaynak:` anahtarıyla geçiyor (Task 1 Step 4 ↔ Step 7 `Kaynak(**ham["kaynak"])`). `gorunum` değerleri `core.stats.GORUNUMLER` sabitinden geliyor ve Task 6'da aynı sabit kullanılıyor. `seri_yolu()` Task 3'te tanımlanıp Task 4'te tüketiliyor. `RENKLER["seri"]` üç elemanlı; `mevsimsellik_figuru` varsayılan `yil_sayisi=3` ile bunu aşmıyor.
