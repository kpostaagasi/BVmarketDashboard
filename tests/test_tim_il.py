"""TİM il×sektör karşılaştırma bülteni istemcisi (`il_seri_cek`) testleri.

`il_sektor_noktalari` ayrıştırıcısı kendi testinde (`test_tim.py`) zaten
pinlenmiş; burada gerçek XLSX üretmek yerine onu monkeypatch'leyip
ayrıştırıcının ÇIKTISINI besliyoruz — ağ ve openpyxl'e girmeden `il_seri_cek`
düzeyindeki davranışı (TOPLAM = sektör toplamı, aylık sütun seçimi, önbellek
paylaşımı, eksik il/sektör, 404 atlama) pinliyoruz.
"""

from datetime import date
from types import SimpleNamespace

import pytest

import ingest.tim as tim
from ingest.tim import il_bazinda_url, il_seri_cek


def il_seri(**kwargs):
    varsayilan = dict(
        id="ihracat-il/istanbul-otomotiv",
        kaynak_tipi="tim_il",
        tim_il="İSTANBUL",
        tim_sektor="Otomotiv Endüstrisi",
        start_date=None,
    )
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


class SahteYanit:
    def __init__(self, status_code, content=b""):
        self.status_code = status_code
        self.content = content


class SahteOturum:
    def __init__(self, yanitlar):
        """`yanitlar`: url -> SahteYanit. Listede olmayan URL 404 döner."""
        self.yanitlar = yanitlar
        self.cagrilar = []

    def get(self, url, timeout=None):
        self.cagrilar.append(url)
        return self.yanitlar.get(url, SahteYanit(404, b"<html>404</html>"))


def agustos_2026_noktalari():
    """2026-08 bülteninin ölçülen gerçek sütun etiketleriyle sahte çıktısı.

    Hem doğru aylık sütun ("1 - 31 AĞUSTOS / 2026") hem de tuzak sütunlar
    (önceki yıl aynı ay, DEĞ., YTD, ve — kritik — aynı yılın ÖNCEKİ ayı
    "1 - 31 TEMMUZ / 2026") taşır; bu ikincisi de "1 - " ile başlayıp
    "/ 2026" ile bittiği için salt önek/sonek eşleşmesi yeterli olmaz.
    """
    def sutunlar(bu_ay, gecen_yil):
        return {
            "1 - 31 AĞUSTOS / 2025": gecen_yil,
            "1 - 31 AĞUSTOS / 2026": bu_ay,
            "1 - 31 AĞUSTOS / DEĞ.": (bu_ay - gecen_yil) / gecen_yil,
            "1 - 31 TEMMUZ / 2026": bu_ay * 0.9,  # tuzak: aynı yıl, farklı ay
            "1 OCAK - 31 AĞUSTOS / 2025": gecen_yil * 7,
            "1 OCAK - 31 AĞUSTOS / 2026": bu_ay * 7,
            "1 OCAK - 31 AĞUSTOS / DEĞ.": 0.05,
        }

    return {
        ("İSTANBUL", "Otomotiv Endüstrisi"): sutunlar(5000.0, 4500.0),
        ("İSTANBUL", "Hazır Giyim"): sutunlar(3000.0, 2800.0),
        ("İSTANBUL", "Kimyevi Maddeler"): sutunlar(679756.86, 600000.0),
        ("İSTANBUL", "TOPLAM"): sutunlar(8800137.83, 8000000.0),  # birlik bazlı fazlalık
        ("ADANA", "Otomotiv Endüstrisi"): sutunlar(100.0, 90.0),
        ("ADANA", "TOPLAM"): sutunlar(100.0, 90.0),
    }


# --- TOPLAM = sektör satırlarının toplamı (bülten TOPLAM satırı DEĞİL) ---


def test_toplam_serisi_sektor_satirlarinin_toplamidir(monkeypatch):
    monkeypatch.setattr(tim, "il_sektor_noktalari", lambda baytlar, anahtar: agustos_2026_noktalari())
    oturum = SahteOturum({il_bazinda_url(2026, 8): SahteYanit(200, b"xlsx")})
    seri = il_seri(id="ihracat-il/istanbul-toplam", tim_sektor="TOPLAM")

    df = il_seri_cek(seri, session=oturum, bugun=date(2026, 8, 15))

    beklenen = 5000.0 + 3000.0 + 679756.86  # sektör satırları — TOPLAM satırı (8.800.137,83) DEĞİL
    assert len(df) == 1
    assert df["value"].iloc[0] == pytest.approx(beklenen)
    assert df["value"].iloc[0] != pytest.approx(8800137.83)


def test_tek_sektor_serisi_dogrudan_deger_dondurur(monkeypatch):
    monkeypatch.setattr(tim, "il_sektor_noktalari", lambda baytlar, anahtar: agustos_2026_noktalari())
    oturum = SahteOturum({il_bazinda_url(2026, 8): SahteYanit(200, b"xlsx")})

    df = il_seri_cek(il_seri(), session=oturum, bugun=date(2026, 8, 15))

    assert df["value"].iloc[0] == 5000.0


# --- Aylık sütun seçimi: YTD, DEĞ. ve aynı yılın önceki ayı elenir ---


def test_aylik_sutun_secimi_ytd_ve_deg_sutunlarini_almaz(monkeypatch):
    monkeypatch.setattr(tim, "il_sektor_noktalari", lambda baytlar, anahtar: agustos_2026_noktalari())
    oturum = SahteOturum({il_bazinda_url(2026, 8): SahteYanit(200, b"xlsx")})

    df = il_seri_cek(il_seri(), session=oturum, bugun=date(2026, 8, 15))

    # 5000.0 == "1 - 31 AĞUSTOS / 2026"; YTD (35000.0), DEĞ. (~0.11) ve
    # önceki yıl (4500.0) ile önceki ay tuzağı (4500.0) alınmamalı.
    assert df["value"].iloc[0] == 5000.0
    assert df["value"].iloc[0] not in (4500.0, 35000.0)


# --- Eksik il/sektör: sessiz atlama yasak ---


def test_eksik_il_hata_yukseltir(monkeypatch):
    monkeypatch.setattr(tim, "il_sektor_noktalari", lambda baytlar, anahtar: agustos_2026_noktalari())
    oturum = SahteOturum({il_bazinda_url(2026, 8): SahteYanit(200, b"xlsx")})
    seri = il_seri(tim_il="BURSA")

    with pytest.raises(RuntimeError, match="il/sektör bulunamadı"):
        il_seri_cek(seri, session=oturum, bugun=date(2026, 8, 15))


def test_eksik_sektor_hata_yukseltir(monkeypatch):
    monkeypatch.setattr(tim, "il_sektor_noktalari", lambda baytlar, anahtar: agustos_2026_noktalari())
    oturum = SahteOturum({il_bazinda_url(2026, 8): SahteYanit(200, b"xlsx")})
    seri = il_seri(tim_sektor="Çelik")

    with pytest.raises(RuntimeError, match="il/sektör bulunamadı"):
        il_seri_cek(seri, session=oturum, bugun=date(2026, 8, 15))


def test_eksik_il_toplam_serisinde_de_hata_yukseltir(monkeypatch):
    monkeypatch.setattr(tim, "il_sektor_noktalari", lambda baytlar, anahtar: agustos_2026_noktalari())
    oturum = SahteOturum({il_bazinda_url(2026, 8): SahteYanit(200, b"xlsx")})
    seri = il_seri(tim_il="BURSA", tim_sektor="TOPLAM")

    with pytest.raises(RuntimeError, match="il bulunamadı"):
        il_seri_cek(seri, session=oturum, bugun=date(2026, 8, 15))


# --- 404: o ay atlanır, seri kalan aylarla üretilir ---


def test_404_ay_atlanir_seri_kalan_aylarla_uretilir(monkeypatch):
    monkeypatch.setattr(tim, "il_sektor_noktalari", lambda baytlar, anahtar: agustos_2026_noktalari())
    # Yalnızca temmuz ayı yayımlanmış; ağustos 404.
    oturum = SahteOturum({il_bazinda_url(2026, 7): SahteYanit(200, b"xlsx")})

    df = il_seri_cek(il_seri(), session=oturum, bugun=date(2026, 8, 15))

    assert len(df) == 1
    assert df["date"].iloc[0] == "2026-07-01"


def test_hicbir_ay_yoksa_hata_yukseltir(monkeypatch):
    monkeypatch.setattr(tim, "il_sektor_noktalari", lambda baytlar, anahtar: agustos_2026_noktalari())
    oturum = SahteOturum({})

    with pytest.raises(RuntimeError, match="hiç nokta bulunamadı"):
        il_seri_cek(il_seri(), session=oturum, bugun=date(2023, 1, 15))


# --- Önbellek paylaşımı: aynı ay iki seri için tek indirme ---


def test_onbellek_ayni_ayi_iki_seri_icin_yeniden_indirmez(monkeypatch):
    cagri_sayisi = SimpleNamespace(n=0)

    def sahte_ayikla(baytlar, anahtar):
        cagri_sayisi.n += 1
        return agustos_2026_noktalari()

    monkeypatch.setattr(tim, "il_sektor_noktalari", sahte_ayikla)
    oturum = SahteOturum({il_bazinda_url(2026, 8): SahteYanit(200, b"xlsx")})
    onbellek: dict = {}

    il_seri_cek(il_seri(), onbellek=onbellek, session=oturum, bugun=date(2026, 8, 15))
    ilk_indirme_sayisi = len(oturum.cagrilar)
    ilk_ayiklama_sayisi = cagri_sayisi.n

    il_seri_cek(
        il_seri(id="ihracat-il/istanbul-hazir-giyim", tim_sektor="Hazır Giyim"),
        onbellek=onbellek, session=oturum, bugun=date(2026, 8, 15),
    )

    assert len(oturum.cagrilar) == ilk_indirme_sayisi
    assert cagri_sayisi.n == ilk_ayiklama_sayisi


def test_onbellek_404u_de_paylasir_ikinci_seri_yeniden_denemez():
    oturum = SahteOturum({})  # her URL 404
    onbellek: dict = {}

    with pytest.raises(RuntimeError, match="hiç nokta bulunamadı"):
        il_seri_cek(il_seri(), onbellek=onbellek, session=oturum, bugun=date(2023, 1, 15))
    ilk_cagri = len(oturum.cagrilar)

    with pytest.raises(RuntimeError, match="hiç nokta bulunamadı"):
        il_seri_cek(
            il_seri(id="ihracat-il/istanbul-hazir-giyim", tim_sektor="Hazır Giyim"),
            onbellek=onbellek, session=oturum, bugun=date(2023, 1, 15),
        )

    assert len(oturum.cagrilar) == ilk_cagri


# --- start_date süzmesi (mevcut seri_cek ile aynı davranış) ---


def test_start_date_oncesini_kirpar(monkeypatch):
    monkeypatch.setattr(tim, "il_sektor_noktalari", lambda baytlar, anahtar: agustos_2026_noktalari())
    oturum = SahteOturum({
        il_bazinda_url(2026, 7): SahteYanit(200, b"xlsx"),
        il_bazinda_url(2026, 8): SahteYanit(200, b"xlsx"),
    })
    seri = il_seri(start_date="2026-08-01")

    df = il_seri_cek(seri, session=oturum, bugun=date(2026, 8, 15))

    assert len(df) == 1
    assert df["date"].iloc[0] == "2026-08-01"
