"""TİM sektörel ihracat bülteni istemcisi testleri.

Bülten baytları testte openpyxl ile üretilir: gerçek dosya yapısının aynısı
(satır 1 başlık/yıl, satır 4 ay başlıkları, satır 5+ sektörler, `TOPLAM`
satırı, ondan sonra 2019–2020 dosyalarındaki alt mal grubu tabloları).
"""

import io
from datetime import date
from types import SimpleNamespace

import openpyxl
import pytest

from ingest.tim import (
    bulten_url,
    cekilecek_bultenler,
    dogrula,
    sayfayi_ayikla,
    sektor_adini_normalize,
    seri_cek,
    sifir_aylari_at,
)

AYLAR = ["OCAK", "ŞUBAT", "MART", "NİSAN", "MAYIS", "HAZİRAN", "TEMMUZ",
         "AĞUSTOS", "EYLÜL", "EKİM", "KASIM", "ARALIK"]


def bulten_baytlari(yil=2026, satirlar=None, alt_tablo=False, sektor_sayisi=30):
    """Gerçek şablona uygun bir XLSX üretir.

    `satirlar` verilmezse ana gruplar + TOPLAM tutarlı olacak şekilde
    doldurulur; `sektor_sayisi` asgari satır kontrolünü geçmek için dolgu
    satırı ekler.
    """
    kitap = openpyxl.Workbook()
    sayfa = kitap.active
    sayfa.title = "SEKTOR"
    sayfa.append([" ", f"31.08.{yil} TARİHİ İTİBARİYLE SEKTÖREL "])
    sayfa.append([])
    sayfa.append([])
    sayfa.append(["S E K T Ö R", *AYLAR, "TOPLAM"])

    if satirlar is None:
        satirlar = [
            (".I. TARIM", [100.0] * 12),
            (".     A. BİTKİSEL ÜRÜNLER", [60.0] * 12),
            (" Yaş Meyve ve Sebze  ", [60.0] * 12),
            (".II. SANAYİ", [800.0] * 12),
            (" Otomotiv Endüstrisi", [300.0] * 12),
            (" Elektrik ve Elektronik", [120.0] * 12),
            (".III. MADENCİLİK", [50.0] * 12),
            (" Madencilik Ürünleri", [50.0] * 12),
        ]
        dolgu = sektor_sayisi - (len(satirlar) + 1)
        satirlar += [(f" Dolgu Sektör {i}", [1.0] * 12) for i in range(dolgu)]
        satirlar.append((".                         TOPLAM", [950.0] * 12))

    for ad, degerler in satirlar:
        sayfa.append([ad, *degerler, sum(degerler)])

    if alt_tablo:
        # 2019–2020 dosyalarında TOPLAM'dan sonra gelen alt mal grubu
        # tabloları: sızarsa sektör sanılırlar.
        sayfa.append(["ALT MAL GRUBU"])
        sayfa.append([" Diğer Sanayi Ürünleri", *([7.0] * 12), 84.0])

    tampon = io.BytesIO()
    kitap.save(tampon)
    return tampon.getvalue()


def tim_seri(**kwargs):
    varsayilan = dict(
        id="ihracat/otomotiv",
        kaynak_tipi="tim",
        tim_sektor="Otomotiv Endüstrisi",
        tim_eski_adlar=None,
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


# --- URL ve bülten seçimi ---


def test_bulten_url_ayi_dizinde_sifirsiz_dosyada_sifirli_yazar():
    assert bulten_url(2026, 8) == (
        "https://tim.org.tr/files/downloads/rakamlar/2026/8/"
        "2026-08-sektorel-bazda-rakamlar.xlsx"
    )


def test_bulten_url_iki_haneli_ayda_ayni_kalir():
    assert bulten_url(2025, 12).endswith("/2025/12/2025-12-sektorel-bazda-rakamlar.xlsx")


def test_cekilecek_bultenler_yil_basina_tek_dosya_secer():
    """Her dosya o yılın tamamını taşır; geçmiş yıllar için Aralık yeter."""
    assert cekilecek_bultenler(date(2026, 9, 8)) == [
        (2019, 12), (2020, 12), (2021, 12), (2022, 12), (2023, 12),
        (2024, 12), (2025, 12), (2026, 9),
    ]


def test_cekilecek_bultenler_2019da_tek_dosya():
    """2019 xlsx yayının ilk yılı; 2019/1 kaynakta 404."""
    assert cekilecek_bultenler(date(2019, 12, 31)) == [(2019, 12)]


# --- Ad normalizasyonu (gerçek bülten etiketleri) ---


def test_sektor_adi_bastaki_noktalari_ve_fazla_bosluklari_atar():
    assert sektor_adini_normalize(".I. TARIM") == "I. TARIM"
    assert sektor_adini_normalize(".     A. BİTKİSEL ÜRÜNLER") == "A. BİTKİSEL ÜRÜNLER"
    assert sektor_adini_normalize(" Yaş Meyve ve Sebze  ") == "Yaş Meyve ve Sebze"
    assert sektor_adini_normalize(".                         TOPLAM") == "TOPLAM"


def test_sektor_adi_bos_hucrede_bos_string():
    assert sektor_adini_normalize(None) == ""
    assert sektor_adini_normalize("   ") == ""


# --- Sayfa ayrıştırma ---


def test_sayfayi_ayikla_yili_baslikatan_alir_ve_ay_tarihleri_uretir():
    noktalar = sayfayi_ayikla(bulten_baytlari(yil=2026))
    assert noktalar["Otomotiv Endüstrisi"]["2026-01-01"] == 300.0
    assert noktalar["Otomotiv Endüstrisi"]["2026-12-01"] == 300.0
    assert len(noktalar["Otomotiv Endüstrisi"]) == 12


def test_sayfayi_ayikla_toplam_satirinda_durur():
    """2019–2020 dosyalarının alt mal grubu tabloları sektör sanılmamalı."""
    noktalar = sayfayi_ayikla(bulten_baytlari(alt_tablo=True))
    assert "TOPLAM" in noktalar
    assert "Diğer Sanayi Ürünleri" not in noktalar


def test_sayfayi_ayikla_sayfa_adi_degisirse_hata():
    kitap = openpyxl.Workbook()
    kitap.active.title = "BASKA"
    tampon = io.BytesIO()
    kitap.save(tampon)
    with pytest.raises(RuntimeError, match="SEKTOR"):
        sayfayi_ayikla(tampon.getvalue())


# --- Yayımlanmamış ay (sıfır) tuzağı ---


def test_sifir_aylari_at_yayimlanmamis_ayi_tum_sektorlerden_duser():
    """Sıfır "ihracat yok" değil, "henüz yayımlanmadı" demek."""
    noktalar = {
        "TOPLAM": {"2026-07-01": 950.0, "2026-08-01": 0.0},
        "Otomotiv Endüstrisi": {"2026-07-01": 300.0, "2026-08-01": 0.0},
    }
    temiz = sifir_aylari_at(noktalar)
    assert temiz["TOPLAM"] == {"2026-07-01": 950.0}
    assert temiz["Otomotiv Endüstrisi"] == {"2026-07-01": 300.0}


def test_sifir_aylari_at_sektorun_gercek_sifirini_korur():
    """Kararı TOPLAM verir: toplamı dolu bir ayda sektörün sıfırı veridir."""
    noktalar = {
        "TOPLAM": {"2026-07-01": 950.0},
        "Mücevher": {"2026-07-01": 0.0},
    }
    assert sifir_aylari_at(noktalar)["Mücevher"] == {"2026-07-01": 0.0}


def test_sifir_aylari_at_toplam_satiri_yoksa_hata():
    with pytest.raises(RuntimeError, match="TOPLAM"):
        sifir_aylari_at({"Otomotiv Endüstrisi": {"2026-07-01": 1.0}})


# --- Öz-doğrulama ---


def test_dogrula_tutarli_bulteni_gecirir():
    dogrula(sifir_aylari_at(sayfayi_ayikla(bulten_baytlari())), "2026.08")


def test_dogrula_ana_grup_toplami_uymazsa_hata():
    """Şablon kayması: TOPLAM ile I+II+III ayrışır."""
    noktalar = sifir_aylari_at(sayfayi_ayikla(bulten_baytlari()))
    noktalar["II. SANAYİ"]["2026-03-01"] += 100.0
    with pytest.raises(RuntimeError, match="uyuşmuyor"):
        dogrula(noktalar, "2026.08")


def test_dogrula_az_sektor_satirinda_hata():
    noktalar = sifir_aylari_at(sayfayi_ayikla(bulten_baytlari(sektor_sayisi=12)))
    with pytest.raises(RuntimeError, match="asgari"):
        dogrula(noktalar, "2026.08")


def test_dogrula_ana_grup_satiri_eksikse_hata():
    noktalar = sifir_aylari_at(sayfayi_ayikla(bulten_baytlari(sektor_sayisi=32)))
    del noktalar["III. MADENCİLİK"]
    with pytest.raises(RuntimeError, match="ana grup"):
        dogrula(noktalar, "2026.08")


# --- seri_cek: ağ kabuğu ---


def _oturum(yillar, **kwargs):
    return SahteOturum({
        bulten_url(yil, ay): SahteYanit(200, bulten_baytlari(yil=yil, **kwargs))
        for yil, ay in yillar
    })


def test_seri_cek_yillari_birlestirip_tek_seri_uretir():
    yillar = cekilecek_bultenler(date(2021, 6, 15))
    oturum = _oturum([(2019, 12), (2020, 12), (2021, 6)])
    df = seri_cek(tim_seri(), session=oturum, bugun=date(2021, 6, 15))
    assert list(df.columns) == ["date", "value"]
    assert len(df) == 36  # üç yıl × 12 ay
    assert df["date"].is_monotonic_increasing
    assert df["value"].iloc[0] == 300.0
    assert len(yillar) == 3


def test_seri_cek_onbellek_ayni_dosyayi_yeniden_indirmez():
    """13 seri aynı sekiz dosyayı paylaşır; önbelleksiz 104 indirme olurdu."""
    oturum = _oturum([(2019, 12), (2020, 6)])
    onbellek: dict = {}
    seri_cek(tim_seri(), onbellek=onbellek, session=oturum, bugun=date(2020, 6, 1))
    ilk_cagri = len(oturum.cagrilar)
    seri_cek(
        tim_seri(id="ihracat/madencilik", tim_sektor="Madencilik Ürünleri"),
        onbellek=onbellek, session=oturum, bugun=date(2020, 6, 1),
    )
    assert len(oturum.cagrilar) == ilk_cagri


def test_seri_cek_eski_adi_da_toplar():
    """2019'da 'Elektrik Elektronik', 2026'da 'Elektrik ve Elektronik'."""
    eski_satirlar = [
        (".I. TARIM", [100.0] * 12),
        (".II. SANAYİ", [800.0] * 12),
        (" Elektrik Elektronik", [120.0] * 12),
        (".III. MADENCİLİK", [50.0] * 12),
        *[(f" Dolgu {i}", [1.0] * 12) for i in range(26)],
        (".                         TOPLAM", [950.0] * 12),
    ]
    oturum = SahteOturum({
        bulten_url(2019, 12): SahteYanit(
            200, bulten_baytlari(yil=2019, satirlar=eski_satirlar)
        ),
        bulten_url(2020, 3): SahteYanit(200, bulten_baytlari(yil=2020)),
    })
    seri = tim_seri(
        id="ihracat/elektrik-elektronik",
        tim_sektor="Elektrik ve Elektronik",
        tim_eski_adlar=("Elektrik Elektronik",),
    )
    df = seri_cek(seri, session=oturum, bugun=date(2020, 3, 1))
    assert len(df) == 24
    assert df["value"].iloc[0] == 120.0


def test_seri_cek_sektor_bulunamazsa_hata():
    """Kısmi kayıp sessiz geçmemeli: bülten başına kontrol edilir."""
    oturum = _oturum([(2019, 12)])
    seri = tim_seri(id="ihracat/celik", tim_sektor="Çelik")
    with pytest.raises(RuntimeError, match="sektör bulunamadı"):
        seri_cek(seri, session=oturum, bugun=date(2019, 12, 31))


def test_seri_cek_yayimlanmamis_cari_ayi_geriye_dogru_dener():
    """1 Ocak'ta cari yıl dosyası yoktur; geçen yıl serisi kesilmemeli."""
    oturum = SahteOturum({
        bulten_url(2019, 12): SahteYanit(200, bulten_baytlari(yil=2019)),
        bulten_url(2020, 12): SahteYanit(200, bulten_baytlari(yil=2020)),
    })
    df = seri_cek(tim_seri(), session=oturum, bugun=date(2021, 1, 3))
    assert len(df) == 24  # 2021 dosyası hiç yok, 2019 + 2020 duruyor
    assert bulten_url(2021, 1) in oturum.cagrilar


def test_seri_cek_start_date_oncesini_kirpar():
    oturum = _oturum([(2019, 12), (2020, 6)])
    seri = tim_seri(start_date="2020-01-01")
    df = seri_cek(seri, session=oturum, bugun=date(2020, 6, 1))
    assert df["date"].min() == "2020-01-01"
    assert len(df) == 12


def test_seri_cek_http_hatasi_yukselir():
    """404 "henüz yok" demek; 500 sessizce yutulmamalı."""
    oturum = SahteOturum({bulten_url(2019, 12): SahteYanit(500)})
    with pytest.raises(RuntimeError, match="HTTP 500"):
        seri_cek(tim_seri(), session=oturum, bugun=date(2019, 12, 31))
