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

# Modern (xlsx) yayının başladığı dosya. 2019'un tamamı bu dosyada.
ILK_YIL = 2019
ILK_AY = 12

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
) -> dict[tuple[str, str], dict[str, float]]:
    """Karşılaştırma tablosunu `{(il, sektör): {dönem / yıl: değer}}` okur.

    Bu dosya aylık zaman serisi değildir: ay, önceki ay ve yılbaşından
    bugüne birikimli karşılaştırmaları yan yana taşır. Dönem başlıkları
    aynen korunur; YYYY-MM-01 noktaları üretilmez. Tutarlar Bin USD,
    `DEĞ.` sütunları ise kaynakta yazıldığı gibi oran (0.10 = %10) kalır.
    Eski dosyaların ek dönem grubu sabit sütun konumu varsaymadan okunur.
    Eksik sektör satırı/sayısal hücre sıfıra çevrilmez; gerçek sıfır korunur.
    İl hücresi boş genel TOPLAM, `(IL_GENEL_TOPLAM, TOPLAM_ETIKETI)`
    anahtarında korunur; tutarları il toplamlarıyla doğrulanır.
    """
    kitap = openpyxl.load_workbook(io.BytesIO(baytlar), data_only=True)
    try:
        if IL_SAYFA_ADI not in kitap.sheetnames:
            raise RuntimeError(
                f"TİM il bülteni {anahtar}: '{IL_SAYFA_ADI}' sayfası yok"
            )
        sayfa = kitap[IL_SAYFA_ADI]
        yil = _yili_bul(sayfa)
        gruplar = next(sayfa.iter_rows(min_row=3, max_row=3, values_only=True))
        basliklar = next(sayfa.iter_rows(min_row=4, max_row=4, values_only=True))
        if tuple(sektor_adini_normalize(h) for h in basliklar[:2]) != (
            "SEKTÖR", "ILLER",
        ):
            raise RuntimeError(f"TİM il bülteni {anahtar}: SEKTÖR/ILLER başlığı yok")
        donemler = [sektor_adini_normalize(h) for h in gruplar if h is not None and str(h).strip()]
        yillar = (str(yil - 1), str(yil), "DEĞ.")
        bloklar = [yillar, (str(yil), "DEĞ."), yillar]
        if len(donemler) == 4:
            bloklar.insert(0, yillar)
        beklenen = tuple(h for blok in bloklar for h in blok)
        okunan = tuple(sektor_adini_normalize(h) for h in basliklar[2:])
        # Sonda yalnızca biçimlendirme için ayrılmış boş sütunlar olabilir.
        while okunan and not okunan[-1]:
            okunan = okunan[:-1]
        if len(donemler) not in (3, 4) or okunan != beklenen:
            raise RuntimeError(f"TİM il bülteni {anahtar}: bilinmeyen dönem/yıl başlıkları")
        etiketler = [
            f"{donem} / {baslik}"
            for donem, blok in zip(donemler, bloklar)
            for baslik in blok
        ]
        if len(set(etiketler)) != len(etiketler):
            raise RuntimeError(f"TİM il bülteni {anahtar}: yinelenen dönem başlığı")
        sutunlar = dict(enumerate(etiketler, start=2))

        noktalar = {}
        for satir in sayfa.iter_rows(min_row=5, values_only=True):
            sektor, il = (sektor_adini_normalize(h) for h in satir[:2])
            if not sektor and not il:
                continue
            # Genel toplam iki imzayla gelir: 2023'te boş IL ('TOPLAM',
            # boş), 2026'da ('TOPLAM', 'TOPLAM'). İkisi de aynı satır.
            if sektor == TOPLAM_ETIKETI and (not il or il == TOPLAM_ETIKETI):
                il = IL_GENEL_TOPLAM
            if not sektor or not il:
                raise RuntimeError(f"TİM il bülteni {anahtar}: eksik il/sektör anahtarı")
            if (il, sektor) in noktalar:
                raise RuntimeError(
                    f"TİM il bülteni {anahtar}: yinelenen il/sektör {(il, sektor)!r}"
                )
            degerler = {}
            for sutun, etiket in sutunlar.items():
                hucre = satir[sutun]
                if hucre is None:
                    continue
                if isinstance(hucre, bool) or not isinstance(hucre, (int, float)):
                    raise RuntimeError(
                        f"TİM il bülteni {anahtar}: sayısal olmayan hücre "
                        f"{il}/{sektor}/{etiket}: {hucre!r}"
                    )
                degerler[etiket] = float(hucre)
            if not degerler:
                raise RuntimeError(f"TİM il bülteni {anahtar}: boş veri {il}/{sektor}")
            noktalar[il, sektor] = degerler
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
