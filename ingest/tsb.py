"""TSB (Türkiye Sigorta Birliği) "Mali Tablolar ve İstatistikler" istemcisi.

Kaynak gerçekleri 2026-09-18'de canlı ölçüldü (sıfırdan yeniden keşfetmeye
çalışmayın):

- Dosya listesi ucu: `GET /Statistic/GetAllStatistics?CategoryUrl=<kategori>
  &SubCategoryUrl=<alt_kategori>&pageId=<n>` (10 dosya/sayfa, en yeniden
  eskiye). Her satır `PeriodYear`/`PeriodMonth`/`FileName`/`FilePath`
  taşır; `FilePath` doğrudan indirilebilir bir `.xlsx` yoludur
  (`/content/Statistics/...`), site kökünde barındırılıyor.
- **Doğrulama kapısı ŞU AN KAPALI**: `GET /Statistic/GetStatisticReportStatus`
  `IsActiveStatisticReport=false` döndürüyor. Bu bayrak `true` olursa TSB'nin
  önyüzü indirmeyi e-posta doğrulama kodu + reCAPTCHA akışının arkasına
  alır (bkz. `/page/Statistics.js` — `ControlRememberMe`/`SendVerification
  CodeToEmail`); o noktada bu adaptör HTTP 200 dışı ya da beklenmeyen içerik
  alır ve `RuntimeError` ile patlar (otomasyona kapatılmış bir akışı
  atlatmaya ÇALIŞILMAZ — bu durumda seri BLOKE olarak işaretlenmeli).
- "Prim Üretimleri Sıralama <YYYY> <MM>.xlsx" dosyası (kategori
  `genel-sigorta-verileri`, alt kategori `prim-adet`) her ay o aya kadar
  **01.01'den itibaren YIL BAŞINDAN KÜMÜLATİF** şirket bazlı "Toplam
  Üretim (TL)" verir. Workbook'ta branş bazlı ayrı sheet'ler var (`Hayat`,
  `Hayatdışı`, `Hastalık-Sağlık`, `Kasko`, `Trafik`, ... — tam liste
  `workbook.sheetnames`). Her şirket-sıralı sheette satır biçimi:
  `(Sıralama, Şirket Adı, Şirket Kodu, Toplam Üretim (TL), Pazar Payı %)`,
  veri 7. satırdan başlar (üstü başlık/dönem metadatası — satır NUMARASI
  yerine `"Sıralama"` başlık satırı ARANARAK bulunur, şablon kayarsa da
  çalışsın diye).
- **Sektör toplamı** güncel şirket-sıralı sheetlerde `Şirket Kodu=9003`
  ("SEKTÖR TOPLAMI") satırıyla verilir; bu değer `Genel` sheet'indeki
  `"<BRANŞ> TOPLAM"` satırıyla çapraz doğrulandı (Ağustos 2026: ikisi de
  815.731.863.400,10 TL YTD). **ESKİ dosyalarda (ör. 2022-03) bu satırın
  `Şirket Kodu` hücresi BOŞ** (kod hiç yazılmamış, yalnızca `Şirket Adı`
  = "SEKTÖR TOPLAMI") — ölçüldü, canlı doğrulandı. `sheet_degerleri` bu
  satırı isimden tanıyıp `SEKTOR_KODU`ya (9003) normalize eder.
- **AYLIK tekil üretim = ay(N) kümülatif − ay(N−1) kümülatif** (Ocak hariç,
  Ocak zaten tek aylıktır) — BDDK kar/zarar kalemleriyle BİREBİR AYNI
  desen, dönüşüm `ingest.bddk.kumulatifi_ayliga_cevir`den yeniden
  kullanılıyor. Ölçüldü: Türkiye Sigorta AŞ Ağustos 2026 = 120.434.918.659,72
  (Ağu YTD) − 107.113.524.712,56 (Tem YTD) = 13.321.393.947,16 TL.
- Dosya adındaki BAŞTAKİ sıra numarası (ör. "3 Prim Üretimleri...") yıllar
  içinde değişiyor (2012–2015 arası dosyalarda hiç yok, ay biçimi de
  "2015-11" / "2012-4" arası tutarsız); bu yüzden dosya EŞLEŞTİRMESİ
  `FileName` İÇİNDE `tsb_rapor` alt dizesi aranarak yapılıyor, dönem de
  dosya adından değil `PeriodYear`/`PeriodMonth` alanlarından okunuyor.
- **`.xls` DUVARI**: Kasım 2014'ten ÖNCEKİ dosyalar eski ikili Excel
  biçiminde (`.xls` uzantılı) yayımlanıyor; `openpyxl` bunu AÇAMAZ
  (`BadZipFile`). Ölçüldü: 2014-11 `.xlsx`, 2013-10 ve 2012-3 `.xls`.
  `ILK_DESTEKLENEN_YIL` (2015) bu yüzden `start_date`den bağımsız SERT
  bir taban — daha eskisi istense de aşılmaz (bkz. `ingest.bddk.ILK_YIL`
  ile aynı desen).
- **UNICODE NORMALİZASYONU**: 2021-03'ten önce yeniden indekslenmiş (ör.
  `CreatedDate` 2021 olan 2018 dönemli kayıtlar) `FileName` alanları NFD
  (bileşke, "Ü" = U+0055 + U+0308) kodlanmış; daha yeni kayıtlar ve
  katalogdaki `tsb_rapor` NFC ("Ü" = U+00DC). Normalize etmeden substring
  araması ikisi arasında SESSİZCE hiç eşleşmiyordu (`in` operatörü hata
  vermez, boş liste döner) — dosya eşleştirmesi `unicodedata.normalize
  ("NFC", ...)` ile yapılıyor.
"""

from __future__ import annotations

from io import BytesIO
from unicodedata import normalize

import openpyxl
import pandas as pd
import requests

from ingest.bddk import kumulatifi_ayliga_cevir

UC = "https://www.tsb.org.tr"
ZAMAN_ASIMI = 60
KATEGORI = "genel-sigorta-verileri"
SEKTOR_KODU = 9003  # her şirket-sıralı sheette "SEKTÖR TOPLAMI" satırının kodu
ILK_DESTEKLENEN_YIL = 2015  # bundan önceki dosyalar .xls (openpyxl açamaz)


def _yil(start_date: str | None) -> int:
    return int(start_date[:4]) if start_date else 0


def dosya_listesi(alt_kategori: str, en_eski_yil: int, session=None) -> list[dict]:
    """`alt_kategori` altındaki dosyaları en yeniden `en_eski_yil`e kadar döndürür.

    Sayfalar en yeniden eskiye sıralı; bir sayfadaki TÜM kayıtların yılı
    `en_eski_yil`den eskiyse daha eskiye inmeye gerek yok (erken durur).
    """
    http = session or requests
    dosyalar: list[dict] = []
    sayfa = 1
    while True:
        yanit = http.get(
            f"{UC}/Statistic/GetAllStatistics",
            params={"CategoryUrl": KATEGORI, "SubCategoryUrl": alt_kategori, "pageId": sayfa},
            timeout=ZAMAN_ASIMI,
        )
        if yanit.status_code != 200:
            raise RuntimeError(
                f"TSB HTTP {yanit.status_code} (alt kategori {alt_kategori}, sayfa {sayfa})"
            )
        govde = yanit.json()
        satirlar = govde.get("Result") or []
        if not satirlar:
            break
        dosyalar.extend(satirlar)
        yillar = [s["PeriodYear"] for s in satirlar if s.get("PeriodYear") is not None]
        if yillar and max(yillar) < en_eski_yil:
            break
        sayfa += 1
    if not dosyalar:
        raise RuntimeError(f"TSB '{alt_kategori}' alt kategorisinde hiç dosya yok")
    return dosyalar


def sheet_degerleri(wb: openpyxl.Workbook, sheet: str) -> dict[int, float]:
    """Şirket-sıralı bir sheet'i `{Şirket Kodu: Toplam Üretim (TL)}` olarak okur.

    Sütunlar POZİSYONDAN değil `"Sıralama"` başlık satırından sonraki
    sabit üç kolon (Şirket Kodu, Toplam Üretim) taşınarak bulunur.
    Eski dosyalarda "SEKTÖR TOPLAMI" satırının `Şirket Kodu` hücresi boş
    olabiliyor (bkz. modül docstring'i) — isimden tanınıp `SEKTOR_KODU`ya
    normalize edilir.
    """
    if sheet not in wb.sheetnames:
        raise RuntimeError(f"TSB workbook'unda '{sheet}' sheet'i yok")
    ws = wb[sheet]
    basliklar_gorundu = False
    degerler: dict[int, float] = {}
    for satir in ws.iter_rows(values_only=True):
        if not satir:
            continue
        if not basliklar_gorundu:
            if satir[0] == "Sıralama":
                basliklar_gorundu = True
            continue
        if len(satir) < 4 or satir[3] is None:
            continue
        kod = satir[2]
        if kod is None:
            if satir[1] != "SEKTÖR TOPLAMI":
                continue
            kod = SEKTOR_KODU
        degerler[int(kod)] = float(satir[3])
    if not degerler:
        raise RuntimeError(f"TSB '{sheet}' sheet'inde hiç şirket satırı yok")
    return degerler


def _workbook_indir(url: str, session=None) -> openpyxl.Workbook:
    http = session or requests
    yanit = http.get(url, timeout=ZAMAN_ASIMI)
    if yanit.status_code != 200:
        raise RuntimeError(f"TSB dosyası indirilemedi: {url} (HTTP {yanit.status_code})")
    return openpyxl.load_workbook(BytesIO(yanit.content), data_only=True)


def kumulatif_seri(seri, session=None, onbellek: dict | None = None) -> dict[str, float]:
    """`(alt_kategori, rapor, sheet, şirket_kodu)` için ay→YTD-kümülatif eşlemesi.

    Dosya listesi `(alt_kategori, en_eski_yil)`e göre, indirilen workbook
    `FilePath` başına, sheet çözümü `(FilePath, sheet)`e göre önbelleklenir:
    aynı ayın workbook'u ve sheet'i birden çok şirket serisi arasında
    (ör. 5 hayat dışı şirket + sektör toplamı, ya da aynı workbook'un farklı
    sheet'lerini isteyen kardeş aileler) tek sefer indirilip okunur.
    `en_eski_yil` `ILK_DESTEKLENEN_YIL`nin altına asla inmez (`.xls` duvarı).
    """
    onbellek = {} if onbellek is None else onbellek
    en_eski_yil = max(_yil(seri.start_date), ILK_DESTEKLENEN_YIL)

    liste_anahtari = ("liste", seri.tsb_alt_kategori, en_eski_yil)
    if liste_anahtari not in onbellek:
        onbellek[liste_anahtari] = dosya_listesi(
            seri.tsb_alt_kategori, en_eski_yil, session=session
        )
    dosyalar = onbellek[liste_anahtari]

    # 2021-03'ten önce yeniden indekslenen kayıtlarda FileName NFD (bileşke
    # Unicode, ör. "Ü" = "U" + birleşen çift nokta) kullanıyor, katalogdaki
    # `tsb_rapor` ve daha yeni kayıtlar NFC (tek kod noktalı "Ü") — normalize
    # etmeden substring araması bu ikisi arasında sessizce hiç eşleşmiyordu.
    rapor_nfc = normalize("NFC", seri.tsb_rapor)
    eslesen = [
        d for d in dosyalar
        if rapor_nfc in normalize("NFC", d.get("FileName") or "")
    ]
    if not eslesen:
        raise RuntimeError(
            f"TSB '{seri.tsb_alt_kategori}' altında '{seri.tsb_rapor}' eşleşen dosya yok"
        )

    kumulatif: dict[str, float] = {}
    for kayit in eslesen:
        yil, ay = kayit.get("PeriodYear"), kayit.get("PeriodMonth")
        if yil is None or ay is None:
            raise RuntimeError(f"TSB dosyası dönem bilgisi eksik: {kayit.get('FileName')}")
        if yil < en_eski_yil:
            continue

        wb_anahtari = ("wb", kayit["FilePath"])
        if wb_anahtari not in onbellek:
            onbellek[wb_anahtari] = _workbook_indir(f"{UC}{kayit['FilePath']}", session=session)

        sheet_anahtari = (kayit["FilePath"], seri.tsb_sheet)
        if sheet_anahtari not in onbellek:
            onbellek[sheet_anahtari] = sheet_degerleri(onbellek[wb_anahtari], seri.tsb_sheet)
        degerler = onbellek[sheet_anahtari]

        if seri.tsb_sirket_kodu not in degerler:
            raise RuntimeError(
                f"TSB '{seri.tsb_sheet}' sheet'inde ({kayit['FileName']}) "
                f"şirket kodu {seri.tsb_sirket_kodu} yok"
            )
        kumulatif[f"{yil}-{int(ay):02d}-01"] = degerler[seri.tsb_sirket_kodu]
    return kumulatif


def seri_cek(seri, *, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """Yıl başından kümülatif YTD verisini aylık akıma çevirip döner."""
    onbellek = {} if onbellek is None else onbellek
    kumulatif = kumulatif_seri(seri, session=session, onbellek=onbellek)
    aylik = kumulatifi_ayliga_cevir(kumulatif)
    df = pd.DataFrame(sorted(aylik.items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)
