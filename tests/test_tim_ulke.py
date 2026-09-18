"""TİM ülke×sektör karşılaştırma bülteni istemcisi (`ulke_seri_cek`) testleri.

`il_sektor_noktalari` ayrıştırıcısı kendi testinde (`test_tim.py`) zaten
pinlenmiş; burada gerçek XLSX üretmek yerine onu monkeypatch'leyip
ayrıştırıcının ÇIKTISINI besliyoruz — ağ ve openpyxl'e girmeden
`ulke_seri_cek` düzeyindeki davranışı (TOPLAM = sektör toplamı, aylık
sütun seçimi, önbellek paylaşımı, eksik ülke/sektör, 404 atlama) pinliyoruz.

`ulke_seri_cek`, `il_seri_cek` ile aynı ortak gövdeyi (`_karsilastirma_seri_cek`)
paylaşır; monkeypatch imzası bu yüzden `il_sektor_noktalari`nın PARAMETRİZE
edilmiş haliyle (sayfa_adi/ikinci_sutun keyword'leri) uyumlu olmalı.
"""

import io
from datetime import date
from types import SimpleNamespace

import openpyxl
import pytest

import ingest.tim as tim
from ingest.tim import ULKE_SAYFA_ADI, il_sektor_noktalari, ulke_bazinda_url, ulke_seri_cek


def ulke_seri(**kwargs):
    varsayilan = dict(
        id="ihracat-ulke/almanya-otomotiv-endustrisi",
        kaynak_tipi="tim_ulke",
        tim_ulke="ALMANYA",
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


def agustos_2026_ulke_noktalari():
    """2026-08 ülke bülteninin ölçülen gerçek sütun etiketleriyle sahte çıktısı.

    Hem doğru aylık sütun ("1 - 31 AĞUSTOS / 2026") hem de tuzak sütunlar
    (önceki yıl aynı ay, DEĞ., YTD, ve — kritik — aynı yılın ÖNCEKİ ayı
    "1 - 31 TEMMUZ / 2026") taşır. Ayrıca gerçek bültende YOK ama savunma
    amaçlı: ALMANYA için şişirilmiş bir (ALMANYA, TOPLAM) satırı da var —
    kod bunu asla okumamalı, sektör satırlarını toplamalı (ölçüldü: gerçek
    ülke bülteninde ülke başına ayrı TOPLAM satırı hiç yayımlanmıyor).
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
        ("ALMANYA", "Otomotiv Endüstrisi"): sutunlar(5000.0, 4500.0),
        ("ALMANYA", "Hazırgiyim ve Konfeksiyon"): sutunlar(3000.0, 2800.0),
        ("ALMANYA", "Kimyevi Maddeler ve Mamulleri"): sutunlar(679756.86, 600000.0),
        ("ALMANYA", "TOPLAM"): sutunlar(999999.0, 888888.0),  # gerçekte yok; yok sayılmalı
        ("ABD", "Otomotiv Endüstrisi"): sutunlar(100.0, 90.0),
    }


def _sahte_ayikla(baytlar, anahtar, sayfa_adi=None, ikinci_sutun=None):
    """`il_sektor_noktalari`nın parametrize imzasını taklit eden monkeypatch hedefi."""
    return agustos_2026_ulke_noktalari()


# --- TOPLAM = sektör satırlarının toplamı (gerçekte hiç yayımlanmayan bir
# satırı değil) ---


def test_toplam_serisi_sektor_satirlarinin_toplamidir(monkeypatch):
    monkeypatch.setattr(tim, "il_sektor_noktalari", _sahte_ayikla)
    oturum = SahteOturum({ulke_bazinda_url(2026, 8): SahteYanit(200, b"xlsx")})
    seri = ulke_seri(id="ihracat-ulke/almanya-toplam", tim_sektor="TOPLAM")

    df = ulke_seri_cek(seri, session=oturum, bugun=date(2026, 8, 15))

    beklenen = 5000.0 + 3000.0 + 679756.86  # sektör satırları — sahte TOPLAM satırı DEĞİL
    assert len(df) == 1
    assert df["value"].iloc[0] == pytest.approx(beklenen)
    assert df["value"].iloc[0] != pytest.approx(999999.0)


def test_tek_sektor_serisi_dogrudan_deger_dondurur(monkeypatch):
    monkeypatch.setattr(tim, "il_sektor_noktalari", _sahte_ayikla)
    oturum = SahteOturum({ulke_bazinda_url(2026, 8): SahteYanit(200, b"xlsx")})

    df = ulke_seri_cek(ulke_seri(), session=oturum, bugun=date(2026, 8, 15))

    assert df["value"].iloc[0] == 5000.0


# --- Aylık sütun seçimi: YTD, DEĞ. ve aynı yılın önceki ayı elenir ---


def test_aylik_sutun_secimi_ytd_ve_deg_sutunlarini_almaz(monkeypatch):
    monkeypatch.setattr(tim, "il_sektor_noktalari", _sahte_ayikla)
    oturum = SahteOturum({ulke_bazinda_url(2026, 8): SahteYanit(200, b"xlsx")})

    df = ulke_seri_cek(ulke_seri(), session=oturum, bugun=date(2026, 8, 15))

    # 5000.0 == "1 - 31 AĞUSTOS / 2026"; YTD (35000.0), DEĞ. (~0.11) ve
    # önceki yıl (4500.0) ile önceki ay tuzağı (4500.0) alınmamalı.
    assert df["value"].iloc[0] == 5000.0
    assert df["value"].iloc[0] not in (4500.0, 35000.0)


# --- Eksik ülke/sektör: sessiz atlama yasak ---


def test_eksik_ulke_hata_yukseltir(monkeypatch):
    monkeypatch.setattr(tim, "il_sektor_noktalari", _sahte_ayikla)
    oturum = SahteOturum({ulke_bazinda_url(2026, 8): SahteYanit(200, b"xlsx")})
    seri = ulke_seri(tim_ulke="FRANSA")

    with pytest.raises(RuntimeError, match="ülke/sektör bulunamadı"):
        ulke_seri_cek(seri, session=oturum, bugun=date(2026, 8, 15))


def test_eksik_sektor_hata_yukseltir(monkeypatch):
    monkeypatch.setattr(tim, "il_sektor_noktalari", _sahte_ayikla)
    oturum = SahteOturum({ulke_bazinda_url(2026, 8): SahteYanit(200, b"xlsx")})
    seri = ulke_seri(tim_sektor="Çelik")

    with pytest.raises(RuntimeError, match="ülke/sektör bulunamadı"):
        ulke_seri_cek(seri, session=oturum, bugun=date(2026, 8, 15))


def test_eksik_ulke_toplam_serisinde_de_hata_yukseltir(monkeypatch):
    monkeypatch.setattr(tim, "il_sektor_noktalari", _sahte_ayikla)
    oturum = SahteOturum({ulke_bazinda_url(2026, 8): SahteYanit(200, b"xlsx")})
    seri = ulke_seri(tim_ulke="FRANSA", tim_sektor="TOPLAM")

    with pytest.raises(RuntimeError, match="ülke bulunamadı"):
        ulke_seri_cek(seri, session=oturum, bugun=date(2026, 8, 15))


# --- 404: o ay atlanır, seri kalan aylarla üretilir ---


def test_404_ay_atlanir_seri_kalan_aylarla_uretilir(monkeypatch):
    monkeypatch.setattr(tim, "il_sektor_noktalari", _sahte_ayikla)
    # Yalnızca temmuz ayı yayımlanmış; ağustos 404.
    oturum = SahteOturum({ulke_bazinda_url(2026, 7): SahteYanit(200, b"xlsx")})

    df = ulke_seri_cek(ulke_seri(), session=oturum, bugun=date(2026, 8, 15))

    assert len(df) == 1
    assert df["date"].iloc[0] == "2026-07-01"


def test_hicbir_ay_yoksa_hata_yukseltir(monkeypatch):
    monkeypatch.setattr(tim, "il_sektor_noktalari", _sahte_ayikla)
    oturum = SahteOturum({})

    with pytest.raises(RuntimeError, match="hiç nokta bulunamadı"):
        ulke_seri_cek(ulke_seri(), session=oturum, bugun=date(2023, 1, 15))


# --- Önbellek paylaşımı: aynı ay iki seri için tek indirme ---


def test_onbellek_ayni_ayi_iki_seri_icin_yeniden_indirmez(monkeypatch):
    cagri_sayisi = SimpleNamespace(n=0)

    def sahte_ayikla(baytlar, anahtar, sayfa_adi=None, ikinci_sutun=None):
        cagri_sayisi.n += 1
        return agustos_2026_ulke_noktalari()

    monkeypatch.setattr(tim, "il_sektor_noktalari", sahte_ayikla)
    oturum = SahteOturum({ulke_bazinda_url(2026, 8): SahteYanit(200, b"xlsx")})
    onbellek: dict = {}

    ulke_seri_cek(ulke_seri(), onbellek=onbellek, session=oturum, bugun=date(2026, 8, 15))
    ilk_indirme_sayisi = len(oturum.cagrilar)
    ilk_ayiklama_sayisi = cagri_sayisi.n

    ulke_seri_cek(
        ulke_seri(
            id="ihracat-ulke/almanya-hazirgiyim-ve-konfeksiyon",
            tim_sektor="Hazırgiyim ve Konfeksiyon",
        ),
        onbellek=onbellek, session=oturum, bugun=date(2026, 8, 15),
    )

    assert len(oturum.cagrilar) == ilk_indirme_sayisi
    assert cagri_sayisi.n == ilk_ayiklama_sayisi


def test_onbellek_404u_de_paylasir_ikinci_seri_yeniden_denemez():
    oturum = SahteOturum({})  # her URL 404
    onbellek: dict = {}

    with pytest.raises(RuntimeError, match="hiç nokta bulunamadı"):
        ulke_seri_cek(ulke_seri(), onbellek=onbellek, session=oturum, bugun=date(2023, 1, 15))
    ilk_cagri = len(oturum.cagrilar)

    with pytest.raises(RuntimeError, match="hiç nokta bulunamadı"):
        ulke_seri_cek(
            ulke_seri(
                id="ihracat-ulke/almanya-hazirgiyim-ve-konfeksiyon",
                tim_sektor="Hazırgiyim ve Konfeksiyon",
            ),
            onbellek=onbellek, session=oturum, bugun=date(2023, 1, 15),
        )

    assert len(oturum.cagrilar) == ilk_cagri


# --- start_date süzmesi (mevcut il_seri_cek ile aynı davranış) ---


def test_start_date_oncesini_kirpar(monkeypatch):
    monkeypatch.setattr(tim, "il_sektor_noktalari", _sahte_ayikla)
    oturum = SahteOturum({
        ulke_bazinda_url(2026, 7): SahteYanit(200, b"xlsx"),
        ulke_bazinda_url(2026, 8): SahteYanit(200, b"xlsx"),
    })
    seri = ulke_seri(start_date="2026-08-01")

    df = ulke_seri_cek(seri, session=oturum, bugun=date(2026, 8, 15))

    assert len(df) == 1
    assert df["date"].iloc[0] == "2026-08-01"


# --- Parametrize edilen sayfa adı: yanlışsa "sayfası yok" hatası ---


def test_yanlis_sayfa_adi_parametresi_sayfasi_yok_hatasi_verir():
    kitap = openpyxl.Workbook()  # varsayılan sayfa adı "Sheet", ULKE_SAYFA_ADI değil
    tampon = io.BytesIO()
    kitap.save(tampon)
    kitap.close()

    with pytest.raises(RuntimeError, match=f"'{ULKE_SAYFA_ADI}' sayfası yok"):
        il_sektor_noktalari(
            tampon.getvalue(), "2026.08", sayfa_adi=ULKE_SAYFA_ADI, ikinci_sutun="ULKE",
        )


# --- Genel toplam satırının ülke bülteninde SEKTÖR sütunu boş gelir (il
# bülteninden farklı) — ölçüldü: 2023.01–2024.06 ülke dosyalarında
# ('', 'TOPLAM'); 2025'ten itibaren ('TOPLAM', 'TOPLAM'). Regresyon: bu satır
# "eksik ülke/sektör anahtarı" hatası fırlatmamalı, ama gerçek veri taşıyan
# bir satırda anahtar eksikse hata hâlâ yükselmeli.


def _ulke_bulten_baytlari(genel_toplam_satiri):
    """Gerçek 2023 ülke bülteni şablonuyla uyumlu minimal XLSX üretir."""
    kitap = openpyxl.Workbook()
    sayfa = kitap.active
    sayfa.title = ULKE_SAYFA_ADI
    sayfa.append(["31.01.2023 Konsolide Ülkelere Göre Sektörel İhracat  (1000 $)"])
    sayfa.append([])
    sayfa.append([None, None, "1 - 31 OCAK"])
    sayfa.append(["SEKTÖR", "ULKE", 2022, 2023, "DEĞ."])
    sayfa.append(["Çelik", "ALMANYA", 100.0, 120.0, 0.2])
    sayfa.append(genel_toplam_satiri)
    tampon = io.BytesIO()
    kitap.save(tampon)
    kitap.close()
    return tampon.getvalue()


def test_ulke_bulteninde_bos_sektorlu_genel_toplam_hata_vermez():
    """Ölçülen 2023.01–2024.06 imzası: (boş SEKTÖR, 'TOPLAM' ÜLKE)."""
    baytlar = _ulke_bulten_baytlari([None, "TOPLAM", 1000.0, 1200.0, 0.2])

    noktalar = il_sektor_noktalari(
        baytlar, "2023.01", sayfa_adi=ULKE_SAYFA_ADI, ikinci_sutun="ULKE",
    )

    assert ("GENEL TOPLAM", "TOPLAM") in noktalar
    assert noktalar["GENEL TOPLAM", "TOPLAM"]["1 - 31 OCAK / 2023"] == 1200.0
    assert noktalar["ALMANYA", "Çelik"]["1 - 31 OCAK / 2023"] == 120.0


def test_ulke_bulteninde_toplam_toplam_genel_toplam_hata_vermez():
    """Ölçülen 2025+ imzası: ('TOPLAM', 'TOPLAM') — mevcut il davranışıyla aynı."""
    baytlar = _ulke_bulten_baytlari(["TOPLAM", "TOPLAM", 1000.0, 1200.0, 0.2])

    noktalar = il_sektor_noktalari(
        baytlar, "2025.01", sayfa_adi=ULKE_SAYFA_ADI, ikinci_sutun="ULKE",
    )

    assert ("GENEL TOPLAM", "TOPLAM") in noktalar
    assert noktalar["GENEL TOPLAM", "TOPLAM"]["1 - 31 OCAK / 2023"] == 1200.0


def test_ulke_bulteninde_gercek_veri_tasiyan_bos_anahtar_hala_hata_verir():
    """Genel toplam MASKESİ gerçek şablon kaymasını gizlememeli: SEKTÖR boş
    ama ÜLKE gerçek bir ülke adıysa (TOPLAM değil) bu veri kaybıdır."""
    baytlar = _ulke_bulten_baytlari([None, "FRANSA", 1000.0, 1200.0, 0.2])

    with pytest.raises(RuntimeError, match="eksik ülke/sektör anahtarı"):
        il_sektor_noktalari(baytlar, "2023.01", sayfa_adi=ULKE_SAYFA_ADI, ikinci_sutun="ULKE")
