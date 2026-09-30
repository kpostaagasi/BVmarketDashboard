"""Migros Ticaret A.Ş. (BIST: MGROS) "Ara Dönem Faaliyet Raporu" PDF
istemcisi testleri."""

from types import SimpleNamespace

import pytest

from ingest.migros import (
    GECERLI_METRIKLER,
    _belge_metnini_getir,
    magaza_sayisini_ayikla,
    seri_cek,
)


class SahteYanit:
    def __init__(self, status_code=200, content=b""):
        self.status_code = status_code
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class SahteOturum:
    def __init__(self, status_code=404):
        self.status_code = status_code

    def get(self, url, headers=None, timeout=None):
        return SahteYanit(status_code=self.status_code)


def test_belge_metnini_getir_404_link_curumesinde_none_doner():
    """Ölçülen gerçek anomali: 2012 dönemine ait bazı rapor bağlantıları
    artık 404 veriyor — dönem atlanır, seri PATLAMAZ."""
    onbellek = {}
    sonuc = _belge_metnini_getir("http://x/eski-2012.pdf", onbellek, session=SahteOturum(404))
    assert sonuc is None
    assert onbellek["http://x/eski-2012.pdf"] is None  # önbelleklenir, tekrar denenmez


def test_seri_cek_404lu_donemi_atlar_digerlerini_kullanir(monkeypatch):
    import ingest.migros as migros_modul

    monkeypatch.setattr(
        migros_modul, "_rapor_listesi",
        lambda session=None: [
            {"tarih": "2012-09-01", "url": "http://x/eski.pdf"},
            {"tarih": "2026-06-01", "url": "http://x/haz.pdf"},
        ],
    )

    def sahte_getir(url, onbellek, session=None):
        return None if url == "http://x/eski.pdf" else "30 Haziran 2026 itibarıyla toplam\nmağaza sayısı 3.830 oldu."

    monkeypatch.setattr(migros_modul, "_belge_metnini_getir", sahte_getir)
    df = seri_cek(mgros_seri())
    assert list(df["date"]) == ["2026-06-01"]
    assert list(df["value"]) == [3830.0]


def mgros_seri(**kwargs):
    varsayilan = dict(id="perakende/mgros-toplam-magaza-sayisi", migros_metrik="toplam-magaza-sayisi")
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


def test_magaza_sayisini_ayikla_detayli_dokum_kalibi():
    metin = (
        "Şirketimiz, 30 Haziran 2026 itibarıyla yurt içinde 7 coğrafi bölgede 2.220 Migros, "
        "1.186 Migros Jet, 157 Macrocenter, 109 Macrokiosk, 50 hipermarket, 24 Toptan, 80 Mion "
        "ve 4 Petimo mağazası olmak üzere toplam\n3.830 mağazaya ulaştı."
    )
    assert magaza_sayisini_ayikla(metin) == 3830.0


def test_magaza_sayisini_ayikla_ozet_cumle_kalibi():
    """Bazı çeyreklerde yalnızca kısa özet cümlesi var (ölçülen ikinci biçim)."""
    metin = "30 Eylül 2025 itibarıyla toplam\nmağaza sayısı 3.730 oldu."
    assert magaza_sayisini_ayikla(metin) == 3730.0


def test_magaza_sayisini_ayikla_eslesme_yoksa_none():
    assert magaza_sayisini_ayikla("ilgisiz içerik") is None


def test_seri_cek_bilinmeyen_metrik_hata_verir():
    with pytest.raises(RuntimeError, match="Bilinmeyen migros_metrik"):
        seri_cek(mgros_seri(migros_metrik="olmayan"))


def test_seri_cek_hicbir_raporda_deger_yoksa_patlar(monkeypatch):
    import ingest.migros as migros_modul

    monkeypatch.setattr(
        migros_modul, "_rapor_listesi",
        lambda session=None: [{"tarih": "2026-06-01", "url": "http://x/haz.pdf"}],
    )
    monkeypatch.setattr(
        migros_modul, "_belge_metnini_getir",
        lambda url, onbellek, session=None: "ilgisiz içerik",
    )
    with pytest.raises(RuntimeError, match="mağaza sayısı bulunamadı"):
        seri_cek(mgros_seri())


def test_seri_cek_dogru_seriyi_uretir(monkeypatch):
    import ingest.migros as migros_modul

    monkeypatch.setattr(
        migros_modul, "_rapor_listesi",
        lambda session=None: [
            {"tarih": "2026-06-01", "url": "http://x/haz.pdf"},
            {"tarih": "2026-03-01", "url": "http://x/mar.pdf"},
        ],
    )
    icerikler = {
        "http://x/haz.pdf": "30 Haziran 2026 itibarıyla toplam\nmağaza sayısı 3.830 oldu.",
        "http://x/mar.pdf": "31 Mart 2026 itibarıyla toplam\nmağaza sayısı 3.812 oldu.",
    }
    monkeypatch.setattr(
        migros_modul, "_belge_metnini_getir",
        lambda url, onbellek, session=None: icerikler[url],
    )
    df = seri_cek(mgros_seri())
    assert list(df["date"]) == ["2026-03-01", "2026-06-01"]
    assert list(df["value"]) == [3812.0, 3830.0]


def test_gecerli_metrikler_tek_seriyi_kapsar():
    assert GECERLI_METRIKLER == {"toplam-magaza-sayisi"}


# --- 2Ç 2026 "Online Operasyonlar" sayfası ---
#
# Koordinatlar 2Ç 2026 sunumunun s.24'ünden ÖLÇÜLMÜŞTÜR (2026-09-30):
# dört grafik, her biri 2Ç24/2Ç25/2Ç26 sütunlu, "Çeyreksel Öne
# Çıkanlar" şeridi + grafik başlıkları + değer kutuları + en alttaki
# "NÇ YYYY" eksen etiketleri. Test bu geometriyi birebir taklit eder.

_SAYFA24_METIN = (
    "Online Operasyonlar\nEnflasyondan (TÜFE) arındırılmış\nÇeyreksel Öne Çıkanlar\n"
    "28,5 milyar TL Migros One GMV\n5,0 milyar TL Migros Yemek GMV\n"
    "Aktif kullanıcı Migros One GMV Günlük Sipariş Migros’ta e- ticaret payı sayısı(2)\n"
    "(milyar TL) (milyon)\n"
    "2Ç 2024 2Ç 2025 2Ç 2026\n"
)


def _sayfa24_kelimeler(ceyrekler):
    """s.24 geometrisini verilen üç çeyrek için üretir. `ceyrekler`
    soldan sağa (geçmiş -> sunumun kendi çeyreği)."""
    eksen_topu = 420.0
    kelimeler = []
    # üstteki "Çeyreksel Öne Çıkanlar" şeridi — aynı anahtar sözcükleri
    # burada da geçiyor, ayrıştırıcı bunları elemesi gerekiyor
    kelimeler += [
        {"text": "28,5", "top": 123.0, "x0": 90.0, "x1": 117.0},
        {"text": "GMV", "top": 138.3, "x0": 158.5, "x1": 187.5},
        {"text": "GMV", "top": 145.5, "x0": 290.6, "x1": 319.7},
        {"text": "6,6", "top": 115.8, "x0": 603.6, "x1": 623.5},
        {"text": "%23,1", "top": 115.8, "x0": 457.1, "x1": 492.3},
        {"text": "240", "top": 184.2, "x0": 428.8, "x1": 454.2},
        # sağdaki dipnot şeridinde de "2Ç" geçiyor
        {"text": "2Ç", "top": 262.1, "x0": 865.3, "x1": 877.8},
        {"text": "677", "top": 260.6, "x0": 746.6, "x1": 767.9},
    ]
    # grafik başlıkları
    kelimeler += [
        {"text": "Aktif", "top": 243.7, "x0": 598.8, "x1": 623.4},
        {"text": "GMV", "top": 248.2, "x0": 155.5, "x1": 179.9},
        {"text": "Sipariş", "top": 248.5, "x0": 311.5, "x1": 345.6},
    ]
    # değer kutuları: (metin, top, merkez) — sütun merkezleri ölçülen
    # eksen etiketi merkezlerine göre
    kutular = [
        (("18,6", 321.3, 94.4), ("23,5", 300.5, 133.6), ("28,5", 279.3, 173.4),
         ("1,9", 337.8, 96.1), ("2,9", 319.7, 134.0), ("5,0", 299.9, 173.8)),
        (("226k", 316.6, 266.9), ("263k", 303.2, 307.0), ("327k", 279.9, 347.0),
         ("45k", 335.3, 266.1), ("57k", 322.9, 306.8), ("91k", 299.4, 348.0)),
        (("18,5", 303.6, 433.7), ("20,7", 292.4, 472.4), ("23,1", 280.2, 513.6)),
        (("5,1", 305.5, 597.1), ("5,8", 292.8, 636.1), ("6,6", 278.2, 675.9)),
    ]
    for grup in kutular:
        for metin, top, merkez in grup:
            kelimeler.append({"text": metin, "top": top, "x0": merkez - 6, "x1": merkez + 6})
    for x0, (ceyrek, yil) in zip((78.7, 119.0, 158.7, 252.4, 292.7, 332.4, 417.8, 458.1,
                                  497.9, 580.8, 621.1, 660.8), ceyrekler * 4):
        kelimeler += [
            {"text": f"{ceyrek}Ç", "top": eksen_topu, "x0": x0, "x1": x0 + 10.5},
            {"text": str(yil), "top": eksen_topu - 0.4, "x0": x0 + 12.8, "x1": x0 + 25.3},
        ]
    return kelimeler


class SahteSayfa:
    def __init__(self, metin, kelimeler):
        self._metin = metin
        self._kelimeler = kelimeler

    def extract_text(self):
        return self._metin

    def extract_words(self):
        return self._kelimeler


class SahtePdf:
    def __init__(self, sayfalar):
        self.pages = sayfalar

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class SahtePdfplumber:
    def __init__(self, sayfalar):
        self._sayfalar = sayfalar

    def open(self, *a, **k):
        return SahtePdf(self._sayfalar)


def _sayfa24_kur(ceyrekler):
    import ingest.migros as migros_modul

    sayfa = SahteSayfa(_SAYFA24_METIN, _sayfa24_kelimeler(ceyrekler))
    return SahtePdfplumber([sayfa])


def test_online_operasyonlari_gmv_ve_kullaniciyi_okur(monkeypatch):
    """2Ç 2026 sunumu s.24: GMV 28,5 milyar TL, aktif kullanıcı 6,6 mn.
    Her ikisi de sayfanın SAĞINDAKİ (kendi çeyrek) sütunundan."""
    import ingest.migros as migros_modul

    monkeypatch.setattr(migros_modul, "pdfplumber", _sayfa24_kur([(2, 2024), (2, 2025), (2, 2026)]))
    sonuc = migros_modul.online_operasyonlarini_ayikla(b"x", 2026, 2)
    assert sonuc["migros-one-gmv"] == 28.5
    assert sonuc["migros-one-aktif-kullanici"] == 6.6


def test_online_operasyonlari_siparis_gunlukten_ceyrek_toplam_turetir(monkeypatch):
    """BİRİM TUZAĞI: sayfa GÜNLÜK ortalama veriyor (2Ç 2026: 327k/gün),
    seri ise ÇEYREKLİK TOPLAM tutuyor (birim "milyon"). Çarpan sabit 90/91
    değil, eksen etiketindeki çeyreğin GERÇEK gün sayısından gelir:
    2Ç 2026 = 30+31+30 = 91 gün -> 327.000 x 91 / 1e6 = 29,757 mn.
    1Ç 2026 olsaydı (31+28+31 = 90 gün) 29,43 mn çıkardı — çarpan
    etiketten türetildiği için iki çeyrek birbirine karışmaz."""
    import ingest.migros as migros_modul

    monkeypatch.setattr(migros_modul, "pdfplumber", _sayfa24_kur([(2, 2024), (2, 2025), (2, 2026)]))
    deger = migros_modul.online_operasyonlarini_ayikla(b"x", 2026, 2)["migros-one-siparis-sayisi"]
    assert deger == pytest.approx(327_000 * 91 / 1e6)
    assert deger == pytest.approx(29.757)
    assert deger != pytest.approx(327.0)  # günlük ham değer sızmamalı

    # Etiketler sunumun kendi çeyreğiyle uyuşmuyorsa (etiket 2Ç 2026,
    # sunum 1Ç 2026) hiçbir şey dönülmez — yanlış çeyreğe yazma riski.
    assert migros_modul.online_operasyonlarini_ayikla(b"x", 2026, 1) is None


def test_online_operasyonlari_gun_sayisi_etiketten_turetilir(monkeypatch):
    """Aynı sayfa, kendi çeyreği 3Ç 2026 (Temmuz+Ağustos+Eylül = 92 gün)
    olarak etiketlendiğinde çarpan değişir — sabit gün sayısı değil."""
    import ingest.migros as migros_modul

    monkeypatch.setattr(migros_modul, "pdfplumber", _sayfa24_kur([(1, 2026), (2, 2026), (3, 2026)]))
    deger = migros_modul.online_operasyonlarini_ayikla(b"x", 2026, 3)["migros-one-siparis-sayisi"]
    assert deger == pytest.approx(327_000 * 92 / 1e6)


def test_ceyrek_gun_sayisi_gercek_takvim_gunleri():
    import ingest.migros as migros_modul

    gun = migros_modul._ceyrek_gun_sayisi
    assert [gun(2026, c) for c in (1, 2, 3, 4)] == [90, 91, 92, 92]
    assert gun(2024, 4) == 92  # artık yıl: 30+31+30+31
    assert gun(2025, 1) == 90


def test_online_operasyonlari_sayfa_yoksa_none(monkeypatch):
    """2Ç 2026 öncesi sunumların hiçbirinde bu sayfa yok (ölçüldü:
    2Ç 2025 sunumunda 'Online Operasyonlar' geçmiyor) — None döner."""
    import ingest.migros as migros_modul

    monkeypatch.setattr(
        migros_modul, "pdfplumber",
        SahtePdfplumber([SahteSayfa("Online ve Dijital Ödeme Çözümleri", [])]),
    )
    assert migros_modul.online_operasyonlarini_ayikla(b"x", 2025, 2) is None


def test_ekosistem_izgarasi_deger_sayisi_degisirse_patma_yerine_none(monkeypatch):
    """Eski ızgara sayfası şablon değiştirirse RuntimeError yerine None:
    tek sayfa değişikliği üç dijital seriyi de düşürmemeli."""
    import ingest.migros as migros_modul

    kelimeler = [{"text": "Aktif", "top": 189.0, "x0": 44.0, "x1": 90.0}]
    kelimeler += [{"text": "6,3", "top": 255.0, "x0": 138.0 + 20 * i, "x1": 150.0 + 20 * i} for i in range(7)]
    sayfa = SahteSayfa("Migros Dijital Ekosistemi Performans Göstergeleri", kelimeler)
    monkeypatch.setattr(migros_modul, "pdfplumber", SahtePdfplumber([sayfa]))
    assert migros_modul.ekosistem_izgarasini_ayikla(b"x", 2026, 1) is None


def test_seri_cek_yeni_sayfadan_ucuncu_ceyrek_noktasini_yazar(monkeypatch):
    """Entegrasyon: 2Ç 2026 sunumu yayımladı, eski ızgara yok -> seri
    1Ç 2026'da kesilmemeli, 2Ç 2026 noktasını almalı."""
    import ingest.migros as migros_modul

    monkeypatch.setattr(
        migros_modul, "_sunum_listesi",
        lambda session=None: [{"yil": 2026, "ceyrek": 2, "url": "http://x/2c26.pdf"}],
    )
    monkeypatch.setattr(migros_modul, "_sunum_pdfsini_getir", lambda url, onbellek, session=None: b"pdf")
    monkeypatch.setattr(migros_modul, "pdfplumber", _sayfa24_kur([(2, 2024), (2, 2025), (2, 2026)]))

    df = seri_cek(
        SimpleNamespace(
            id="perakende/mgros-one-siparis-sayisi", migros_metrik="migros-one-siparis-sayisi"
        )
    )
    assert list(df["date"]) == ["2026-04-01"]
    assert list(df["value"]) == [pytest.approx(29.757)]
