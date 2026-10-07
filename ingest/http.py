"""HTTP durumunu RuntimeError metnine gömmeden yükseltir.

Adaptörler `if status != 200: raise RuntimeError(f"HTTP {kod}")` diyordu.
Zincirde `HTTPError` olmadığı için 504 kod hatası sayılıp koşuyu kırmızı
yapıyordu. Burada tür `requests.HTTPError` kalır: 403/429/5xx erişilemez,
404 bizim hatamız.
"""

from __future__ import annotations

import requests


def durum_kodu_yukselt(yanit) -> None:
    """200 değilse `HTTPError` yükselt. 200'de bir şey yapma.

    Gerçek `requests.Response` kendi `raise_for_status` metodunu kullanır.
    Test çiftleri yalnızca `status_code` taşır; onlar `HTTP {kod}` metniyle
    aynı türü yükseltir.
    """
    if yanit.status_code == 200:
        return
    yukselt = getattr(yanit, "raise_for_status", None)
    if yukselt is not None:
        yukselt()
        return
    raise requests.HTTPError(f"HTTP {yanit.status_code}")
