"""BV Market Dashboard — giriş noktası.

Sol menü katalogdan üretilir; yeni bir kategori eklemek için
catalog/categories.yaml'a bir satır eklemek yeterlidir.
"""

import streamlit as st

from core.catalog import kategorileri_yukle
from core.page import kategori_sayfasi_yap

st.set_page_config(
    page_title="BV Market Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

sayfalar = [
    st.Page(
        kategori_sayfasi_yap(kategori),
        title=kategori.title,
        url_path=kategori.slug,
        default=(sira == 0),
    )
    for sira, kategori in enumerate(kategorileri_yukle())
]

st.navigation({"Veri Sayfaları": sayfalar}).run()
