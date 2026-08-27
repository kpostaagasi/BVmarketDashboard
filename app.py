"""BV Market Dashboard — giriş noktası.

Sol menü katalogdan üretilir; yeni bir kategori eklemek için
catalog/categories.yaml'a bir satır eklemek yeterlidir.
"""

import streamlit as st

from core.catalog import kategorileri_yukle
from core.page import genel_bakis_yap, kategori_sayfasi_yap

st.set_page_config(
    page_title="BV Market Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
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

st.navigation(
    {"Genel": [ana_sayfa], "Veri Sayfaları": kategori_sayfalari}
).run()
