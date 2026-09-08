"""BV Market Dashboard — giriş noktası.

Sol menü katalogdan üretilir; yeni bir kategori eklemek için
catalog/categories.yaml'a bir satır eklemek yeterlidir.
"""

import streamlit as st

from core.catalog import hisseleri_yukle, kategorileri_yukle
from core.page import (
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

st.navigation(
    {
        "Genel": [ana_sayfa, takvim_sayfasi],
        "Hisseler": hisse_sayfalari,
        "Veri Sayfaları": kategori_sayfalari,
    }
).run()
