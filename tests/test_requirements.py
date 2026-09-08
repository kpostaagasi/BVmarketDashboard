"""requirements ayrımı: pdfplumber ve openpyxl ingest'e ait, uygulamaya değil.

Streamlit Cloud `requirements.txt`'i kurar. PDF ve XLSX kütüphaneleri oraya
girerse uygulama gereksiz büyür ve çalışma zamanında hiç kullanılmaz.
"""

from pathlib import Path

KOK = Path(__file__).resolve().parent.parent


def _satirlar(ad: str) -> list[str]:
    return [
        s.strip()
        for s in (KOK / ad).read_text(encoding="utf-8").splitlines()
        if s.strip() and not s.strip().startswith("#")
    ]


def test_uygulama_requirements_pdfplumber_icermez():
    assert not any("pdfplumber" in s for s in _satirlar("requirements.txt"))


def test_ingest_requirements_pdfplumber_icerir():
    assert any("pdfplumber" in s for s in _satirlar("requirements-ingest.txt"))


def test_uygulama_requirements_openpyxl_icermez():
    assert not any("openpyxl" in s for s in _satirlar("requirements.txt"))


def test_ingest_requirements_openpyxl_icerir():
    """TİM sektörel bültenleri XLSX; okuyucu yalnızca ingest'te gerekli."""
    assert any("openpyxl" in s for s in _satirlar("requirements-ingest.txt"))


def test_ingest_requirements_uygulamayi_kapsar():
    """Ingest, uygulamanın bağımlılıklarına da ihtiyaç duyar (pandas, requests)."""
    assert "-r requirements.txt" in _satirlar("requirements-ingest.txt")


def test_ingest_workflow_ingest_requirements_kurar():
    metin = (KOK / ".github/workflows/ingest.yml").read_text(encoding="utf-8")
    assert "requirements-ingest.txt" in metin
