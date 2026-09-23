"""BV Market Dashboard — giriş noktası.

Üst menü katalogdan üretilir; yeni bir kategori eklemek için
catalog/categories.yaml'a (mevcut bir `grup` ile) bir girdi eklemek yeterlidir.
"""

import streamlit as st

from core.catalog import KATEGORI_GRUPLARI, hisseleri_yukle, kategorileri_yukle
from core.components import stil_uygula
from core.page import (
    arama_sayfasi,
    fon_sayfasi,
    genel_bakis_yap,
    hisse_sayfasi_yap,
    kategori_sayfasi_yap,
    veri_takvimi_sayfasi,
)

st.set_page_config(
    page_title="BV Market Dashboard",
    page_icon="📊",
    layout="wide",
    # "auto": geniş ekranda açık, mobilde kapalı. "expanded" 420 px
    # genişlikte menüyü içeriğin üzerine bindiriyordu.
    initial_sidebar_state="auto",
)

stil_uygula()

kategoriler = list(kategorileri_yukle())

kategori_sayfalari = [
    st.Page(
        kategori_sayfasi_yap(kategori),
        title=kategori.title,
        url_path=kategori.slug,
    )
    for kategori in kategoriler
]

ana_sayfa = st.Page(
    genel_bakis_yap(list(zip(kategoriler, kategori_sayfalari))),
    title="Genel Bakış",
    url_path="genel-bakis",
    default=True,
)

takvim_sayfasi = st.Page(
    veri_takvimi_sayfasi,
    title="Veri Takvimi",
    url_path="veri-takvimi",
)

arama = st.Page(
    arama_sayfasi,
    title="Ara",
    url_path="ara",
)

fonlar_sayfasi = st.Page(
    fon_sayfasi,
    title="Fonlar",
    url_path="fon",
)

# Hisse sayfaları katalogdan üretilir (catalog/hisseler.yaml); menüde kendi
# grubunda durur, çünkü kategori sayfaları veri kaynağına göre, hisse
# sayfaları şirkete göre kesiyor — aynı seriler iki eksende görünür.
hisse_sayfalari = [
    st.Page(
        hisse_sayfasi_yap(hisse),
        title=f"{hisse.kod} · {hisse.title}",
        url_path=f"hisse-{hisse.kod.lower()}",
    )
    for hisse in hisseleri_yukle()
]

# Kategoriler katalogdaki `grup` alanına göre bölümlenir; 49 kategorilik
# düz liste menüde aranan sayfayı bulmayı zorlaştırıyordu. Bölüm sırası
# KATEGORI_GRUPLARI'ndan, bölüm içi sıra categories.yaml'dan gelir.
bolumler = {
    grup: [
        sayfa
        for kategori, sayfa in zip(kategoriler, kategori_sayfalari)
        if kategori.grup == grup
    ]
    for grup in KATEGORI_GRUPLARI
}

st.navigation(
    {
        "Genel": [ana_sayfa, arama, fonlar_sayfasi, takvim_sayfasi],
        **bolumler,
        "Hisseler": hisse_sayfalari,
    },
    position="top",
).run()
