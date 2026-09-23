"""Kategori sayfası üreticisi.

Sayfalar bildirimseldir: katalogdaki her kategori için bir kapanış
üretilir, içerik katalogdan okunur.
"""

from __future__ import annotations

from datetime import date
from html import escape
from typing import Callable

import pandas as pd
import streamlit as st

from core.catalog import (
    KATEGORI_GRUPLARI,
    Hisse,
    Kategori,
    KatalogHatasi,
    SIKLIK_ETIKETLERI,
    Seri,
    hisseleri_yukle,
    kategorileri_yukle,
    seri_getir,
    seri_listele,
)
from core.components import (
    degisim_rozeti,
    donem_etiketi,
    fon_karti,
    grafik_karti,
    kisa_sayi,
    kompozisyon_karti,
    kpi_satiri,
    piyasa_karti_html,
)
from core.data import VeriYokHatasi, load_series
from core.ozet import OzetSatiri, one_cikanlar, ozet_uret, son_yayimlananlar
from core.stats import GORUNUMLER, VARSAYILAN
from core.takvim import GUNCEL, OKUNAMADI, tablo_df, takvim


# Bir kategori bu sayıdan çok seri taşıyorsa hepsi birden çizilmez: TİM
# il×sektör 741, ülke×sektör 674 seri içeriyor ve tamamı 1.400+ Plotly
# figürü demek — sayfa açılmıyor. Eşiğin üstünde seri SEÇİCİ gösterilir.
IZGARA_TAVANI = 24

# Yalnızca "Durum" ayarlanır: "bekleniyor (59 gün)" otomatik genişliğe
# sığmıyor. Diğer sütunlarda otomatik boyutlandırma zaten doğru sonuç
# veriyor; genişlik dayatmak onları kesiyordu.
TAKVIM_SUTUN_AYARI = {
    "Durum": st.column_config.TextColumn("Durum", width="medium"),
}


def takvim_sutun_sirasi(df: pd.DataFrame) -> list[str]:
    """Tamamen boş sütunları çıkarır.

    "Yayın notu" bugün her seride boş; yer kaplayıp bilgi taşımıyor ve
    kalan sütunları daraltıyor. Not girildiğinde sütun kendiliğinden döner.
    """
    return [ad for ad in df.columns if df[ad].astype(str).str.strip().any()]


def pano_serileri(kategori: Kategori, seriler: list[Seri]) -> list[Seri]:
    """Panoda gösterilecek serileri, kategorinin belirlediği sırada döndürür.

    Pano tanımlı değilse mevcut davranış korunur: kpi_satiri zaten ilk dördü
    alır (ve çok bileşenli serileri kendi içinde sessizce atlar — bkz.
    `core.components._kpi_uygun_seriler`). Bilinmeyen bir id sessizce
    yutulmaz — yazım hatası, kartın sessizce kaybolmasından daha ucuza
    yakalanmalı. Aynı gerekçeyle, `pano`da AÇIKÇA çok bileşenli (geniş) bir
    seri istenmişse de hata verilir: KPI kartı tek bir sayı gösterir, böyle
    bir serinin tek sayısı yoktur — bunu açıkça istemek de bir yazım/tasarım
    hatasıdır ve sessizce kaybolmamalı (bkz. I3).
    """
    if not kategori.pano:
        return seriler
    indeks = {s.id: s for s in seriler}
    eksik = [i for i in kategori.pano if i not in indeks]
    if eksik:
        raise KatalogHatasi(
            f"{kategori.slug} panosunda bilinmeyen seri: {', '.join(eksik)}"
        )
    genis = [i for i in kategori.pano if indeks[i].epias_bilesenler or "fon" in indeks[i].charts]
    if genis:
        raise KatalogHatasi(
            f"{kategori.slug} panosunda çok bileşenli (geniş) seri: "
            f"{', '.join(genis)} — KPI kartı tek sayı gösterir, bu serilerin "
            "tek sayısı yoktur"
        )
    return [indeks[i] for i in kategori.pano]


def _kategoriyi_ciz(kategori: Kategori) -> None:
    seriler = seri_listele(kategori.slug)

    st.title(kategori.title)
    kaynaklar = sorted({s.kaynak.name for s in seriler})
    st.caption(f"{len(seriler)} seri · Kaynak: {', '.join(kaynaklar)}")
    if kategori.note:
        st.caption(kategori.note)

    gorunum = st.segmented_control(
        "Görünüm",
        GORUNUMLER,
        default=VARSAYILAN,
        key=f"gorunum_{kategori.slug}",
        label_visibility="collapsed",
    )
    gorunum = gorunum or VARSAYILAN

    kpi_satiri(pano_serileri(kategori, seriler))

    with st.expander("Veri Takvimi", expanded=False):
        takvim_df = tablo_df(takvim(kategori=kategori.slug))
        st.dataframe(
            takvim_df,
            width="stretch",
            hide_index=True,
            column_config=TAKVIM_SUTUN_AYARI,
            column_order=takvim_sutun_sirasi(takvim_df),
        )
    st.divider()

    if len(seriler) > IZGARA_TAVANI:
        indeks = {seri.id: seri for seri in seriler}
        varsayilan = [seri.id for seri in pano_serileri(kategori, seriler)[:4]]
        secim = st.multiselect(
            "Seri",
            list(indeks),
            default=varsayilan,
            format_func=lambda seri_id: indeks[seri_id].title,
            key=f"secim_{kategori.slug}",
            placeholder="Seri adı yazın",
        )
        st.caption(
            f"{len(seriler)} serinin tamamı birden çizilmez; yazarak seçin "
            f"(en çok {IZGARA_TAVANI} kart önerilir)."
        )
        _izgara_ciz([indeks[seri_id] for seri_id in secim], gorunum)
        return

    _izgara_ciz(seriler, gorunum)


def kategori_sayfasi_yap(kategori: Kategori) -> Callable[[], None]:
    def sayfa() -> None:
        _kategoriyi_ciz(kategori)

    sayfa.__name__ = f"sayfa_{kategori.slug.replace('-', '_')}"
    return sayfa


def _izgara_ciz(seriler: list[Seri], gorunum: str, sutun_sayisi: int = 2) -> None:
    """Grafik ızgarası — kategori sayfasıyla aynı ritim.

    `sutun_sayisi` yalnızca hisse sayfasının şirket bloğu için 1 olur: tek
    serili bir bloğu iki sütuna koymak ızgaranın yarısını boş bırakıyordu.
    Tam genişlik kart aynı zamanda doğru hiyerarşi: sayfanın baş aktörü
    şirketin kendi verisi, bağlam serileri yanında değil altında durur.
    """
    seriler = [seri for seri in seriler if "fon" not in seri.charts]
    if not seriler:
        return
    sutunlar = st.columns(sutun_sayisi)
    for sira, seri in enumerate(seriler):
        with sutunlar[sira % sutun_sayisi]:
            if "composition" in seri.charts:
                kompozisyon_karti(seri)
            else:
                grafik_karti(seri, gorunum)


def arama_etiketi(seri: Seri, kategori_basliklari: dict[str, str]) -> str:
    """Arama listesindeki tek satır: seri adı · kategori · birim.

    Süzme işini `st.multiselect`in kendi yazarak-arama davranışı yapar;
    ayrı bir arama indeksi ya da eşleştirme kodu YOKTUR. Dolayısıyla
    aranabilir olması gereken her şey etikette geçmek zorunda: kategori
    başlığı "bankacılık" yazınca kategoriyi süzsün diye, birim ise aynı
    adı taşıyan iki seriyi ayırsın diye burada.

    Bilinmeyen slug `KeyError` verir — kategori referansları zaten
    `serileri_yukle` içinde doğrulanır, buraya düşmesi katalog hatasıdır.
    """
    return f"{seri.title} · {kategori_basliklari[seri.category]} · {seri.unit}"


def arama_sayfasi() -> None:
    """Seri arama: 111 seri 15 kategori sayfasına dağılmış, menüden bulmak zor.

    Seçilenler tek ızgarada çizilir; böylece arama aynı zamanda kategori
    sınırlarını aşan serbest karşılaştırma panosu olur. Seçenekler seri
    id'si (string) tutulur, `Seri` nesnesi değil: kompozisyon serilerinin
    `epias_bilesenler` sözlüğü onları hash'lenemez yapıyor.
    """
    indeks = {s.id: s for s in seri_listele()}
    basliklar = {k.slug: k.title for k in kategorileri_yukle()}

    st.title("Ara")
    st.caption(f"{len(indeks)} seri · yazarak süzün, seçtikleriniz altta çizilir")

    secim = st.multiselect(
        "Seri",
        list(indeks),
        format_func=lambda seri_id: arama_etiketi(indeks[seri_id], basliklar),
        key="arama_secim",
        label_visibility="collapsed",
        placeholder="Seri, kategori ya da birim yazın",
    )
    if not secim:
        return

    gorunum = st.segmented_control(
        "Görünüm",
        GORUNUMLER,
        default=VARSAYILAN,
        key="gorunum_arama",
        label_visibility="collapsed",
    )
    st.divider()
    _izgara_ciz([indeks[i] for i in secim], gorunum or VARSAYILAN)


def _hisseyi_ciz(hisse: Hisse) -> None:
    """Ticker sayfası: şirketin kendi verisi, sonra sektör/girdi bağlamı.

    İki bölüm AYRI başlıklar altında çizilir. Aynı ızgaraya karıştırmak
    sayfayı makro grafik yığınına çevirirdi; portföy yöneticisinin ilk
    sorusu "şirketin kendi verisi ne diyor" olduğu için o blok üstte ve
    KPI satırı yalnızca ondan besleniyor.
    """
    kendi = [seri_getir(i) for i in hisse.kendi]
    baglam = [seri_getir(i) for i in hisse.baglam]
    tumu = kendi + baglam

    st.title(hisse.title)
    kaynaklar = sorted({s.kaynak.name for s in tumu})
    st.caption(
        f"`{hisse.kod}` · {hisse.sektor} · {len(tumu)} seri · "
        f"Kaynak: {', '.join(kaynaklar)}"
    )
    if hisse.note:
        st.caption(hisse.note)

    gorunum = st.segmented_control(
        "Görünüm",
        GORUNUMLER,
        default=VARSAYILAN,
        key=f"gorunum_hisse_{hisse.kod}",
        label_visibility="collapsed",
    )
    gorunum = gorunum or VARSAYILAN

    kpi_satiri(kendi)

    with st.expander("Veri Takvimi", expanded=False):
        takvim_df = tablo_df([s for s in takvim() if s.seri.id in set(hisse.kendi + hisse.baglam)])
        st.dataframe(
            takvim_df,
            width="stretch",
            hide_index=True,
            column_config=TAKVIM_SUTUN_AYARI,
            column_order=takvim_sutun_sirasi(takvim_df),
        )
    st.divider()

    st.subheader("Şirketin kendi verisi")
    _izgara_ciz(kendi, gorunum, sutun_sayisi=1 if len(kendi) == 1 else 2)

    if baglam:
        st.subheader("Sektör ve girdi bağlamı")
        st.caption(
            "Bu seriler şirkete ait değil; talep ve maliyet kanallarının "
            "vekilidir."
        )
        _izgara_ciz(baglam, gorunum)


def hisse_sayfasi_yap(hisse: Hisse) -> Callable[[], None]:
    def sayfa() -> None:
        _hisseyi_ciz(hisse)

    sayfa.__name__ = f"sayfa_hisse_{hisse.kod.lower()}"
    return sayfa


# Ana sayfanın piyasa şeridi. Günlük seriler; her gün değişen, "bugün ne
# oldu" sorusunun cevabı. Bilinmeyen id `seri_getir`de KeyError verir.
PIYASA_SERIDI = (
    "ekonomi-makro/usd-try",
    "ekonomi-makro/eur-try",
    "ekonomi-makro/bist100",
    "emtia-metaller/altin",
    "emtia-enerji/brent",
    "ekonomi-makro/politika-faizi",
)


def ozet_adaylari() -> tuple[str, ...]:
    """Öne çıkanlar için aday seriler: kategori panoları + hisse "kendi".

    Gerekçe `core/ozet.py` modül docstring'inde. Sıra korunur, tekrar atılır;
    geniş (bileşenli) seriler tek sayı taşımadığı için dışarıda.
    """
    idler: dict[str, None] = {}
    for kategori in kategorileri_yukle():
        idler.update(dict.fromkeys(kategori.pano))
    for hisse in hisseleri_yukle():
        idler.update(dict.fromkeys(hisse.kendi))
    return tuple(
        i for i in idler
        if not seri_getir(i).epias_bilesenler and "fon" not in seri_getir(i).charts
    )


@st.cache_data(show_spinner=False, ttl=3600)
def _ozet_satirlari(idler: tuple[str, ...], bugun: date) -> list[OzetSatiri]:
    """Bozuk ya da eksik CSV bir satırı düşürür, ana sayfayı değil."""
    satirlar = []
    for seri_id in idler:
        try:
            df = load_series(seri_id)
        except VeriYokHatasi:
            continue
        satir = ozet_uret(seri_getir(seri_id), df, bugun)
        if satir is not None:
            satirlar.append(satir)
    return satirlar


def _ozet_rozeti(satir: OzetSatiri) -> str:
    if "%" in satir.seri.unit:
        return degisim_rozeti(satir.yoy_puan, "YoY", puan=True)
    return degisim_rozeti(satir.yoy, "YoY")


def ozet_listesi_html(
    satirlar: list[OzetSatiri], kategori_basliklari: dict[str, str]
) -> str:
    """Öne çıkan / son yayımlanan satırları: başlık → kategori sayfasına link.

    Link düz <a>: `st.page_link` bir tablo hücresine konamıyor. Bedeli tam
    sayfa yüklemesi; ana sayfadan bir kategoriye geçişte kabul edilebilir.
    """
    if not satirlar:
        return "<p class='bv-kart-meta'>Şu an listelenecek seri yok.</p>"
    satir_html = []
    for s in satirlar:
        seri = s.seri
        satir_html.append(
            "<tr>"
            f"<td><a href='./{seri.category}' target='_self' "
            f"style='color:inherit;text-decoration:none'>{escape(seri.title)}</a>"
            f"<br><span class='bv-kart-meta'>"
            f"{escape(kategori_basliklari[seri.category])} · "
            f"{donem_etiketi(s.son_tarih, seri.freq)}</span></td>"
            f"<td class='sag'>{kisa_sayi(s.son_deger)}<br>"
            f"<span class='bv-kart-meta'>{escape(seri.unit)}</span></td>"
            f"<td class='sag'>{_ozet_rozeti(s)}</td>"
            "</tr>"
        )
    return f"<table class='bv-liste'>{''.join(satir_html)}</table>"


def genel_bakis_yap(
    eslesmeler: list[tuple[Kategori, "st.Page"]],
) -> Callable[[], None]:
    def sayfa() -> None:
        tum_seriler = seri_listele()
        kaynaklar = sorted({s.kaynak.name for s in tum_seriler})
        basliklar = {k.slug: k.title for k, _ in eslesmeler}

        st.title("BV Market Dashboard")
        st.html(
            "<div class='bv-hero-alt'>Türkiye ekonomisi, sektörler ve küresel "
            "emtia için veri ve grafikler</div>"
            "<div class='bv-sayac'>"
            f"<div><b>{_tr_tam(len(tum_seriler))}</b><span>seri</span></div>"
            f"<div><b>{len(eslesmeler)}</b><span>kategori</span></div>"
            f"<div><b>{len(kaynaklar)}</b><span>veri kaynağı</span></div>"
            f"<div><b>{len(hisseleri_yukle())}</b><span>hisse sayfası</span></div>"
            "</div>"
        )

        st.html("<div class='bv-bolum'>Piyasalar</div>")
        piyasa = [seri_getir(i) for i in PIYASA_SERIDI]
        for sutun, seri in zip(st.columns(len(piyasa)), piyasa):
            with sutun:
                st.html(piyasa_karti_html(seri))

        satirlar = _ozet_satirlari(ozet_adaylari(), date.today())
        artan, dusen = one_cikanlar(satirlar)
        sol, sag = st.columns([3, 2], gap="large")
        with sol:
            st.html("<div class='bv-bolum'>Dikkat çekenler · yıllık değişim</div>")
            sekme_artan, sekme_dusen = st.tabs(["En çok artan", "En çok düşen"])
            with sekme_artan:
                st.html(ozet_listesi_html(artan, basliklar))
            with sekme_dusen:
                st.html(ozet_listesi_html(dusen, basliklar))
        with sag:
            st.html("<div class='bv-bolum'>Son yayımlanan veriler</div>")
            st.html(ozet_listesi_html(son_yayimlananlar(satirlar, adet=7), basliklar))
        st.caption(
            "Aday küme: kategori panoları ve hisse sayfalarındaki şirket verileri. "
            "Birimi yüzde olan seriler (faiz, oran) ve bayat seriler yıllık "
            "sıralamaya girmez."
        )

        for grup in KATEGORI_GRUPLARI:
            gruptakiler = [(k, h) for k, h in eslesmeler if k.grup == grup]
            if not gruptakiler:
                continue
            st.html(f"<div class='bv-bolum'>{escape(grup)}</div>")
            sutunlar = st.columns(4)
            for sira, (kategori, hedef) in enumerate(gruptakiler):
                with sutunlar[sira % 4], st.container(key=f"kutu-{kategori.slug}"):
                    st.page_link(hedef, label=f"**{kategori.title}**")
                    st.caption(f"{len(seri_listele(kategori.slug))} seri")

        with st.expander(f"Veri kaynakları ({len(kaynaklar)})"):
            st.caption(" · ".join(kaynaklar))

    return sayfa


def _tr_tam(sayi: int) -> str:
    return f"{sayi:,}".replace(",", ".")


def fon_sayfasi() -> None:
    """Fon sayfası: 958 fonun kartı tek sayfada yığılmaz, fon seçilir.

    Referans platform fon başına ayrı sayfa yayımlıyor; burada aynı kart
    kümesi tek sayfada fon seçiciyle veriliyor — 958 menü girdisi yerine
    yazarak arama, `arama_sayfasi` ile aynı desen.
    """
    fonlar = [seri for seri in seri_listele() if "fon" in seri.charts]
    st.title("Fonlar")
    st.caption(f"{len(fonlar)} TEFAS fonu · yazarak süzün")
    if not fonlar:
        st.warning("Katalogda fon serisi yok")
        return
    indeks = {seri.id: seri for seri in fonlar}
    secim = st.selectbox(
        "Fon",
        list(indeks),
        format_func=lambda seri_id: indeks[seri_id].title,
        key="fon_secim",
        label_visibility="collapsed",
    )
    st.divider()
    fon_karti(indeks[secim])


def veri_takvimi_sayfasi() -> None:
    satirlar = takvim()
    sorunlular = [s for s in satirlar if s.durum != GUNCEL]

    st.title("Veri Takvimi")
    st.caption(
        f"{len(satirlar)} seri · {len(satirlar) - len(sorunlular)} güncel · "
        f"{len(sorunlular)} dikkat gerektiriyor"
    )
    st.caption(
        "Bir seri geciktiğinde ya kaynak geç kalmıştır ya da ingest kırılmıştır."
    )

    if sorunlular:
        with st.container(border=True):
            st.markdown(f"**⚠ {len(sorunlular)} seri dikkat gerektiriyor**")
            for s in sorunlular:
                if s.durum == OKUNAMADI:
                    sure = "veri dosyası okunamıyor"
                elif s.bekleme_gunu is None:
                    sure = "hiç veri yok"
                else:
                    sure = f"{s.bekleme_gunu} gündür yeni veri yok"
                st.markdown(
                    f"- **{s.seri.title}** — {sure} "
                    f"({SIKLIK_ETIKETLERI[s.seri.freq].lower()})"
                )
        st.divider()

    df = tablo_df(satirlar)
    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        column_config=TAKVIM_SUTUN_AYARI,
        column_order=takvim_sutun_sirasi(df),
    )
