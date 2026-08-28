# Faz 3b: Elektrik Sektörü Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** İlk sektör sayfasını kurmak — EPİAŞ kaynak tipi, üç elektrik serisi ve kategori sayfasına eklenen pano + kategoriye filtreli Veri Takvimi.

**Architecture:** `ingest/epias.py`, `ingest/evds.py`'nin biçimini izler: saf ayrıştırıcılar ağdan ayrık ve fixture'la test edilir, tek I/O kabuğu `seri_cek()`. Kimlik doğrulama TGT ticket'ı ile yapılır; ticket bir kez alınıp üç serinin çekiminde paylaşılır. Sunum tarafında `Kategori` isteğe bağlı bir `pano` alanı kazanır — mevcut `kpi_satiri()` yeniden kullanılır, yeni istatistik hesabı yazılmaz.

**Tech Stack:** Python 3.12 · Streamlit ≥1.49 · pandas · PyYAML · requests · pytest

**Spec:** `docs/superpowers/specs/2026-08-28-faz3b-elektrik-sektoru-design.md`

## Global Constraints

- **Python 3.12.** Testler `.venv/bin/python -m pytest` ile koşar.
- **Arayüz dili Türkçe.** Tanımlayıcılar, fonksiyon adları, etiketler, mesajlar ve yorumlar Türkçe.
- **Yeni çalışma zamanı bağımlılığı yok.** `requirements.txt` değişmez; `eptr2` kullanılmaz.
- **`core/` modülleri ingest'i, `ingest/` modülleri Streamlit'i import etmez.** Mevcut sınır korunur.
- **Parola koda, teste, fixture'a veya commit'e yazılmaz.** Yalnızca `os.environ` üzerinden okunur.
- **Renk paleti `core/theme.py`'de kilitli.** Bu dilim o dosyaya dokunmaz.
- **`st.dataframe` `width="stretch"` kullanır** (`use_container_width` deprecate edildi).
- **Kaynak bazlı üretim payları ve Eurostat bu dilimde YOK.** Spec'te gerekçeli olarak ertelendi.

## Doğrulanmış API bilgileri

Bunlar araştırıldı ve teyit edildi — uydurma değil:

| | |
|---|---|
| TGT alma | `POST https://giris.epias.com.tr/cas/v1/tickets` |
| TGT gövdesi | `username=<urlencoded>&password=<urlencoded>` |
| TGT başlıkları | `Content-Type: application/x-www-form-urlencoded`, `Accept: text/plain` |
| TGT yanıtı | Düz metin, `TGT-` ile başlar; HTTP 200 veya 201 |
| API tabanı | `https://seffaflik.epias.com.tr` |
| Servis öneki | `/electricity-service/` |
| API başlıkları | `Content-Type: application/json`, `TGT: <ticket>` |

**Teyit edilmemiş tek şey endpoint yollarının tam biçimi.** Teknik doküman
`realtime-generation`, `mcp` (PTF) ve `active-fullness` (baraj doluluk)
adlarını veriyor ama tam yol önekini vermiyor. Task 2 Step 1 bunu canlı API'ye
karşı çözer — konvansiyondan tahmin edilmez.

---

### Task 1: Katalog — `epias` kaynak tipi ve `pano` alanı

Katalog `epias` kaynak tipini ve kategorilerde isteğe bağlı `pano` alanını
tanır. Bu görev hiçbir seri veya kategori eklemez; mevcut altı kategori
etkilenmez.

**Files:**
- Modify: `core/catalog.py` (`GECERLI_KAYNAK_TIPLERI`, `Kategori.pano`, `kategorileri_yukle`)
- Test: `tests/test_catalog.py`

**Interfaces:**
- Produces:
  - `core.catalog.Kategori.pano: tuple[str, ...] = ()`
  - `core.catalog.GECERLI_KAYNAK_TIPLERI` artık `"epias"` içerir

- [ ] **Step 1: Testleri yaz (başarısız olmalı)**

`tests/test_catalog.py` sonuna ekleyin:

```python
def test_kategori_pano_alani_tuple_olarak_okunur(tmp_path, monkeypatch):
    from core import catalog

    (tmp_path / "categories.yaml").write_text(
        "- slug: elektrik\n"
        "  title: Elektrik\n"
        "  pano: [elektrik/uretim, elektrik/ptf]\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(catalog, "KATALOG_DIZINI", tmp_path)
    (kategori,) = catalog.kategorileri_yukle()
    assert kategori.pano == ("elektrik/uretim", "elektrik/ptf")


def test_kategori_pano_yoksa_bos_tuple(tmp_path, monkeypatch):
    from core import catalog

    (tmp_path / "categories.yaml").write_text(
        "- slug: enflasyon\n  title: Enflasyon\n", encoding="utf-8"
    )
    monkeypatch.setattr(catalog, "KATALOG_DIZINI", tmp_path)
    (kategori,) = catalog.kategorileri_yukle()
    assert kategori.pano == ()


def test_epias_gecerli_kaynak_tipi():
    from core.catalog import GECERLI_KAYNAK_TIPLERI

    assert "epias" in GECERLI_KAYNAK_TIPLERI
```

- [ ] **Step 2: Testleri koştur, başarısız olduklarını gör**

Run: `.venv/bin/python -m pytest tests/test_catalog.py -q`
Expected: FAIL — `Kategori` nesnesinin `pano` özniteliği yok; `"epias"` sette değil.

- [ ] **Step 3: `core/catalog.py`'yi güncelle**

`GECERLI_KAYNAK_TIPLERI` satırını değiştirin:

```python
GECERLI_KAYNAK_TIPLERI = {"evds", "yahoo", "epias"}
```

`Kategori` dataclass'ına alanı ekleyin (`note`'tan sonra, ikisi de varsayılanlı):

```python
@dataclass(frozen=True)
class Kategori:
    slug: str
    title: str
    note: str | None = None
    pano: tuple[str, ...] = ()
```

`kategorileri_yukle()` içinde `Kategori(...)` çağrısını değiştirin:

```python
        kategoriler.append(
            Kategori(
                slug=slug,
                title=ham["title"],
                note=ham.get("note"),
                pano=tuple(ham.get("pano", ())),
            )
        )
```

- [ ] **Step 4: Testleri koştur, geçtiklerini gör**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — tümü.

- [ ] **Step 5: Commit**

```bash
git add core/catalog.py tests/test_catalog.py
git commit -m "feat: katalog epias kaynak tipini ve kategori panosunu tanısın"
```

---

### Task 2: `ingest/epias.py` — kimlik doğrulama ve ayrıştırma

EPİAŞ istemcisi. Saf ayrıştırıcılar ağsız test edilir; ağa çıkan tek nokta
`tgt_al()` ve `seri_cek()`'tir.

**Files:**
- Create: `ingest/epias.py`
- Test: `tests/test_epias.py`

**Interfaces:**
- Consumes: `core.catalog.Seri`
- Produces:
  - `ingest.epias.TGT_URL: str`
  - `ingest.epias.TABAN: str`
  - `ingest.epias.UCLAR: dict[str, str]` — `epias_ucu` değeri → tam yol
  - `ingest.epias.tgt_al(kullanici: str, parola: str, session=None) -> str`
  - `ingest.epias.noktalari_ayikla(yanit: dict, alan: str) -> list[tuple[str, float]]`
  - `ingest.epias.seri_cek(seri: Seri, tgt: str, session=None, bugun: date | None = None) -> pd.DataFrame`

- [ ] **Step 1: Endpoint yollarını canlı API'ye karşı doğrula**

Bu adım plandaki tek keşif adımıdır ve kod yazmadan önce yapılır. Yolları
konvansiyondan tahmin etmeyin.

Önce kimlik bilgilerini kabuğa alın (parolayı komut geçmişine yazmamak için
`read -s` kullanın):

```bash
read -r EPIAS_USERNAME && export EPIAS_USERNAME   # kayıt e-postanız
read -rs EPIAS_PASSWORD && export EPIAS_PASSWORD
```

TGT alın:

```bash
TGT=$(curl -s -X POST https://giris.epias.com.tr/cas/v1/tickets \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'Accept: text/plain' \
  --data-urlencode "username=$EPIAS_USERNAME" \
  --data-urlencode "password=$EPIAS_PASSWORD")
echo "${TGT:0:12}..."   # TGT- ile başlamalı
```

Aday yolları deneyin. Teknik doküman
(https://seffaflik.epias.com.tr/electricity-service/technical/tr/index.html)
üç servisi `realtime-generation`, `mcp` ve `active-fullness` olarak adlandırıyor:

```bash
for YOL in \
  "/electricity-service/v1/generation/data/realtime-generation" \
  "/electricity-service/v1/markets/dam/data/mcp" \
  "/electricity-service/v1/generation/data/dam-active-fullness"
do
  echo "--- $YOL"
  curl -s -o /dev/null -w '%{http_code}\n' -X POST \
    "https://seffaflik.epias.com.tr$YOL" \
    -H 'Content-Type: application/json' -H "TGT: $TGT" \
    -d '{"startDate":"2026-08-01T00:00:00+03:00","endDate":"2026-08-05T00:00:00+03:00"}'
done
```

404 dönen yolları teknik dokümandaki servis listesinden düzeltin. Üçü de 200
dönene kadar devam edin, sonra **gerçek yanıt gövdesini kaydedin** — Step 2'de
fixture olarak kullanacaksınız:

```bash
curl -s -X POST "https://seffaflik.epias.com.tr<DOĞRULANAN_PTF_YOLU>" \
  -H 'Content-Type: application/json' -H "TGT: $TGT" \
  -d '{"startDate":"2026-08-01T00:00:00+03:00","endDate":"2026-08-03T00:00:00+03:00"}' \
  | head -c 2000
```

Yanıttaki liste alanının adını (`items` mi, `body.content` mi) ve her kaydın
tarih/değer alan adlarını not edin. Bunlar Step 2'deki fixture'ı ve Step 4'teki
`UCLAR`/`alan` değerlerini belirler.

- [ ] **Step 2: Testleri yaz (başarısız olmalı)**

`tests/test_epias.py` oluşturun. Aşağıdaki fixture, TP 2.0'ın tipik zarf
biçimidir; **Step 1'de kaydettiğiniz gerçek gövdeyle birebir eşleşmiyorsa
fixture'ı gerçeğe göre düzeltin** — testin değeri gerçek biçimi yansıtmasından
gelir.

```python
import pytest

from ingest.epias import noktalari_ayikla


def yanit(kayitlar):
    return {"items": kayitlar}


def test_noktalari_ayikla_tarih_ve_degeri_cikarir():
    ham = yanit([
        {"date": "2026-08-01T00:00:00+03:00", "price": 2500.0},
        {"date": "2026-08-01T01:00:00+03:00", "price": 2450.5},
    ])
    assert noktalari_ayikla(ham, "price") == [
        ("2026-08-01", 2500.0),
        ("2026-08-01", 2450.5),
    ]


def test_noktalari_ayikla_bos_degeri_atlar():
    ham = yanit([
        {"date": "2026-08-01T00:00:00+03:00", "price": None},
        {"date": "2026-08-02T00:00:00+03:00", "price": 2450.5},
    ])
    assert noktalari_ayikla(ham, "price") == [("2026-08-02", 2450.5)]


def test_noktalari_ayikla_bos_listede_bos_doner():
    assert noktalari_ayikla(yanit([]), "price") == []


def test_noktalari_ayikla_eksik_alanda_hata_verir():
    ham = yanit([{"date": "2026-08-01T00:00:00+03:00"}])
    with pytest.raises(KeyError):
        noktalari_ayikla(ham, "price")
```

- [ ] **Step 3: Testleri koştur, başarısız olduklarını gör**

Run: `.venv/bin/python -m pytest tests/test_epias.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingest.epias'`.

- [ ] **Step 4: `ingest/epias.py`'yi yaz**

`<DOĞRULANAN_*>` yer tutucularını Step 1'de teyit ettiğiniz yollarla
doldurun. Bu dosyada başka yer tutucu kalmamalı.

```python
"""EPİAŞ Şeffaflık Platformu 2.0 istemcisi.

Kimlik doğrulama TGT (ticket granting ticket) ile yapılır: kullanıcı adı ve
parola bir kez gönderilip ticket alınır, sonraki isteklere `TGT` başlığında
eklenir. Ticket ~2 saat geçerlidir; ingest koşusu dakikalar sürdüğü için
tazeleme mantığı yoktur.

Endpoint yolları UCLAR sözlüğünde toplanmıştır: EPİAŞ yol değiştirirse tek
yerde düzelir.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import requests

TGT_URL = "https://giris.epias.com.tr/cas/v1/tickets"
TABAN = "https://seffaflik.epias.com.tr"
ZAMAN_ASIMI = 30

UCLAR = {
    "uretim": "<DOĞRULANAN_URETIM_YOLU>",
    "ptf": "<DOĞRULANAN_PTF_YOLU>",
    "baraj": "<DOĞRULANAN_BARAJ_YOLU>",
}


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
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı)."""
    bugun = bugun or date.today()
    baslangic = (
        date.fromisoformat(seri.start_date)
        if seri.start_date
        else bugun - timedelta(days=365 * 5)
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
    # Saatlik veri günlüğe indirgenir; aylık toplama core tarafında yapılır.
    return df.groupby("date", as_index=False)["value"].mean()
```

- [ ] **Step 5: Testleri koştur, geçtiklerini gör**

Run: `.venv/bin/python -m pytest tests/test_epias.py -q`
Expected: PASS — dört test.

- [ ] **Step 6: Commit**

```bash
git add ingest/epias.py tests/test_epias.py
git commit -m "feat: EPİAŞ istemcisi — TGT kimlik doğrulama ve nokta ayrıştırma"
```

---

### Task 3: Katalog kayıtları ve ingest entegrasyonu

Üç seri katalogda tanımlanır, `run.py` `epias` dalını kazanır ve veri gerçek
API'den bir kez çekilip commit'lenir.

**Files:**
- Modify: `core/catalog.py` (`Seri.epias_ucu`, `Seri.epias_alani`, doğrulama)
- Modify: `catalog/categories.yaml` (`elektrik` kategorisi)
- Modify: `catalog/series.yaml` (üç seri)
- Modify: `ingest/run.py` (`_cek` üçüncü dal, kimlik okuma)
- Modify: `.github/workflows/ingest.yml` (iki secret)
- Test: `tests/test_catalog.py`, `tests/test_run.py`

**Interfaces:**
- Consumes: `ingest.epias.tgt_al`, `ingest.epias.seri_cek`
- Produces:
  - `core.catalog.Seri.epias_ucu: str | None = None`
  - `core.catalog.Seri.epias_alani: str | None = None`

- [ ] **Step 1: Testleri yaz (başarısız olmalı)**

`tests/test_catalog.py` sonuna:

```python
def test_epias_serisi_uc_ve_alan_ister():
    from core.catalog import KatalogHatasi, serileri_yukle

    serileri_yukle.cache_clear()
    seriler = serileri_yukle()
    epias = [s for s in seriler if s.kaynak_tipi == "epias"]
    assert epias, "katalogda epias serisi yok"
    for s in epias:
        assert s.epias_ucu, f"{s.id}: epias_ucu boş"
        assert s.epias_alani, f"{s.id}: epias_alani boş"
```

`tests/test_run.py` sonuna:

```python
def test_cek_epias_serisini_epias_modulune_yonlendirir(monkeypatch):
    import dataclasses

    from core.catalog import seri_getir
    from ingest import run

    cagrildi = {}

    def sahte_seri_cek(seri, tgt, session=None):
        cagrildi["tgt"] = tgt
        cagrildi["id"] = seri.id
        return "DF"

    monkeypatch.setattr(run.epias, "seri_cek", sahte_seri_cek)
    seri = dataclasses.replace(
        seri_getir("enflasyon/tufe-genel"),
        kaynak_tipi="epias", epias_ucu="ptf", epias_alani="price",
    )
    assert run._cek(seri, "ANAHTAR", "TGT-123", None) == "DF"
    assert cagrildi == {"tgt": "TGT-123", "id": "enflasyon/tufe-genel"}
```

- [ ] **Step 2: Testleri koştur, başarısız olduklarını gör**

Run: `.venv/bin/python -m pytest tests/test_catalog.py tests/test_run.py -q`
Expected: FAIL — `Seri` nesnesinin `epias_ucu` özniteliği yok; `_cek` üç
konumsal argüman alıyor.

- [ ] **Step 3: `core/catalog.py`'ye alanları ve doğrulamayı ekle**

`Seri` dataclass'ına `yahoo_symbol`'dan sonra ekleyin:

```python
    epias_ucu: str | None = None
    epias_alani: str | None = None
```

`serileri_yukle()` içinde `Seri(...)` kurulumuna ekleyin:

```python
            epias_ucu=ham.get("epias_ucu"),
            epias_alani=ham.get("epias_alani"),
```

`_dogrula()` içine, mevcut kaynak tipi kontrollerinin yanına:

```python
    if seri.kaynak_tipi == "epias" and not (seri.epias_ucu and seri.epias_alani):
        raise KatalogHatasi(
            f"epias serisi epias_ucu ve epias_alani ister: {seri.id}"
        )
```

- [ ] **Step 4: Kategoriyi ve serileri katalogda tanımla**

`catalog/categories.yaml` sonuna ekleyin:

```yaml
- slug: elektrik
  title: Elektrik
  pano: [elektrik/uretim, elektrik/ptf, elektrik/baraj-doluluk]
  note: >-
    Üretim ve PTF saatlik yayımlanır; buradaki seriler günlük ortalamaya
    indirgenmiştir.
```

`catalog/series.yaml` sonuna ekleyin. `epias_alani` değerlerini Task 2 Step 1'de
gördüğünüz gerçek alan adlarıyla değiştirin:

```yaml
- id: elektrik/uretim
  title: Toplam Elektrik Üretimi
  category: elektrik
  kaynak: { name: EPİAŞ Şeffaflık Platformu, url: "https://seffaflik.epias.com.tr" }
  kaynak_tipi: epias
  epias_ucu: uretim
  epias_alani: <GERÇEK_ÜRETİM_ALANI>
  unit: "GWh"
  freq: daily
  monthly_agg: sum
  charts: [level, seasonality]

- id: elektrik/ptf
  title: Piyasa Takas Fiyatı (PTF)
  category: elektrik
  kaynak: { name: EPİAŞ Şeffaflık Platformu, url: "https://seffaflik.epias.com.tr" }
  kaynak_tipi: epias
  epias_ucu: ptf
  epias_alani: <GERÇEK_PTF_ALANI>
  unit: "TL/MWh"
  freq: daily
  monthly_agg: mean
  charts: [level, seasonality]

- id: elektrik/baraj-doluluk
  title: Baraj Doluluk Oranı
  category: elektrik
  kaynak: { name: EPİAŞ Şeffaflık Platformu, url: "https://seffaflik.epias.com.tr" }
  kaynak_tipi: epias
  epias_ucu: baraj
  epias_alani: <GERÇEK_BARAJ_ALANI>
  unit: "%"
  freq: daily
  monthly_agg: mean
  charts: [level, seasonality]
```

**Baraj doluluk endpoint'i Task 2 Step 1'de doğrulanamadıysa** bu üçüncü seriyi
ve `pano` listesindeki `elektrik/baraj-doluluk` girdisini silin; dilim iki
seriyle tamamlanır (spec Risk 4).

- [ ] **Step 5: `ingest/run.py`'yi güncelle**

Import satırını değiştirin:

```python
from ingest import epias, evds, yahoo
```

`_cek()` imzasını ve gövdesini değiştirin:

```python
def _cek(seri: Seri, api_key: str | None, tgt: str | None, oturum):
    """Seriyi kaynak tipine göre doğru istemciye yönlendirir."""
    if seri.kaynak_tipi == "evds":
        return evds.seri_cek(seri, api_key, session=oturum)
    if seri.kaynak_tipi == "yahoo":
        return yahoo.seri_cek(seri, session=oturum)
    if seri.kaynak_tipi == "epias":
        return epias.seri_cek(seri, tgt, session=oturum)
    raise ValueError(f"Bilinmeyen kaynak tipi: {seri.kaynak_tipi}")
```

`main()` içinde, `api_key` kontrolünden hemen sonra:

```python
    tgt = None
    if any(s.kaynak_tipi == "epias" for s in seriler):
        kullanici = os.environ.get("EPIAS_USERNAME")
        parola = os.environ.get("EPIAS_PASSWORD")
        if not (kullanici and parola):
            print(
                "HATA: EPIAS_USERNAME veya EPIAS_PASSWORD tanımlı değil",
                file=sys.stderr,
            )
            return 2
```

Ve `with requests.Session() as oturum:` bloğunun **ilk satırı** olarak
(döngüden önce — ticket bir kez alınır, her seride değil):

```python
        if any(s.kaynak_tipi == "epias" for s in seriler):
            tgt = epias.tgt_al(kullanici, parola, session=oturum)
```

Döngüdeki çağrıyı güncelleyin:

```python
                df = _cek(seri, api_key, tgt, oturum)
```

- [ ] **Step 6: Workflow'a secret'ları ekle**

`.github/workflows/ingest.yml` içinde "Verileri çek" adımının `env` bloğunu:

```yaml
        env:
          EVDS_API_KEY: ${{ secrets.EVDS_API_KEY }}
          EPIAS_USERNAME: ${{ secrets.EPIAS_USERNAME }}
          EPIAS_PASSWORD: ${{ secrets.EPIAS_PASSWORD }}
```

- [ ] **Step 7: Testleri koştur, geçtiklerini gör**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — tümü.

- [ ] **Step 8: Gerçek veriyi çek**

Kimlik bilgileri kabukta tanımlı olmalı (Task 2 Step 1'deki gibi):

```bash
.venv/bin/python -m ingest.run --only elektrik/uretim
.venv/bin/python -m ingest.run --only elektrik/ptf
.venv/bin/python -m ingest.run --only elektrik/baraj-doluluk
```

Her biri `✓ ... — N nokta` yazmalı. Üretilen dosyaları doğrulayın:

```bash
head -3 data/elektrik/*.csv
wc -l data/elektrik/*.csv
```

Beklenen: `date,value` başlığı, artan tarih sırası, birkaç yüz satır.
Değerler makul aralıkta olmalı — PTF için binler mertebesinde TL/MWh, baraj
doluluk için 0–100 arası. Aralık saçmaysa `epias_alani` yanlış seçilmiş
demektir; Task 2 Step 1'deki gövdeye dönüp doğru alanı bulun.

- [ ] **Step 9: Commit**

```bash
git add core/catalog.py catalog/ ingest/run.py .github/workflows/ingest.yml \
        tests/test_catalog.py tests/test_run.py data/elektrik
git commit -m "feat: elektrik serileri — EPİAŞ ingest entegrasyonu"
```

---

### Task 4: Pano ve kategoriye filtreli Veri Takvimi

Kategori sayfası, `pano` tanımlıysa KPI kartlarını ondan seçer ve altına o
kategorinin tazelik tablosunu ekler.

**Files:**
- Modify: `core/takvim.py` (`takvim()` kategori parametresi)
- Modify: `core/page.py` (`pano_serileri`, `_kategoriyi_ciz`)
- Test: `tests/test_takvim.py`, `tests/test_page.py`

**Interfaces:**
- Consumes: `core.catalog.Kategori.pano`, `core.components.kpi_satiri`, `core.takvim.tablo_df`
- Produces:
  - `core.takvim.takvim(bugun: date | None = None, kategori: str | None = None) -> list[TakvimSatiri]`
  - `core.page.pano_serileri(kategori: Kategori, seriler: list[Seri]) -> list[Seri]`

- [ ] **Step 1: Testleri yaz (başarısız olmalı)**

`tests/test_page.py` sonuna:

```python
def test_pano_serileri_pano_sirasini_korur():
    import dataclasses

    from core.catalog import Kategori, seri_getir
    from core.page import pano_serileri

    a = dataclasses.replace(seri_getir("enflasyon/tufe-genel"), id="k/a")
    b = dataclasses.replace(seri_getir("enflasyon/tufe-genel"), id="k/b")
    kategori = Kategori(slug="k", title="K", pano=("k/b", "k/a"))
    assert [s.id for s in pano_serileri(kategori, [a, b])] == ["k/b", "k/a"]


def test_pano_bossa_ilk_seriler_dondurulur():
    import dataclasses

    from core.catalog import Kategori, seri_getir
    from core.page import pano_serileri

    seriler = [
        dataclasses.replace(seri_getir("enflasyon/tufe-genel"), id=f"k/{i}")
        for i in range(6)
    ]
    kategori = Kategori(slug="k", title="K")
    assert pano_serileri(kategori, seriler) == seriler


def test_pano_bilinmeyen_id_hata_verir():
    import pytest

    from core.catalog import Kategori, KatalogHatasi, seri_getir
    from core.page import pano_serileri

    kategori = Kategori(slug="k", title="K", pano=("k/yok",))
    with pytest.raises(KatalogHatasi):
        pano_serileri(kategori, [seri_getir("enflasyon/tufe-genel")])
```

`tests/test_takvim.py` sonuna:

```python
def test_takvim_kategoriye_filtreler():
    from core.takvim import takvim

    satirlar = takvim(kategori="enflasyon")
    assert satirlar, "enflasyon kategorisinde seri yok"
    assert {s.seri.category for s in satirlar} == {"enflasyon"}
```

- [ ] **Step 2: Testleri koştur, başarısız olduklarını gör**

Run: `.venv/bin/python -m pytest tests/test_page.py tests/test_takvim.py -q`
Expected: FAIL — `pano_serileri` import edilemiyor; `takvim()` `kategori`
argümanı almıyor.

- [ ] **Step 3: `core/takvim.py`'ye kategori parametresini ekle**

`takvim()` imzasını ve ilk satırını değiştirin:

```python
def takvim(bugun: date | None = None,
           kategori: str | None = None) -> list[TakvimSatiri]:
    bugun = bugun or date.today()
    seriler = seri_listele(kategori)
```

(`seri_listele` zaten isteğe bağlı kategori argümanı alıyor; mevcut gövdenin
geri kalanı değişmez.)

- [ ] **Step 4: `core/page.py`'ye `pano_serileri`'ni ekle**

Import satırını genişletin:

```python
from core.catalog import Kategori, KatalogHatasi, SIKLIK_ETIKETLERI, Seri, seri_listele
```

`TAKVIM_SUTUN_AYARI` tanımından sonra ekleyin:

```python
def pano_serileri(kategori: Kategori, seriler: list[Seri]) -> list[Seri]:
    """Panoda gösterilecek serileri, kategorinin belirlediği sırada döndürür.

    Pano tanımlı değilse mevcut davranış korunur: kpi_satiri zaten ilk dördü
    alır. Bilinmeyen bir id sessizce yutulmaz — yazım hatası, kartın sessizce
    kaybolmasından daha ucuza yakalanmalı.
    """
    if not kategori.pano:
        return seriler
    indeks = {s.id: s for s in seriler}
    eksik = [i for i in kategori.pano if i not in indeks]
    if eksik:
        raise KatalogHatasi(
            f"{kategori.slug} panosunda bilinmeyen seri: {', '.join(eksik)}"
        )
    return [indeks[i] for i in kategori.pano]
```

- [ ] **Step 5: `_kategoriyi_ciz`'i güncelle**

`kpi_satiri(seriler)` satırını değiştirin:

```python
    kpi_satiri(pano_serileri(kategori, seriler))
```

Ve `st.divider()`'dan hemen sonra, grafik ızgarasından önce, takvim bloğunu
ekleyin:

```python
    with st.expander("Veri Takvimi", expanded=False):
        st.dataframe(
            tablo_df(takvim(kategori=kategori.slug)),
            width="stretch",
            hide_index=True,
            column_config=TAKVIM_SUTUN_AYARI,
        )
    st.divider()
```

- [ ] **Step 6: Testleri koştur, geçtiklerini gör**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — tümü.

- [ ] **Step 7: Tarayıcıda doğrula**

```bash
.venv/bin/streamlit run app.py --server.headless true --server.port 8570 \
  > /tmp/bv-elektrik.log 2>&1 &
```

`http://localhost:8570/_stcore/health` `ok` dönene kadar bekleyin, sonra
`http://localhost:8570/elektrik` adresinde doğrulayın:

1. Sol menüde "Elektrik" görünüyor
2. Panoda üç kart: Toplam Elektrik Üretimi, PTF, Baraj Doluluk — bu sırada
3. Her kartta değer + birim + YoY + dönem var, "veri yok" yazmıyor
4. "Veri Takvimi" açılır bölümü yalnızca elektrik serilerini listeliyor
5. Üç grafik gerçek veriyle çiziliyor
6. Genel Bakış ve mevcut altı kategori sayfası bozulmamış (panosuz kategoriler
   eskisi gibi ilk dört seriyi gösteriyor)
7. `/tmp/bv-elektrik.log` içinde traceback yok

Ekran görüntüsü alın. Sunucuyu kapatın.

- [ ] **Step 8: Commit**

```bash
git add core/takvim.py core/page.py tests/test_page.py tests/test_takvim.py
git commit -m "feat: kategori panosu ve kategoriye filtreli Veri Takvimi"
```

---

## Self-Review

**Spec coverage:**

| Spec gereksinimi | Karşılayan görev |
|---|---|
| Üç EPİAŞ serisi (üretim, PTF, baraj) | Task 3 Step 4 |
| `elektrik` kategorisi | Task 3 Step 4 |
| `epias` kaynak tipi | Task 1 Step 3 |
| `Kategori.pano` alanı | Task 1 Step 3 |
| Pano render'ı, `kpi_satiri` yeniden kullanımı | Task 4 Step 4–5 |
| `takvim(kategori=...)` filtresi | Task 4 Step 3 |
| `ingest/epias.py`: TGT + `UCLAR` + `seri_cek` | Task 2 Step 4 |
| TGT bir kez alınıp paylaşılır | Task 3 Step 5 |
| Kimlik ortam değişkeninden | Task 3 Step 5 |
| Endpoint yolları implementasyonda doğrulanır | Task 2 Step 1 |
| Saf fonksiyonlar ağsız test | Task 2 Step 2, Task 4 Step 1 |
| Tarayıcı doğrulaması | Task 4 Step 7 |
| Baraj doluluk çıkmazsa iki seriyle tamamla | Task 3 Step 4 (not) |
| Yeni çalışma zamanı bağımlılığı yok | Global Constraints |

Boşluk yok.

**Kapsam dışı (spec'te de öyle):** kaynak bazlı üretim payları (çok serili
grafik gerektirir — Faz 3c), Eurostat fiyat karşılaştırması, `sectors.yaml`
ekseni, sektör hakkında/yatırımcı rehberi düzyazı bölümleri.

**Type consistency:** `Seri.epias_ucu`/`epias_alani` Task 3 Step 3'te tanımlanıp
aynı görevde doğrulanıyor; Task 2'nin `seri_cek`'i ikisini de okuyor ve Task 2
Task 3'ten önce geldiği için `ingest/epias.py` yazılırken alanlar henüz yok —
ancak `seri_cek` çalışma zamanında okuduğu için import hatası doğurmaz ve
Task 2'nin testleri yalnızca `noktalari_ayikla`'yı çağırır. `UCLAR` anahtarları
(`uretim`, `ptf`, `baraj`) Task 2 Step 4'te tanımlanıp Task 3 Step 4'teki
`epias_ucu` değerleriyle birebir eşleşiyor. `_cek()` imzası Task 3 Step 5'te
dört argümana çıkıyor ve aynı adımda tek çağrı yeri güncelleniyor;
`tests/test_run.py`'deki yeni test bu imzayı kullanıyor.

**Bilinçli sapma:** Task 2'nin fixture'ı gerçek yanıt gövdesine göre
düzeltilmek üzere yazılmıştır. TP 2.0 zarf biçimini kimlik bilgisi olmadan
teyit edemedik; testin değeri gerçek biçimi yansıtmasından geldiği için
adımda bu açıkça belirtildi.
