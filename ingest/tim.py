"""TİM (Türkiye İhracatçılar Meclisi) sektörel ihracat bülteni istemcisi.

Kaynak gerçekleri 2026-09-08'de canlı ölçüldü (sıfırdan yeniden
keşfetmeye çalışmayın; detay: docs/superpowers/specs/2026-09-08-faz3g-*):

- URL DETERMİNİSTİK, indeks kazımaya gerek yok:
  `/files/downloads/rakamlar/<yıl>/<ay>/<yıl>-<aa>-sektorel-bazda-rakamlar.xlsx`
  Ay dizinde sıfırsız (`/8/`), dosya adında sıfırlı (`2026-08`).
- HER DOSYA O YILIN TAMAMINI taşır: tek sayfa (`SEKTOR`), satır 4 başlık
  (OCAK…ARALIK + TOPLAM), sonrasında sektör satırları, `TOPLAM` etiketli
  satır tabloyu kapatır. Bu yüzden tam geçmiş için ayda bir değil YILDA BİR
  dosya çekilir.
- Pratik geçmiş sınırı 2019-01: `2019/12` ve sonrası 200, `2019/1` ve
  öncesi 404 (eski dosyalar `.xls` ve düzensiz adlandırmada).
- 2019–2020 dosyalarında `TOPLAM` satırından SONRA alt mal grubu tabloları
  da var (TİM Nisan 2025'te yayımı durdurdu); ayrıştırma `TOPLAM`da durur.
- YAYIMLANMAMIŞ AY `0` YAZAR: cari yıl dosyasında gelecek aylar sıfırdır.
  Sıfır "ihracat yok" değil, "henüz yok" demek; yazılırsa grafik dibe düşer
  ve YoY yönü yanlış çıkar. `sifir_aylari_at` bunu düşer.
- SEKTÖR ADLARI DEĞİŞİYOR: 2019'da `Elektrik Elektronik`, 2026'da
  `Elektrik ve Elektronik`. Kaçış yolu katalogdaki `tim_eski_adlar`.
- TİM ≠ TÜİK: Temmuz 2026'da TİM toplamı 22.028,9 mn USD, TÜİK 25.622,9.
  TİM ihracatçı birlikleri kayıtlarını sayar; iki seri aynı büyüklük
  değildir, seviye olarak karşılaştırılmamalıdır.

Değerler bültende Bin USD cinsindedir; Milyon USD'ye çevirim katalogdaki
`olcek` ile orchestrator'da yapılır (bkz. `ingest.run.olcekle`).
"""

from __future__ import annotations

import calendar
import io
from datetime import date

import openpyxl
import pandas as pd
import requests

TABAN = "https://tim.org.tr"
ZAMAN_ASIMI = 60
SAYFA_ADI = "SEKTOR"
IL_SAYFA_ADI = "ILLER_SEKTOR"
ASGARI_IL_SAYISI = 75
IL_GENEL_TOPLAM = "GENEL TOPLAM"
ULKE_SAYFA_ADI = "GUNLUK_SEKTOR_ULKE"
# İl bülteninde ikinci sütun "ILLER", ülke bülteninde "ULKE"; hata
# mesajlarında okunaklı tekil ad ("il"/"ülke") burada eşlenir.
_VARLIK_ADLARI = {"ILLER": "il", "ULKE": "ülke"}

# Modern (xlsx) yayının başladığı dosya. 2019'un tamamı bu dosyada.
ILK_YIL = 2019
ILK_AY = 12

# İl×sektör karşılaştırma dosyası AYLIKTIR (yıllık değil): sektörel bülten
# gibi tek dosyada 12 ay taşımaz, bu yüzden tam pencere için her ay ayrı
# indirilir. Kaynak 2023 Ocak'tan itibaren mevcut.
ILK_IL_YIL = 2023
ILK_IL_AY = 1
AY_ADLARI = (
    "OCAK", "ŞUBAT", "MART", "NİSAN", "MAYIS", "HAZİRAN",
    "TEMMUZ", "AĞUSTOS", "EYLÜL", "EKİM", "KASIM", "ARALIK",
)

TOPLAM_ETIKETI = "TOPLAM"
ANA_GRUPLAR = ("I. TARIM", "II. SANAYİ", "III. MADENCİLİK")

# Şablon kayarsa (sütun eklenir, satırlar kayar) ayrıştırma birkaç satır
# bulup sessizce devam edebilir. 2019–2026 dosyalarının hepsinde tablo 37
# satır; eşik bunun altında ama gürültüye kapalı bir yerde tutuluyor.
ASGARI_SEKTOR_SAYISI = 30
TOLERANS = 0.5


def bulten_url(yil: int, ay: int) -> str:
    """Ay dizinde sıfırsız, dosya adında sıfırlı — TİM böyle yayımlıyor."""
    return (
        f"{TABAN}/files/downloads/rakamlar/{yil}/{ay}/"
        f"{yil}-{ay:02d}-sektorel-bazda-rakamlar.xlsx"
    )


def il_bazinda_url(yil: int, ay: int) -> str:
    """İl×sektör karşılaştırma bülteni; dosya adı 2024'te tekile döndü."""
    kapsam = "il" if yil >= 2024 else "iller"
    return (
        f"{TABAN}/files/downloads/rakamlar/{yil}/{ay}/"
        f"{yil}-{ay:02d}-{kapsam}-bazinda-sektor-rakamlari.xlsx"
    )


def ulke_bazinda_url(yil: int, ay: int) -> str:
    """Ülke×sektör karşılaştırma bülteni; il bülteninden farklı olarak
    dosya adı yıl geçişinde değişmiyor (ölçüldü: 2022–2026 arası sabit)."""
    return (
        f"{TABAN}/files/downloads/rakamlar/{yil}/{ay}/"
        f"{yil}-{ay:02d}-ulkelere-gore-sektorel-ihracat-rakamlari.xlsx"
    )


def sektor_adini_normalize(ham: object) -> str:
    """Baştaki noktaları, satır sonlarını ve fazla boşluğu temizler.

    Bültende satır etiketleri hiyerarşi için nokta ve boşlukla süslüdür:
    `'.     A. BİTKİSEL ÜRÜNLER'`, `' Yaş Meyve ve Sebze  '`.
    """
    if ham is None:
        return ""
    return " ".join(str(ham).replace("\x00", "").split()).lstrip(".").strip()


def cekilecek_bultenler(bugun: date) -> list[tuple[int, int]]:
    """Yıl başına tek bülten: geçmiş yıllar için Aralık, cari yıl için bugün.

    Cari yılın dosyası yayımlanmamış olabilir (ör. 1 Ocak'ta); `seri_cek`
    bulunamayan ayı geriye doğru dener. Geçmiş yıllar için Aralık dosyası
    o yılın on iki ayını da taşır.
    """
    yillar = [(ILK_YIL, ILK_AY)]
    yillar += [(yil, 12) for yil in range(ILK_YIL + 1, bugun.year)]
    if bugun.year > ILK_YIL:
        yillar.append((bugun.year, bugun.month))
    return yillar


def sayfayi_ayikla(baytlar: bytes) -> dict[str, dict[str, float]]:
    """XLSX baytlarından `{sektör: {"YYYY-MM-01": değer}}` çıkarır.

    `TOPLAM` satırı tabloyu kapatır ve kendisi de bir "sektör" olarak
    döner (`ihracat/toplam` serisi onu kullanır, öz-doğrulama da).
    """
    kitap = openpyxl.load_workbook(io.BytesIO(baytlar), data_only=True)
    if SAYFA_ADI not in kitap.sheetnames:
        raise RuntimeError(
            f"TİM bülteninde '{SAYFA_ADI}' sayfası yok: {kitap.sheetnames}"
        )
    sayfa = kitap[SAYFA_ADI]

    yil = _yili_bul(sayfa)
    noktalar: dict[str, dict[str, float]] = {}
    for satir in sayfa.iter_rows(min_row=5, values_only=True):
        ad = sektor_adini_normalize(satir[0])
        if not ad:
            continue
        aylik = {}
        for ay, hucre in enumerate(satir[1:13], start=1):
            if isinstance(hucre, (int, float)):
                aylik[f"{yil}-{ay:02d}-01"] = float(hucre)
        if aylik:
            noktalar[ad] = aylik
        if ad.upper() == TOPLAM_ETIKETI:
            # 2019–2020 dosyalarında bu satırdan sonra alt mal grubu
            # tabloları geliyor; okumaya devam etmek onları sektör sanardı.
            break
    return noktalar


def il_sektor_noktalari(
    baytlar: bytes, anahtar: str = IL_SAYFA_ADI,
    sayfa_adi: str = IL_SAYFA_ADI, ikinci_sutun: str = "ILLER",
) -> dict[tuple[str, str], dict[str, float]]:
    """Karşılaştırma tablosunu `{(ikinci sütun değeri, sektör): {dönem/yıl: değer}}` okur.

    İl×sektör (`ILLER_SEKTOR`/"ILLER") ve ülke×sektör (`GUNLUK_SEKTOR_ULKE`/
    "ULKE") bültenleri AYNI şablonu paylaşır; `sayfa_adi`/`ikinci_sutun`
    hangisinin okunduğunu seçer (varsayılan il bülteni — mevcut çağıranlar
    etkilenmez).

    Bu dosya aylık zaman serisi değildir: ay, önceki ay ve yılbaşından
    bugüne birikimli karşılaştırmaları yan yana taşır. Dönem başlıkları
    aynen korunur; YYYY-MM-01 noktaları üretilmez. Tutarlar Bin USD,
    `DEĞ.` sütunları ise kaynakta yazıldığı gibi oran (0.10 = %10) kalır.
    Eski dosyaların ek dönem grubu sabit sütun konumu varsaymadan okunur.
    Eksik sektör satırı/sayısal hücre sıfıra çevrilmez; gerçek sıfır korunur.
    İkinci sütun hücresi boş genel TOPLAM, `(IL_GENEL_TOPLAM, TOPLAM_ETIKETI)`
    anahtarında korunur.

    `il_sektor_dogrula` (asgari satır sayısı + GENEL TOPLAM uzlaşımı) yalnızca
    il bülteninde çalışır: her il kendi TOPLAM satırını taşır, o yüzden
    uzlaştırılabilir. Ülke bülteninde bu satır hiç yayımlanmıyor (ölçüldü:
    2026-08 dosyasında 4869 veri satırında tek bir TOPLAM/TOPLAM satırı var —
    tüm ülkelerin genel toplamı — ülke başına ayrı satır yok), bu yüzden
    `ulke_seri_cek` ülke TOPLAM'ını sektör satırlarını toplayarak kendi
    hesaplar ve bu doğrulamaya ihtiyaç duymaz.
    """
    kitap = openpyxl.load_workbook(io.BytesIO(baytlar), data_only=True)
    try:
        if sayfa_adi not in kitap.sheetnames:
            raise RuntimeError(
                f"TİM {sayfa_adi} bülteni {anahtar}: '{sayfa_adi}' sayfası yok"
            )
        sayfa = kitap[sayfa_adi]
        yil = _yili_bul(sayfa)
        gruplar = next(sayfa.iter_rows(min_row=3, max_row=3, values_only=True))
        basliklar = next(sayfa.iter_rows(min_row=4, max_row=4, values_only=True))
        if tuple(sektor_adini_normalize(h) for h in basliklar[:2]) != (
            "SEKTÖR", ikinci_sutun,
        ):
            raise RuntimeError(
                f"TİM {sayfa_adi} bülteni {anahtar}: SEKTÖR/{ikinci_sutun} başlığı yok"
            )
        # Dönem blokları sabit şablondan değil başlık satırının KENDİ
        # yapısından türetilir: 2023 dosyalarında blok sırası değişiyor
        # (ör. 2023.01: '31 OCAK' | '1 - 31 OCAK' | '1 - 31 ARALıK') ve
        # sabit şablon bunları "bilinmeyen dönem/yıl başlıkları" diye
        # reddediyordu. Grup etiketi satırı bazı dosyalarda sütunlarıyla
        # hizalı değil, o yüzden hizaya değil SIRAYA güvenilir: 'DEĞ.'
        # sütunu bir bloğu kapatır, blok içinde yıl tekrarı yeni blok
        # başlatır. Yıl/DEĞ. dışı başlık hâlâ hata — şablon kayması
        # sessizce geçmemeli.
        donemler = [
            sektor_adini_normalize(h)
            for h in gruplar if h is not None and str(h).strip()
        ]
        gecerli = {str(yil - 1), str(yil), "DEĞ."}
        okunan = [(sutun, sektor_adini_normalize(h))
                  for sutun, h in enumerate(basliklar[2:], start=2)
                  if sektor_adini_normalize(h)]
        if any(baslik not in gecerli for _, baslik in okunan) or not okunan:
            raise RuntimeError(
                f"TİM {sayfa_adi} bülteni {anahtar}: bilinmeyen dönem/yıl başlıkları"
            )
        bloklar: list[list[tuple[int, str]]] = [[]]
        for sutun, baslik in okunan:
            simdiki = bloklar[-1]
            if simdiki and (baslik in {b for _, b in simdiki}
                            or simdiki[-1][1] == "DEĞ."):
                bloklar.append([])
            bloklar[-1].append((sutun, baslik))
        if len(bloklar) != len(donemler):
            raise RuntimeError(
                f"TİM {sayfa_adi} bülteni {anahtar}: bilinmeyen dönem/yıl başlıkları"
            )
        sutunlar = {
            sutun: f"{donem} / {baslik}"
            for donem, blok in zip(donemler, bloklar)
            for sutun, baslik in blok
        }
        if len(set(sutunlar.values())) != len(sutunlar):
            raise RuntimeError(
                f"TİM {sayfa_adi} bülteni {anahtar}: yinelenen dönem başlığı"
            )

        varlik_adi = _VARLIK_ADLARI.get(ikinci_sutun, ikinci_sutun.lower())
        noktalar = {}
        for satir in sayfa.iter_rows(min_row=5, values_only=True):
            sektor, ikinci = (sektor_adini_normalize(h) for h in satir[:2])
            if not sektor and not ikinci:
                continue
            # Genel toplam iki imzayla gelir: 2023'te boş ikinci sütun
            # ('TOPLAM', boş), 2026'da ('TOPLAM', 'TOPLAM'). İkisi de aynı satır.
            if sektor == TOPLAM_ETIKETI and (not ikinci or ikinci == TOPLAM_ETIKETI):
                ikinci = IL_GENEL_TOPLAM
            if not sektor or not ikinci:
                raise RuntimeError(
                    f"TİM {sayfa_adi} bülteni {anahtar}: eksik {varlik_adi}/sektör anahtarı"
                )
            degerler = {}
            for sutun, etiket in sutunlar.items():
                hucre = satir[sutun]
                if hucre is None:
                    continue
                if isinstance(hucre, bool) or not isinstance(hucre, (int, float)):
                    raise RuntimeError(
                        f"TİM {sayfa_adi} bülteni {anahtar}: sayısal olmayan hücre "
                        f"{ikinci}/{sektor}/{etiket}: {hucre!r}"
                    )
                degerler[etiket] = float(hucre)
            if not degerler:
                raise RuntimeError(
                    f"TİM {sayfa_adi} bülteni {anahtar}: boş veri {ikinci}/{sektor}"
                )
            if (ikinci, sektor) in noktalar:
                # Ölçüm (2024.10): ADANA/ANTALYA TOPLAM satırı ikinci kez,
                # aylık sütunları sıfır ama YTD'de küçük bir dilim taşıyan
                # ek satır olarak geliyor — aynı anahtarın PARÇASI. Parçalar
                # toplanır; BİREBİR AYNI satır tekrarı ise şablon kaymasıdır
                # ve toplamak değeri ikiye katlardı, o yüzden hata.
                if noktalar[ikinci, sektor] == degerler:
                    raise RuntimeError(
                        f"TİM {sayfa_adi} bülteni {anahtar}: yinelenen {varlik_adi}/sektör "
                        f"{(ikinci, sektor)!r}"
                    )
                for etiket, deger in degerler.items():
                    noktalar[ikinci, sektor][etiket] = (
                        noktalar[ikinci, sektor].get(etiket, 0.0) + deger
                    )
                continue
            noktalar[ikinci, sektor] = degerler
        if sayfa_adi == IL_SAYFA_ADI:
            il_sektor_dogrula(noktalar, anahtar)
        return noktalar
    finally:
        kitap.close()


def il_sektor_dogrula(
    noktalar: dict[tuple[str, str], dict[str, float]], anahtar: str,
) -> None:
    """Kısmi okuma ve kayıp il TOPLAM anahtarları sessizce geçmemeli."""
    iller = {il for il, _ in noktalar if il != IL_GENEL_TOPLAM}
    if len(iller) < ASGARI_IL_SAYISI:
        raise RuntimeError(
            f"TİM il bülteni {anahtar}: yalnızca {len(iller)} il okundu "
            f"(asgari {ASGARI_IL_SAYISI}) — şablon değişmiş olabilir"
        )
    eksik = sorted(il for il in iller if (il, TOPLAM_ETIKETI) not in noktalar)
    if eksik:
        raise RuntimeError(
            f"TİM il bülteni {anahtar}: TOPLAM anahtarı bulunamadı: {', '.join(eksik)}"
        )
    genel = noktalar.get((IL_GENEL_TOPLAM, TOPLAM_ETIKETI))
    if genel is not None:
        for etiket, toplam in genel.items():
            # Değişim oranları toplanamaz; yalnızca tutar sütunları uzlaşır.
            if etiket.endswith(" / DEĞ."):
                continue
            if any(etiket not in noktalar[il, TOPLAM_ETIKETI] for il in iller):
                raise RuntimeError(
                    f"TİM il bülteni {anahtar}: il TOPLAM değeri eksik: {etiket}"
                )
            il_toplami = sum(noktalar[il, TOPLAM_ETIKETI][etiket] for il in iller)
            # Ölçüldü (2026.08): cari yıl sütunları bire bir; GEÇMİŞ yıl
            # sütunlarında TİM'in il yuvarlamaları birikir (göreli ~%0.002).
            # Mutlak 0.5 bu yüzden geçmiş yıl sütununda patlar; eşik göreli.
            # ponytail: sabit %0.01; il sayısı 100'i aşarsa yeniden ölç.
            if abs(il_toplami - toplam) > toplam * 0.01 + TOLERANS:
                raise RuntimeError(
                    f"TİM il bülteni {anahtar}: {etiket} il toplamı "
                    f"{il_toplami:.1f} ile GENEL TOPLAM {toplam:.1f} uyuşmuyor"
                )


def _yili_bul(sayfa) -> int:
    """Yıl, birinci satırdaki `31.08.2026 TARİHİ İTİBARİYLE ...` başlığından.

    Dosya adından da çıkarılabilirdi ama o zaman ayrıştırma URL'e bağımlı
    olurdu; başlık dosyanın kendi beyanıdır ve tutarsızlık burada yakalanır.
    """
    for satir in sayfa.iter_rows(min_row=1, max_row=3, values_only=True):
        for hucre in satir:
            metin = str(hucre or "")
            for parca in metin.replace(".", " ").split():
                if len(parca) == 4 and parca.isdigit() and 2000 < int(parca) < 2100:
                    return int(parca)
    raise RuntimeError("TİM bülteninin başlığında yıl bulunamadı")


def sifir_aylari_at(
    noktalar: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    """`TOPLAM` sıfır olan ayı TÜM sektörlerden düşer.

    Cari yıl dosyasında yayımlanmamış aylar sıfırdır. Kararı toplam satırı
    verir: tek bir sektörün gerçekten sıfır olduğu bir ay olabilir, ama
    toplamın sıfır olduğu ay yayımlanmamış aydır.
    """
    toplam = noktalar.get(TOPLAM_ETIKETI)
    if not toplam:
        raise RuntimeError("TİM bülteninde TOPLAM satırı bulunamadı")
    yayimlanmamis = {tarih for tarih, deger in toplam.items() if deger == 0}
    return {
        ad: {t: d for t, d in aylik.items() if t not in yayimlanmamis}
        for ad, aylik in noktalar.items()
    }


def dogrula(noktalar: dict[str, dict[str, float]], anahtar: str) -> None:
    """I. TARIM + II. SANAYİ + III. MADENCİLİK == TOPLAM, her ay için.

    Ölçüldü: 2019–2026 dosyalarında fark tam olarak sıfır. Şablon kayması
    (sütun eklenmesi, satır kayması) bu eşitliği bozar ve sessiz yanlış
    veri yerine hata verir.
    """
    if len(noktalar) < ASGARI_SEKTOR_SAYISI:
        raise RuntimeError(
            f"TİM bülteni {anahtar}: yalnızca {len(noktalar)} sektör satırı "
            f"okundu (asgari {ASGARI_SEKTOR_SAYISI}) — şablon değişmiş olabilir"
        )
    eksik = [ad for ad in (*ANA_GRUPLAR, TOPLAM_ETIKETI) if ad not in noktalar]
    if eksik:
        raise RuntimeError(
            f"TİM bülteni {anahtar}: ana grup satırı bulunamadı: "
            f"{', '.join(eksik)}"
        )
    for tarih, toplam in noktalar[TOPLAM_ETIKETI].items():
        gruplar = sum(noktalar[ad].get(tarih, 0.0) for ad in ANA_GRUPLAR)
        if abs(gruplar - toplam) > TOLERANS:
            raise RuntimeError(
                f"TİM bülteni {anahtar}: {tarih} ana grup toplamı "
                f"{gruplar:.1f} ile TOPLAM {toplam:.1f} uyuşmuyor"
            )


def _bulten_indir(url: str, session=None) -> bytes | None:
    """404 → None (o ay henüz yayımlanmamış); diğer hatalar yükselir."""
    http = session or requests
    yanit = http.get(url, timeout=ZAMAN_ASIMI)
    if yanit.status_code == 404:
        return None
    if yanit.status_code != 200:
        raise RuntimeError(f"TİM HTTP {yanit.status_code} ({url})")
    return yanit.content


def _bulteni_getir(
    yil: int, ay: int, onbellek: dict, session=None
) -> dict[str, dict[str, float]] | None:
    """Bir yılın bültenini önbellekten ya da ağdan alır; yoksa geriye gider.

    Cari yıl için istenen ay yayımlanmamış olabilir; ay ay geriye inilir.
    Yılın hiçbir ayı yoksa None döner — o yıl atlanır, diğer yıllar
    etkilenmez (ör. 1 Ocak'ta cari yıl dosyası henüz yoktur).
    """
    for deneme_ayi in range(ay, 0, -1):
        anahtar = f"{yil}.{deneme_ayi:02d}"
        if anahtar in onbellek:
            return onbellek[anahtar]
        baytlar = _bulten_indir(bulten_url(yil, deneme_ayi), session)
        if baytlar is None:
            continue
        noktalar = sifir_aylari_at(sayfayi_ayikla(baytlar))
        dogrula(noktalar, anahtar)
        onbellek[anahtar] = noktalar
        return noktalar
    return None


def seri_cek(seri, onbellek: dict | None = None, session=None,
             bugun: date | None = None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `onbellek` verilirse ayrıştırılmış bülten noktaları koşu boyunca
    paylaşılır: 13 seri aynı 8 dosyayı okuduğu için yoksa 104 indirme
    olurdu.

    Sektör bültende ad değiştirmiş olabilir (`Elektrik Elektronik` →
    `Elektrik ve Elektronik`); `seri.tim_eski_adlar` verilirse eski adlar
    da denenir. Bir bültende sektör hiçbir adıyla yoksa RuntimeError:
    kısmi kayıp, hiç eşleşmemekten çok daha sık ve sessizce geçebilir.
    """
    bugun = bugun or date.today()
    onbellek = {} if onbellek is None else onbellek
    adaylar = [seri.tim_sektor, *(seri.tim_eski_adlar or ())]

    kendi: dict[str, float] = {}
    for yil, ay in cekilecek_bultenler(bugun):
        noktalar = _bulteni_getir(yil, ay, onbellek, session)
        if noktalar is None:
            continue
        eslesen = [ad for ad in adaylar if ad in noktalar]
        if not eslesen:
            raise RuntimeError(
                f"TİM bülteninde sektör bulunamadı: {seri.tim_sektor!r} "
                f"({seri.id}) — bülten {yil} — katalogdaki ad(lar) bültenle "
                "eşleşmiyor olabilir (ad değişmiş olabilir, tim_eski_adlar'a "
                "eklemeyi düşünün)"
            )
        for ad in eslesen:
            kendi.update(noktalar[ad])

    if not kendi:
        raise RuntimeError(
            f"TİM bültenlerinde hiç nokta bulunamadı: {seri.id}"
        )

    df = pd.DataFrame(sorted(kendi.items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)


def cekilecek_il_bultenleri(bugun: date) -> list[tuple[int, int]]:
    """Her ay ayrı dosya: 2023 Ocak'tan bugüne kadar tüm (yıl, ay) çiftleri.

    İl VE ülke karşılaştırma bültenleri aynı pencereyi paylaşır (ikisi de
    2023-01'den itibaren yayımlanıyor; ölçüldü), bu yüzden fonksiyon adı
    "il" olsa da `ulke_seri_cek` de aynı listeyi kullanır.

    Sektörel bültenin aksine bu dosya bir yılı değil tek bir ayı taşır,
    bu yüzden `cekilecek_bultenler`in aksine burada yıl başına tek dosya
    yetmez — pencere kadar dosya indirilir.
    """
    aylar = []
    yil, ay = ILK_IL_YIL, ILK_IL_AY
    while (yil, ay) <= (bugun.year, bugun.month):
        aylar.append((yil, ay))
        yil, ay = (yil + 1, 1) if ay == 12 else (yil, ay + 1)
    return aylar


def _sadelestir(metin: str) -> str:
    """Türkçe harf varyantlarını eşitler: bülten 'NİSAN' da 'NISAN' da yazıyor."""
    esleme = str.maketrans("İIıiĞğÜüŞşÖöÇç", "IIIIGGUUSSOOCC")
    return metin.translate(esleme).upper()


def _aylik_sutun(
    noktalar: dict[tuple[str, str], dict[str, float]], yil: int, ay: int,
) -> str:
    """O ayın tutar sütununun etiketini bültenin kendi başlıklarından bulur.

    Etiket kurulamıyor, ARANIYOR: bülten ay adını iki yazımla ('NİSAN' /
    'NISAN') ve ayın gün sayısını kendi kuralıyla ('1 - 30 MART') yazıyor,
    yani `calendar.monthrange` ile kurulan etiket tutmuyor. Aranan sütun
    '1 - ' ile başlar (YTD '1 OCAK - ' ile başlar), ay adını taşır ve
    '/ <yıl>' ile biter ('DEĞ.' oran sütunu dışlanır). Bir önceki ayın
    sütunu da aynı yılı taşıdığı için ay adı eşleşmesi zorunlu.
    """
    ay_adi = _sadelestir(AY_ADLARI[ay - 1])
    adaylar = {
        etiket
        for degerler in noktalar.values()
        for etiket in degerler
        if etiket.endswith(f"/ {yil}")
        and (sade := _sadelestir(etiket)).startswith("1 - ")
        and ay_adi in sade
    }
    if len(adaylar) != 1:
        raise RuntimeError(
            f"TİM il bülteni {yil}.{ay:02d}: aylık sütun belirlenemedi "
            f"({len(adaylar)} aday: {sorted(adaylar)})"
        )
    return adaylar.pop()


def _karsilastirma_seri_cek(
    seri, varlik_alani: str, varlik_adi: str, url_fn, ayikla_fn,
    onbellek: dict | None = None, session=None, bugun: date | None = None,
) -> pd.DataFrame:
    """İl×sektör ya da ülke×sektör karşılaştırma bülteninden tek satırın
    aylık serisini çeker — `il_seri_cek`/`ulke_seri_cek` ortak gövdesi.

    `onbellek` verilirse ayrıştırılmış `(yıl, ay) -> noktalar` eşlemesi koşu
    boyunca paylaşılır: 741 il serisi aynı ~40 aylık dosyayı, 674 ülke
    serisi de aynı sayıda dosyayı paylaşır. 404 (o ay henüz yayımlanmamış)
    de önbelleğe `None` olarak yazılır ki iki seri aynı eksik ayı iki kez
    denemesin.

    `seri.tim_sektor == "TOPLAM"` ise dönen değer bültenin kendi TOPLAM
    satırı DEĞİL, `varlik_alani`nin (il/ülke) TOPLAM-olmayan sektör
    satırlarının toplamıdır: il tarafında bülten TOPLAM satırı birlik
    bazlı bir fazlalık taşır (ölçüm: İstanbul Ağustos 2026 — sektör toplamı
    8.679.756,86, bülten TOPLAM satırı 8.800.137,83), ülke tarafında ise
    böyle bir satır hiç yayımlanmıyor — ikisi için de sektör satırlarını
    toplamak doğru ve tutarlı tek yoldur.

    Aylık sütun etiketi hesaplanarak bulunur: `'1 - <ayın son günü> <AY
    ADI> / <yıl>'`. Salt "1 - " öneki + "/ <yıl>" soneki YETMEZ: aynı
    yılın bülteninde bir önceki ayın da kendi sütunu vardır (ör. Ağustos
    dosyasında "1 - 31 TEMMUZ / 2026" de "/ 2026" ile biter) — bu yüzden
    ay adı ve gün sayısı da eşleştirilir.
    """
    bugun = bugun or date.today()
    onbellek = {} if onbellek is None else onbellek
    varlik = getattr(seri, varlik_alani)

    kendi: dict[str, float] = {}
    for yil, ay in cekilecek_il_bultenleri(bugun):
        anahtar = (yil, ay)
        if anahtar in onbellek:
            noktalar = onbellek[anahtar]
        else:
            baytlar = _bulten_indir(url_fn(yil, ay), session)
            noktalar = (
                None if baytlar is None
                else ayikla_fn(baytlar, f"{yil}.{ay:02d}")
            )
            onbellek[anahtar] = noktalar
        if noktalar is None:
            continue

        etiket = _aylik_sutun(noktalar, yil, ay)

        if seri.tim_sektor == TOPLAM_ETIKETI:
            satirlar = [
                (v, sektor) for v, sektor in noktalar
                if v == varlik and sektor != TOPLAM_ETIKETI
            ]
            if not satirlar:
                raise RuntimeError(
                    f"TİM {varlik_adi} bülteni {yil}.{ay:02d}: {varlik_adi} "
                    f"bulunamadı: {varlik!r}"
                )
        else:
            satirlar = [(varlik, seri.tim_sektor)]
            if satirlar[0] not in noktalar:
                raise RuntimeError(
                    f"TİM {varlik_adi} bülteni {yil}.{ay:02d}: {varlik_adi}/sektör "
                    f"bulunamadı: {satirlar[0]!r}"
                )

        toplam = 0.0
        for anahtar_satir in satirlar:
            degerler = noktalar[anahtar_satir]
            if etiket not in degerler:
                raise RuntimeError(
                    f"TİM {varlik_adi} bülteni {yil}.{ay:02d}: aylık sütun bulunamadı: "
                    f"{anahtar_satir} / {etiket!r}"
                )
            toplam += degerler[etiket]
        kendi[f"{yil}-{ay:02d}-01"] = toplam

    if not kendi:
        raise RuntimeError(
            f"TİM {varlik_adi} bültenlerinde hiç nokta bulunamadı: {seri.id}"
        )

    df = pd.DataFrame(sorted(kendi.items()), columns=["date", "value"])
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df.reset_index(drop=True)


def il_seri_cek(seri, onbellek: dict | None = None, session=None,
                 bugun: date | None = None) -> pd.DataFrame:
    """İl×sektör karşılaştırma bülteninden tek il/sektörün aylık serisini çeker.

    Ortak gövde `_karsilastirma_seri_cek`tedir; bu fonksiyon yalnızca il
    bültenine özgü parametreleri (sayfa adı, ikinci sütun, URL şeması)
    bağlar. 741 seri aynı ~40 aylık dosyayı paylaşır (bkz. o fonksiyonun
    docstring'i: TOPLAM sözleşmesi, aylık sütun eşleştirmesi).
    """
    return _karsilastirma_seri_cek(
        seri, "tim_il", "il", il_bazinda_url,
        lambda baytlar, anahtar: il_sektor_noktalari(baytlar, anahtar),
        onbellek=onbellek, session=session, bugun=bugun,
    )


def ulke_seri_cek(seri, onbellek: dict | None = None, session=None,
                   bugun: date | None = None) -> pd.DataFrame:
    """Ülke×sektör karşılaştırma bülteninden tek ülke/sektörün aylık
    serisini çeker. Ortak gövde `_karsilastirma_seri_cek`tedir (bkz.
    `il_seri_cek`, aynı önbellek/404/aylık sütun mantığını paylaşır).

    `seri.tim_sektor == "TOPLAM"` ise dönen değer ülkenin sektör
    satırlarının toplamıdır. İl bülteninin aksine burada "bülten TOPLAM
    satırından kaçınma" değil "hiç yayımlanmayan satırı türetme" durumu
    söz konusu (ölçüldü: 2026-08 dosyasında 4869 veri satırında tek bir
    TOPLAM/TOPLAM satırı var — genel toplam — ülke başına ayrı satır yok);
    sonuç yine de sektör satırlarının toplamıdır ve referans platformun
    "Toplam" kartıyla eşleşir (ölçüldü: ALMANYA Ağustos 2026 → 1.561.591,73,
    Temmuz 2026 → 1.860.767,43, Ağustos 2025 → 1.571.570,19).
    """
    return _karsilastirma_seri_cek(
        seri, "tim_ulke", "ülke", ulke_bazinda_url,
        lambda baytlar, anahtar: il_sektor_noktalari(
            baytlar, anahtar, sayfa_adi=ULKE_SAYFA_ADI, ikinci_sutun="ULKE",
        ),
        onbellek=onbellek, session=session, bugun=bugun,
    )
