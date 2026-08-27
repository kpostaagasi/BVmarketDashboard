# Faz 3a: Veri Takvimi — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Panoya, her serinin ne kadar süredir güncellenmediğini ve bunun frekansı için normal olup olmadığını gösteren bir Veri Takvimi sayfası eklemek.

**Architecture:** `core/takvim.py` durum hesabını saf tutar — I/O'yu ince bir kabuğa iterek `satir_uret(seri, son_donem, bugun)` veriyi parametre olarak alır, böylece mantığın tamamı dosyasız ve Streamlit'siz test edilir. Render `core/page.py`'ye gider. Ingest tarafı hiç değişmez.

**Tech Stack:** Python 3.12 · Streamlit ≥1.49 · pandas · PyYAML · pytest

**Spec:** `docs/superpowers/specs/2026-08-27-faz3a-veri-takvimi-design.md`

## Global Constraints

- **Python 3.12.**
- **Arayüz dili Türkçe.** Tanımlayıcılar, fonksiyon adları, etiketler, mesajlar ve yorumlar Türkçe.
- **`core/takvim.py` doğrudan Streamlit import etmez.** Durum hesabı saf kalır; render `core/page.py`'de.
- **`ingest/` bu dilimde hiç değişmez.** Diff `ingest/` altına dokunmamalı.
- **Renk paleti `core/theme.py`'de kilitli.** Hiçbir hex değeri değiştirilmez; bu dilim o dosyaya dokunmaz.
- **Eşikler tek yerde:** `daily` 5 gün, `weekly` 14 gün, `monthly` 50 gün. Sezgisel oldukları modül docstring'inde açıkça yazılı.
- **`gecikmiş` eşiği:** eşiğin 2 katı. Yani `bekleme <= esik` → güncel, `<= esik*2` → bekleniyor, üstü → gecikmiş.
- **`yayin_notu` alanı kurulur ama hiçbir seriye doldurulmaz.** Yayın ritimleri doğrulanmadan yazılmaz — yanlış bir not hiç not olmamasından kötüdür.
- **`st.dataframe` `width="stretch"` kullanır** (`use_container_width` 1.49'da deprecate edildi).

---

### Task 1: Saf hesaplama katmanı ve katalog alanı

`core/takvim.py` durum hesabını, sıralamayı ve tablo üretimini sağlar. `Seri` opsiyonel bir `yayin_notu` alanı kazanır. Sıklık etiketleri `core/components.py`'deki özel sabitten çıkarılıp `core/catalog.py`'ye taşınır ki iki modül paylaşsın.

**Files:**
- Create: `core/takvim.py`
- Modify: `core/catalog.py` (`Seri.yayin_notu`, `SIKLIK_ETIKETLERI`)
- Modify: `core/components.py` (özel sıklık sözlüğü yerine ortak sabit)
- Test: `tests/test_takvim.py`, `tests/test_catalog.py`

**Interfaces:**
- Consumes: `core.catalog.Seri`, `core.catalog.seri_listele`, `core.data.seri_csv_oku`, `core.data.seri_yolu`, `core.data.VeriYokHatasi`
- Produces:
  - `core.catalog.SIKLIK_ETIKETLERI: dict[str, str]` — `{"daily": "GÜNLÜK", "weekly": "HAFTALIK", "monthly": "AYLIK"}`
  - `core.catalog.Seri.yayin_notu: str | None = None`
  - `core.takvim.ESIKLER: dict[str, int]`
  - `core.takvim.GUNCEL`, `BEKLENIYOR`, `GECIKMIS`, `VERI_YOK` — durum sabitleri
  - `core.takvim.TakvimSatiri` — frozen dataclass `(seri: Seri, son_donem: date | None, bekleme_gunu: int | None, durum: str)`
  - `core.takvim.durum_hesapla(freq: str, bekleme_gunu: int) -> str`
  - `core.takvim.satir_uret(seri: Seri, son_donem: date | None, bugun: date) -> TakvimSatiri`
  - `core.takvim.sirala(satirlar: list[TakvimSatiri]) -> list[TakvimSatiri]`
  - `core.takvim.tablo_df(satirlar: list[TakvimSatiri]) -> pd.DataFrame`
  - `core.takvim.takvim(bugun: date | None = None) -> list[TakvimSatiri]` — I/O kabuğu

- [ ] **Step 1: Testleri yaz (başarısız olmalı)**

`tests/test_takvim.py`:

```python
import dataclasses
from datetime import date

import pandas as pd

from core.catalog import seri_getir
from core.takvim import (
    BEKLENIYOR,
    GECIKMIS,
    GUNCEL,
    VERI_YOK,
    TakvimSatiri,
    durum_hesapla,
    satir_uret,
    sirala,
    tablo_df,
)


def seri(freq="monthly"):
    return dataclasses.replace(seri_getir("enflasyon/tufe-genel"), freq=freq)


def test_gunluk_esik_icinde_guncel():
    assert durum_hesapla("daily", 0) == GUNCEL
    assert durum_hesapla("daily", 5) == GUNCEL


def test_gunluk_esigin_bir_ustu_bekleniyor():
    assert durum_hesapla("daily", 6) == BEKLENIYOR
    assert durum_hesapla("daily", 10) == BEKLENIYOR


def test_gunluk_iki_kat_esigin_ustu_gecikmis():
    assert durum_hesapla("daily", 11) == GECIKMIS


def test_haftalik_esikleri():
    assert durum_hesapla("weekly", 14) == GUNCEL
    assert durum_hesapla("weekly", 15) == BEKLENIYOR
    assert durum_hesapla("weekly", 29) == GECIKMIS


def test_aylik_esikleri():
    assert durum_hesapla("monthly", 50) == GUNCEL
    assert durum_hesapla("monthly", 51) == BEKLENIYOR
    assert durum_hesapla("monthly", 101) == GECIKMIS


def test_satir_uret_bekleme_gununu_hesaplar():
    satir = satir_uret(seri("monthly"), date(2026, 7, 1), date(2026, 8, 27))
    assert satir.bekleme_gunu == 57
    assert satir.durum == BEKLENIYOR
    assert satir.son_donem == date(2026, 7, 1)


def test_satir_uret_verisi_olmayan_seriyi_isaretler():
    satir = satir_uret(seri("daily"), None, date(2026, 8, 27))
    assert satir.durum == VERI_YOK
    assert satir.son_donem is None
    assert satir.bekleme_gunu is None


def test_sirala_once_ciddiyeti_sonra_beklemeyi_kullanir():
    s = seri("daily")
    satirlar = [
        TakvimSatiri(s, date(2026, 8, 26), 1, GUNCEL),
        TakvimSatiri(s, date(2026, 8, 1), 26, GECIKMIS),
        TakvimSatiri(s, None, None, VERI_YOK),
        TakvimSatiri(s, date(2026, 8, 20), 7, BEKLENIYOR),
        TakvimSatiri(s, date(2026, 8, 10), 17, GECIKMIS),
    ]
    assert [x.durum for x in sirala(satirlar)] == [
        VERI_YOK,
        GECIKMIS,
        GECIKMIS,
        BEKLENIYOR,
        GUNCEL,
    ]
    # aynı durumda daha uzun bekleyen üstte
    gecikmisler = [x for x in sirala(satirlar) if x.durum == GECIKMIS]
    assert [x.bekleme_gunu for x in gecikmisler] == [26, 17]


def test_tablo_df_sutunlari_ve_sirasi():
    s = seri("monthly")
    satirlar = [TakvimSatiri(s, date(2026, 7, 1), 57, BEKLENIYOR)]
    df = tablo_df(satirlar)
    assert list(df.columns) == [
        "Veri",
        "Kategori",
        "Son Dönem",
        "Durum",
        "Sıklık",
        "Kaynak",
        "Yayın notu",
    ]
    assert df.iloc[0]["Veri"] == s.title
    assert df.iloc[0]["Son Dönem"] == "2026-07-01"
    assert df.iloc[0]["Durum"] == "bekleniyor (57 gün)"
    assert df.iloc[0]["Sıklık"] == "AYLIK"


def test_tablo_df_verisi_olmayan_seride_tire_gosterir():
    s = seri("daily")
    df = tablo_df([TakvimSatiri(s, None, None, VERI_YOK)])
    assert df.iloc[0]["Son Dönem"] == "—"
    assert df.iloc[0]["Durum"] == "veri yok"


def test_tablo_df_yayin_notu_yoksa_bos():
    s = seri("monthly")
    df = tablo_df([TakvimSatiri(s, date(2026, 7, 1), 57, BEKLENIYOR)])
    assert df.iloc[0]["Yayın notu"] == ""
```

`tests/test_catalog.py`'ye ekleyin:

```python
def test_yayin_notu_varsayilan_none():
    assert seri_getir("enflasyon/tufe-genel").yayin_notu is None


def test_siklik_etiketleri_tum_frekanslari_kapsar():
    from core.catalog import GECERLI_FREKANSLAR, SIKLIK_ETIKETLERI

    assert set(SIKLIK_ETIKETLERI) == GECERLI_FREKANSLAR
```

- [ ] **Step 2: Testleri koştur, başarısız olduklarını gör**

Run: `.venv/bin/python -m pytest tests/test_takvim.py tests/test_catalog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.takvim'` ve `test_catalog.py`'de `ImportError: cannot import name 'SIKLIK_ETIKETLERI'`

- [ ] **Step 3: Katalogu güncelle**

`core/catalog.py`'de `GECERLI_KAYNAK_TIPLERI` satırının altına ekleyin:

```python
SIKLIK_ETIKETLERI = {"daily": "GÜNLÜK", "weekly": "HAFTALIK", "monthly": "AYLIK"}
```

`Seri` dataclass'ının sonuna, `start_date`'in altına ekleyin:

```python
    yayin_notu: str | None = None
```

`serileri_yukle` içindeki `Seri(...)` çağrısına, `start_date` satırının altına ekleyin:

```python
            yayin_notu=ham.get("yayin_notu"),
```

- [ ] **Step 4: `core/components.py`'yi ortak sabite geçir**

Dosyanın başındaki şu satırı **silin**:

```python
_SIKLIK_ETIKETLERI = {"daily": "GÜNLÜK", "weekly": "HAFTALIK", "monthly": "AYLIK"}
```

Import satırını şu hâle getirin (mevcut `from core.catalog import Seri` satırını değiştirin):

```python
from core.catalog import SIKLIK_ETIKETLERI, Seri
```

Ve `grafik_karti` içindeki kullanımı güncelleyin:

```python
        etiket = SIKLIK_ETIKETLERI[seri.freq]
```

- [ ] **Step 5: `core/takvim.py`'yi yaz**

```python
"""Veri Takvimi: serilerin tazelik durumu.

Saf hesaplama — bu modül doğrudan Streamlit import etmez. Sayfa render'ı
core/page.py'dedir.

Eşikler SEZGİSELDİR: bir periyot artı tipik yayın gecikmesi. Tek yerde
tutulurlar ki gürültü görüldüğünde ayarlanabilsinler. Seri bazında geçersiz
kılma bilinçli olarak eklenmedi — hangi serinin gürültü çıkaracağı henüz
bilinmiyor.

Bu sayfanın asıl işi ileriye bakan bir yayın takvimi değil, geriye bakan bir
tazelik monitörü olmaktır: bir seri geciktiğinde ya kaynak geç kalmıştır ya da
bizim ingest'imiz sessizce kırılmıştır. İkincisi başka hiçbir yerde görünmez.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from core.catalog import SIKLIK_ETIKETLERI, Seri, seri_listele
from core.data import VeriYokHatasi, seri_csv_oku, seri_yolu

ESIKLER = {"daily": 5, "weekly": 14, "monthly": 50}

GUNCEL = "güncel"
BEKLENIYOR = "bekleniyor"
GECIKMIS = "gecikmiş"
VERI_YOK = "veri yok"

# Sıralama ciddiyeti: verisi hiç olmayan en gürültülü sorundur.
_CIDDIYET = {VERI_YOK: 0, GECIKMIS: 1, BEKLENIYOR: 2, GUNCEL: 3}


@dataclass(frozen=True)
class TakvimSatiri:
    seri: Seri
    son_donem: date | None
    bekleme_gunu: int | None
    durum: str


def durum_hesapla(freq: str, bekleme_gunu: int) -> str:
    esik = ESIKLER[freq]
    if bekleme_gunu <= esik:
        return GUNCEL
    if bekleme_gunu <= esik * 2:
        return BEKLENIYOR
    return GECIKMIS


def satir_uret(seri: Seri, son_donem: date | None, bugun: date) -> TakvimSatiri:
    """Veriyi parametre alır — I/O yapmaz, bu yüzden dosyasız test edilebilir."""
    if son_donem is None:
        return TakvimSatiri(
            seri=seri, son_donem=None, bekleme_gunu=None, durum=VERI_YOK
        )
    bekleme = (bugun - son_donem).days
    return TakvimSatiri(
        seri=seri,
        son_donem=son_donem,
        bekleme_gunu=bekleme,
        durum=durum_hesapla(seri.freq, bekleme),
    )


def sirala(satirlar: list[TakvimSatiri]) -> list[TakvimSatiri]:
    """Önce durum ciddiyeti, sonra bekleme süresi azalan."""
    return sorted(
        satirlar,
        key=lambda s: (_CIDDIYET[s.durum], -(s.bekleme_gunu or 0)),
    )


def _durum_metni(satir: TakvimSatiri) -> str:
    if satir.bekleme_gunu is None:
        return satir.durum
    if satir.durum == GUNCEL:
        return satir.durum
    return f"{satir.durum} ({satir.bekleme_gunu} gün)"


def tablo_df(satirlar: list[TakvimSatiri]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Veri": s.seri.title,
                "Kategori": s.seri.category,
                "Son Dönem": "—" if s.son_donem is None else s.son_donem.isoformat(),
                "Durum": _durum_metni(s),
                "Sıklık": SIKLIK_ETIKETLERI[s.seri.freq],
                "Kaynak": s.seri.kaynak.name,
                "Yayın notu": s.seri.yayin_notu or "",
            }
            for s in satirlar
        ]
    )


def takvim(bugun: date | None = None) -> list[TakvimSatiri]:
    """Katalogdaki her seri için satır üretir. Tek I/O yapan fonksiyon."""
    bugun = bugun or date.today()
    satirlar = []
    for seri in seri_listele():
        try:
            df = seri_csv_oku(seri_yolu(seri.id))
            son = df.index.max().date()
        except VeriYokHatasi:
            son = None
        satirlar.append(satir_uret(seri, son, bugun))
    return sirala(satirlar)
```

Not: `core.data` import'u dolaylı olarak Streamlit'i çekiyor (devredilen işler listesinde 14 numara). Bu modül doğrudan Streamlit import etmiyor ve mantığın tamamı `satir_uret`/`durum_hesapla`/`sirala`/`tablo_df` içinde saf — testler dosyaya da Streamlit'e de dokunmuyor.

- [ ] **Step 6: Testleri koştur, geçtiklerini gör**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — 94 mevcut + 13 yeni = 107 test. Sayı farklı çıkarsa testleri sayıya uydurmayın, bildirin.

- [ ] **Step 7: Commit**

```bash
git add core/takvim.py core/catalog.py core/components.py tests/test_takvim.py tests/test_catalog.py
git commit -m "feat: Veri Takvimi hesaplama katmanı

Durum hesabı saf: satir_uret veriyi parametre alıyor, testler dosyasız
koşuyor. Sıklık etiketleri components'ten catalog'a taşındı."
```

---

### Task 2: Sayfa ve navigasyon

Veri Takvimi sayfası "Genel" grubuna eklenir. Sorun varsa üstte uyarı bloğu, altta tam tablo.

**Files:**
- Modify: `core/page.py` (`veri_takvimi_sayfasi()`)
- Modify: `app.py` ("Genel" grubuna ikinci sayfa)
- Test: tarayıcı doğrulaması (Streamlit render'ı birim testine uygun değil; hesaplama Task 1'de test edildi)

**Interfaces:**
- Consumes: `core.takvim.takvim`, `core.takvim.tablo_df`, `core.takvim.GUNCEL`, `core.takvim.TakvimSatiri`, `core.catalog.SIKLIK_ETIKETLERI`
- Produces: `core.page.veri_takvimi_sayfasi() -> None`

- [ ] **Step 1: `core/page.py`'ye sayfayı ekle**

Import satırlarına ekleyin:

```python
from core.catalog import SIKLIK_ETIKETLERI
from core.takvim import GUNCEL, tablo_df, takvim
```

(`core.catalog`'dan zaten `Kategori, seri_listele` import ediliyor — `SIKLIK_ETIKETLERI`'ni o satıra ekleyin, ayrı satır açmayın.)

Dosyanın sonuna ekleyin:

```python
def veri_takvimi_sayfasi() -> None:
    satirlar = takvim()
    sorunlular = [s for s in satirlar if s.durum != GUNCEL]

    st.title("Veri Takvimi")
    st.caption(
        f"{len(satirlar)} seri · {len(satirlar) - len(sorunlular)} güncel · "
        f"{len(sorunlular)} dikkat gerektiriyor"
    )
    st.caption(
        "Bir seri geciktiğinde ya kaynak geç kalmıştır ya da ingest kırılmıştır."
    )

    if sorunlular:
        with st.container(border=True):
            st.markdown(f"**⚠ {len(sorunlular)} seri dikkat gerektiriyor**")
            for s in sorunlular:
                sure = (
                    "hiç veri yok"
                    if s.bekleme_gunu is None
                    else f"{s.bekleme_gunu} gündür yeni veri yok"
                )
                st.markdown(
                    f"- **{s.seri.title}** — {sure} "
                    f"({SIKLIK_ETIKETLERI[s.seri.freq].lower()})"
                )
        st.divider()

    st.dataframe(tablo_df(satirlar), width="stretch", hide_index=True)
```

- [ ] **Step 2: `app.py`'ye bağla**

Import satırını şu hâle getirin:

```python
from core.page import genel_bakis_yap, kategori_sayfasi_yap, veri_takvimi_sayfasi
```

`ana_sayfa` tanımının altına ekleyin:

```python
takvim_sayfasi = st.Page(
    veri_takvimi_sayfasi,
    title="Veri Takvimi",
    url_path="veri-takvimi",
)
```

Ve `st.navigation` çağrısını şu hâle getirin:

```python
st.navigation(
    {"Genel": [ana_sayfa, takvim_sayfasi], "Veri Sayfaları": kategori_sayfalari}
).run()
```

- [ ] **Step 3: Testleri koştur**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — 107, değişmemiş (bu görev test eklemiyor).

- [ ] **Step 4: Tarayıcıda doğrula**

```bash
.venv/bin/streamlit run app.py --server.headless true --server.port 8560 > /tmp/bv-takvim.log 2>&1 &
```

`http://localhost:8560/_stcore/health` `ok` dönene kadar bekleyin, sonra doğrulayın:

1. Sol menüde "Genel" grubunda iki sayfa: Genel Bakış, Veri Takvimi
2. `/veri-takvimi` doğrudan açılıyor ("Page not found" yok)
3. Başlıkta özet satırı: "23 seri · N güncel · M dikkat gerektiriyor"
4. Tablo 23 satır, sütunlar `Veri · Kategori · Son Dönem · Durum · Sıklık · Kaynak · Yayın notu`
5. Sıralama doğru: dikkat gerektirenler en üstte
6. `/tmp/bv-takvim.log` içinde traceback yok

Ekran görüntüsü alın. Sunucuyu kapatın.

- [ ] **Step 5: Uyarı bloğunu sentetik bir bayat seriyle doğrula**

Uyarı bloğu ancak sorun varsa render olur. Gerçek veri tazeyse blok hiç görünmez ve o yolu doğrulamamış olursunuz. Geçici olarak bir CSV'nin son satırlarını silip bloğun göründüğünü teyit edin:

```bash
cp data/enflasyon/tufe-genel.csv /tmp/tufe-yedek.csv
head -100 /tmp/tufe-yedek.csv > data/enflasyon/tufe-genel.csv
```

Sayfayı yenileyin: "TÜFE Genel Endeks" uyarı bloğunda görünmeli ve tablonun en üstünde olmalı. Ekran görüntüsü alın.

**Sonra mutlaka geri alın:**

```bash
cp /tmp/tufe-yedek.csv data/enflasyon/tufe-genel.csv
git diff --stat data/   # boş olmalı
```

`git status --short` commit öncesi temiz olmalı — bu görev `data/` altında hiçbir şey değiştirmez.

- [ ] **Step 6: Commit**

```bash
git add core/page.py app.py
git commit -m "feat: Veri Takvimi sayfası

Genel grubuna eklendi. Sorun varsa üstte uyarı bloğu, altta tam tablo."
```

---

## Self-Review

**Spec coverage:**

| Spec gereksinimi | Karşılayan görev |
|---|---|
| Durum üç değer + `veri yok` | Task 1 (`durum_hesapla`, `satir_uret`) |
| Eşikler tek yerde, sezgisel olduğu belgeli | Task 1 (`ESIKLER` + modül docstring) |
| `gecikmiş` = eşiğin 2 katı | Task 1 (`durum_hesapla`) |
| Sıralama: ciddiyet, sonra bekleme azalan | Task 1 (`sirala`) |
| Tablo sütunları | Task 1 (`tablo_df`) |
| `yayin_notu` opsiyonel, doldurulmuyor | Task 1 (katalog alanı, hiçbir seriye eklenmiyor) |
| `core/takvim.py` doğrudan Streamlit import etmez | Task 1 (import listesi) |
| Uyarı bloğu, yalnızca sorun varsa | Task 2 |
| Tam tablo, `st.dataframe` | Task 2 |
| "Genel" grubuna navigasyon | Task 2 |
| Tarayıcı doğrulaması | Task 2 Step 4–5 |
| `ingest/` değişmez | Her iki görevin dosya listesi |

Boşluk yok.

**Kapsam dışı (spec'te de öyle):** sektör sayfası kabuğu, yayın kuralı motoru, seri bazında eşik geçersiz kılma, ileriye bakan yayın tarihleri.

**Type consistency:** `TakvimSatiri` alan adları Task 1'de tanımlanıp aynı görevde test ediliyor; Task 2 yalnızca `.durum`, `.bekleme_gunu`, `.seri.title`, `.seri.freq` okuyor — hepsi tanımlı. `SIKLIK_ETIKETLERI` Task 1'de `core/catalog.py`'ye taşınıp `components.py` ve `takvim.py` tarafından, Task 2'de `page.py` tarafından tüketiliyor. `takvim()` ve `tablo_df()` imzaları Task 1'de sabitlenip Task 2'de aynen çağrılıyor.

**Bilinçli sapma:** `core/takvim.py`, `core.data`'dan import ettiği için dolaylı olarak Streamlit'i çekiyor. Spec "doğrudan Streamlit import etmez" diyor ve bu sağlanıyor; dolaylı bağımlılık devredilen işler listesinde 14 numaradır ve bu dilim onu değiştirmiyor. Mantığın tamamı I/O'suz fonksiyonlarda olduğu için testler ne dosyaya ne Streamlit'e dokunuyor.
