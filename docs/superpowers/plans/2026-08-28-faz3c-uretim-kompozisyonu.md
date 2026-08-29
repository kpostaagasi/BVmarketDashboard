# Faz 3c: Üretim Kompozisyonu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Elektrik üretiminin kaynak bazlı dağılımını gösteren çok bileşenli bir seri ve kompozisyon grafiği eklemek.

**Architecture:** Yeni bir üst kavram icat edilmez; mevcut `Seri` geniş CSV'ye (`date` + grup başına bir sütun) izin veren isteğe bağlı bir `epias_bilesenler` alanı kazanır. Okuma tarafında `load_series`'in sözleşmesi korunur, geniş seriler için ayrı bir okuyucu eklenir. Paylar diske YAZILMAZ; CSV mutlak GWh tutar ve yüzde, çizim anında hesaplanır — böylece Pay%/GWh toggle'ı tek dosyadan beslenir.

**Tech Stack:** Python 3.12 · Streamlit ≥1.49 · pandas · Plotly · PyYAML · requests · pytest

**Spec:** `docs/superpowers/specs/2026-08-28-faz3c-uretim-kompozisyonu-design.md`

## Global Constraints

- **Python 3.12.** Testler `.venv/bin/python -m pytest` ile koşar.
- **Arayüz dili Türkçe.** Tanımlayıcılar, fonksiyon adları, etiketler, mesajlar, yorumlar ve docstring'ler Türkçe.
- **Yeni çalışma zamanı bağımlılığı yok.** `requirements.txt` değişmez.
- **`core/` modülleri `ingest/`'i import etmez; `ingest/` Streamlit import etmez.**
- **Kimlik bilgisi koda, teste, fixture'a veya commit'e yazılmaz.** Kimlik yalnızca `os.environ` üzerinden; canlı çekim `set -a; . ./.env; set +a` ile yapılır, `.env` okunmaz/yazdırılmaz.
- **`load_series`'in mevcut sözleşmesi bozulmaz** — 24 seri ona bağlı.
- **Paylar diske yazılmaz.** CSV mutlak değer tutar; yüzde çizim anında hesaplanır.
- **`importExport` hiçbir gruba girmez ve paydadan dışlanır.** Üretim kaynağı değil, ticaret kalemidir.
- **`st.dataframe` / `st.plotly_chart` `width="stretch"` kullanır.**

## Doğrulanmış API bilgileri

Canlı EPİAŞ'a karşı ölçüldü (2026-08-20, 12:00 saati) — uydurma değil:

- `realtime-generation` yanıtı saat başına 16 kaynak alanı + `total` + `date` + `hour` döndürür.
- 16 alanın toplamı `total`'a **birebir** eşittir (fark 0,00).
- `total`, `importExport`'u İÇERİR ve o negatif olabilir (ölçümde −833,9 MWh).
- Alan adları: `naturalGas`, `dammedHydro`, `lignite`, `river`, `importCoal`, `wind`, `sun`, `fueloil`, `geothermal`, `asphaltiteCoal`, `blackCoal`, `biomass`, `naphta`, `lng`, `importExport`, `wasteheat`.

---

### Task 1: Katalog — `composition` grafiği ve `epias_bilesenler` alanı

Katalog çok bileşenli seriyi tanır. Bu görev veri çekmez, grafik çizmez.

**Files:**
- Modify: `core/catalog.py` (`GECERLI_GRAFIKLER`, `Seri.epias_bilesenler`, `KAYNAK_ALANLARI`, `serileri_yukle`, `_dogrula`)
- Modify: `catalog/series.yaml` (yeni seri + `elektrik/uretim` başlık düzeltmesi)
- Test: `tests/test_catalog.py`

**Interfaces:**
- Produces:
  - `core.catalog.Seri.epias_bilesenler: dict[str, tuple[str, ...]] | None = None`
  - `core.catalog.GECERLI_GRAFIKLER` artık `"composition"` içerir
  - Katalogda `elektrik/uretim-kompozisyon` serisi

**Modelleme notu — neden XOR:** `epias_alani` bugün epias için ZORUNLU. Kompozisyon serisinin tek bir alanı yoktur, bileşenleri vardır. Bu yüzden `epias_alani` tablodaki `zorunlu`dan `istege_bagli`ya taşınır ve yerine açık bir XOR kuralı gelir: bir epias serisi ya `epias_alani` ya `epias_bilesenler` taşır, ikisini birden ya da hiçbirini değil.

- [ ] **Step 1: Testleri yaz (başarısız olmalı)**

`tests/test_catalog.py` sonuna ekleyin:

```python
def test_composition_gecerli_grafik_turu():
    from core.catalog import GECERLI_GRAFIKLER

    assert "composition" in GECERLI_GRAFIKLER


def test_epias_serisi_alan_ve_bilesenleri_birlikte_tasiyamaz():
    with pytest.raises(KatalogHatasi, match="epias_bilesenler"):
        _dogrula_ham(
            _ham_seri(
                kaynak_tipi="epias", epias_ucu="uretim", epias_alani="total",
                epias_bilesenler={"Kömür": ["lignite"]},
                evds_code=None, evds_frequency=None,
            )
        )


def test_epias_serisi_ikisinden_birini_tasimali():
    with pytest.raises(KatalogHatasi, match="epias_alani"):
        _dogrula_ham(
            _ham_seri(
                kaynak_tipi="epias", epias_ucu="uretim",
                evds_code=None, evds_frequency=None,
            )
        )


def test_bilesenli_seri_composition_grafigi_ister():
    with pytest.raises(KatalogHatasi, match="composition"):
        _dogrula_ham(
            _ham_seri(
                kaynak_tipi="epias", epias_ucu="uretim",
                epias_bilesenler={"Kömür": ["lignite"]},
                charts=["level"],
                evds_code=None, evds_frequency=None,
            )
        )


def test_composition_grafigi_bilesen_ister():
    with pytest.raises(KatalogHatasi, match="composition"):
        _dogrula_ham(
            _ham_seri(
                kaynak_tipi="epias", epias_ucu="ptf", epias_alani="price",
                charts=["composition"],
                evds_code=None, evds_frequency=None,
            )
        )


def test_bilesenler_tuple_olarak_okunur():
    from core.catalog import seri_getir, serileri_yukle

    serileri_yukle.cache_clear()
    try:
        seri = seri_getir("elektrik/uretim-kompozisyon")
        assert seri.epias_bilesenler["Hidroelektrik"] == ("dammedHydro", "river")
        assert "importExport" not in {
            alan for alanlar in seri.epias_bilesenler.values() for alan in alanlar
        }
    finally:
        serileri_yukle.cache_clear()


def test_uretim_serisi_basligi_net_ithalati_belirtir():
    """total = üretim + net ithalat; başlık bunu saklamamalı."""
    from core.catalog import seri_getir

    assert "ithalat" in seri_getir("elektrik/uretim").title.lower()
```

- [ ] **Step 2: Testleri koştur, başarısız olduklarını gör**

Run: `.venv/bin/python -m pytest tests/test_catalog.py -q`
Expected: FAIL — `"composition"` sette değil; `Seri` nesnesinin `epias_bilesenler` özniteliği yok; `elektrik/uretim-kompozisyon` katalogda yok.

- [ ] **Step 3: `core/catalog.py`'yi güncelle**

`GECERLI_GRAFIKLER` satırını değiştirin:

```python
GECERLI_GRAFIKLER = {"seasonality", "level", "composition"}
```

`Seri` dataclass'ına `epias_alani`'ndan sonra ekleyin:

```python
    epias_bilesenler: dict[str, tuple[str, ...]] | None = None
```

`KAYNAK_ALANLARI["epias"]` girdisini değiştirin — `epias_alani` artık zorunlu değil, XOR kuralı `_dogrula`'da:

```python
    "epias": {
        "zorunlu": ("epias_ucu",),
        "istege_bagli": ("epias_alani", "epias_bilesenler", "start_date", "olcek"),
    },
```

`serileri_yukle()` içinde `Seri(...)` kurulumuna ekleyin:

```python
            epias_bilesenler=(
                {ad: tuple(alanlar) for ad, alanlar in ham["epias_bilesenler"].items()}
                if "epias_bilesenler" in ham
                else None
            ),
```

`_dogrula()` içinde, mevcut `epias` `monthly_agg` kuralının yanına ekleyin:

```python
    if seri.kaynak_tipi == "epias":
        # Tek alan mı, bileşen grubu mu: biri ya da diğeri, ikisi birden değil.
        if bool(seri.epias_alani) == bool(seri.epias_bilesenler):
            raise KatalogHatasi(
                f"{seri.id}: epias serisi ya epias_alani ya epias_bilesenler "
                "taşımalı (ikisi birden ya da hiçbiri değil)"
            )
    if bool(seri.epias_bilesenler) != ("composition" in seri.charts):
        raise KatalogHatasi(
            f"{seri.id}: epias_bilesenler ile composition grafiği birlikte "
            "kullanılır; biri varsa diğeri de olmalı"
        )
```

- [ ] **Step 4: Katalog kaydını ekle ve başlığı düzelt**

`catalog/series.yaml` içinde `elektrik/uretim` serisinin `title` satırını değiştirin:

```yaml
  title: Toplam Elektrik Arzı (net ithalat dahil)
```

Aynı dosyanın sonuna yeni seriyi ekleyin. Gruplar spec'teki tabloyla birebir; `importExport`, `total` ve `hour` hiçbir gruba girmez:

```yaml
- id: elektrik/uretim-kompozisyon
  title: Kaynak Bazlı Üretim
  category: elektrik
  kaynak: { name: EPİAŞ Şeffaflık Platformu, url: "https://seffaflik.epias.com.tr" }
  kaynak_tipi: epias
  epias_ucu: uretim
  epias_bilesenler:
    Kömür: [importCoal, lignite, blackCoal, asphaltiteCoal]
    Hidroelektrik: [dammedHydro, river]
    Doğalgaz: [naturalGas, lng]
    Güneş: [sun]
    Rüzgar: [wind]
    Jeotermal: [geothermal]
    Biyo/Atık: [biomass, wasteheat]
    Diğer: [fueloil, naphta]
  unit: "GWh"
  freq: daily
  monthly_agg: sum
  olcek: 0.001
  charts: [composition]
```

- [ ] **Step 5: Testleri koştur, geçtiklerini gör**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — tümü. Katalog artık 26 seri içerir; seri sayısını sabitleyen mevcut testler (`test_seri_sayisi`, `test_gercek_katalog_alan_sahipligini_gecer`) 25 → 26 güncellenmelidir.

**Not:** Bu adımda veri dosyası HENÜZ YOK. `core/takvim.py` katalogdaki her seriyi okumaya çalıştığı için takvim testleri `VeriYokHatasi` yolundan geçecek — bu beklenen davranış (o yol zaten `VERI_YOK` durumu üretiyor) ve testleri kırmamalı. Kırıyorsa sebebini raporlayın.

- [ ] **Step 6: Commit**

```bash
git add core/catalog.py catalog/series.yaml tests/test_catalog.py
git commit -m "feat: katalog çok bileşenli seriyi ve composition grafiğini tanısın"
```

---

### Task 2: Geniş CSV okuma ve takvim uyumu

Geniş CSV için ayrı okuyucu; Veri Takvimi bu seride kırılmamalı.

**Files:**
- Modify: `core/data.py` (`genis_csv_oku`, `load_wide_series`)
- Modify: `core/takvim.py` (geniş seriyi de okuyabilmeli)
- Test: `tests/test_data.py`, `tests/test_takvim.py`

**Interfaces:**
- Consumes: `core.catalog.Seri.epias_bilesenler`, `core.data.seri_yolu`, `core.data.VeriYokHatasi`
- Produces:
  - `core.data.genis_csv_oku(yol: Path) -> pd.DataFrame` — tarih indeksli, her grup bir sütun
  - `core.data.load_wide_series(seri_id: str) -> pd.DataFrame` — önbellekli sarmalayıcı

**Neden ayrı okuyucu:** `seri_csv_oku` gövdesinde `df[["value"]]` var; geniş CSV'de `value` sütunu yoktur ve `KeyError` fırlar. 24 seri o fonksiyona bağlı olduğu için sözleşmesi değiştirilmez.

- [ ] **Step 1: Testleri yaz (başarısız olmalı)**

`tests/test_data.py` sonuna:

```python
def test_genis_csv_oku_tum_sutunlari_dondurur(tmp_path):
    from core.data import genis_csv_oku

    yol = tmp_path / "k.csv"
    yol.write_text(
        "date,Kömür,Rüzgar\n2026-08-01,10.0,5.0\n2026-08-02,12.0,6.0\n",
        encoding="utf-8",
    )
    df = genis_csv_oku(yol)
    assert list(df.columns) == ["Kömür", "Rüzgar"]
    assert df.index.name == "date"
    assert len(df) == 2
    assert df["Kömür"].dtype == "float64"


def test_genis_csv_oku_tarihe_gore_siralar(tmp_path):
    from core.data import genis_csv_oku

    yol = tmp_path / "k.csv"
    yol.write_text(
        "date,Kömür\n2026-08-02,12.0\n2026-08-01,10.0\n", encoding="utf-8"
    )
    df = genis_csv_oku(yol)
    assert list(df["Kömür"]) == [10.0, 12.0]


def test_genis_csv_oku_dosya_yoksa_veri_yok_hatasi(tmp_path):
    import pytest

    from core.data import VeriYokHatasi, genis_csv_oku

    with pytest.raises(VeriYokHatasi):
        genis_csv_oku(tmp_path / "yok.csv")
```

`tests/test_takvim.py` sonuna:

```python
def test_seriyi_oku_genis_biciminde_kirilmaz():
    """Kompozisyon serisinde `value` sütunu yok; seri_csv_oku KeyError verir."""
    from core.catalog import seri_getir
    from core.takvim import _seriyi_oku

    df = _seriyi_oku(seri_getir("elektrik/uretim-kompozisyon"))
    assert "Kömür" in df.columns
    assert not df.empty


def test_seriyi_oku_tek_degerli_seride_value_dondurur():
    """Dallanma mevcut 25 seriyi etkilememeli."""
    from core.catalog import seri_getir
    from core.takvim import _seriyi_oku

    df = _seriyi_oku(seri_getir("enflasyon/tufe-genel"))
    assert list(df.columns) == ["value"]


def test_takvim_kompozisyon_serisini_okunamadi_saymaz():
    """Geniş CSV bozuk değil; OKUNAMADI'ya düşerse dallanma çalışmıyordur."""
    from core.takvim import OKUNAMADI, takvim

    (satir,) = [
        s for s in takvim(kategori="elektrik")
        if s.seri.id == "elektrik/uretim-kompozisyon"
    ]
    assert satir.durum != OKUNAMADI
    assert satir.son_donem is not None
```

- [ ] **Step 2: Testleri koştur, başarısız olduklarını gör**

Run: `.venv/bin/python -m pytest tests/test_data.py tests/test_takvim.py -q`
Expected: FAIL — `genis_csv_oku` ve `_seriyi_oku` import edilemiyor.

- [ ] **Step 3: `core/data.py`'ye geniş okuyucuyu ekle**

`seri_csv_oku`'dan sonra ekleyin:

```python
def genis_csv_oku(yol: Path) -> pd.DataFrame:
    """Çok sütunlu (bileşenli) seri dosyasını okur.

    `seri_csv_oku` gövdesinde `df[["value"]]` vardır ve geniş dosyada
    `value` sütunu yoktur. 24 seri o fonksiyona bağlı olduğu için
    sözleşmesi değiştirilmez; geniş biçim ayrı kapıdan okunur.
    """
    if not yol.exists():
        raise VeriYokHatasi(
            f"Veri dosyası yok: {yol}\n"
            "Veriyi üretmek için `python -m ingest.run` çalıştırın."
        )
    df = pd.read_csv(yol, parse_dates=["date"])
    df = df.sort_values("date").set_index("date")
    df.index.name = "date"
    return df.astype("float64")


@st.cache_data(show_spinner=False)
def load_wide_series(seri_id: str) -> pd.DataFrame:
    """Çok bileşenli serinin verisini döndürür (önbellekli)."""
    return genis_csv_oku(seri_yolu(seri_id))
```

- [ ] **Step 4: `core/takvim.py`'yi geniş seriye dayanıklı yap**

`takvim()` bugün üç durumu ayırt ediyor: `VeriYokHatasi` → `VERI_YOK`, başka
bir istisna → `OKUNAMADI`, başarı → tarih. **Bu ayrım korunmalıdır.** Bu yüzden
yalnızca okuyucu SEÇİMİ dışarı alınır; try/except yapısı olduğu yerde kalır.

`core/takvim.py`'ye ekleyin:

```python
def _seriyi_oku(seri: Seri) -> pd.DataFrame:
    """Biçime göre doğru okuyucuyu seçer; hataları yukarı bırakır.

    Kompozisyon serilerinde `value` sütunu yoktur ve `seri_csv_oku`
    gövdesindeki `df[["value"]]` KeyError fırlatır. Hata yakalama
    `takvim()` içinde kalır: VERI_YOK ile OKUNAMADI ayrımı oraya aittir.
    """
    if seri.epias_bilesenler:
        return genis_csv_oku(seri_yolu(seri.id))
    return seri_csv_oku(seri_yolu(seri.id))
```

`takvim()` içindeki `df = seri_csv_oku(seri_yolu(seri.id))` satırını
değiştirin:

```python
            df = _seriyi_oku(seri)
```

Import satırını genişletin:

```python
from core.data import VeriYokHatasi, genis_csv_oku, seri_csv_oku, seri_yolu
```

`pandas` bu modülde zaten import edilmiştir.

- [ ] **Step 5: Testleri koştur, geçtiklerini gör**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — tümü.

- [ ] **Step 6: Commit**

```bash
git add core/data.py core/takvim.py tests/test_data.py tests/test_takvim.py
git commit -m "feat: geniş CSV okuyucusu ve takvimin bileşenli seri uyumu"
```

---

### Task 3: Ingest — bileşen çekimi ve geniş CSV yazımı

EPİAŞ yanıtından bileşenleri gruplayıp geniş CSV üretir ve gerçek veriyi çeker.

**Files:**
- Modify: `ingest/epias.py` (`bilesen_noktalari_ayikla`, `seri_cek` dallanması)
- Test: `tests/test_epias.py`

**Interfaces:**
- Consumes: `core.catalog.Seri.epias_bilesenler`
- Produces:
  - `ingest.epias.bilesen_noktalari_ayikla(yanit: dict, gruplar: dict[str, tuple[str, ...]]) -> list[dict]`

- [ ] **Step 1: Testleri yaz (başarısız olmalı)**

`tests/test_epias.py` sonuna. Fixture gövdesi canlı API biçimidir:

```python
def _uretim_kaydi(tarih, saat, **degerler):
    kayit = {
        "date": f"{tarih}T{saat}:00:00+03:00", "hour": f"{saat}:00",
        "total": 0.0, "naturalGas": 0.0, "dammedHydro": 0.0, "lignite": 0.0,
        "river": 0.0, "importCoal": 0.0, "wind": 0.0, "sun": 0.0,
        "fueloil": 0.0, "geothermal": 0.0, "asphaltiteCoal": 0.0,
        "blackCoal": 0.0, "biomass": 0.0, "naphta": 0.0, "lng": 0.0,
        "importExport": 0.0, "wasteheat": 0.0,
    }
    kayit.update(degerler)
    return kayit


GRUPLAR = {
    "Kömür": ("importCoal", "lignite"),
    "Hidroelektrik": ("dammedHydro", "river"),
    "Rüzgar": ("wind",),
}


def test_bilesen_noktalari_ayikla_gruplari_toplar():
    from ingest.epias import bilesen_noktalari_ayikla

    yanit = {"items": [
        _uretim_kaydi("2026-08-01", "00", importCoal=100.0, lignite=50.0,
                      dammedHydro=30.0, river=20.0, wind=10.0),
    ]}
    (nokta,) = bilesen_noktalari_ayikla(yanit, GRUPLAR)
    assert nokta == {
        "date": "2026-08-01", "Kömür": 150.0,
        "Hidroelektrik": 50.0, "Rüzgar": 10.0,
    }


def test_bilesen_noktalari_ayikla_import_export_hicbir_gruba_girmez():
    """importExport üretim değil ticaret kalemidir; negatif de olabilir."""
    from ingest.epias import bilesen_noktalari_ayikla

    yanit = {"items": [
        _uretim_kaydi("2026-08-01", "00", wind=10.0, importExport=-500.0),
    ]}
    (nokta,) = bilesen_noktalari_ayikla(yanit, GRUPLAR)
    assert sum(v for k, v in nokta.items() if k != "date") == 10.0


def test_bilesen_noktalari_ayikla_bilinmeyen_alanda_hata_verir():
    from ingest.epias import bilesen_noktalari_ayikla

    yanit = {"items": [_uretim_kaydi("2026-08-01", "00")]}
    with pytest.raises(KeyError):
        bilesen_noktalari_ayikla(yanit, {"X": ("yokBoyleAlan",)})


def test_seri_cek_bilesenli_seriyi_genis_df_olarak_dondurur():
    from ingest.epias import seri_cek

    kayitlar = [
        _uretim_kaydi("2026-08-01", f"{s:02d}", importCoal=100.0, wind=10.0)
        for s in range(24)
    ]
    oturum = SahteOturum(SahteYanit(200, {"items": kayitlar}))
    seri = _epias_seri(
        id="elektrik/uretim-kompozisyon", epias_ucu="uretim", epias_alani=None,
        epias_bilesenler=GRUPLAR, monthly_agg="sum", olcek=0.001,
        start_date="2026-08-01",
    )

    df = seri_cek(seri, "TGT-x", session=oturum, bugun=date(2026, 8, 2))

    assert list(df.columns) == ["date", "Kömür", "Hidroelektrik", "Rüzgar"]
    # 24 saat × 100 MWh = 2400 MWh → olcek 0.001 → 2.4 GWh
    assert df["Kömür"].iloc[0] == pytest.approx(2.4)
    assert df["Rüzgar"].iloc[0] == pytest.approx(0.24)


def test_seri_cek_bilesenli_seride_eksik_saatli_gunu_atar():
    """Faz 3b C1 kuralı bileşenli seride de geçerli."""
    from ingest.epias import seri_cek

    tam = [
        _uretim_kaydi("2026-08-01", f"{s:02d}", importCoal=100.0)
        for s in range(24)
    ]
    kesik = [
        _uretim_kaydi("2026-08-02", f"{s:02d}", importCoal=100.0)
        for s in range(12)
    ]
    oturum = SahteOturum(SahteYanit(200, {"items": tam + kesik}))
    seri = _epias_seri(
        id="elektrik/uretim-kompozisyon", epias_ucu="uretim", epias_alani=None,
        epias_bilesenler=GRUPLAR, monthly_agg="sum", olcek=1.0,
        start_date="2026-08-01",
    )

    df = seri_cek(seri, "TGT-x", session=oturum, bugun=date(2026, 8, 3))

    assert list(df["date"]) == ["2026-08-01"]
```

Mevcut `_epias_seri` yardımcısı `epias_bilesenler` anahtarını kabul etmiyorsa (SimpleNamespace ise zaten kabul eder) genişletin.

- [ ] **Step 2: Testleri koştur, başarısız olduklarını gör**

Run: `.venv/bin/python -m pytest tests/test_epias.py -q`
Expected: FAIL — `bilesen_noktalari_ayikla` import edilemiyor.

- [ ] **Step 3: `ingest/epias.py`'ye bileşen ayrıştırıcısını ekle**

`noktalari_ayikla`'dan sonra ekleyin:

```python
def bilesen_noktalari_ayikla(
    yanit: dict, gruplar: dict[str, tuple[str, ...]]
) -> list[dict]:
    """Saatlik kayıtları grup toplamlarına indirger.

    `importExport` bilerek hiçbir gruba girmez: üretim kaynağı değil,
    ticaret kalemidir ve negatif olabilir (net ihracat). Paydaya karışırsa
    paylar %100'ü aşar. `total` da alınmaz — grup toplamlarından türetilir.

    Bilinmeyen alan adı sessizce sıfır sayılmaz; KeyError yükselir, çünkü
    EPİAŞ bir alanı yeniden adlandırırsa o grup sessizce boşalır ve grafik
    yanlış çizilir.
    """
    noktalar = []
    for kayit in yanit.get("items") or []:
        nokta = {"date": kayit["date"][:10]}
        for grup, alanlar in gruplar.items():
            nokta[grup] = float(sum(kayit[alan] for alan in alanlar))
        noktalar.append(nokta)
    return noktalar
```

- [ ] **Step 4: `seri_cek`'i bileşenli seri için dallandır**

`seri_cek` içinde, dilim döngüsündeki ayrıştırma çağrısını ve döngü sonrası indirgeme bloğunu biçime göre dallandırın. Dilim döngüsünde:

```python
        if seri.epias_bilesenler:
            dilim_noktalari = bilesen_noktalari_ayikla(
                yanit.json(), seri.epias_bilesenler
            )
        else:
            dilim_noktalari = noktalari_ayikla(yanit.json(), seri.epias_alani)
```

Döngüden sonraki indirgeme bloğunu şununla değiştirin. Eksik saat filtresi ve ölçekleme kuralları aynen korunur, yalnızca sütun sayısı değişir:

```python
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
    for grup in gruplar:
        gunluk[grup] = _olcekle(gunluk[[grup]].rename(columns={grup: "value"}),
                                seri.olcek)["value"]
    return gunluk
```

- [ ] **Step 5: Testleri koştur, geçtiklerini gör**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — tümü. Mevcut `seri_cek` testleri (tek değerli seriler) değişmeden geçmelidir; geçmiyorsa dallanma tek değerli yolu bozmuştur.

- [ ] **Step 6: Gerçek veriyi çek ve doğrula**

```bash
set -a; . ./.env; set +a
.venv/bin/python -m ingest.run --only elektrik/uretim-kompozisyon
```

Çekim birkaç dakika sürer (5 yıl / 89 günlük dilimler ≈ 21 istek). Bitmesini BEKLEYİN; arka plana atıp devam etmeyin.

Sonra doğrulayın:

```bash
head -2 data/elektrik/uretim-kompozisyon.csv
.venv/bin/python -c "
import pandas as pd
k = pd.read_csv('data/elektrik/uretim-kompozisyon.csv', parse_dates=['date'])
u = pd.read_csv('data/elektrik/uretim.csv', parse_dates=['date'])
gruplar = [s for s in k.columns if s != 'date']
print('nokta:', len(k), ' aralık:', k.date.min().date(), '→', k.date.max().date())
print('gruplar:', gruplar)
birlesik = k.assign(kompozisyon=k[gruplar].sum(axis=1)).merge(u, on='date')
birlesik['fark'] = birlesik.kompozisyon - birlesik.value
print('grup toplamı − uretim serisi:')
print('  ortalama fark:', round(birlesik.fark.mean(), 3), 'GWh')
print('  |fark| maks  :', round(birlesik.fark.abs().max(), 3), 'GWh')
print('günlük grup toplamı GWh aralığı:',
      round(birlesik.kompozisyon.min(),1), '→', round(birlesik.kompozisyon.max(),1))
"
```

**Beklenen:** Grup toplamı, `elektrik/uretim` serisinden **net ithalat kadar farklı** olmalıdır — sıfır fark BEKLENMEZ, çünkü `uretim` serisi `total` (importExport dahil), kompozisyon ise yalnızca üretim kaynaklarıdır. Fark tipik olarak günlük ±50 GWh mertebesindedir ve işareti değişebilir. Günlük grup toplamı ~800–1.300 GWh bandında olmalıdır.

Fark sıfırsa `importExport` yanlışlıkla bir gruba girmiş demektir; fark yüzlerce GWh ise bir grup eksik kalmıştır. İkisi de hatadır — DURUN ve raporlayın, yanlış veriyi commit'lemeyin.

- [ ] **Step 7: Commit**

```bash
git add ingest/epias.py tests/test_epias.py data/elektrik/uretim-kompozisyon.csv
git commit -m "feat: EPİAŞ bileşen çekimi ve geniş CSV yazımı"
```

---

### Task 4: Kategorik palet

Sekiz kaynak grubu için koyu temada ayırt edilebilir renkler.

**Files:**
- Modify: `core/theme.py` (`RENKLER["kategorik"]`)
- Test: `tests/test_theme.py` (yoksa oluşturun)

**Interfaces:**
- Produces: `core.theme.RENKLER["kategorik"]: list[str]` — 8 hex değeri

**REQUIRED SUB-SKILL:** Bu görevde `dataviz` skill'ini yükleyin ve paleti onun doğrulayıcısıyla üretin. Renkleri gözle seçmeyin.

- [ ] **Step 1: `dataviz` skill'ini yükle ve paleti üret**

Kısıtlar:
- Zeminler: sayfa `#0F1E33`, kart `#16273F`
- Sekiz kategori, hepsi aynı grafikte çizgi olarak
- Metin rengi `#E6EDF5`, ızgara `#22354F` — çizgiler bunlardan da ayrılmalı
- `RENKLER["seri"]` (`#3987e5`, `#d95926`, `#199e70`) güncellik yuvasıdır ve kategorik palete karıştırılmaz; ancak aynı görsel dilde durmalıdır
- `RENKLER["artis"]`/`["dusus"]` durum renkleridir, grafiğin içinde asla kullanılmaz

Hedef semantik çapa: Güneş sarı, Kömür koyu/nötr, Hidroelektrik mavi, Rüzgar turkuaz/açık mavi, Doğalgaz turuncu, Jeotermal kırmızımsı, Biyo/Atık yeşil, Diğer gri. **Kısıt erişilebilirliktir:** doğrulayıcı semantik seçimi geçirmezse semantik feda edilir.

Doğrulayıcı çıktısını (ikili ayrım ölçümleri) rapora ekleyin.

- [ ] **Step 2: Testi yaz (başarısız olmalı)**

`tests/test_theme.py`:

```python
import re

from core.theme import RENKLER

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def test_kategorik_palet_sekiz_renk():
    assert len(RENKLER["kategorik"]) == 8


def test_kategorik_renkler_gecerli_hex():
    assert all(HEX.match(r) for r in RENKLER["kategorik"])


def test_kategorik_renkler_tekil():
    assert len(set(RENKLER["kategorik"])) == 8


def test_kategorik_palet_durum_renkleriyle_karismaz():
    """artis/dusus durum rengidir; grafiğin içinde asla kullanılmaz."""
    assert RENKLER["artis"] not in RENKLER["kategorik"]
    assert RENKLER["dusus"] not in RENKLER["kategorik"]
```

- [ ] **Step 3: Testi koştur, başarısız olduğunu gör**

Run: `.venv/bin/python -m pytest tests/test_theme.py -q`
Expected: FAIL — `RENKLER` sözlüğünde `"kategorik"` anahtarı yok.

- [ ] **Step 4: Paleti `core/theme.py`'ye yaz**

Step 1'de doğrulayıcıdan geçen sekiz hex değerini `RENKLER` sözlüğüne `"kategorik"` anahtarıyla ekleyin. Docstring'e, mevcut `"seri"` açıklamasının yanına, bu paletin **kategorik** olduğunu (güncellik yuvası değil) ve hangi doğrulayıcıdan geçtiğini yazın.

- [ ] **Step 5: Testleri koştur, geçtiklerini gör**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — tümü.

- [ ] **Step 6: Commit**

```bash
git add core/theme.py tests/test_theme.py
git commit -m "feat: sekiz renkli kategorik palet"
```

---

### Task 5: Kompozisyon grafiği ve kartı

Grafiği çizer, Pay%/GWh toggle'lı kartı sayfaya bağlar.

**Files:**
- Modify: `core/charts.py` (`paylara_cevir`, `kompozisyon_figuru`)
- Modify: `core/components.py` (`kompozisyon_karti`, `grafik_karti` dallanması)
- Test: `tests/test_charts.py`, `tests/test_components.py`

**Interfaces:**
- Consumes: `core.data.load_wide_series`, `core.theme.RENKLER["kategorik"]`, `core.charts.aylige_cevir`
- Produces:
  - `core.charts.paylara_cevir(df: pd.DataFrame) -> pd.DataFrame`
  - `core.charts.kompozisyon_figuru(df: pd.DataFrame, birim: str) -> go.Figure`
  - `core.components.kompozisyon_karti(seri: Seri) -> None`

- [ ] **Step 1: Testleri yaz (başarısız olmalı)**

`tests/test_charts.py` sonuna:

```python
def test_paylara_cevir_yuzdeye_normalize_eder():
    from core.charts import paylara_cevir

    df = pd.DataFrame(
        {"Kömür": [60.0, 30.0], "Rüzgar": [40.0, 10.0]},
        index=pd.to_datetime(["2026-07-01", "2026-08-01"]),
    )
    paylar = paylara_cevir(df)
    assert list(paylar["Kömür"]) == [60.0, 75.0]
    assert list(paylar["Rüzgar"]) == [40.0, 25.0]


def test_paylara_cevir_her_satir_yuze_toplanir():
    from core.charts import paylara_cevir

    df = pd.DataFrame(
        {"A": [1.0, 2.0], "B": [3.0, 5.0], "C": [6.0, 3.0]},
        index=pd.to_datetime(["2026-07-01", "2026-08-01"]),
    )
    toplamlar = paylara_cevir(df).sum(axis=1)
    assert all(abs(t - 100.0) < 1e-9 for t in toplamlar)


def test_paylara_cevir_sifir_toplamli_satirda_nan_uretir():
    """Sıfıra bölme sessizce 0 pay üretmemeli — veri yokluğu görünür kalsın."""
    from core.charts import paylara_cevir

    df = pd.DataFrame(
        {"A": [0.0, 2.0], "B": [0.0, 2.0]},
        index=pd.to_datetime(["2026-07-01", "2026-08-01"]),
    )
    paylar = paylara_cevir(df)
    assert paylar.iloc[0].isna().all()
    assert list(paylar.iloc[1]) == [50.0, 50.0]


def test_kompozisyon_figuru_her_gruba_bir_iz_ekler():
    from core.charts import kompozisyon_figuru

    df = pd.DataFrame(
        {"Kömür": [60.0, 30.0], "Rüzgar": [40.0, 10.0]},
        index=pd.to_datetime(["2026-07-01", "2026-08-01"]),
    )
    fig = kompozisyon_figuru(df, "GWh")
    assert len(fig.data) == 2
    assert {iz.name for iz in fig.data} == {"Kömür", "Rüzgar"}


def test_kompozisyon_figuru_kategorik_paleti_kullanir():
    from core.charts import kompozisyon_figuru
    from core.theme import RENKLER

    df = pd.DataFrame(
        {"A": [1.0], "B": [2.0], "C": [3.0]},
        index=pd.to_datetime(["2026-07-01"]),
    )
    fig = kompozisyon_figuru(df, "GWh")
    renkler = [iz.line.color for iz in fig.data]
    assert renkler == RENKLER["kategorik"][:3]
```

- [ ] **Step 2: Testleri koştur, başarısız olduklarını gör**

Run: `.venv/bin/python -m pytest tests/test_charts.py -q`
Expected: FAIL — `paylara_cevir` ve `kompozisyon_figuru` import edilemiyor.

- [ ] **Step 3: `core/charts.py`'ye iki fonksiyonu ekle**

```python
def paylara_cevir(df: pd.DataFrame) -> pd.DataFrame:
    """Her satırı kendi toplamının yüzdesine çevirir.

    Payda yalnızca sütunlardaki üretim gruplarıdır; `importExport` zaten
    ingest tarafında dışlandığı için paylar %100'e toplanır. Toplamı sıfır
    olan satır NaN üretir — sessizce 0 pay göstermek, veri yokluğunu
    "hiç üretim yok"muş gibi gösterirdi.
    """
    toplam = df.sum(axis=1)
    return df.div(toplam.where(toplam != 0), axis=0) * 100


def kompozisyon_figuru(df: pd.DataFrame, birim: str) -> go.Figure:
    """Grup başına bir çizgi. Renkler sütun sırasına göre sabittir."""
    fig = go.Figure()
    for sira, sutun in enumerate(df.columns):
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df[sutun],
                name=sutun,
                mode="lines",
                line={"color": RENKLER["kategorik"][sira % len(RENKLER["kategorik"])],
                      "width": 2},
            )
        )
    return _temayi_uygula(fig, birim)
```

`RENKLER` zaten `core/charts.py`'de import edilmiştir; değilse import satırına ekleyin.

- [ ] **Step 4: `core/components.py`'ye kartı ekle**

```python
def kompozisyon_karti(seri: Seri) -> None:
    """Kaynak bazlı üretim kartı: kendi Pay%/GWh seçicisiyle.

    Sayfa düzeyindeki Varsayılan/YoY/MoM seçicisine bağlanmaz —
    kompozisyon grafiğinde YoY'un anlamı yoktur ve iki seçiciyi bağlamak
    anlamsız kombinasyonlar üretir.
    """
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
            df = load_wide_series(seri.id)
        except VeriYokHatasi as hata:
            st.warning(str(hata))
            return

        gorunum = st.segmented_control(
            "Görünüm",
            ["Pay %", seri.unit],
            default="Pay %",
            key=f"kompozisyon_{seri.id}",
            label_visibility="collapsed",
        ) or "Pay %"

        # NOT (yürütme sonrası): Aşağıdaki karşılaştırma TERSTİR ve final
        # incelemede Critical bulgu oldu — koşul her zaman True verir.
        # DÜZELTİLDİ: bkz. core/charts.py `uc_aylar_tamamlanmamissa_dus`.
        # Bu plan yeniden yürütülürse aşağıdaki blok KULLANILMAMALIDIR.
        aylik = df.resample("MS").sum(min_count=1).dropna(how="all")
        if aylik.index.max() < df.index.max() + pd.offsets.MonthEnd(0):
            # Tamamlanmamış son ay sahte bir düşüş gibi görünür (aylige_cevir
            # ile aynı gerekçe); bileşenli seri günlük olduğu için burada da geçerli.
            aylik = aylik.iloc[:-1]

        gosterilecek = paylara_cevir(aylik) if gorunum == "Pay %" else aylik
        birim = "%" if gorunum == "Pay %" else seri.unit

        st.caption(
            f"Son Dönem: {donem_etiketi(aylik.index.max(), 'monthly')} · AYLIK"
        )
        st.plotly_chart(
            kompozisyon_figuru(gosterilecek, birim),
            width="stretch",
            key=f"{seri.id}-composition",
        )

        with st.expander("Veri tablosu"):
            st.dataframe(gosterilecek, width="stretch")
```

Import satırlarına ekleyin: `from core.data import load_wide_series`, `from core.charts import kompozisyon_figuru, paylara_cevir`.

- [ ] **Step 5: `grafik_karti`'nı dallandır**

`core/page.py` içindeki ızgara döngüsünde, `grafik_karti(seri, gorunum)` çağrısını değiştirin:

```python
            if "composition" in seri.charts:
                kompozisyon_karti(seri)
            else:
                grafik_karti(seri, gorunum)
```

`core/page.py` import satırına `kompozisyon_karti` ekleyin.

- [ ] **Step 6: Testleri koştur, geçtiklerini gör**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — tümü.

- [ ] **Step 7: Tarayıcıda doğrula**

```bash
.venv/bin/streamlit run app.py --server.headless true --server.port 8580 \
  > /tmp/bv-kompozisyon.log 2>&1 &
```

`http://localhost:8580/_stcore/health` `ok` dönene kadar bekleyin, sonra `http://localhost:8580/elektrik` adresinde doğrulayın:

1. "Kaynak Bazlı Üretim" kartı render oluyor
2. Sekiz çizgi ve sekiz legend girdisi var; renkler birbirinden ayırt edilebiliyor
3. Varsayılan görünüm "Pay %" ve y ekseni %0–%100 bandında
4. Toggle'ı "GWh"ye çevirince y ekseni mutlak değere geçiyor, çizgiler yeniden çiziliyor
5. Sayfa düzeyindeki Varsayılan/YoY/MoM seçicisi bu kartı ETKİLEMİYOR
6. Diğer iki elektrik kartı (arz, PTF) bozulmamış
7. Veri Takvimi kompozisyon serisini "güncel" gösteriyor, "okunamadı" değil
8. `/tmp/bv-kompozisyon.log` içinde traceback yok

Ekran görüntüsü alın. Sunucuyu kapatın (`pkill -f "streamlit run app.py"`).

- [ ] **Step 8: Commit**

```bash
git add core/charts.py core/components.py core/page.py \
        tests/test_charts.py tests/test_components.py
git commit -m "feat: kompozisyon grafiği ve Pay%/GWh toggle'lı kart"
```

---

## Self-Review

**Spec coverage:**

| Spec gereksinimi | Karşılayan görev |
|---|---|
| 16 alan → 8 grup | Task 1 Step 4 (katalog), Task 3 Step 3 (toplama) |
| `importExport` dışlanır | Task 1 Step 4 (gruplarda yok), Task 3 Step 1 testi |
| `total` başlık düzeltmesi | Task 1 Step 4 |
| Paylar üretim toplamına bölünür | Task 5 Step 3 (`paylara_cevir`) |
| Geniş CSV, `load_series` bozulmaz | Task 2 Step 3 |
| `epias_bilesenler` katalog alanı | Task 1 Step 3 |
| `composition` grafik türü | Task 1 Step 3 |
| Aylığa indirgeme | Task 5 Step 4 |
| Kart kendi toggle'ı, sayfa toggle'ına bağlanmaz | Task 5 Step 4 + Step 7 madde 5 |
| Kategorik palet, dataviz doğrulayıcısı | Task 4 |
| Eksik saatli gün kuralı korunur | Task 3 Step 4 + Step 1 testi |
| Veri Takvimi kırılmaz | Task 2 Step 4 + Step 1 testi |
| Ağ smoke testine bileşen alanları | **BOŞLUK — aşağıya bakın** |
| Tarayıcı doğrulaması | Task 5 Step 7 |

**Kapatılan boşluk:** Spec Risk 3 ağ smoke testine bileşen alanlarının eklenmesini istiyor. Task 3 Step 7'nin commit'ine şu ek adım dahildir:

`tests/test_smoke_network.py` içindeki `test_epias_uclari_beklenen_alanlari_donduruyor` fonksiyonuna, mevcut `epias_alani` kontrolünden sonra ekleyin:

```python
        for seri in seri_listele("elektrik"):
            if not seri.epias_bilesenler:
                continue
            ilk = kayitlar[0] if seri.epias_ucu == uc else None
            if ilk is None:
                continue
            eksik = [
                alan
                for alanlar in seri.epias_bilesenler.values()
                for alan in alanlar
                if alan not in ilk
            ]
            assert not eksik, f"{uc}: bileşen alanları yanıtta yok: {eksik}"
```

Bu ek `git add tests/test_smoke_network.py` ile Task 3 Step 7 commit'ine girer.

**Placeholder taraması:** Task 4 Step 4 hex değerlerini sabitlemiyor — bu bilinçlidir ve spec'te gerekçelendirilmiştir (palet doğrulayıcıdan üretilir, gözle seçilmez). Adım, doğrulayıcı çıktısının rapora eklenmesini zorunlu kılar. Başka placeholder yok.

**Type consistency:** `Seri.epias_bilesenler` Task 1'de tanımlanır; Task 2 (`_seriyi_oku`), Task 3 (`seri_cek` dallanması) ve Task 5 (`kompozisyon_karti` dolaylı) tüketir. `genis_csv_oku`/`load_wide_series` Task 2'de tanımlanıp Task 5'te çağrılır. `paylara_cevir`/`kompozisyon_figuru` Task 5 içinde tanımlanıp aynı görevde kullanılır. `RENKLER["kategorik"]` Task 4'te üretilip Task 5'te tüketilir — bu yüzden Task 4, Task 5'ten ÖNCE gelir. `bilesen_noktalari_ayikla` Task 3'te tanımlanıp aynı görevde çağrılır.

**Bilinçli sapma:** Task 3 Step 4'teki `_olcekle` çağrısı sütun başına yapılır çünkü mevcut `_olcekle` tek `value` sütunu bekler. Alternatif, `_olcekle`'yi çok sütunlu hale getirmekti; mevcut imzayı bozmamak için sarmalama tercih edildi. Ölçekleme yine indirgemeden SONRA ve bir kez uygulanır.
