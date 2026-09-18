"""TİM ülke×sektör katalog girdilerini üretir (674 seri).

Ülke/sektör çiftleri referans platformun ülke sayfasındaki bölüm başlıklarından
alınır ("ALMANYA — Otomotiv Endüstrisi"); böylece hangi ülkede hangi sektörün
yayımlandığı tahmin edilmez. `Toplam` kartı ülkenin sektör satırları
toplamıdır — il tarafındaki gibi bülten TOPLAM satırından "kaçınma" değil,
hiç yayımlanmayan bir satırı türetme durumu (ölçüldü: ülke bülteninde ülke
başına ayrı bir TOPLAM satırı yok, tek bir genel TOPLAM/TOPLAM satırı var).

Kullanım: python -m tools.tim_ulke_katalog_uret > /tmp/tim_ulke.yaml
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata

import requests

SAYFA = "https://marketvisuals.net/tim_export_countries.html"
BASLANGIC = "2023-01-01"
TOPLAM_ETIKETI = "TOPLAM"


def slug(metin: str) -> str:
    esleme = str.maketrans("çğıöşüÇĞİıÖŞÜ", "cgiosuCGIiOSU")
    duz = unicodedata.normalize("NFKD", metin.translate(esleme))
    duz = "".join(k for k in duz if not unicodedata.combining(k))
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", duz.lower())).strip("-")


def ciftler() -> list[tuple[str, str]]:
    html = requests.get(SAYFA, timeout=120).text
    bas = html.find("SECTIONS = ") + len("SECTIONS = ")
    ham = html[bas:]
    bolumler = json.loads(ham[: ham.find("];") + 1])
    bulunan = []
    for bolum in bolumler:
        if bolum.get("isDivider") or "—" not in bolum["title"]:
            continue
        ulke, sektor = (parca.strip() for parca in bolum["title"].split("—", 1))
        bulunan.append((ulke, sektor))
    if not bulunan:
        raise RuntimeError("Ülke sayfasından hiç ülke/sektör çifti okunamadı")
    return bulunan


def girdi(ulke: str, sektor: str) -> str:
    # "Toplam" kartı adaptörde özel değer; katalogda TOPLAM olarak yazılır.
    tim_sektor = TOPLAM_ETIKETI if sektor == "Toplam" else sektor
    return "\n".join([
        f"- id: ihracat-ulke/{slug(ulke)}-{slug(sektor)}",
        f'  title: "{ulke} · {sektor} İhracatı"',
        "  category: ihracat-ulke",
        '  kaynak: { name: TİM, url: "https://tim.org.tr/tr/ihracat-rakamlari" }',
        "  kaynak_tipi: tim_ulke",
        f'  tim_ulke: "{ulke}"',
        f'  tim_sektor: "{tim_sektor}"',
        f'  start_date: "{BASLANGIC}"',
        '  unit: "Bin USD"',
        "  freq: monthly",
        "  monthly_agg: sum",
        "  charts: [seasonality, level]",
        "",
    ])


def main() -> int:
    kayitlar = ciftler()
    sys.stdout.write("\n" + "\n".join(girdi(ulke, sektor) for ulke, sektor in kayitlar))
    print(f"{len(kayitlar)} ülke×sektör girdisi üretildi", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
