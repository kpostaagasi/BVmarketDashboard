"""TİM il×sektör katalog girdilerini üretir (741 seri).

İl/sektör çiftleri referans platformun il sayfasındaki bölüm başlıklarından
alınır ("İSTANBUL — Mücevher"); böylece hangi ilde hangi sektörün yayımlandığı
tahmin edilmez. `Toplam` kartı ilin sektör satırları toplamıdır (ölçüldü:
İSTANBUL 1-31 Ağustos 2026 → 8.679.756,86; bültenin TOPLAM satırı 8.800.137,83
birlik bazlı fazlalık içerir).

Kullanım: python -m tools.tim_il_katalog_uret > /tmp/tim_il.yaml
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata

import requests

SAYFA = "https://marketvisuals.net/tim_export_provinces.html"
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
        il, sektor = (parca.strip() for parca in bolum["title"].split("—", 1))
        bulunan.append((il, sektor))
    if not bulunan:
        raise RuntimeError("İl sayfasından hiç il/sektör çifti okunamadı")
    return bulunan


def girdi(il: str, sektor: str) -> str:
    # "Toplam" kartı adaptörde özel değer; katalogda TOPLAM olarak yazılır.
    tim_sektor = TOPLAM_ETIKETI if sektor == "Toplam" else sektor
    return "\n".join([
        f"- id: ihracat-il/{slug(il)}-{slug(sektor)}",
        f'  title: "{il} · {sektor} İhracatı"',
        "  category: ihracat-il",
        '  kaynak: { name: TİM, url: "https://tim.org.tr/tr/ihracat-rakamlari" }',
        "  kaynak_tipi: tim_il",
        f'  tim_il: "{il}"',
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
    sys.stdout.write("\n" + "\n".join(girdi(il, sektor) for il, sektor in kayitlar))
    print(f"{len(kayitlar)} il×sektör girdisi üretildi", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
