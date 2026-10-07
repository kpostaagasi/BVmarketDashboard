import pytest
import requests

from ingest.http import durum_kodu_yukselt


class _Sahte:
    def __init__(self, kod: int):
        self.status_code = kod


def test_durum_kodu_200_yukselmez():
    durum_kodu_yukselt(_Sahte(200))


def test_durum_kodu_504_httperror():
    with pytest.raises(requests.HTTPError, match="HTTP 504"):
        durum_kodu_yukselt(_Sahte(504))


def test_durum_kodu_404_httperror():
    with pytest.raises(requests.HTTPError, match="HTTP 404"):
        durum_kodu_yukselt(_Sahte(404))


def test_durum_kodu_gercek_yanitta_raise_for_status():
    yanit = requests.Response()
    yanit.status_code = 503
    yanit.url = "https://ornek.test/veri"
    yanit.reason = "Service Unavailable"
    with pytest.raises(requests.HTTPError, match="503 Server Error"):
        durum_kodu_yukselt(yanit)
