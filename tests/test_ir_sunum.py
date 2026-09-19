"""Şirket IR PDF/HTML kaynaklarının ortak yardımcıları (`ingest.ir_sunum`)
testleri."""

import pytest

from ingest.ir_sunum import donem_tarihi, pdf_ayikla, pdf_metnini_normallestir, tr_sayi


# --- pdf_ayikla: Java byte[] serileştirme sarmalayıcısını çözme ---


def test_pdf_ayikla_java_sarmalayiciyi_soyar():
    gercek_pdf = b"%PDF-1.7\n1 0 obj\n%%EOF"
    sarmali = b"\xac\xed\x00\x05ur\x00\x02[B\xac\xf3\x17\xf8\x06\x08T\xe0\x02\x00\x00" + gercek_pdf
    assert pdf_ayikla(sarmali) == gercek_pdf


def test_pdf_ayikla_sarmalayici_yoksa_degistirmez():
    ham = b"%PDF-1.7\nnormal content"
    assert pdf_ayikla(ham) == ham


# --- tr_sayi: Türkçe biçimli sayı ayrıştırma ---


def test_tr_sayi_binlik_ayiraci_ve_ondalik_virgul():
    assert tr_sayi("1.234.567,89") == 1234567.89


def test_tr_sayi_parantezli_negatif():
    assert tr_sayi("(32.229.759)") == -32229759.0


def test_tr_sayi_yuzde_isaretli_negatif_parantez():
    assert tr_sayi("(%2,8)") == -2.8


def test_tr_sayi_bos_deger_hata_verir():
    with pytest.raises(ValueError, match="boş sayı alanı"):
        tr_sayi("-")


def test_tr_sayi_bos_string_hata_verir():
    with pytest.raises(ValueError, match="boş sayı alanı"):
        tr_sayi("")


# --- pdf_metnini_normallestir: tipografik kesme işareti ---


def test_pdf_metnini_normallestir_curly_apostrofu_duzelt():
    """Ölçülen gerçek anomali: BigChefs 'Şirket Profili' paragrafı U+2019 kullanıyor."""
    metin = "Türkiye\u2019de 30 şehirde"
    assert pdf_metnini_normallestir(metin) == "Türkiye'de 30 şehirde"


# --- donem_tarihi: çeyreklik başlık -> çeyreğin ilk ayına damgalı tarih ---


def test_donem_tarihi_tek_ceyrek():
    assert donem_tarihi("1Ç 2026 Finansal ve Operasyonel Özet") == "2026-01-01"


def test_donem_tarihi_dokuz_ay_kumulatif_ucuncu_ceyrege_damgalanir():
    assert donem_tarihi("9A 2025 9A 2024 Değişim Değişim") == "2025-07-01"


def test_donem_tarihi_tam_yil_dorduncu_ceyrege_damgalanir():
    assert donem_tarihi("FY 2025 FY 2024 Yıllık Rakamsal Değişim") == "2025-10-01"


def test_donem_tarihi_tanimadigi_baslikta_hata_verir():
    with pytest.raises(RuntimeError, match="Dönem başlığı tanınamadı"):
        donem_tarihi("ilgisiz başlık metni")
