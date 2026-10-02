"""KTB Bakanlık Belgeli Konaklama bülteni testleri (doluluk + geceleme)."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pandas as pd
import pytest

from ingest import ktb
from ingest.ktb import _konaklama_ay_tablosu, _konaklama_cek


def _bulten_baytlari(basliklar_dogru: bool = True) -> bytes:
    """Gerçek 'Ay' sayfası şablonu: 0. satır başlık (yıl), 1. satır grup
    başlıkları, 2. satır YABANCI/YERLI/TOPLAM, 3.. aylar, sonda TOPLAM."""
    bos = [None] * 13
    r0 = [f"... (2026 OCAK-ŞUBAT)"] + [None] * 12
    r1 = ["AYLAR", "TESİSE GELİŞ SAYISI", None, None,
          "GECELEME" if basliklar_dogru else "XXX", None, None,
          "ORTALAMA KALIŞ", None, None, "DOLULUK ORANI", None, None]
    r2 = [None, "YABANCI", "YERLI", "TOPLAM", "YABANCI", "YERLI", "TOPLAM",
          "YABANCI", "YERLI", "TOPLAM", "YABANCI", "YERLI", "TOPLAM"]
    ocak = ["OCAK", 1, 2, 3, 100, 200, 300, 1, 1, 1, 10.5, 20.5, 30.5]
    subat = ["ŞUBAT", 1, 2, 3, 110, 210, 320, 1, 1, 1, 11.5, 21.5, 31.5]
    toplam = ["TOPLAM"] + [0] * 12
    df = pd.DataFrame([r0, r1, r2, ocak, subat, toplam])
    tampon = BytesIO()
    df.to_excel(tampon, sheet_name="Ay", header=False, index=False)
    return tampon.getvalue()


def _seri(olcut: str, gosterge: str | None = None):
    return SimpleNamespace(ktb_olcut=olcut, ktb_gosterge=gosterge)


def _bulteni_sahtele(monkeypatch):
    monkeypatch.setattr(ktb, "_konaklama_dosya_url", lambda *a, **k: "http://x/a.xlsx")
    monkeypatch.setattr(ktb, "KONAKLAMA_YIL_SAYFALARI", {})
    govde = _bulten_baytlari()
    monkeypatch.setattr(ktb, "_konaklama_indir", lambda *a, **k: govde)


def test_geceleme_toplam_dogru_sutunu_okur(monkeypatch):
    _bulteni_sahtele(monkeypatch)
    df = _konaklama_cek(_seri("toplam", "geceleme"))
    assert df["date"].tolist() == ["2026-01-01", "2026-02-01"]
    assert df["value"].tolist() == pytest.approx([300, 320])


def test_geceleme_yabanci_ve_yerli_ayri_sutunlardir(monkeypatch):
    _bulteni_sahtele(monkeypatch)
    assert _konaklama_cek(_seri("yabancı", "geceleme"))["value"].tolist() == [100, 110]
    assert _konaklama_cek(_seri("yerli", "geceleme"))["value"].tolist() == [200, 210]


def test_gosterge_bos_ise_doluluk_okunur_geriye_uyumlu(monkeypatch):
    _bulteni_sahtele(monkeypatch)
    assert _konaklama_cek(_seri("toplam"))["value"].tolist() == pytest.approx([30.5, 31.5])


def test_gecersiz_gosterge_patlar(monkeypatch):
    _bulteni_sahtele(monkeypatch)
    with pytest.raises(RuntimeError, match="göstergesi geçersiz"):
        _konaklama_cek(_seri("toplam", "oda"))


def test_geceleme_basligi_degismisse_sablon_hatasi():
    with pytest.raises(RuntimeError, match="şablonu değişmiş"):
        _konaklama_ay_tablosu(_bulten_baytlari(basliklar_dogru=False), "geceleme")


def _sinir_bulteni(sayfa: str) -> bytes:
    """Sınır bülteni sayfası: 2. satırda AYLAR + yıl başlıkları, 3.. aylar."""
    aylar = ["OCAK", "ŞUBAT", "MART", "NİSAN", "MAYIS", "HAZİRAN",
             "TEMMUZ", "AĞUSTOS", "EYLÜL", "EKİM", "KASIM", "ARALIK"]
    satirlar = [[None] * 4, [None, "YILLAR", None, None], ["AYLAR", 2025, 2026.0, None]]
    for i, ay in enumerate(aylar):
        satirlar.append([ay, 100 + i, 200 + i if i < 2 else None, None])
    tampon = BytesIO()
    pd.DataFrame(satirlar).to_excel(tampon, sheet_name=sayfa, header=False, index=False)
    return tampon.getvalue()


def test_sinir_toplam_ayri_sayfayi_okur_bos_hucreyi_atlar(monkeypatch):
    govde = _sinir_bulteni("Gelen Ziyaretçiler ")
    monkeypatch.setattr(ktb, "dosya_url", lambda session=None: "http://x/s.xls")
    monkeypatch.setattr(ktb, "_dosya_indir", lambda *a, **k: govde)
    seri = SimpleNamespace(ktb_sinir_olcut="toplam")
    df = ktb._sinir_cek(seri)
    assert df["date"].iloc[-1] == "2026-02-01"
    assert df["value"].iloc[-1] == pytest.approx(201)
    assert len(df) == 12 + 2


def test_sinir_olcut_bos_ise_yabanci_sayfasi_geriye_uyumlu(monkeypatch):
    govde = _sinir_bulteni("Gelen Yabancılar")
    monkeypatch.setattr(ktb, "dosya_url", lambda session=None: "http://x/s.xls")
    monkeypatch.setattr(ktb, "_dosya_indir", lambda *a, **k: govde)
    assert len(ktb._sinir_cek(SimpleNamespace(ktb_sinir_olcut=None))) == 14


def test_sinir_gecersiz_olcut_patlar():
    with pytest.raises(RuntimeError, match="sınır ölçütü geçersiz"):
        ktb._sinir_cek(SimpleNamespace(ktb_sinir_olcut="vatandas"), onbellek={"url": "x"})
