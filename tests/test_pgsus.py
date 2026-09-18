"""Pegasus aylık trafik bülteni istemcisi testleri.

Bülten baytları testte openpyxl ile üretilir: gerçek dosyanın aynı şablonu
(satır 2 yıl, satır 3 ay başlığı + A3='AYLIK', satır 4-21 üç segment × altı
ölçüt; segment etiketi yalnızca segmentin ilk satırında yazılı).
"""

import io
from types import SimpleNamespace

import openpyxl
import pytest

from ingest.pgsus import UC, seri_cek, trafik_noktalari

SEGMENTLER = ["Toplam", "İç Hat", "Dış Hat"]
OLCUT_SIRASI = [
    "Misafir sayısı, mn", "Konma", "Koltuk sayısı, mn",
    "Doluluk Oranı", "ASK (mln km)", "Konma başına Misafir",
]


def _tam_govde(yillar_aylar=(("2019 Ocak", 2019, "Ocak"), ("2019 Şubat", 2019, "Şubat"))):
    """18 satırlık (3 segment × 6 ölçüt) geçerli AYLIK bloğu üretir.

    Her hücreye satır×sütun indeksinden türeyen ayırt edici bir değer
    yazılır (`100*satir_no + sutun_no`), böylece testler yanlış
    satır/sütuna gitmiş değeri de yakalayabilir.
    """
    satir1 = (None,) * 8
    satir2 = (None, None, *(yil for _, yil, _ in yillar_aylar))
    satir3 = ("AYLIK", None, *(ay for _, _, ay in yillar_aylar))
    veri = []
    satir_no = 4
    for seg in SEGMENTLER:
        for j, olcut in enumerate(OLCUT_SIRASI):
            a = seg if j == 0 else None
            degerler = [100.0 * satir_no + k for k in range(len(yillar_aylar))]
            veri.append((a, olcut, *degerler))
            satir_no += 1
    return [satir1, satir2, satir3, *veri]


def _kitap_baytlari(satirlar, sayfa_adi="TRAFİK", ekle_kitap_dolgusu=True):
    kitap = openpyxl.Workbook()
    if ekle_kitap_dolgusu:
        kitap.active.title = "Cover"
    else:
        kitap.remove(kitap.active)
    sayfa = kitap.create_sheet(sayfa_adi)
    for satir in satirlar:
        sayfa.append(list(satir))
    tampon = io.BytesIO()
    kitap.save(tampon)
    return tampon.getvalue()


def _degistir(govde, satir_no, sutun_no, deger):
    """1-indeksli (satır, sütun) hücreyi değiştirip yeni gövdeyi döner."""
    yeni = [list(s) for s in govde]
    yeni[satir_no - 1][sutun_no - 1] = deger
    return [tuple(s) for s in yeni]


def pgsus_seri(**kwargs):
    varsayilan = dict(
        id="havacilik/pgsus-toplam-misafir",
        kaynak_tipi="pgsus",
        pgsus_segment="Toplam",
        pgsus_olcut="misafir",
        start_date=None,
    )
    varsayilan.update(kwargs)
    return SimpleNamespace(**varsayilan)


class SahteYanit:
    def __init__(self, content, status_code=200):
        self.content = content
        self.status_code = status_code


class SahteOturum:
    def __init__(self, yanit):
        self.yanit = yanit
        self.calls = 0

    def get(self, url, headers=None, timeout=None):
        self.calls += 1
        assert url == UC
        assert headers["User-Agent"] == "Mozilla/5.0"
        return self.yanit


# --- trafik_noktalari: yapı çıkarma ---


def test_trafik_noktalari_segment_etiketi_ilk_satirdan_miras_alinir():
    """A sütunu yalnızca segmentin ilk satırında yazılı; sonraki beş satır
    (Konma, Koltuk, Doluluk, ASK, Konma başına Misafir) da aynı segmente
    bağlanmalı."""
    noktalar = trafik_noktalari(_kitap_baytlari(_tam_govde()))
    # "Toplam" satır 4'te yazılı; "Konma" satır 5'te boş A sütunuyla geliyor.
    assert ("Toplam", "konma") in noktalar
    assert noktalar[("Toplam", "konma")]["2019-01-01"] == 100.0 * 5 + 0
    # İç Hat segmenti satır 10'da başlıyor; satır 15'teki ölçüt de ona bağlı.
    assert ("İç Hat", "konma-basina-misafir") in noktalar
    assert noktalar[("İç Hat", "konma-basina-misafir")]["2019-01-01"] == 100.0 * 15 + 0


def test_trafik_noktalari_tarih_izgarasini_dogru_cevirir():
    noktalar = trafik_noktalari(_kitap_baytlari(_tam_govde()))
    toplam_misafir = noktalar[("Toplam", "misafir")]
    assert toplam_misafir == {"2019-01-01": 400.0, "2019-02-01": 401.0}


def test_trafik_noktalari_bos_hucre_sifir_uydurmaz():
    """Yayımlanmamış ay boş hücre olarak gelir; sıfır yazılmamalı, atlanmalı."""
    govde = _degistir(_tam_govde(), 4, 4, None)  # Toplam/misafir Şubat -> boş
    noktalar = trafik_noktalari(_kitap_baytlari(govde))
    toplam_misafir = noktalar[("Toplam", "misafir")]
    assert toplam_misafir == {"2019-01-01": 400.0}
    assert "2019-02-01" not in toplam_misafir


def test_trafik_noktalari_bilinmeyen_segmentte_hata():
    govde = _degistir(_tam_govde(), 4, 1, "Bilinmeyen Segment")
    with pytest.raises(RuntimeError, match="segment"):
        trafik_noktalari(_kitap_baytlari(govde))


def test_trafik_noktalari_bilinmeyen_olcutte_hata():
    govde = _degistir(_tam_govde(), 5, 2, "Bilinmeyen Ölçüt")
    with pytest.raises(RuntimeError, match="ölçüt"):
        trafik_noktalari(_kitap_baytlari(govde))


def test_trafik_noktalari_ay_adi_bozuksa_hata():
    """Şablon kayması: ay adı satırı bozuksa (ör. 'Ocakk') sessizce geçmemeli."""
    govde = _degistir(_tam_govde(), 3, 3, "Ocakk")
    with pytest.raises(RuntimeError, match="ay adı"):
        trafik_noktalari(_kitap_baytlari(govde))


def test_trafik_noktalari_ay_sirasi_bozuksa_hata():
    """Aynı (yıl, ay) çifti tekrar ederse ya da geriye giderse şablon kaymış demektir."""
    govde = _degistir(_tam_govde(), 3, 4, "Ocak")  # Şubat yerine tekrar Ocak
    with pytest.raises(RuntimeError, match="sırası bozuk"):
        trafik_noktalari(_kitap_baytlari(govde))


def test_trafik_noktalari_a3_aylik_degilse_hata():
    govde = _degistir(_tam_govde(), 3, 1, "BAŞKA")
    with pytest.raises(RuntimeError, match="AYLIK"):
        trafik_noktalari(_kitap_baytlari(govde))


def test_trafik_noktalari_eksik_satirda_hata():
    """18 satırdan biri kaybolursa (şablon kayması) sessizce eksik veri üretilmemeli."""
    govde = _tam_govde()
    govde = govde[:-1]  # son ölçüt satırını (Dış Hat/Konma başına Misafir) at
    with pytest.raises(RuntimeError, match="eksik segment/ölçüt"):
        trafik_noktalari(_kitap_baytlari(govde))


def test_trafik_noktalari_sayfa_yoksa_hata():
    with pytest.raises(RuntimeError, match="TRAFİK"):
        trafik_noktalari(_kitap_baytlari(_tam_govde(), sayfa_adi="BAŞKA SAYFA"))


# --- seri_cek: ağ kabuğu ---


def test_seri_cek_dogru_deger_dondurur():
    yanit = SahteYanit(_kitap_baytlari(_tam_govde()))
    oturum = SahteOturum(yanit)
    df = seri_cek(pgsus_seri(pgsus_segment="İç Hat", pgsus_olcut="doluluk"), onbellek={}, session=oturum)
    assert list(df["date"]) == ["2019-01-01", "2019-02-01"]
    assert df["value"].iloc[0] == 100.0 * 13 + 0  # İç Hat/Doluluk satır 13


def test_seri_cek_onbellegi_paylasir():
    """18 seri aynı tek dosyayı paylaşır; ikinci seri hiç indirmemeli."""
    yanit = SahteYanit(_kitap_baytlari(_tam_govde()))
    oturum = SahteOturum(yanit)
    onbellek = {}
    seri_cek(pgsus_seri(pgsus_segment="Toplam", pgsus_olcut="misafir"), onbellek=onbellek, session=oturum)
    seri_cek(pgsus_seri(pgsus_segment="Dış Hat", pgsus_olcut="ask"), onbellek=onbellek, session=oturum)
    assert oturum.calls == 1


def test_seri_cek_start_date_oncesini_kirpar():
    yanit = SahteYanit(_kitap_baytlari(_tam_govde()))
    oturum = SahteOturum(yanit)
    df = seri_cek(pgsus_seri(start_date="2019-02-01"), onbellek={}, session=oturum)
    assert list(df["date"]) == ["2019-02-01"]


def test_seri_cek_http_hatasi_yukselir():
    oturum = SahteOturum(SahteYanit(b"", status_code=404))
    with pytest.raises(RuntimeError, match="HTTP 404"):
        seri_cek(pgsus_seri(), onbellek={}, session=oturum)


def test_seri_cek_bilinmeyen_kombinasyonda_hata():
    """Katalog geçerli segment/ölçüt kümesini zaten doğruluyor; burada
    savunma amaçlı ikinci kontrol — bültende gerçekte olmayan bir
    kombinasyon istenirse sessizce boş df dönmemeli."""
    onbellek = {"noktalar": {("Toplam", "misafir"): {"2019-01-01": 1.0}}}
    with pytest.raises(RuntimeError, match="bulunamadı"):
        seri_cek(pgsus_seri(pgsus_segment="Dış Hat", pgsus_olcut="konma"), onbellek=onbellek)
