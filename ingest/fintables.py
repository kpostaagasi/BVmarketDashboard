"""Fintables (BIST) çeyreklik KAP finansal tabloları istemcisi.

Kaynak gerçekleri 2026-09-29'da canlı ölçüldü (sıfırdan yeniden keşfetmeye
çalışmayın):

- **Tablolar kimlik doğrulaması olmadan açılır, ücret duvarı yoktur.** Üç
  tablo da tek bir Next.js App Router rotasından gelir:
  `https://fintables.com/sirketler/<BIST KOD>/finansal-tablolar/<tablo slug>`.
  Slug'lar tam olarak `bilanco`, `gelir-tablosu`, `nakit-akim-tablosu`
  (ölçüldü: `.../sirketler/THYAO/bilanco` **404** verir — `finansal-tablolar`
  segmenti atlanırsa rota çalışmıyor; bu üç slug'ı sayfanın sol
  menüsünden okumak gerekiyor).
- **Veri sunucu tarafında RSC "flight" yükünde gömülü, ayrı API ucu yok.**
  Sayfada `__NEXT_DATA__`, `/_next/data/` rotası ve JSON-LD tablo verisi
  YOK; tek yapı taşıyıcı `<script>self.__next_f.push([1,"…"])</script>`
  çağrıları. Bunların JSON çözülmüş gövdeleri birleştirilince içinde
  `{"sheetType":"<slug>","data":{"periods":[…],"data":[…]}}` nesnesi duruyor:
  `data.periods` = dönem sütunları (`{"year":…,"month":…,"is_inflation_adjusted":…,
  "is_consolidated":…,"source_period":{…}}`), `data.data` = gruplar
  `values` dizisi `periods` ile **konumsal** hizalıdır. Bu yüzden adaptör HTML
  tablosunu KAZIMAZ — yapılandırılmış yükü ayrıştırır (bkz. aşağıdaki uyarı).
- **Kısa/eksik User-Agent 403 alır.** Ölçüldü: `"User-Agent: Mozilla/5.0"`
  ve User-Agent'sız istek bu rotada **403** döner (~5,5 KB hata sayfası);
  tam tarayıcı User-Agent'ı 200 ile 483 KB tablo verisi döner. Bu yüzden
  `_BASLIKLAR` tam Chrome dizisini taşır (repo'da aynı gerekçe:
  `ingest.tav`/`ingest.tspb`).
- **Düz metin ayrıştırma BU SAYFA İÇİN BOZUKTUR.** Tablo hücresi mutlak
  değerle önceki çeyreğe göre değişim yüzdesini AYNI `<td>` içinde, yalnızca
  fare üzerine gelince görünen (`opacity-0 group-hover:opacity-100`) bir rozet
  içinde taşır: `<span class="absolute left-full …">…%</span>13</span></span><span
  class="inline-flex items-center tabular-nums">80.346.000</span>`. Etiketleri
  soyup birleştiren bir ayrıştırıcı "%1380.346.000" gibi birbirine geçmiş
  değerler üretir (ölçüldü). Yükten okunduğu için bu tuzak hiç oluşmuyor.
- **Geçmiş, sayfada görünenden ÇOK daha derin.** Tablo başlığı yalnızca son
  5 çeyreği gösterir (ölçüldü, THYAO bilanço: 2026/6, 2026/3, 2025/12,
  2025/9, 2025/6) ama yükteki `periods` dizisi 41 (bilanço) / 42 (gelir ve
  nakit akım) çeyrek taşır, 2016'ya kadar (ölçüldü: THYAO bilanço 2016/6,
  gelir tablosu 2016/3). Sayfadaki 5 sütunla birebir doğrulandı: "Nakit ve
  Nakit Benzerleri" 2026/6 → yük `80346000000` TL, sayfa "80.346.000" (Bin TRY,
  yani 80346000000/1000); 2026/3 → 71141000000 / "71.141.000"; 2025/12 →
  86035000000 / "86.035.000"; 2025/9 → 100325000000 / "100.325.000"; 2025/6 →
  98791000000 / "98.791.000". **Yük ham TL taşır, sayfa Bin TL'de gösterir;
  adaptör hiçbir ölçekleme yapmaz** (`unit: "TL"` + `olcek`'siz kullanılmalı;
  "Bin TL" istenirse katalog `olcek: 0.001` verir).
- **Değerler YIL BAŞINDAN KÜMÜLATİFTİR, çeyrek-tek DEĞİL.** Ölçüldü (THYAO
  gelir tablosu "Dönem Karı (Zararı)"): 2025/3 −1.854mn, 2025/6 24.935mn,
  2025/9 80.951mn, 2025/12 118.117mn — çeyrek-tek olsaydı yıllık toplam
  222.149mn çıkardı, kendi 4. sütunundan (118.117mn) büyük olurdu. Site de
  bunu teyit ediyor: türetilmiş çeyrek-tek ölçütlerin adları açıkça
  "(Çeyreklik)" ile ayrılmış (`ceyreklik_net_kar`, "Net Kar Marjı (Çeyreklik)"
  vb.) ve bunlar `allowed: false` — abone dışına kapalı. Bu adaptör yalnızca
  KÜMÜLATİF hâli sunar; çeyrek-tek türetme kapsam dışıdır.
- **Birimler ham TL, işaret kaynakta.** Gider satırlarının başlığında `(-)`
  vardır ("Genel Yönetim Giderleri (-)") ve `values` dizisinde de NEGATİF
  gelir (ölçüldü: −13.300.000.000). Bu nedenle "satış/gider" ayrımı
  katalogda `fintables_kalem` metninin kendisiyle yapılır; işaret ayrıca
  çevrilmez.
- **Satır sözlüğü ŞİRKETE GÖRE DEĞİŞİR — global bir kalem listesi YOKTUR.**
  Aynı "bilanco" tablosu iki farklı TFRS şablonunu kullanıyor (ölçüldü):
  THYAO sanayi şablonunda bölümler "Dönen Varlıklar / Duran Varlıklar /
  Kısa Vadeli Yükümlülükler / Uzun Vadeli Yükümlülükler / Özkaynaklar" ve
  satır dili sade ("Ticari Alacaklar", "Stoklar"); GARAN banka şablonunda
  bölüm "Finansal Varlıklar (Net)" ve satırlar daha ayrıntılı ("Gerçeğe Uygun
  Değer Farkı Kâr Zarara Yansıtılan Finansal Varlıklar", "Donuk Finansal
  Varlıklar", "KREDİLER (Net)"). Bu yüzden `fintables_kalem` sabit bir enum
  DEĞİL, ilgili şirketin sayfasından BİREBİR kopyalanan metindir; katalog
  satırı yazılmadan önce o şirketin tablosu okunmalıdır. Aynı sebeple
  `core/catalog.py`'de `GECERLI_FINTABLES_KALEMLER` gibi bir liste
  tanımlanmamalı — yalnızca tablo slug'ları sabittir.
- **Satır kimliği (bölüm, kalem) çiftidir.** Bilançoda 15 kalem adı İKİ bölümde
  tekrarlanır ("Finansal Borçlar" hem Kısa hem Uzun Vadeli Yükümlülüklerde;
  "Türev Araçlar", "Peşin Ödenmiş Giderler" vb.) — bu yüzden `fintables_bolum`
  opsiyoneldir ama o kalemler için ZORUNLUDUR. Gelir tablosunda 30 satırın
  tamamı bölümsüz (bölüm başlığı `""`/`None`) ve adları tekil. Nakit akım
  tablosunda 56 satır var ve "Alınan Faiz", "Diğer Nakit Girişleri (Çıkışları)"
  adları AYNI bölüm içinde iki kez geçiyor: bölüm bile ayırt edemiyor, bu iki
  kalem kaynakta gerçekten belirsiz — `seri_cek` bunu isim listesiyle birlikte
  RuntimeError olarak bildirir, tahminle bir satır seçmez.
- **Eksik değer `null` gelir, `0` DEĞİL** (ölçüldü: bilançoda "Finans Sektörü
  Faaliyetlerinden Alacaklar" yalnızca 2025/12'de 0, gerisi boş; gelir
  tablosunda "Yurt İçi Satışlar" kırılımı yalnızca belirli dönemlerde
  raporlanmış). `null` nokta ÜRETİLMEZ — seri o dönemde kesik kalır, 0
  yazılmaz.
- **Günlük hisse fiyatı YOK.** Referans sitede "günlük hisse fiyatları"
  geçse de kamuya açık sayfalarda fiyat geçmişi serisi bulunmuyor: şirket
  ana sayfası yalnızca tek günün anlık görüntüsünü (bugünkü fiyat, dünkü
  kapanış, gün içi en yüksek/en düşük) veriyor, `/fiyatlar` ve
  `/fiyat-gecmisi` 404. Site de fiyat takibi için kullanıcıyı giriş gerektiren
  "İşlem Ekranı"na yönlendiriyor. Bu adaptör yalnızca finansal tabloları
  kapsar.
- **Lisans/lisans gecikmesi kısıtı.** Fintables BIST verisini lisanslı,
  gecikmeli olarak sunar; burada yalnızca siteye kimlik doğrulaması olmadan
  yayımlanan, herkese açık sayfalardaki içerik okunur. Hiçbir koruma atlanmaz,
  abonelik uçlarına erişilmez. Yeniden dağıtım/ticari kullanım için
  lisans koşulları ayrıca incelenmelidir.

Ölçülen tablo kapsamı (THYAO, 2026-09-29): bilanço 5 bölüm / 68 satır / 41
çeyrek; gelir tablosu 7 bölüm (başlıksız) / 30 satır / 42 çeyrek; nakit akım
tablosu 3 bölüm (başlıksız) / 56 satır / 42 çeyrek. Tamamı konsolide
(`is_consolidated: true`), enflasyondan arındırılmamış
(`is_inflation_adjusted: false`).
"""
from __future__ import annotations

import json
import re

import pandas as pd
import requests

TABAN = "https://fintables.com"
ZAMAN_ASIMI = 60
_BASLIKLAR = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# Tablo slug'ı = URL segmenti = yükteki `sheetType`. Aynı zamanda
# `core/catalog.py::GECERLI_FINTABLES_TABLOLARI` ile birebir aynı olmalı.
GECERLI_TABLOLAR = ("bilanco", "gelir-tablosu", "nakit-akim-tablosu")

# RSC flight yükünün sayfadaki taşıyıcısı. Gövde bir JSON string'idir
# (tırnaklar `\\\"` kaçışlı) — bu yüzden önce `json.loads` ile çözülür.
_FLIGHT = re.compile(r'self\.__next_f\.push\(\[1,(".*?")\]\)</script>', re.S)

# Çeyrek SONU ayı -> çeyreğin İLK ayı (repo kuralı: "çeyrekselde çeyreğin
# İLK ayı"; bkz. ingest/tspb.py, ingest/tabgida.py).
_CEYREK_ILK_AY = {"03": "01", "06": "04", "09": "07", "12": "10"}


def _uc_kismi_cikar(metin: str, baslangic: int) -> str:
    """`baslangic`'taki `{` ile eşleşen `}`'e kadar olan JSON nesnesini döner.

    Süslü parantez sayımı STRINGLERİN İÇİNDE de saymamak zorunda (satır
    etiketlerinde `{}` geçebilir), bu yüzden tırnak/escape durumu izlenir."""
    derinlik = 0
    tirnak = False
    kacis = False
    for i in range(baslangic, len(metin)):
        c = metin[i]
        if kacis:
            kacis = False
        elif c == "\\":
            kacis = True
        elif c == '"':
            tirnak = not tirnak
        elif tirnak:
            continue
        elif c == "{":
            derinlik += 1
        elif c == "}":
            derinlik -= 1
            if derinlik == 0:
                return metin[baslangic : i + 1]
    raise RuntimeError(
        f"Fintables flight yükünde eşleşen '}}' bulunamadı (konum {baslangic})"
    )


def _tablo_yuku(html: str, tablo: str) -> dict:
    """Sayfadaki RSC flight yükünden `{"sheetType": tablo, "data": {…}}`
    nesnesini sözlük olarak döner."""
    tampon = "".join(json.loads(p) for p in _FLIGHT.findall(html))
    isaret = tampon.find('{"sheetType":"%s"' % tablo)
    if isaret < 0:
        raise RuntimeError(
            f"Fintables flight yükünde sheetType={tablo!r} bulunamadı "
            f"({len(tampon)} karakterlik yük tarandı) — sayfa şablonu değişmiş olabilir"
        )
    return json.loads(_uc_kismi_cikar(tampon, isaret))


def _satirlari_cikar(yuk: dict) -> dict[tuple[str, str], list[list]]:
    """Yükten `{(bölüm, kalem): [values, …]}` sözlüğü çıkarır.

    Bölüm adı boş/None olan gruplarda `""` kullanılır (gelir ve nakit akım
    tabloları bölümsüzdür). `values` `periods` ile konumsal hizalıdır.

    Değer LISTESİ tutulur çünkü nakit akım tablosunda "Alınan Faiz" ve
    "Diğer Nakit Girişleri (Çıkışları)" adları AYNI bölüm içinde iki kez
    geçiyor ve kaynak bu ikisini ne `title`/`sign`/`level` ne de bölüm
    başlığıyla ayırt ediyor (ölçüldü, THYAO: değer dizileri farklı —
    biri yoğun, diğeri seyrek ve negatif). Bu bir hata değil, kaynağın
    kendi belirsizliği: tablonun KALAN 54 satırı kullanılabilir kalmalı,
    belirsizlik yalnızca o satır İSTENDİĞİNde `seri_cek` içinde bildirilir.
    """
    satirlar: dict[tuple[str, str], list[list]] = {}
    for bolum in yuk["data"]["data"]:
        baslik = bolum.get("title") or ""
        for kalem in bolum.get("children", []):
            satirlar.setdefault((baslik, kalem["title"]), []).append(kalem["values"])
    return satirlar


def tablo_verileri(sirket: str, tablo: str, session=None) -> tuple[list[dict], dict]:
    """`<sirket>` için `<tablo>` sayfasını çekip `(periods, satırlar)` döner.

    `periods`: dönem sütunları (yükteki sırayla, YENİDEN ESKİYE).
    `satırlar` : `{(bölüm, kalem): values}` — `values` `periods` ile hizalı.
    """
    if tablo not in GECERLI_TABLOLAR:
        raise RuntimeError(
            f"Fintables: geçersiz tablo {tablo!r} "
            f"(geçerli: {', '.join(GECERLI_TABLOLAR)})"
        )
    url = f"{TABAN}/sirketler/{sirket}/finansal-tablolar/{tablo}"
    http = session or requests
    yanit = http.get(url, headers=_BASLIKLAR, timeout=ZAMAN_ASIMI)
    yanit.raise_for_status()
    yanit.encoding = "utf-8"
    yuk = _tablo_yuku(yanit.text, tablo)
    return yuk["data"]["periods"], _satirlari_cikar(yuk)


def _donem_tarihi(period: dict) -> str:
    """Yük dönemini ("2026/6") repo sözleşmesindeki çeyrek-ilk-ay damgasına
    çevirir: 2026/6 -> "2026-04-01"."""
    ilk_ay = _CEYREK_ILK_AY.get(f"{int(period['month']):02d}")
    if ilk_ay is None:
        raise RuntimeError(
            f"Fintables: beklenmeyen çeyrek sonu ayı {period['month']!r} "
            f"(beklenen: {sorted(_CEYREK_ILK_AY)})"
        )
    return f"{int(period['year'])}-{ilk_ay}-01"


def seri_cek(seri, onbellek: dict | None = None, session=None) -> pd.DataFrame:
    """Tam pencereyi yeniden çeker (artımlı değil — revizyonlar yakalanmalı).

    `onbellek` verilirse (sirket, tablo) başına indirilen + ayrıştırılan sayfa
    koşu boyunca paylaşılır: aynı şirketin üç tablosundaki onlarca seri tek
    şirkette üç indirme yapılmasını sağlar.

    Dönen değerler HAM TL'dir (kaynak yükünün kendisi; sayfa Bin TL'de
    gösterir). Çeyrek-tek değil, YIL BAŞINDAN KÜMÜLATİFTİR — bkz. modül
    docstring'i.
    """
    onbellek = {} if onbellek is None else onbellek
    sirket = seri.fintables_sirket
    tablo = seri.fintables_tipi
    kalem = seri.fintables_kalem
    bolum = getattr(seri, "fintables_bolum", None)

    anahtar = f"{sirket}/{tablo}"
    if anahtar not in onbellek:
        onbellek[anahtar] = tablo_verileri(sirket, tablo, session=session)
    periods, satirlar = onbellek[anahtar]

    adaylar = [b for b, k in satirlar if k == kalem and (bolum is None or b == bolum)]
    if not adaylar:
        raise RuntimeError(
            f"Fintables: {seri.id} — {sirket}/{tablo} tablosunda satır bulunamadı "
            f"(fintables_bolum={bolum!r}, fintables_kalem={kalem!r})"
        )
    # Bölüm verilmemişse kalem adı TEK başına ayırt etmeli (bilançodaki 15
    # tekrar eden adın çoğu bu yolla kasten reddedilir); bölüm verilmiş olsa
    # bile AYNI bölümde tekrar eden ad kalan belirsizliktir.
    adaylar = sorted(set(adaylar))
    toplam = sum(len(satirlar[(b, kalem)]) for b in adaylar)
    if len(adaylar) == 1 and toplam == 1:
        degerler = satirlar[(adaylar[0], kalem)][0]
    else:
        raise RuntimeError(
            f"Fintables: {seri.id} — {kalem!r} adı {sirket}/{tablo} tablosunda "
            f"{toplam} satırda geçiyor ve kaynak onları ne bölüm ne de "
            f"işaret düzeyiyle ayırt ediyor (adaylar: "
            f"{', '.join(repr(b or '-') for b in adaylar)})"
        )
    if len(degerler) != len(periods):
        raise RuntimeError(
            f"Fintables: {seri.id} — {kalem!r} satırında {len(degerler)} değer "
            f"var ama {len(periods)} dönem tanımlı; şablon değişmiş olabilir"
        )

    noktalar: list[tuple[str, float]] = []
    for period, deger in zip(periods, degerler):
        if deger is None:
            continue  # yayımlanmamış/raporlanmamış — 0 DEĞİL, nokta yok
        noktalar.append((_donem_tarihi(period), float(deger)))

    if not noktalar:
        raise RuntimeError(
            f"Fintables: {seri.id} — {sirket}/{tablo} tablosunda {kalem!r} "
            "satırı bulundu ama HİÇBİR dönemde değeri yok"
        )
    df = (
        pd.DataFrame(noktalar, columns=["date", "value"])
        .drop_duplicates("date", keep="last")
        .sort_values("date")
        .reset_index(drop=True)
    )
    if seri.start_date:
        df = df[df["date"] >= seri.start_date]
    return df
