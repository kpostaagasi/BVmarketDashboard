# Faz 3g: TİM İhracat Implementation Plan

**Goal:** TİM'in sektörel ihracat XLSX bültenlerinden 13 seri (toplam + 12
sektör) üretip `ihracat` kategorisini açmak. Katalog 69 → 82 seri.

**Architecture:** `ingest/tim.py` saf katmanlarla kurulur (URL üretimi,
bülten seçimi, ad normalizasyonu, sayfa ayrıştırma, sıfır-ay atma,
öz-doğrulama); ağ yalnızca `seri_cek` kabuğunda. Ayrıştırılmış noktalar koşu
başına önbelleklenir — 13 seri 8 dosyayı paylaşır. `openpyxl` yalnızca
ingest bağımlılığı. Ölçekleme faz 3f'ten beri orchestrator'da.

**Tech Stack:** Python 3.12 · pandas · requests · **openpyxl (yalnızca
ingest)** · pytest

**Spec:** `docs/superpowers/specs/2026-09-08-faz3g-tim-ihracat-design.md`

## Global Constraints

- **Arayüz dili Türkçe** — tanımlayıcılar, mesajlar, yorumlar, docstring'ler.
- **`requirements.txt` DEĞİŞMEZ.** `openpyxl` yalnızca ingest'e girer.
- **`core/` modülleri `ingest/`'i import etmez; `ingest/` Streamlit'i.**
- **Sessiz yanlış veri yasak:** şablon kayarsa hata yükselt, boş/kısmi seri
  yazma. `TOPLAM == 0` olan ay veri değil, yayımlanmamış aydır — atılır.
- **Ölçekleme tek noktada** (`run.olcekle`); adaptör ham Bin USD döner.
- **Seri/etiket bilgileri spec'ten alınır**, TİM'de yeniden keşfedilmez.

## Task 1 — `ingest/tim.py`

- [x] Saf katmanlar: `bulten_url`, `cekilecek_bultenler`,
      `sektor_adini_normalize`, `sayfayi_ayikla`, `sifir_aylari_at`,
      `dogrula`.
- [x] Ağ kabuğu `seri_cek(seri, onbellek=None, session=None, bugun=None)`:
      yıl başına en güncel bülteni bulur (cari yıl için aylar geriye doğru
      denenir), noktaları önbellekten okur, `tim_sektor` + `tim_eski_adlar`
      ile eşleştirir, hiç eşleşme yoksa `RuntimeError`.
- [x] Docstring kaynak gerçeklerini kaydeder (URL deseni, yıllık dosya,
      sıfır-ay tuzağı, TİM≠TÜİK) — "sıfırdan yeniden keşfetmeyin".

**Acceptance:** `seri_cek` `date,value` çerçevesi döndürür; sıfır aylar yok.

## Task 2 — Katalog: `tim` kaynak tipi

- [x] `GECERLI_KAYNAK_TIPLERI`'ne `tim`, `KAYNAK_ALANLARI`'na bir satır.
- [x] `Seri.tim_sektor`, `Seri.tim_eski_adlar` alanları + YAML okuma.
- [x] `ingest/run.py`: `_cek`'e `tim` dalı, `main`'e `tim_onbellek`.

**Acceptance:** `tim` serisi katalog doğrulamasından geçer; başka tipler
`tim_sektor` taşıyamaz.

## Task 3 — `openpyxl` ayrımı

- [x] `requirements-ingest.txt`'e `openpyxl>=3.1`.
- [x] `tests/test_requirements.py`: uygulamada yok / ingest'te var testleri.

## Task 4 — Katalog: kategori ve 13 seri

- [x] `catalog/categories.yaml`: `ihracat` kategorisi (pano + TİM≠TÜİK notu),
      `dis-ticaret`'ten sonra.
- [x] `catalog/series.yaml`: spec tablosundaki 13 kayıt, `olcek: 0.001`.

**Acceptance:** `seri_listele()` 82 seri, `kategorileri_yukle()` 12 kategori.

## Task 5 — Testler

- [x] `tests/test_tim.py`: saf katman testleri (URL ay sıfırı, bülten
      seçimi, ad normalizasyonu gerçek 2019/2026 etiketleriyle, `TOPLAM`
      satırında durma, sıfır-ay atma, öz-doğrulama geçen+kırılan, eski ad
      eşleşmesi, sektör bulunamazsa hata) — `SahteOturum` yerel stub.
- [x] `tests/test_smoke_network.py`: TİM URL'i 200 ve XLSX döner.
- [x] `tests/test_catalog.py`: `tim` tipinin alan sahipliği; seri/kategori
      sayıları.

## Task 6 — Gerçek veri

- [x] Tam koşu `python -m ingest.run`; kabul: 82/82, `ihracat/toplam`
      Temmuz 2026 ≈ 22.029 milyon USD, sıfır ay yok, tarihler tekil/artan.

## Task 7 — Tarayıcı ve belgeler

- [x] `ihracat` sayfası panosuyla render olur; Veri Takvimi 82 seri, TİM
      serileri güncel.
- [x] README (seri/kategori sayısı, kaynak tipi listesi, ingest ağacı) ve
      yol haritası satırı.

## Uygulama sırasında çıkan iş (planda yoktu)

- [x] `tests/test_run.py`'nin iki `main()` testi `osd` ve `tim` adaptörlerini
      stub'lamıyordu; `-m 'not network'` koşusu gerçek OSD PDF'lerini ve TİM
      XLSX'lerini indiriyordu. Stub'landı — paket süresi 9,6 sn → 1,6 sn.
