"""Katalog: serilerin ve kategorilerin tek doğruluk kaynağı.

Metadata burada yaşar; veri dosyaları yalnızca `date,value` içerir.
"""

from __future__ import annotations

import re

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

KOK = Path(__file__).resolve().parent.parent
KATALOG_DIZINI = KOK / "catalog"

GECERLI_FREKANSLAR = {"daily", "weekly", "monthly", "quarterly", "yearly"}
GECERLI_EVDS_FREKANSLARI = {"1", "2", "5", "6"}  # günlük, haftalık, aylık, çeyreklik (bkz. ingest/evds.py docstring)
GECERLI_GRAFIKLER = {"seasonality", "daily_seasonality", "level", "composition", "fon"}
GECERLI_AYLIK_AGG = {"mean", "last", "sum"}
GECERLI_KAYNAK_TIPLERI = {
    "evds", "yahoo", "epias", "osd", "tim", "tim_il", "tim_ulke", "tim_ulke_grubu", "bddk",
    "bddk_haftalik", "bddk_bdmk",
    "tefas", "eurocontrol", "fred", "tefas_fon", "pgsus", "thy",
    "tav", "ebebek",
    "epdk", "epdk_dogalgaz",
    "turkcell", "ttkom",
    "odmd",
    "eib", "usk", "turkbesd",
    "tsb", "tspb",
    "eurostat",
    "ecb", "turkcimento",
    "worldbank", "ifo",
    "istib", "tuik_kanatli", "botas", "epdk_fiyat",
    "sgk", "ayd", "gph", "orge", "tcud",
    "dhmi", "uab", "ktb", "eurostat_turizm",
    "iso_pmi", "tim_pazar_monitoru",
    "bigchefs", "turktraktor", "migros",
    "tepav", "tmsd", "ithib",
}
SIKLIK_ETIKETLERI = {
    "daily": "GÜNLÜK", "weekly": "HAFTALIK", "monthly": "AYLIK",
    "quarterly": "ÇEYREKLİK", "yearly": "YILLIK",
}
# TEFAS'ın iki ekseni katalogda doğrulanır (core, ingest'i import etmez):
# fon tipi ve hangi toplulaştırmanın istendiği.
GECERLI_TEFAS_TIPLERI = {"YAT", "EMK"}
GECERLI_TEFAS_OLCUTLERI = {"buyukluk", "hesap", "fon-sayisi", "ortalama-buyukluk"}
# EUROCONTROL'ün üç dosyası: ülke, hava yolu, havalimanı.
GECERLI_EC_KAYNAKLARI = {"ulke", "havayolu", "havalimani"}
# Pegasus trafik bülteninin iki ekseni: yolcu segmenti ve ölçüt.
GECERLI_PGSUS_SEGMENTLERI = {"Toplam", "İç Hat", "Dış Hat"}
GECERLI_PGSUS_OLCUTLERI = {
    "misafir", "konma", "koltuk", "doluluk", "ask", "konma-basina-misafir",
}
# THY trafik bülteninin iki ekseni: yolcu segmenti ve ölçüt.
GECERLI_THY_SEGMENTLERI = {"Toplam", "Yurt İçi", "Yurt Dışı"}
GECERLI_THY_OLCUTLERI = {"konma", "ask", "doluluk", "yolcu", "kargo"}
# TAV Havalimanları trafik bülteninin üç ekseni: havalimanı (ya da TAV
# TOPLAM), yolcu segmenti ve hangi ölçütün (yolcu sayısı mı uçuş sayısı mı)
# okunacağı. Bkz. ingest/tav.py docstring'i.
GECERLI_TAV_SEGMENTLERI = {"toplam", "dis-hat", "ic-hat"}
GECERLI_TAV_OLCUTLERI = {"yolcu", "ucus"}
# ebebek Mağazacılık'ın aylık KAP Özel Durum Açıklamalarından çekilen altı
# operasyonel ölçüt. Bkz. ingest/ebebek.py docstring'i.
GECERLI_EBEBEK_METRIKLERI = {
    "satis_adedi", "magaza_ziyaretci", "web_ziyaret",
    "toplam_magaza", "standart_magaza", "mega_magaza",
}
# EPDK petrol piyasası aylık sektör raporunun iki ekseni: ölçüt (üretim/
# satış/dış ticaret yönü) ve ürün grubu. Bkz. ingest/epdk.py docstring'i.
GECERLI_EPDK_OLCUTLERI = {"rafineri-uretimi", "yurtici-satis", "ithalat", "ihracat"}
GECERLI_EPDK_URUNLERI = {"benzin", "motorin", "fuel-oil", "havacilik", "denizcilik"}
# EPİAŞ Şeffaflık baraj doluluk servisinin (dams-data/active-fullness) canlı
# döndürdüğü 17 havza (bkz. GET /v1/dams/data/basin-list, ölçüldü 2026-09-18).
# Bu uç tarih parametresini yok sayar — her zaman bugünün anlık görüntüsünü
# döner, geriye dönük veri yoktur (bkz. ingest/epias.py baraj_doluluk_cek).
GECERLI_EPIAS_HAVZALARI = {
    "Doğu Akdeniz", "Ceyhan", "Batı Karadeniz", "Antalya", "Van Gölü",
    "Seyhan", "Marmara", "Batı Akdeniz", "Yeşilırmak", "Asi", "Susurluk",
    "Kuzey Ege", "Doğu Karadeniz", "Sakarya", "Kızılırmak", "Büyük Menderes",
    "Gediz",
}
# Turkcell Yatırımcı İlişkileri'nin çeyreklik "Financial and Operational
# Data" Excel'inden çekilen 27 operasyonel/finansal ölçüt. Bkz.
# ingest/turkcell.py docstring'i.
GECERLI_TURKCELL_METRIKLERI = {
    "mobil-postpaid-abone", "fiber-abone", "superbox-abone",
    "mobil-prepaid-abone", "mobil-m2m-abone", "iptv-abone",
    "resell-sabit-genisbant-abone", "mobil-churn", "sabit-churn",
    "mobil-arpu-m2m-haric", "residential-fiber-arpu", "mobil-arpu-blended",
    "postpaid-arpu-m2m-haric", "prepaid-arpu",
    "turkiye-segment-geliri", "techfin-segment-geliri",
    "turkiye-segment-favok", "techfin-segment-favok",
    "tuketici-geliri", "kurumsal-geliri", "toptan-geliri",
    "paycell-geliri", "financell-geliri",
    "kktc-geliri", "kktc-abone", "best-geliri", "best-abone",
}
# Türk Telekom Yatırımcı İlişkileri'nin çeyreklik "Özet Finansal ve
# Operasyonel Veriler" Excel'inden çekilen 6 ölçüt. Bkz. ingest/ttkom.py
# docstring'i.
GECERLI_TTKOM_METRIKLERI = {
    "mobil-toplam-abone", "sabit-genisbant-abone", "tv-abone", "sabit-ses-abone",
    "sabit-genisbant-arpu-buyume", "mobil-karma-arpu-buyume",
    "mobil-faturali-abone-payi", "sabit-genisbant-fiber-abone-payi",
}
# ODMD (Otomotiv Distribütörleri ve Mobilite Derneği) aylık marka bazında
# perakende satış dosyasının okunan üç sütunu. Bkz. ingest/odmd.py.
GECERLI_ODMD_KATEGORILERI = {"otomobil", "hafif_ticari", "toplam"}
# OSD kaynağının hangi belgeden okunacağı: "uretim" (Aylık Üretim Bülteni,
# varsayılan) ya da "ihracat" (Aylık Değerlendirme Raporu'nun "Dış
# Satışlar" bölümü). Bkz. ingest/osd.py.
GECERLI_OSD_VERI_TIPLERI = {"uretim", "ihracat"}
# EİB (Ege İhracatçı Birlikleri) ESÜHMİB aylık ihracat istatistiğinin iki
# ekseni: kalem (ürün grubu/alt grup ya da hesaplanan toplam) ve ölçüt
# (dolar değeri ya da ton hacmi). Bkz. ingest/eib.py docstring'i.
GECERLI_EIB_KALEMLERI = {
    "SU ÜRÜNLERİ", "LEVREK", "ÇİPURA", "TÜRK SOMONU", "ALABALIK",
    "KAYA LEVREĞİ", "DİĞER SU ÜRÜNLERİ",
    "HAYVANSAL_TOPLAM", "KANATLI", "YUMURTA", "SÜT VE SÜT ÜRÜNLERİ",
    "SOSİS VE BENZERİ ÜRÜNLER (KIRMIZI ET VE KANATLI)", "BAL", "DİĞER",
    "CANLI HAYVAN", "KIRMIZI ET VE SAKATAT",
}
GECERLI_EIB_OLCUTLERI = {"fobusd", "agirlik"}
# USK (Ulusal Süt Konseyi) çiğ süt tavsiye fiyatı + üretim maliyeti
# hesabının kalemleri (maliyet PDF'inin granüler alanları yalnızca yeni
# formatta var). Bkz. ingest/usk.py docstring'i.
GECERLI_USK_KALEMLERI = {
    "tavsiye-fiyati", "uretim-maliyeti", "canli-agirlik", "sut-verimi",
    "buzagi-fiyati", "karma-yem-fiyati", "misir-silaji-fiyati",
    "yonca-fiyati", "saman-fiyati", "yem-maliyeti-toplam", "diger-giderler",
    "buzagi-geliri", "net-maliyet-baz",
}
# TÜRKBESD (Türkiye Beyaz Eşya Sanayicileri Derneği) yıllık ürün kırılımının
# iki ekseni: ölçüt (iç satış/üretim/ihracat/ithalat) ve ürün (6 ana beyaz
# eşya kalemi). Bkz. ingest/turkbesd.py docstring'i.
GECERLI_TURKBESD_OLCUTLERI = {"ic-satis", "uretim", "ihracat", "ithalat"}
GECERLI_TURKBESD_URUNLERI = {
    "buzdolabi", "derin-dondurucu", "camasir-makinesi", "bulasik-makinesi",
    "firin", "kurutucu",
}
# Dünya Bankası "Pink Sheet" emtia fiyat verisinde okunan dört seri
# (ingest/worldbank.py::SERI_TANIMLARI ile birebir).
GECERLI_WB_SERILERI = {"gubre-endeksi", "urea", "dap", "kaucuk-tsr20"}
# ifo Institute "ifo Business Climate Germany" Excel'inde okunan üç endeks
# (ingest/ifo.py::SERI_ETIKETLERI ile birebir).
GECERLI_IFO_SERILERI = {"iklim", "durum", "beklenti"}
# EPDK doğal gaz piyasası aylık sektör raporunun tek ekseni: 9 ölçüt
# (dağıtım/toptan/ithalat/depolama kırılımı). Bkz. ingest/epdk.py
# docstring'i (doğal gaz bölümü).
GECERLI_EPDK_DOGALGAZ_OLCUTLERI = {
    "ahgaz-tuketim", "ahgaz-abone", "ahgaz-serbest",
    "ntgaz-hacim", "aygaz-hacim",
    "botas-ithalat", "ozel-ithalatci-ithalat",
    "depolama-borugazi", "depolama-lng",
}
# Eurostat elektrik fiyatı istatistiğinin (nrg_pc_204 hane, nrg_pc_205
# sanayi) iki ekseni: coğrafya ve para birimi. `tax`/`nrg_cons` katalogda
# EKSEN DEĞİL — tüm serilerde sabit (I_TAX, TOT_KWH), bkz. ingest/eurostat.py.
GECERLI_EUROSTAT_DATASETLERI = {"nrg_pc_204", "nrg_pc_205"}
GECERLI_EUROSTAT_GEO = {"TR", "EU27_2020"}
GECERLI_EUROSTAT_PARA_BIRIMLERI = {"EUR", "NAC"}
# TürkÇimento aylık bölgesel istatistik dosyasından (`.xls`, yıl başına bir
# dosya) okunan sekiz ÇİMENTO/KLİNKER ölçütü. Bkz. ingest/turkcimento.py
# docstring'i (METRIK_ESLEME ile birebir).
GECERLI_TURKCIMENTO_METRIKLERI = {
    "cimento-uretim", "cimento-ic-satis", "cimento-ihracat",
    "cimento-toplam-satis", "cimento-stok",
    "klinker-uretim", "klinker-ihracat", "klinker-stok",
}
# Finansal Kiralama, Faktoring ve Finansman Şirketleri portalının (BultenAylikBdmk)
# iki ürünü: Faktoring ve Finansal Kiralama sektör bültenleri. Bkz.
# ingest/bddk.py::seri_cek_bdmk docstring'i.
GECERLI_BDDK_BDMK_URUNLERI = {"faktoring", "finansal_kiralama"}
# İTB (İstanbul Ticaret Borsası) haftalık tescil bülteninden okunan dört
# kanatlı eti ürünü. Bkz. ingest/istib.py docstring'i.
GECERLI_ISTIB_URUNLERI = {
    "piliç-eti-kemiksiz", "hindi-eti-kemikli", "hindi-eti-kemiksiz", "piliç-kanat",
}
# TÜİK'in Eurostat apro_mt_pwgtm aynasından okunan üç kümes hayvancılığı
# üretim ölçütü. Bkz. ingest/tuik.py docstring'i.
GECERLI_TUIK_KANATLI_OLCUTLERI = {"toplam-uretim", "tavuk-uretim", "kesilen-tavuk"}
# BOTAŞ güncel doğal gaz toptan satış tarifesinin beş tüketici kategorisi.
# Bkz. ingest/botas.py docstring'i.
GECERLI_BOTAS_KATEGORILERI = {
    "konut", "sehit-ailesi", "ekmek-ureticileri",
    "elektrik-uretimi-amacli", "elektrik-uretimi-disi",
}
# EPDK "Petrol ve LPG Piyasası Fiyatlandırma Raporu"nun iki ekseni: ürün ve
# fiyat bileşeni kalemi. Bkz. ingest/epdk.py docstring'i (fiyatlandırma
# bölümü) — mevcut `epdk_urun`/`epdk_olcut` (Sektör Raporu, üretim/satış
# hacmi) ile KARIŞTIRILMAMALI, ayrı bir rapor/ayrı bir kaynak_tipi'dir.
GECERLI_EPDK_FIYAT_URUNLERI = {"motorin", "benzin"}
GECERLI_EPDK_FIYAT_KALEMLERI = {
    "urun-fiyati", "toptanci-marji", "dagitici-bayi-marji",
    "toplam-vergi", "nihai-satis-fiyati",
}
# TSPB (Türkiye Sermaye Piyasaları Birliği) "Veriler" sayfasının iki
# dosyası: "PYŞ Aylık" (portföy yönetim şirketleri AUM/müşteri-fon
# sayısı/gelir, 4 kategori kırılımlı) ve "Krediler" (kredili işlem, tek
# eksenli 4 ölçüt). Bkz. ingest/tspb.py docstring'i.
GECERLI_TSPB_TABLOLAR = {
    "musteri-fon-sayisi", "portfoy-buyuklugu", "portfoy-yonetimi-geliri", "kredili",
}
GECERLI_TSPB_PYS_KATEGORILERI = {
    "bireysel", "yatirim-ortakligi", "emeklilik-yatirim-fonu", "yatirim-fonu", "toplam",
}
GECERLI_TSPB_KREDILI_KATEGORILERI = {
    "araci-kurum-sayisi", "sozlesmeli-yatirimci-sayisi", "kullanan-yatirimci-sayisi",
    "kredi-hacmi",
}
# TEPAV Gıda Fiyat Endeksi (TEGE) aylık bültenlerinden çekilen üç seri.
# Bkz. ingest/tepav.py docstring'i.
GECERLI_TEPAV_SERILERI = {"tege-aylik", "tege-yillik", "kktc-tege-aylik"}
# SGK (Sosyal Güvenlik Kurumu) Aylık Sağlık İstatistik Bülteni'nin tek
# ekseni: Tablo 21 (hastane müracaat/fatura, özel/toplam) ve Tablo 23
# (eczane reçete/fatura) kalemleri. Bkz. ingest/sgk.py docstring'i.
GECERLI_SGK_METRIKLERI = {
    "hastane-ozel-muracaat", "hastane-ozel-fatura",
    "hastane-toplam-muracaat", "hastane-toplam-fatura",
    "eczane-recete-sayisi", "eczane-fatura-tutari",
}
# GPH (Global Ports Holding) aylık trafik istatistiği XLSX'inin tek ekseni.
# Bkz. ingest/gph.py docstring'i.
GECERLI_GPH_METRIKLERI = {"yolcu-konsolide", "sefer-konsolide", "yolcu-konsolide-edilmeyen"}
# ORGE Enerji çeyreklik yatırımcı sunumu PDF'inin tek ekseni. Bkz.
# ingest/orge.py docstring'i.
GECERLI_ORGE_METRIKLERI = {"backlog", "yeni-is-ytd"}
# DHMİ (Devlet Hava Meydanları İşletmesi) "Havalimanları Karşılaştırmalı
# İstatistikleri" bülteninin tek ekseni: hangi ölçüt (yolcu toplam/dış hat,
# kargo, uçak toplam/ticari) okunacağı — hepsi aynı 6 büyük havalimanının
# (İstanbul, Sabiha Gökçen, Ankara Esenboğa, İzmir Adnan Menderes, Antalya,
# Muğla Dalaman) toplamıdır. Bkz. ingest/dhmi.py docstring'i.
GECERLI_DHMI_OLCUTLERI = {
    "yolcu-toplam", "yolcu-dis-hat", "kargo-toplam", "ucak-toplam", "ucak-ticari",
}
# UAB (Ulaştırma ve Altyapı Bakanlığı) "Liman Başkanlıkları Bazında Yük
# Elleçleme" bülteninin tek ekseni: ulusal toplam ya da 9 seçili liman
# başkanlığından biri. Bkz. ingest/uab.py docstring'i.
GECERLI_UAB_LIMANLARI = {
    "toplam", "aliaga", "trabzon", "kocaeli", "ambarli", "izmir",
    "iskenderun", "mersin", "gemlik", "tekirdag",
}
# Eurostat tour_occ_nim (konaklama geceleme) istatistiğinin tek ekseni:
# ikamet ülkesi kırılımı. `ingest/eurostat.py`nin (nrg_pc_204/205, ayrı
# kaynak_tipi: eurostat) eksenleriyle KARIŞTIRILMAMALI. Bkz.
# ingest/eurostat_turizm.py docstring'i.
GECERLI_EUROSTAT_TURIZM_RESID = {"TOTAL", "DOM", "FOR"}

# İSO (İstanbul Sanayi Odası) Türkiye Sektörel PMI raporunun iki ekseni:
# 10 alt sektör (None ise manşet Türkiye İmalat PMI) ve 4 ölçüt. Bkz.
# ingest/iso_pmi.py::SEKTOR_SIRASI/GECERLI_METRIKLER ile birebir.
GECERLI_ISO_PMI_SEKTORLERI = frozenset({
    "Gıda Ürünleri", "Tekstil Ürünleri", "Giyim ve Deri Ürünleri",
    "Ağaç ve Kağıt Ürünleri", "Kimyasal, Plastik ve Kauçuk Ürünler",
    "Metalik Olmayan Mineral Ürünler", "Ana Metal Sanayi",
    "Makine ve Metal Ürünler", "Elektrikli ve Elektronik Ürünler",
    "Kara ve Deniz Taşıtları",
})
GECERLI_ISO_PMI_METRIKLERI = frozenset({
    "pmi", "yeni-siparisler", "yeni-ihracat-siparisleri", "fiyat-farki",
})
# TİM İhracat Pazar Monitörü'nün üç ekseni: endeks (talep/dayanıklılık,
# zorunlu), sektör ve ülke (ikisi de opsiyonel, birlikte kullanılamaz —
# ikisi de boşsa milli endeks). Bkz. ingest/tim.py::PM_SEKTORLER/PM_ULKELER
# ile birebir.
GECERLI_TIM_PM_ENDEKSLERI = frozenset({"talep", "dayaniklilik"})
GECERLI_TIM_PM_SEKTORLERI = frozenset({
    "Çelik", "Çimento, Cam, Ser. Topr. Ür.", "Demir ve Demir Dışı Metaller",
    "Deri ve Deri Mamulleri", "Elektrik ve Elektronik", "Fındık ve Mamulleri",
    "Gemi, Yat ve Hizmetleri", "Halı", "Hazırgiyim ve Konfeksiyon",
    "Hububat, Bakliyat, Yağlı Toh.", "İklimlendirme Sanayi",
    "Kimyevi Maddeler ve Mamulleri", "Kuru Meyve ve Mamulleri",
    "Madencilik Ürünleri", "Makine ve Aksamları", "Meyve Sebze Mamulleri",
    "Mobilya, Kağıt ve Orman Ür.", "Mücevher", "Otomotiv Endüstrisi",
    "Savunma ve Havacılık", "Su Ürünleri ve Hayvancılık",
    "Süs Bitkileri ve Mamulleri", "Tekstil ve Hammaddeleri", "Tütün",
    "Yaş Meyve ve Sebze", "Zeytin ve Zeytinyağı",
})
GECERLI_TIM_PM_ULKELERI = frozenset({
    "ABD", "Almanya", "Belçika", "Çin", "Danimarka", "Finlandiya", "Fransa",
    "Güney Kore", "Hollanda", "İspanya", "İsveç", "İtalya", "Kolombiya",
    "Macaristan", "Meksika", "Polonya", "Portekiz", "Şili", "Tayland",
})

# BigChefs (BIST: BIGCH) Yatırımcı İlişkileri'nin aylık "Şube Sayısı
# Bildirimi" (3 ölçüt) + çeyreklik "Bilgilendirme Notu"ndan (17 ölçüt)
# çekilen 20 metrik. Bkz. ingest/bigchefs.py docstring'i.
GECERLI_BIGCHEFS_METRIKLERI = {
    "sube-sayisi", "sehir-sayisi", "ulke-sayisi", "calisan-sayisi",
    "sistem-geneli-net-satislar", "net-satislar", "brut-kar", "brut-kar-marji",
    "favok", "favok-marji", "net-kar", "net-kar-marji",
    "fis-sayisi", "ziyaretci-sayisi", "nakit", "toplam-borclar",
    "net-nakit-pozisyonu", "geri-alinan-paylar",
    "fis-ortalamasi-bigchefs", "fis-ortalamasi-buselik", "fis-ortalamasi-numnum",
}
# TürkTraktör (BIST: TTRAK) Yatırımcı İlişkileri'nin aylık "OSD'ye
# Bildirilen Üretim ve Satış Adetleri" PDF'inden çekilen üç ölçüt (üretim
# zaten mevcut `osd_firma: TÜRK TRAKTÖR` ile karşılanıyor). Bkz.
# ingest/turktraktor.py docstring'i.
GECERLI_TURKTRAKTOR_METRIKLERI = {"fabrika-satis", "yurtdisi-satis", "toplam-satis"}
# Migros Ticaret A.Ş. (BIST: MGROS) "Ara Dönem Faaliyet Raporu"ndan çekilen
# tek ölçüt (çeyrek sonu mağaza sayısı anlık görüntüsü). Bkz.
# ingest/migros.py docstring'i.
GECERLI_MIGROS_METRIKLERI = {"toplam-magaza-sayisi"}



# Hangi kaynak tipi hangi TİPE ÖZGÜ alanı taşıyabilir. Bir alan burada
# listelenmemişse o kaynak için YASAKTIR: sessizce yok sayılan bir alan
# (ör. yalnızca yahoo'nun onurlandırdığı `yahoo_symbol`) seriyi yanlış
# kaynaktan çektirir ya da fark edilmeden yok sayılır.
# Yeni bir kaynak tipi eklemek, mevcut tiplere ayrı ayrı red kuralı yazmak
# değil, buraya bir satır eklemektir.
KAYNAK_ALANLARI = {
    "evds": {
        "zorunlu": ("evds_code", "evds_frequency"),
        "istege_bagli": ("start_date",),
    },
    "yahoo": {
        # start_date yok: yahoo istemcisi range=15y sabitiyle çalışıyor.
        "zorunlu": ("yahoo_symbol",),
        "istege_bagli": (),
    },
    "epias": {
        "zorunlu": ("epias_ucu",),
        "istege_bagli": ("epias_alani", "epias_bilesenler", "epias_havza", "start_date"),
    },
    "osd": {
        "zorunlu": ("osd_firma",),
        "istege_bagli": (
            "start_date", "osd_eski_adlar", "osd_arac_tipi", "osd_veri_tipi",
        ),
    },
    "tim": {
        "zorunlu": ("tim_sektor",),
        "istege_bagli": ("start_date", "tim_eski_adlar"),
    },
    "tim_il": {
        "zorunlu": ("tim_il", "tim_sektor"),
        "istege_bagli": ("start_date",),
    },
    "tim_ulke": {
        "zorunlu": ("tim_ulke", "tim_sektor"),
        "istege_bagli": ("start_date",),
    },
    "tim_ulke_grubu": {
        "zorunlu": ("tim_ulke_grubu",),
        "istege_bagli": ("start_date",),
    },
    "bddk": {
        "zorunlu": ("bddk_kalem",),
        "istege_bagli": ("bddk_taraf", "bddk_kumulatif", "start_date"),
    },
    "bddk_haftalik": {
        "zorunlu": ("bddk_haftalik_id",),
        "istege_bagli": ("bddk_haftalik_sutun", "bddk_haftalik_taraf", "start_date"),
    },
    "bddk_bdmk": {
        "zorunlu": ("bddk_bdmk_urun", "bddk_bdmk_tablo", "bddk_bdmk_kalem"),
        "istege_bagli": ("bddk_bdmk_kumulatif", "start_date"),
    },
    "tefas": {
        "zorunlu": ("tefas_tip", "tefas_olcut"),
        "istege_bagli": ("start_date",),
    },
    "tefas_fon": {
        "zorunlu": ("tefas_tip", "tefas_kod", "start_date"),
        "istege_bagli": (),
    },
    "eurocontrol": {
        "zorunlu": ("ec_kaynak", "ec_varlik"),
        "istege_bagli": ("start_date",),
    },
    "fred": {
        "zorunlu": ("fred_code",),
        "istege_bagli": ("start_date",),
    },
    "pgsus": {
        "zorunlu": ("pgsus_segment", "pgsus_olcut"),
        "istege_bagli": ("start_date",),
    },
    "thy": {
        "zorunlu": ("thy_segment", "thy_olcut"),
        "istege_bagli": ("start_date",),
    },
    "tav": {
        "zorunlu": ("tav_varlik", "tav_segment"),
        "istege_bagli": ("start_date", "tav_olcut"),
    },
    "ebebek": {
        "zorunlu": ("ebebek_metrik",),
        "istege_bagli": ("start_date",),
    },
    "epdk": {
        "zorunlu": ("epdk_olcut", "epdk_urun"),
        "istege_bagli": ("start_date",),
    },
    "turkcell": {
        "zorunlu": ("turkcell_metrik",),
        "istege_bagli": ("start_date",),
    },
    "ttkom": {
        "zorunlu": ("ttkom_metrik",),
        "istege_bagli": ("start_date",),
    },
    "odmd": {
        "zorunlu": ("odmd_marka", "odmd_kategori"),
        "istege_bagli": ("odmd_yarim_marka", "start_date"),
    },
    "eib": {
        "zorunlu": ("eib_kalem", "eib_olcut"),
        "istege_bagli": ("start_date",),
    },
    "usk": {
        "zorunlu": ("usk_kalem",),
        "istege_bagli": ("start_date",),
    },
    "turkbesd": {
        "zorunlu": ("turkbesd_olcut", "turkbesd_urun"),
        "istege_bagli": ("start_date",),
    },
    "worldbank": {
        "zorunlu": ("wb_seri",),
        "istege_bagli": ("start_date",),
    },
    "ifo": {
        "zorunlu": ("ifo_seri",),
        "istege_bagli": ("start_date",),
    },
    "tsb": {
        "zorunlu": ("tsb_alt_kategori", "tsb_rapor", "tsb_sheet", "tsb_sirket_kodu"),
        "istege_bagli": ("start_date",),
    },
    "epdk_dogalgaz": {
        "zorunlu": ("epdk_dogalgaz_olcut",),
        "istege_bagli": ("start_date",),
    },
    "eurostat": {
        "zorunlu": ("eurostat_dataset", "eurostat_geo", "eurostat_currency"),
        "istege_bagli": ("start_date",),
    },
    "ecb": {
        "zorunlu": ("ecb_akis", "ecb_anahtar"),
        "istege_bagli": ("start_date",),
    },
    "turkcimento": {
        "zorunlu": ("turkcimento_metrik",),
        "istege_bagli": ("start_date",),
    },
    "istib": {
        "zorunlu": ("istib_urun",),
        "istege_bagli": ("start_date",),
    },
    "tuik_kanatli": {
        "zorunlu": ("tuik_kanatli_olcut",),
        "istege_bagli": ("start_date",),
    },
    "botas": {
        "zorunlu": ("botas_kategori",),
        "istege_bagli": (),
    },
    "epdk_fiyat": {
        "zorunlu": ("epdk_fiyat_urun", "epdk_fiyat_kalem"),
        "istege_bagli": ("start_date",),
    },
    "tspb": {
        "zorunlu": ("tspb_tablo", "tspb_kategori"),
        "istege_bagli": ("start_date",),
    },
    "sgk": {
        "zorunlu": ("sgk_metrik",),
        "istege_bagli": (),
    },
    "ayd": {
        "zorunlu": (),
        "istege_bagli": (),
    },
    "gph": {
        "zorunlu": ("gph_metrik",),
        "istege_bagli": (),
    },
    "orge": {
        "zorunlu": ("orge_metrik",),
        "istege_bagli": (),
    },
    "tcud": {
        "zorunlu": ("tcud_kalem",),
        "istege_bagli": ("start_date",),
    },
    "dhmi": {
        "zorunlu": ("dhmi_olcut",),
        "istege_bagli": ("start_date",),
    },
    "uab": {
        "zorunlu": ("uab_liman",),
        "istege_bagli": ("start_date",),
    },
    "ktb": {
        "zorunlu": (),
        "istege_bagli": ("start_date",),
    },
    "eurostat_turizm": {
        "zorunlu": ("eurostat_turizm_resid",),
        "istege_bagli": ("start_date",),
    },
    "iso_pmi": {
        "zorunlu": ("iso_pmi_metrik",),
        "istege_bagli": ("iso_pmi_sektor", "start_date"),
    },
    "tim_pazar_monitoru": {
        "zorunlu": ("tim_pm_endeks",),
        "istege_bagli": ("tim_pm_sektor", "tim_pm_ulke", "start_date"),
    },
    "bigchefs": {
        "zorunlu": ("bigchefs_metrik",),
        "istege_bagli": (),
    },
    "turktraktor": {
        "zorunlu": ("turktraktor_metrik",),
        "istege_bagli": (),
    },
    "migros": {
        "zorunlu": ("migros_metrik",),
        "istege_bagli": (),
    },
    "tepav": {
        "zorunlu": ("tepav_seri",),
        "istege_bagli": ("start_date",),
    },
    "tmsd": {
        "zorunlu": ("tmsd_kalem",),
        "istege_bagli": ("start_date",),
    },
    "ithib": {
        "zorunlu": ("ithib_kalem",),
        "istege_bagli": ("start_date",),
    },
}

# Tipe değil, kataloğa ait alanlar: kaynak tipi ne olursa olsun
# onurlandırılırlar (`olcek` → `ingest.run.olcekle`, `gecikme_gunu` →
# `core.takvim`), dolayısıyla hiçbir tip için yasak değildir. Faz 3f'te
# `olcek` buraya taşındı: EVDS serilerinin bir kısmı "Bin TL"/"Bin USD"
# cinsinden gelir ve ölçeklenmeden KPI kartında okunamaz.
ORTAK_ALANLAR = frozenset({"olcek", "gecikme_gunu"})

TIPE_OZGU_ALANLAR = (
    frozenset(
        alan
        for tanim in KAYNAK_ALANLARI.values()
        for alan in tanim["zorunlu"] + tanim["istege_bagli"]
    )
    - ORTAK_ALANLAR
)


@dataclass(frozen=True)
class Hisse:
    """Bir BIST tickerının sayfası: kendi verisi + bağlam serileri.

    `kendi` şirketin yayımlanan verisi (üretim adedi, uçuş sayısı),
    `baglam` sektör/girdi serileri (sektör ihracatı, kur, hammadde).
    Ayrım sayfada görünür: iki liste iki ayrı başlık altında çizilir.
    """

    kod: str
    title: str
    sektor: str
    kendi: tuple[str, ...]
    baglam: tuple[str, ...] = ()
    note: str | None = None


class KatalogHatasi(Exception):
    """Katalog dosyaları tutarsız ya da eksik."""


@dataclass(frozen=True)
class Kaynak:
    name: str
    url: str


@dataclass(frozen=True)
class Kategori:
    slug: str
    title: str
    note: str | None = None
    pano: tuple[str, ...] = ()


@dataclass(frozen=True)
class Seri:
    id: str
    title: str
    category: str
    kaynak: Kaynak
    kaynak_tipi: str
    unit: str
    freq: str
    charts: tuple[str, ...]
    evds_code: str | None = None
    evds_frequency: str | None = None
    yahoo_symbol: str | None = None
    epias_ucu: str | None = None
    epias_alani: str | tuple[str, ...] | None = None
    epias_bilesenler: dict[str, tuple[str, ...]] | None = None
    epias_havza: str | None = None
    osd_firma: str | None = None
    osd_eski_adlar: tuple[str, ...] | None = None
    osd_arac_tipi: str | None = None
    osd_veri_tipi: str | None = None
    tim_sektor: str | None = None
    tim_eski_adlar: tuple[str, ...] | None = None
    tim_il: str | None = None
    tim_ulke: str | None = None
    tim_ulke_grubu: str | None = None
    monthly_agg: str = "mean"
    start_date: str | None = None
    bddk_kalem: str | None = None
    bddk_taraf: str | None = None
    bddk_kumulatif: bool | None = None
    bddk_haftalik_id: str | None = None
    bddk_haftalik_sutun: int | None = None
    bddk_haftalik_taraf: str | None = None
    bddk_bdmk_urun: str | None = None
    bddk_bdmk_tablo: int | None = None
    bddk_bdmk_kalem: str | None = None
    bddk_bdmk_kumulatif: bool | None = None
    tefas_tip: str | None = None
    tefas_olcut: str | None = None
    tefas_kod: str | None = None
    ec_kaynak: str | None = None
    ec_varlik: str | None = None
    fred_code: str | None = None
    pgsus_segment: str | None = None
    pgsus_olcut: str | None = None
    thy_segment: str | None = None
    thy_olcut: str | None = None
    tav_varlik: str | None = None
    tav_segment: str | None = None
    tav_olcut: str | None = None
    ebebek_metrik: str | None = None
    epdk_olcut: str | None = None
    epdk_urun: str | None = None
    turkcell_metrik: str | None = None
    ttkom_metrik: str | None = None
    odmd_marka: tuple[str, ...] | None = None
    odmd_yarim_marka: tuple[str, ...] | None = None
    odmd_kategori: str | None = None
    eib_kalem: str | None = None
    eib_olcut: str | None = None
    usk_kalem: str | None = None
    turkbesd_olcut: str | None = None
    turkbesd_urun: str | None = None
    wb_seri: str | None = None
    ifo_seri: str | None = None
    tsb_alt_kategori: str | None = None
    tsb_rapor: str | None = None
    tsb_sheet: str | None = None
    tsb_sirket_kodu: int | None = None
    epdk_dogalgaz_olcut: str | None = None
    eurostat_dataset: str | None = None
    eurostat_geo: str | None = None
    eurostat_currency: str | None = None
    ecb_akis: str | None = None
    ecb_anahtar: str | None = None
    turkcimento_metrik: str | None = None
    istib_urun: str | None = None
    tuik_kanatli_olcut: str | None = None
    botas_kategori: str | None = None
    epdk_fiyat_urun: str | None = None
    epdk_fiyat_kalem: str | None = None
    tspb_tablo: str | None = None
    tspb_kategori: str | None = None
    sgk_metrik: str | None = None
    gph_metrik: str | None = None
    orge_metrik: str | None = None
    tcud_kalem: str | None = None
    yayin_notu: str | None = None
    olcek: float | None = None
    gecikme_gunu: int | None = None
    hareketli_ortalama_gun: int | None = None
    dhmi_olcut: str | None = None
    uab_liman: str | None = None
    eurostat_turizm_resid: str | None = None
    iso_pmi_sektor: str | None = None
    iso_pmi_metrik: str | None = None
    tim_pm_sektor: str | None = None
    tim_pm_ulke: str | None = None
    tim_pm_endeks: str | None = None
    bigchefs_metrik: str | None = None
    turktraktor_metrik: str | None = None
    migros_metrik: str | None = None
    tepav_seri: str | None = None
    tmsd_kalem: str | None = None
    ithib_kalem: str | None = None


def _alan_verilmis(seri: Seri, alan: str) -> bool:
    """Tipe özgü alanların tamamı None varsayılanlıdır: verilmiş = None değil.

    `olcek` de bu kurala uyar (varsayılanı None; 1.0'a `ingest` tarafında
    düşülür), böylece katalogda açıkça yazılmış etkisiz bir `olcek: 1.0` da
    yakalanır — onurlandırılmayan bir alan, değeri ne olursa olsun yanıltıcıdır.
    """
    return getattr(seri, alan) is not None


def _alan_sahipligini_dogrula(seri: Seri) -> None:
    tanim = KAYNAK_ALANLARI[seri.kaynak_tipi]
    izinli = set(tanim["zorunlu"]) | set(tanim["istege_bagli"])

    for alan in tanim["zorunlu"]:
        # Boş string alanı doldurmaz: `evds_code: ""` kod yazmakla aynı değil.
        # Not: zorunlu alanlar bugün yalnızca string. Sayısal bir zorunlu alan
        # eklenirse bu falsy kontrolü 0'ı da reddeder — o gün ayrılması gerekir.
        if not getattr(seri, alan):
            raise KatalogHatasi(
                f"{seri.id}: {seri.kaynak_tipi} kaynağı için {alan} zorunlu"
            )

    for alan in sorted(TIPE_OZGU_ALANLAR - izinli):
        if _alan_verilmis(seri, alan):
            raise KatalogHatasi(
                f"{seri.id}: {seri.kaynak_tipi} kaynağı {alan} taşıyamaz"
            )


def _yaml_oku(ad: str) -> list[dict]:
    yol = KATALOG_DIZINI / ad
    if not yol.exists():
        raise KatalogHatasi(f"Katalog dosyası bulunamadı: {yol}")
    icerik = yaml.safe_load(yol.read_text(encoding="utf-8"))
    if not isinstance(icerik, list) or not icerik:
        raise KatalogHatasi(f"{ad} boş ya da liste değil")
    return icerik


@lru_cache(maxsize=1)
def kategorileri_yukle() -> tuple[Kategori, ...]:
    kategoriler = []
    gorulen: set[str] = set()
    for ham in _yaml_oku("categories.yaml"):
        slug = ham["slug"]
        if slug in gorulen:
            raise KatalogHatasi(f"Kategori slug'ı tekrar ediyor: {slug}")
        gorulen.add(slug)
        kategoriler.append(
            Kategori(
                slug=slug,
                title=ham["title"],
                note=ham.get("note"),
                pano=tuple(ham.get("pano", ())),
            )
        )
    return tuple(kategoriler)


@lru_cache(maxsize=1)
def hisseleri_yukle() -> tuple[Hisse, ...]:
    """Ticker tanımlarını okur ve seri referanslarını doğrular.

    Bilinmeyen bir seri id'si sessizce yutulmaz: `pano_serileri` ile aynı
    gerekçe — yazım hatası, kartın sayfada sessizce kaybolmasından ucuza
    yakalanmalı. `kendi` boş olamaz: şirketin kendi verisi olmayan bir
    ticker sayfası yalnızca makro grafik yığınıdır, sayfanın var oluş
    nedeni ortadan kalkar.
    """
    id_kumesi = {s.id for s in serileri_yukle()}
    hisseler: list[Hisse] = []
    gorulen: set[str] = set()
    for ham in _yaml_oku("hisseler.yaml"):
        kod = str(ham["kod"])
        if kod in gorulen:
            raise KatalogHatasi(f"Hisse kodu tekrar ediyor: {kod}")
        if not re.fullmatch(r"[A-Z]{4,6}", kod):
            raise KatalogHatasi(
                f"{kod}: hisse kodu 4–6 büyük harf olmalı (BIST kodu)"
            )
        gorulen.add(kod)
        kendi = tuple(ham.get("kendi", ()))
        baglam = tuple(ham.get("baglam", ()))
        if not kendi:
            raise KatalogHatasi(f"{kod}: en az bir 'kendi' serisi olmalı")
        eksik = [i for i in kendi + baglam if i not in id_kumesi]
        if eksik:
            raise KatalogHatasi(
                f"{kod}: katalogda olmayan seri: {', '.join(eksik)}"
            )
        cakisan = sorted(set(kendi) & set(baglam))
        if cakisan:
            raise KatalogHatasi(
                f"{kod}: aynı seri hem kendi hem baglam listesinde: "
                f"{', '.join(cakisan)} — sayfada iki kez çizilirdi"
            )
        hisseler.append(
            Hisse(
                kod=kod,
                title=ham["title"],
                sektor=ham["sektor"],
                kendi=kendi,
                baglam=baglam,
                note=ham.get("note"),
            )
        )
    return tuple(hisseler)


@lru_cache(maxsize=1)
def serileri_yukle() -> tuple[Seri, ...]:
    sluglar = {k.slug for k in kategorileri_yukle()}
    seriler = []
    gorulen: set[str] = set()

    for ham in _yaml_oku("series.yaml"):
        evds_frekans = ham.get("evds_frequency")
        _epias_alani_ham = ham.get("epias_alani")
        seri = Seri(
            id=ham["id"],
            title=ham["title"],
            category=ham["category"],
            kaynak=Kaynak(**ham["kaynak"]),
            kaynak_tipi=ham["kaynak_tipi"],
            unit=ham["unit"],
            freq=ham["freq"],
            charts=tuple(ham["charts"]),
            evds_code=ham.get("evds_code"),
            evds_frequency=None if evds_frekans is None else str(evds_frekans),
            yahoo_symbol=ham.get("yahoo_symbol"),
            epias_ucu=ham.get("epias_ucu"),
            epias_alani=(
                tuple(_epias_alani_ham)
                if isinstance(_epias_alani_ham, list)
                else _epias_alani_ham
            ),
            epias_bilesenler=(
                {ad: tuple(alanlar) for ad, alanlar in ham["epias_bilesenler"].items()}
                if "epias_bilesenler" in ham
                else None
            ),
            epias_havza=ham.get("epias_havza"),
            osd_firma=ham.get("osd_firma"),
            osd_eski_adlar=(
                tuple(ham["osd_eski_adlar"]) if "osd_eski_adlar" in ham else None
            ),
            osd_arac_tipi=ham.get("osd_arac_tipi"),
            osd_veri_tipi=ham.get("osd_veri_tipi"),
            tim_sektor=ham.get("tim_sektor"),
            tim_eski_adlar=(
                tuple(ham["tim_eski_adlar"]) if "tim_eski_adlar" in ham else None
            ),
            tim_il=ham.get("tim_il"),
            tim_ulke=ham.get("tim_ulke"),
            tim_ulke_grubu=ham.get("tim_ulke_grubu"),
            bddk_kalem=ham.get("bddk_kalem"),
            bddk_taraf=(
                str(ham["bddk_taraf"]) if "bddk_taraf" in ham else None
            ),
            bddk_kumulatif=ham.get("bddk_kumulatif"),
            bddk_haftalik_id=ham.get("bddk_haftalik_id"),
            bddk_haftalik_sutun=(
                int(ham["bddk_haftalik_sutun"]) if "bddk_haftalik_sutun" in ham else None
            ),
            bddk_haftalik_taraf=(
                str(ham["bddk_haftalik_taraf"]) if "bddk_haftalik_taraf" in ham else None
            ),
            bddk_bdmk_urun=ham.get("bddk_bdmk_urun"),
            bddk_bdmk_tablo=(
                int(ham["bddk_bdmk_tablo"]) if "bddk_bdmk_tablo" in ham else None
            ),
            bddk_bdmk_kalem=ham.get("bddk_bdmk_kalem"),
            bddk_bdmk_kumulatif=ham.get("bddk_bdmk_kumulatif"),
            tefas_tip=ham.get("tefas_tip"),
            tefas_olcut=ham.get("tefas_olcut"),
            tefas_kod=ham.get("tefas_kod"),
            ec_kaynak=ham.get("ec_kaynak"),
            ec_varlik=ham.get("ec_varlik"),
            fred_code=ham.get("fred_code"),
            pgsus_segment=ham.get("pgsus_segment"),
            pgsus_olcut=ham.get("pgsus_olcut"),
            thy_segment=ham.get("thy_segment"),
            thy_olcut=ham.get("thy_olcut"),
            tav_varlik=ham.get("tav_varlik"),
            tav_segment=ham.get("tav_segment"),
            tav_olcut=ham.get("tav_olcut"),
            epdk_olcut=ham.get("epdk_olcut"),
            epdk_urun=ham.get("epdk_urun"),
            turkcell_metrik=ham.get("turkcell_metrik"),
            ttkom_metrik=ham.get("ttkom_metrik"),
            odmd_marka=(
                tuple(ham["odmd_marka"]) if "odmd_marka" in ham else None
            ),
            odmd_yarim_marka=(
                tuple(ham["odmd_yarim_marka"]) if "odmd_yarim_marka" in ham else None
            ),
            odmd_kategori=ham.get("odmd_kategori"),
            ebebek_metrik=ham.get("ebebek_metrik"),
            eib_kalem=ham.get("eib_kalem"),
            eib_olcut=ham.get("eib_olcut"),
            usk_kalem=ham.get("usk_kalem"),
            turkbesd_olcut=ham.get("turkbesd_olcut"),
            turkbesd_urun=ham.get("turkbesd_urun"),
            wb_seri=ham.get("wb_seri"),
            ifo_seri=ham.get("ifo_seri"),
            tsb_alt_kategori=ham.get("tsb_alt_kategori"),
            tsb_rapor=ham.get("tsb_rapor"),
            tsb_sheet=ham.get("tsb_sheet"),
            tsb_sirket_kodu=(
                int(ham["tsb_sirket_kodu"]) if "tsb_sirket_kodu" in ham else None
            ),
            epdk_dogalgaz_olcut=ham.get("epdk_dogalgaz_olcut"),
            eurostat_dataset=ham.get("eurostat_dataset"),
            eurostat_geo=ham.get("eurostat_geo"),
            eurostat_currency=ham.get("eurostat_currency"),
            ecb_akis=ham.get("ecb_akis"),
            ecb_anahtar=ham.get("ecb_anahtar"),
            turkcimento_metrik=ham.get("turkcimento_metrik"),
            istib_urun=ham.get("istib_urun"),
            tuik_kanatli_olcut=ham.get("tuik_kanatli_olcut"),
            botas_kategori=ham.get("botas_kategori"),
            epdk_fiyat_urun=ham.get("epdk_fiyat_urun"),
            epdk_fiyat_kalem=ham.get("epdk_fiyat_kalem"),
            tspb_tablo=ham.get("tspb_tablo"),
            tspb_kategori=ham.get("tspb_kategori"),
            sgk_metrik=ham.get("sgk_metrik"),
            gph_metrik=ham.get("gph_metrik"),
            orge_metrik=ham.get("orge_metrik"),
            monthly_agg=ham.get("monthly_agg", "mean"),
            start_date=ham.get("start_date"),
            tcud_kalem=ham.get("tcud_kalem"),
            yayin_notu=ham.get("yayin_notu"),
            olcek=float(ham["olcek"]) if "olcek" in ham else None,
            gecikme_gunu=(
                int(ham["gecikme_gunu"]) if "gecikme_gunu" in ham else None
            ),
            hareketli_ortalama_gun=ham.get("hareketli_ortalama_gun"),
            dhmi_olcut=ham.get("dhmi_olcut"),
            uab_liman=ham.get("uab_liman"),
            eurostat_turizm_resid=ham.get("eurostat_turizm_resid"),
            iso_pmi_sektor=ham.get("iso_pmi_sektor"),
            iso_pmi_metrik=ham.get("iso_pmi_metrik"),
            tim_pm_sektor=ham.get("tim_pm_sektor"),
            tim_pm_ulke=ham.get("tim_pm_ulke"),
            tim_pm_endeks=ham.get("tim_pm_endeks"),
            bigchefs_metrik=ham.get("bigchefs_metrik"),
            turktraktor_metrik=ham.get("turktraktor_metrik"),
            migros_metrik=ham.get("migros_metrik"),
            tepav_seri=ham.get("tepav_seri"),
            tmsd_kalem=ham.get("tmsd_kalem"),
            ithib_kalem=ham.get("ithib_kalem"),
        )
        _dogrula(seri, sluglar, gorulen)
        gorulen.add(seri.id)
        seriler.append(seri)

    return tuple(seriler)


def _dogrula(seri: Seri, kategori_sluglari: set[str], gorulen: set[str]) -> None:
    if seri.id in gorulen:
        raise KatalogHatasi(f"Seri id'si tekrar ediyor: {seri.id}")
    if seri.category not in kategori_sluglari:
        raise KatalogHatasi(
            f"{seri.id}: '{seri.category}' kategorisi categories.yaml'da yok"
        )
    if not seri.id.startswith(f"{seri.category}/"):
        raise KatalogHatasi(
            f"{seri.id}: id, kategori adıyla başlamalı ('{seri.category}/')"
        )
    if seri.freq not in GECERLI_FREKANSLAR:
        raise KatalogHatasi(f"{seri.id}: geçersiz freq '{seri.freq}'")
    if seri.monthly_agg not in GECERLI_AYLIK_AGG:
        raise KatalogHatasi(f"{seri.id}: geçersiz monthly_agg '{seri.monthly_agg}'")
    if not seri.charts:
        raise KatalogHatasi(f"{seri.id}: en az bir grafik tanımlı olmalı")
    if not set(seri.charts) <= GECERLI_GRAFIKLER:
        raise KatalogHatasi(f"{seri.id}: bilinmeyen grafik türü {seri.charts}")
    if len(set(seri.charts)) != len(seri.charts):
        raise KatalogHatasi(f"{seri.id}: charts listesinde tekrar var {seri.charts}")
    if "daily_seasonality" in seri.charts and seri.freq != "daily":
        raise KatalogHatasi(f"{seri.id}: daily_seasonality günlük seri gerektirir")
    if "fon" in seri.charts and seri.freq != "daily":
        raise KatalogHatasi(f"{seri.id}: fon grafiği günlük seri gerektirir")
    if seri.freq == "quarterly" and set(seri.charts) != {"level"}:
        raise KatalogHatasi(f"{seri.id}: çeyreklik seri yalnızca level grafiği destekler")
    if seri.hareketli_ortalama_gun is not None:
        if type(seri.hareketli_ortalama_gun) is not int or seri.hareketli_ortalama_gun <= 0:
            raise KatalogHatasi(
                f"{seri.id}: hareketli_ortalama_gun pozitif tam sayı olmalı"
            )
        if seri.freq != "daily" or set(seri.charts) & {"composition", "fon"}:
            raise KatalogHatasi(
                f"{seri.id}: hareketli_ortalama_gun günlük tek değerli seri gerektirir"
            )
    if seri.kaynak_tipi not in GECERLI_KAYNAK_TIPLERI:
        raise KatalogHatasi(f"{seri.id}: geçersiz kaynak_tipi '{seri.kaynak_tipi}'")
    _alan_sahipligini_dogrula(seri)
    if seri.kaynak_tipi == "dhmi" and seri.dhmi_olcut not in GECERLI_DHMI_OLCUTLERI:
        raise KatalogHatasi(
            f"{seri.id}: geçersiz dhmi_olcut '{seri.dhmi_olcut}' "
            f"(geçerli: {', '.join(sorted(GECERLI_DHMI_OLCUTLERI))})"
        )
    if seri.kaynak_tipi == "uab" and seri.uab_liman not in GECERLI_UAB_LIMANLARI:
        raise KatalogHatasi(
            f"{seri.id}: geçersiz uab_liman '{seri.uab_liman}' "
            f"(geçerli: {', '.join(sorted(GECERLI_UAB_LIMANLARI))})"
        )
    if (
        seri.kaynak_tipi == "eurostat_turizm"
        and seri.eurostat_turizm_resid not in GECERLI_EUROSTAT_TURIZM_RESID
    ):
        raise KatalogHatasi(
            f"{seri.id}: geçersiz eurostat_turizm_resid "
            f"'{seri.eurostat_turizm_resid}' "
            f"(geçerli: {', '.join(sorted(GECERLI_EUROSTAT_TURIZM_RESID))})"
        )
    if seri.kaynak_tipi == "iso_pmi":
        if seri.iso_pmi_metrik not in GECERLI_ISO_PMI_METRIKLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz iso_pmi_metrik '{seri.iso_pmi_metrik}' "
                f"(geçerli: {', '.join(sorted(GECERLI_ISO_PMI_METRIKLERI))})"
            )
        if seri.iso_pmi_sektor is not None and seri.iso_pmi_sektor not in GECERLI_ISO_PMI_SEKTORLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz iso_pmi_sektor '{seri.iso_pmi_sektor}' "
                f"(geçerli: {', '.join(sorted(GECERLI_ISO_PMI_SEKTORLERI))})"
            )
        if seri.iso_pmi_sektor is None and seri.iso_pmi_metrik != "pmi":
            raise KatalogHatasi(
                f"{seri.id}: manşet seri (iso_pmi_sektor yok) yalnızca "
                "iso_pmi_metrik='pmi' olabilir"
            )
    if seri.kaynak_tipi == "tim_pazar_monitoru":
        if seri.tim_pm_endeks not in GECERLI_TIM_PM_ENDEKSLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz tim_pm_endeks '{seri.tim_pm_endeks}' "
                f"(geçerli: {', '.join(sorted(GECERLI_TIM_PM_ENDEKSLERI))})"
            )
        if seri.tim_pm_sektor is not None and seri.tim_pm_sektor not in GECERLI_TIM_PM_SEKTORLERI:
            raise KatalogHatasi(f"{seri.id}: geçersiz tim_pm_sektor '{seri.tim_pm_sektor}'")
        if seri.tim_pm_ulke is not None and seri.tim_pm_ulke not in GECERLI_TIM_PM_ULKELERI:
            raise KatalogHatasi(f"{seri.id}: geçersiz tim_pm_ulke '{seri.tim_pm_ulke}'")
        if seri.tim_pm_sektor and seri.tim_pm_ulke:
            raise KatalogHatasi(
                f"{seri.id}: tim_pm_sektor ve tim_pm_ulke birlikte kullanılamaz"
            )
    if (seri.kaynak_tipi == "tefas_fon") != ("fon" in seri.charts):
        raise KatalogHatasi(f"{seri.id}: tefas_fon kaynağı ile fon grafiği birlikte kullanılmalı")
    if "fon" in seri.charts and seri.charts != ("fon",):
        raise KatalogHatasi(f"{seri.id}: fon tek başına olmalı, başka grafikle birleştirilemez")
    if seri.kaynak_tipi == "epias":
        if seri.epias_ucu == "baraj-doluluk":
            # EPİAŞ'ın baraj doluluk ucu (dams-data/active-fullness +
            # active-volume + dam-volume) saatlik alan/bileşen değil,
            # havza/ülke bazında kapasite ağırlıklı tek bir günlük değerdir
            # (bkz. ingest/epias.py baraj_doluluk_cek) — epias_alani ve
            # epias_bilesenler bu uçta anlamsızdır.
            if seri.epias_alani or seri.epias_bilesenler:
                raise KatalogHatasi(
                    f"{seri.id}: baraj-doluluk serisi epias_alani/"
                    "epias_bilesenler taşıyamaz"
                )
            if (
                seri.epias_havza is not None
                and seri.epias_havza not in GECERLI_EPIAS_HAVZALARI
            ):
                raise KatalogHatasi(
                    f"{seri.id}: geçersiz epias_havza '{seri.epias_havza}' "
                    f"(geçerli: {', '.join(sorted(GECERLI_EPIAS_HAVZALARI))})"
                )
        else:
            if seri.epias_havza is not None:
                raise KatalogHatasi(
                    f"{seri.id}: epias_havza yalnızca baraj-doluluk "
                    "serisinde kullanılır"
                )
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
    if "composition" in seri.charts and set(seri.charts) != {"composition"}:
        # `page.py` bileşenli seri için yalnızca kompozisyon grafiğini çizer;
        # composition başka bir grafikle (ör. level) birlikte listelenirse
        # o ikinci grafik sessizce hiç çizilmez — KAYNAK_ALANLARI tablosunun
        # var oluş gerekçesiyle aynı ilke: sessizce yok sayılan bir alan
        # yanıltıcıdır.
        raise KatalogHatasi(
            f"{seri.id}: composition tek başına olmalı, başka grafikle "
            f"birleştirilemez (charts={list(seri.charts)})"
        )
    if seri.kaynak_tipi == "epias" and seri.monthly_agg == "last":
        # epias.seri_cek yalnızca sum/mean günlük indirgemesi biliyor;
        # "last" verilirse else dalı bunu sessizce ortalamaya çeviriyordu.
        raise KatalogHatasi(
            f"{seri.id}: epias kaynağı monthly_agg='last' alamaz "
            "(yalnızca 'sum' ya da 'mean' desteklenir)"
        )
    if seri.kaynak_tipi == "eurocontrol" and seri.ec_kaynak not in GECERLI_EC_KAYNAKLARI:
        raise KatalogHatasi(
            f"{seri.id}: geçersiz ec_kaynak '{seri.ec_kaynak}' "
            f"(geçerli: {', '.join(sorted(GECERLI_EC_KAYNAKLARI))})"
        )
    if seri.kaynak_tipi == "pgsus":
        if seri.pgsus_segment not in GECERLI_PGSUS_SEGMENTLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz pgsus_segment '{seri.pgsus_segment}' "
                f"(geçerli: {', '.join(sorted(GECERLI_PGSUS_SEGMENTLERI))})"
            )
        if seri.pgsus_olcut not in GECERLI_PGSUS_OLCUTLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz pgsus_olcut '{seri.pgsus_olcut}' "
                f"(geçerli: {', '.join(sorted(GECERLI_PGSUS_OLCUTLERI))})"
            )
    if seri.kaynak_tipi == "thy":
        if seri.thy_segment not in GECERLI_THY_SEGMENTLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz thy_segment '{seri.thy_segment}' "
                f"(geçerli: {', '.join(sorted(GECERLI_THY_SEGMENTLERI))})"
            )
        if seri.thy_olcut not in GECERLI_THY_OLCUTLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz thy_olcut '{seri.thy_olcut}' "
                f"(geçerli: {', '.join(sorted(GECERLI_THY_OLCUTLERI))})"
            )
    if seri.kaynak_tipi == "tav":
        if seri.tav_segment not in GECERLI_TAV_SEGMENTLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz tav_segment '{seri.tav_segment}' "
                f"(geçerli: {', '.join(sorted(GECERLI_TAV_SEGMENTLERI))})"
            )
        # Verilmemişse "yolcu" kabul edilir (ingest/tav.py:seri_cek ile aynı
        # varsayılan) — mevcut 28 yolcu serisi tav_olcut hiç taşımıyor.
        if seri.tav_olcut is not None and seri.tav_olcut not in GECERLI_TAV_OLCUTLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz tav_olcut '{seri.tav_olcut}' "
                f"(geçerli: {', '.join(sorted(GECERLI_TAV_OLCUTLERI))})"
            )
    if seri.kaynak_tipi == "ebebek" and seri.ebebek_metrik not in GECERLI_EBEBEK_METRIKLERI:
        raise KatalogHatasi(
            f"{seri.id}: geçersiz ebebek_metrik '{seri.ebebek_metrik}' "
            f"(geçerli: {', '.join(sorted(GECERLI_EBEBEK_METRIKLERI))})"
        )
    if seri.kaynak_tipi == "epdk":
        if seri.epdk_olcut not in GECERLI_EPDK_OLCUTLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz epdk_olcut '{seri.epdk_olcut}' "
                f"(geçerli: {', '.join(sorted(GECERLI_EPDK_OLCUTLERI))})"
            )
        if seri.epdk_urun not in GECERLI_EPDK_URUNLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz epdk_urun '{seri.epdk_urun}' "
                f"(geçerli: {', '.join(sorted(GECERLI_EPDK_URUNLERI))})"
            )
    if seri.kaynak_tipi == "epdk_dogalgaz" and seri.epdk_dogalgaz_olcut not in GECERLI_EPDK_DOGALGAZ_OLCUTLERI:
        raise KatalogHatasi(
            f"{seri.id}: geçersiz epdk_dogalgaz_olcut '{seri.epdk_dogalgaz_olcut}' "
            f"(geçerli: {', '.join(sorted(GECERLI_EPDK_DOGALGAZ_OLCUTLERI))})"
        )
    if seri.kaynak_tipi == "eurostat":
        if seri.eurostat_dataset not in GECERLI_EUROSTAT_DATASETLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz eurostat_dataset '{seri.eurostat_dataset}' "
                f"(geçerli: {', '.join(sorted(GECERLI_EUROSTAT_DATASETLERI))})"
            )
        if seri.eurostat_geo not in GECERLI_EUROSTAT_GEO:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz eurostat_geo '{seri.eurostat_geo}' "
                f"(geçerli: {', '.join(sorted(GECERLI_EUROSTAT_GEO))})"
            )
        if seri.eurostat_currency not in GECERLI_EUROSTAT_PARA_BIRIMLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz eurostat_currency '{seri.eurostat_currency}' "
                f"(geçerli: {', '.join(sorted(GECERLI_EUROSTAT_PARA_BIRIMLERI))})"
            )
    if (
        seri.kaynak_tipi == "turkcimento"
        and seri.turkcimento_metrik not in GECERLI_TURKCIMENTO_METRIKLERI
    ):
        raise KatalogHatasi(
            f"{seri.id}: geçersiz turkcimento_metrik '{seri.turkcimento_metrik}' "
            f"(geçerli: {', '.join(sorted(GECERLI_TURKCIMENTO_METRIKLERI))})"
        )
    if seri.kaynak_tipi == "turkcell" and seri.turkcell_metrik not in GECERLI_TURKCELL_METRIKLERI:
        raise KatalogHatasi(
            f"{seri.id}: geçersiz turkcell_metrik '{seri.turkcell_metrik}' "
            f"(geçerli: {', '.join(sorted(GECERLI_TURKCELL_METRIKLERI))})"
        )
    if seri.kaynak_tipi == "ttkom" and seri.ttkom_metrik not in GECERLI_TTKOM_METRIKLERI:
        raise KatalogHatasi(
            f"{seri.id}: geçersiz ttkom_metrik '{seri.ttkom_metrik}' "
            f"(geçerli: {', '.join(sorted(GECERLI_TTKOM_METRIKLERI))})"
        )
    if (
        seri.kaynak_tipi == "osd"
        and seri.osd_veri_tipi is not None
        and seri.osd_veri_tipi not in GECERLI_OSD_VERI_TIPLERI
    ):
        raise KatalogHatasi(
            f"{seri.id}: geçersiz osd_veri_tipi '{seri.osd_veri_tipi}' "
            f"(geçerli: {', '.join(sorted(GECERLI_OSD_VERI_TIPLERI))})"
        )
    if seri.kaynak_tipi == "odmd":
        if seri.odmd_kategori not in GECERLI_ODMD_KATEGORILERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz odmd_kategori '{seri.odmd_kategori}' "
                f"(geçerli: {', '.join(sorted(GECERLI_ODMD_KATEGORILERI))})"
            )
        if not seri.odmd_marka:
            raise KatalogHatasi(f"{seri.id}: odmd_marka en az bir marka içermeli")
        cakisan = set(seri.odmd_marka) & set(seri.odmd_yarim_marka or ())
        if cakisan:
            raise KatalogHatasi(
                f"{seri.id}: {', '.join(sorted(cakisan))} hem odmd_marka hem "
                "odmd_yarim_marka içinde olamaz"
            )
    if seri.kaynak_tipi in {"tefas", "tefas_fon"}:
        # Yazım hatası adaptörün derinliklerinde KeyError'a dönüşmesin.
        if seri.tefas_tip not in GECERLI_TEFAS_TIPLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz tefas_tip '{seri.tefas_tip}' "
                f"(geçerli: {', '.join(sorted(GECERLI_TEFAS_TIPLERI))})"
            )
        if seri.kaynak_tipi == "tefas" and seri.tefas_olcut not in GECERLI_TEFAS_OLCUTLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz tefas_olcut '{seri.tefas_olcut}' "
                f"(geçerli: {', '.join(sorted(GECERLI_TEFAS_OLCUTLERI))})"
            )
    if seri.kaynak_tipi == "tefas_fon":
        if not isinstance(seri.tefas_kod, str) or not re.fullmatch(r"[A-Z0-9]+", seri.tefas_kod):
            raise KatalogHatasi(f"{seri.id}: geçersiz tefas_kod '{seri.tefas_kod}'")
        try:
            baslangic = date.fromisoformat(seri.start_date)
        except (TypeError, ValueError) as hata:
            raise KatalogHatasi(f"{seri.id}: start_date YYYY-MM-DD biçiminde geçerli tarih olmalı") from hata
        if baslangic.isoformat() != seri.start_date or baslangic > date.today():
            raise KatalogHatasi(f"{seri.id}: start_date YYYY-MM-DD biçiminde ve bugün veya öncesinde olmalı")
    if (
        seri.kaynak_tipi == "bddk_haftalik"
        and seri.bddk_haftalik_sutun is not None
        and seri.bddk_haftalik_sutun not in (1, 2, 3)
    ):
        raise KatalogHatasi(
            f"{seri.id}: geçersiz bddk_haftalik_sutun '{seri.bddk_haftalik_sutun}' "
            "(geçerli: 1=TP, 2=YP, 3=Toplam)"
        )
    if (
        seri.kaynak_tipi == "bddk_bdmk"
        and seri.bddk_bdmk_urun not in GECERLI_BDDK_BDMK_URUNLERI
    ):
        raise KatalogHatasi(
            f"{seri.id}: geçersiz bddk_bdmk_urun '{seri.bddk_bdmk_urun}' "
            f"(geçerli: {', '.join(sorted(GECERLI_BDDK_BDMK_URUNLERI))})"
        )
    # Alan varlığı tabloda; burada yalnızca değer geçerliliği kalıyor.
    if seri.olcek is not None and seri.olcek <= 0:
        raise KatalogHatasi(
            f"{seri.id}: olcek pozitif olmalı (verilen: {seri.olcek})"
        )
    if seri.gecikme_gunu is not None and seri.gecikme_gunu <= 0:
        # 0 "gecikme yok" demek değil, alanı gereksiz yazmak demek: eşik
        # zaten tipik gecikmeyi içeriyor. Negatif değer eşiği daraltarak
        # sahte "gecikmiş" üretir.
        raise KatalogHatasi(
            f"{seri.id}: gecikme_gunu pozitif olmalı (verilen: {seri.gecikme_gunu})"
        )
    if seri.kaynak_tipi == "evds" and seri.evds_frequency not in GECERLI_EVDS_FREKANSLARI:
        raise KatalogHatasi(
            f"{seri.id}: geçersiz evds_frequency '{seri.evds_frequency}'"
        )
    if seri.kaynak_tipi == "epdk_fiyat":
        if seri.epdk_fiyat_urun not in GECERLI_EPDK_FIYAT_URUNLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz epdk_fiyat_urun '{seri.epdk_fiyat_urun}' "
                f"(geçerli: {', '.join(sorted(GECERLI_EPDK_FIYAT_URUNLERI))})"
            )
        if seri.epdk_fiyat_kalem not in GECERLI_EPDK_FIYAT_KALEMLERI:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz epdk_fiyat_kalem '{seri.epdk_fiyat_kalem}' "
                f"(geçerli: {', '.join(sorted(GECERLI_EPDK_FIYAT_KALEMLERI))})"
            )
    if seri.kaynak_tipi == "istib" and seri.istib_urun not in GECERLI_ISTIB_URUNLERI:
        raise KatalogHatasi(
            f"{seri.id}: geçersiz istib_urun '{seri.istib_urun}' "
            f"(geçerli: {', '.join(sorted(GECERLI_ISTIB_URUNLERI))})"
        )
    if (
        seri.kaynak_tipi == "tuik_kanatli"
        and seri.tuik_kanatli_olcut not in GECERLI_TUIK_KANATLI_OLCUTLERI
    ):
        raise KatalogHatasi(
            f"{seri.id}: geçersiz tuik_kanatli_olcut '{seri.tuik_kanatli_olcut}' "
            f"(geçerli: {', '.join(sorted(GECERLI_TUIK_KANATLI_OLCUTLERI))})"
        )
    if seri.kaynak_tipi == "botas" and seri.botas_kategori not in GECERLI_BOTAS_KATEGORILERI:
        raise KatalogHatasi(
            f"{seri.id}: geçersiz botas_kategori '{seri.botas_kategori}' "
            f"(geçerli: {', '.join(sorted(GECERLI_BOTAS_KATEGORILERI))})"
        )
    if seri.kaynak_tipi == "tspb":
        if seri.tspb_tablo not in GECERLI_TSPB_TABLOLAR:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz tspb_tablo '{seri.tspb_tablo}' "
                f"(geçerli: {', '.join(sorted(GECERLI_TSPB_TABLOLAR))})"
            )
        gecerli_kategoriler = (
            GECERLI_TSPB_KREDILI_KATEGORILERI if seri.tspb_tablo == "kredili"
            else GECERLI_TSPB_PYS_KATEGORILERI
        )
        if seri.tspb_kategori not in gecerli_kategoriler:
            raise KatalogHatasi(
                f"{seri.id}: geçersiz tspb_kategori '{seri.tspb_kategori}' "
                f"(tspb_tablo='{seri.tspb_tablo}' için geçerli: "
                f"{', '.join(sorted(gecerli_kategoriler))})"
            )
    if seri.kaynak_tipi == "tepav" and seri.tepav_seri not in GECERLI_TEPAV_SERILERI:
        raise KatalogHatasi(
            f"{seri.id}: geçersiz tepav_seri '{seri.tepav_seri}' "
            f"(geçerli: {', '.join(sorted(GECERLI_TEPAV_SERILERI))})"
        )
    if seri.kaynak_tipi == "bigchefs" and seri.bigchefs_metrik not in GECERLI_BIGCHEFS_METRIKLERI:
        raise KatalogHatasi(
            f"{seri.id}: geçersiz bigchefs_metrik '{seri.bigchefs_metrik}' "
            f"(geçerli: {', '.join(sorted(GECERLI_BIGCHEFS_METRIKLERI))})"
        )
    if (
        seri.kaynak_tipi == "turktraktor"
        and seri.turktraktor_metrik not in GECERLI_TURKTRAKTOR_METRIKLERI
    ):
        raise KatalogHatasi(
            f"{seri.id}: geçersiz turktraktor_metrik '{seri.turktraktor_metrik}' "
            f"(geçerli: {', '.join(sorted(GECERLI_TURKTRAKTOR_METRIKLERI))})"
        )
    if seri.kaynak_tipi == "migros" and seri.migros_metrik not in GECERLI_MIGROS_METRIKLERI:
        raise KatalogHatasi(
            f"{seri.id}: geçersiz migros_metrik '{seri.migros_metrik}' "
            f"(geçerli: {', '.join(sorted(GECERLI_MIGROS_METRIKLERI))})"
        )


def seri_listele(kategori: str | None = None) -> list[Seri]:
    seriler = serileri_yukle()
    if kategori is None:
        return list(seriler)
    return [s for s in seriler if s.category == kategori]


def seri_getir(seri_id: str) -> Seri:
    for seri in serileri_yukle():
        if seri.id == seri_id:
            return seri
    raise KatalogHatasi(f"Katalogda böyle bir seri yok: {seri_id}")
