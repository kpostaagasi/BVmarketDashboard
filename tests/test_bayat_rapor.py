import dataclasses
from datetime import date

from core.catalog import seri_listele
from core.takvim import satir_uret
from ingest.bayat_rapor import rapor_uret


def test_rapor_sorunsuzken_esik_icinde_der():
    seri = seri_listele()[0]
    satir = satir_uret(seri, date(2026, 10, 2), date(2026, 10, 2))
    metin = rapor_uret([satir])
    assert "0 / 1" in metin
    assert "Tüm seriler eşik içinde" in metin


def test_rapor_gecikmis_seriyi_kaynak_tipiyle_listeler():
    seri = seri_listele()[0]
    satir = satir_uret(seri, date(2020, 1, 1), date(2026, 10, 2))
    metin = rapor_uret([satir])
    assert "1 / 1 seri sorunlu" in metin
    assert seri.id in metin
    assert seri.kaynak_tipi in metin


def test_rapor_verisi_olmayan_seriyi_sorunlu_sayar():
    seri = seri_listele()[0]
    satir = satir_uret(seri, None, date(2026, 10, 2))
    assert "veri yok 1" in rapor_uret([satir])


def test_rapor_notlu_ve_notsuz_gecikmeyi_ayirir():
    seri = seri_listele()[0]
    notlu = dataclasses.replace(seri, yayin_notu="Eurostat TR 2025-12'de duruyor")
    notsuz = dataclasses.replace(
        seri, id="ornek/notsuz", title="Notsuz seri", yayin_notu=None
    )
    metin = rapor_uret([
        satir_uret(notlu, date(2020, 1, 1), date(2026, 10, 2)),
        satir_uret(notsuz, date(2020, 1, 1), date(2026, 10, 2)),
    ])
    assert "Notu olan (kaynak geride): 1" in metin
    assert "Notu olmayan (bakılacak): 1" in metin
    assert "Eurostat TR 2025-12'de duruyor" in metin
    assert "ornek/notsuz" in metin
