"""Favori seri listesi. Saf: Streamlit yok.

Kalıcılık tavanı URL'deki `f` parametresi. 40 id yer imine sığar;
daha fazlası için tarayıcı localStorage gerekir (Streamlit bileşeni
değer döndürürse).
"""

from __future__ import annotations

FAVORI_TAVANI = 40


def favorileri_coz(ham: str | None, gecerli: set[str]) -> list[str]:
    """Virgüllü id metnini geçerli, tekrarsız, tavanlı listeye çevirir."""
    if not ham:
        return []
    sonuc: list[str] = []
    for parca in ham.split(","):
        seri_id = parca.strip()
        if seri_id in gecerli and seri_id not in sonuc:
            sonuc.append(seri_id)
        if len(sonuc) == FAVORI_TAVANI:
            break
    return sonuc


def favori_metni(idler: list[str]) -> str:
    return ",".join(idler)


def favori_degistir(idler: list[str], seri_id: str) -> list[str]:
    """Varsa çıkarır, yoksa tavana kadar ekler. Tavan doluysa liste aynı kalır."""
    if seri_id in idler:
        return [i for i in idler if i != seri_id]
    if len(idler) >= FAVORI_TAVANI:
        return list(idler)
    return [*idler, seri_id]
