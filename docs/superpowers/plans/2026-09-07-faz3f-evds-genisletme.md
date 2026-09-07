# Faz 3f: EVDS Genişletme Implementation Plan

**Goal:** Katalogdaki EVDS dilimini 14'ten 43 seriye çıkarmak — üç yeni
kategori sayfası (`sanayi`, `dis-ticaret`, `para-banka`), dört mevcut
sayfaya 16 seri, toplam katalog 40 → 69.

**Architecture:** Yeni ingest kodu yok; `kaynak_tipi: evds` yolu olduğu gibi
kullanılır. Tek kod değişikliği `olcek`'in kaynak-tipinden bağımsız ortak
katalog alanına yükseltilmesi ve uygulama noktasının `ingest/epias.py`'den
`ingest/run.py`'ye taşınması. `pano` on bir kategorinin tamamına yazılır
(devredilen iş #3 kapanır).

**Tech Stack:** Python 3.12 · Streamlit · pandas · Plotly · PyYAML ·
requests · pytest. Yeni bağımlılık yok.

**Spec:** `docs/superpowers/specs/2026-09-07-faz3f-evds-genisletme-design.md`

## Global Constraints

- **Arayüz dili Türkçe** — tanımlayıcılar, mesajlar, yorumlar, docstring'ler.
- **`requirements*.txt` DEĞİŞMEZ.**
- **`core/` modülleri `ingest/`'i import etmez; `ingest/` Streamlit'i.**
- **Tek ölçekleme noktası:** `run.olcekle`. Bir adaptör kendi içinde
  ölçeklerse çift ölçekleme olur; adaptörler ham (indirgenmiş) değer döner.
- **Sessiz yanlış veri yasak** — `olcek` ortak alana çıkarken tip yasakları
  (ör. `yahoo` + `evds_code`) gevşemez.
- **Seri kodları spec'ten alınır**, EVDS'te yeniden aranmaz: 29 kodun
  tamamı 2026-09-07'de canlı doğrulandı.

## Task 1 — `olcek` ortak alana yükselir

- [x] `core/catalog.py`: `ORTAK_ALANLAR = frozenset({"olcek"})` eklenir;
      `olcek` `KAYNAK_ALANLARI["epias"]["istege_bagli"]`'dan çıkarılır;
      tablo yorumu ortak alan ayrımını anlatacak şekilde güncellenir.
      `TIPE_OZGU_ALANLAR` yalnızca tip tablosunun birleşimi kalır.
- [x] `ingest/run.py`: `olcekle(df, olcek)` — `None`'da dokunmaz, aksi
      halde `date` dışındaki tüm sütunları çarpar, girdiyi mutasyona
      uğratmaz. `_cek` adaptörden dönen çerçeveyi bu fonksiyondan geçirir.
      Docstring tek uygulama noktası olduğunu yazar.
- [x] `ingest/epias.py`: `_olcekle` ve `seri_cek`'in son satırındaki çağrı
      silinir; `seri_cek` docstring'inin ölçekleme paragrafı "ölçekleme
      orchestrator'da uygulanır" olarak düzeltilir.

**Acceptance:** `olcek` taşıyan bir EVDS serisi `KatalogHatasi` almaz;
`epias.seri_cek` ham değer döner; `_cek` ölçekli değer döner.

## Task 2 — Testlerin kontrata göre güncellenmesi

- [x] `tests/test_catalog.py`: `test_evds_serisi_olcek_tasiyamaz` ve
      `test_evds_serisi_acik_yazilmis_olcek_1_de_tasiyamaz` **silinir**
      (artık geçersiz kuralı çiviliyorlar). Yerine `olcek`'in EVDS'te
      kabul edildiğini gösteren test eklenir. `olcek`'in yanlış tipe
      sızmasını değil, `evds_code`'un `yahoo`'ya sızmasını kontrol eden
      testler dokunulmaz kalır (ortak alan yükseltmesinin tip yasaklarını
      gevşetmediğinin kanıtı).
- [x] `tests/test_catalog.py`: `test_olcek_verilmemisse_ingest_olceklemez`
      ve `test_olcekle_sutun_listesiyle_coklu_sutunu_olcekler`
      `ingest.run.olcekle` imzasına taşınır.
- [x] `tests/test_epias.py`: ölçeklemeyi çivileyen üç test
      (`test_seri_cek_olceklendirmeyi_indirgemeden_sonra_uygular` ve iki
      kompozisyon ölçek testi) adaptörün artık ham değer döndürdüğünü
      doğrulayacak şekilde güncellenir.
- [x] `tests/test_run.py`: `_cek`'in EVDS serisinde ölçeği uyguladığı ve
      geniş serinin tüm bileşen sütunlarının ölçeklendiği eklenir.
- [x] `tests/test_catalog.py`: her kategorinin `pano`sunun dolu olduğu ve
      geçerli id'lere işaret ettiği testi eklenir (devredilen iş #3'ün
      kalıcı koruması).

**Acceptance:** `pytest` yeşil; ölçekleme davranışı tek noktadan test
ediliyor.

## Task 3 — Katalog: üç yeni kategori ve panolar

- [x] `catalog/categories.yaml`: `sanayi`, `dis-ticaret`, `para-banka`
      eklenir (başlıklar spec'ten). Menü sırası makro → enflasyon →
      sanayi → dış ticaret → para-banka → inşaat → kredi kartı → emtia →
      elektrik → otomotiv mantığında düzenlenir.
- [x] On bir kategorinin tamamına `pano` yazılır.
- [x] `dis-ticaret` ve `para-banka` için `note`: cari denge ve rezerv
      serilerinin birim/stok-akım ayrımını açıklar.

**Acceptance:** `kategorileri_yukle()` 11 kategori döndürür, her birinin
`pano`su boş değil.

## Task 4 — Katalog: 29 seri

- [x] `catalog/series.yaml`: spec'teki tablolardan 29 kayıt; `start_date`
      YAZILMADI (katalogdaki hiçbir seri yazmıyor; EVDS istemcisinin 15 yıllık
      varsayılan penceresi daha uzun geçmiş veriyor), `charts:
      [seasonality, level]`.
- [x] Ölçek taşıyanlar: ihracat/ithalat `0.001`; kredi hacmi, mevduat, M3,
      bütçe dengesi `0.000001`.
- [x] `monthly_agg`: stok büyüklükleri (`rezervler`, kredi hacmi, mevduat,
      M3) `last`; akım büyüklükleri (ihracat, ithalat, cari denge, bütçe,
      konut satışları, şirket adetleri, kredi kartı sektörleri) `sum`;
      endeks ve oranlar `mean`.

**Acceptance:** `seri_listele()` 69 seri döndürür; `pytest` yeşil.

## Task 4b — Seri bazında yayın gecikmesi (planda yoktu, ingest sonrası çıktı)

- [x] `Seri.gecikme_gunu` ortak alan olarak eklenir, `durum_hesapla`
      eşiği o kadar genişletir; `sanayi/uretim-endeksi` ve
      `dis-ticaret/cari-denge` `gecikme_gunu: 25` taşır.
      Gerekçe ve elenen alternatif: spec, "İkinci kod değişikliği".

## Task 5 — Gerçek veri

- [x] `EVDS_API_KEY=... python -m ingest.run` tam koşu.
- [x] Kabul: 69/69 başarılı; 29 yeni CSV tarihleri tekil ve artan; son
      değerler spec'in "son nokta" sütunlarıyla tutarlı.

## Task 6 — Tarayıcı doğrulaması

- [x] `streamlit run app.py`; üç yeni sayfa ve zenginleşen dört sayfa
      gezilir; KPI satırları panodan gelir; Veri Takvimi 69 satır listeler
      ve yeni serilerin hiçbiri "dikkat gerektiriyor" bandında değildir.

## Task 7 — Belgeler

- [x] `README.md`: yol haritası tablosu (Faz 3 ✅, 3f satırı), mimari
      ağacındaki eksik adaptörler (`epias.py`, `osd.py`), `kaynak_tipi`
      listesi ve seri/kategori sayıları güncellenir.
- [x] `docs/superpowers/plans/2026-08-27-faz1-devredilen-isler.md`: #3
      kapandı olarak işaretlenir.
