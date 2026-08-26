import Link from "next/link";
import { getSeries, listSeries } from "@/lib/data";
import ChartClient from "@/components/ChartClient";
import SourceNote from "@/components/SourceNote";

const HISSELER = ["TUPRS", "THYAO", "FROTO", "KARSN", "TTRAK", "MGROS", "TOASO", "EBEBK"];
const SIK_ARANAN = [
  { slug: "ihracat", ad: "İhracat" },
  { slug: "enflasyon", ad: "Enflasyon" },
  { slug: "altin", ad: "Altın" },
  { slug: "brent-petrol", ad: "Brent Petrol" },
  { slug: "bankacilik", ad: "Bankacılık" },
  { slug: "sigorta", ad: "Sigorta" },
];
const SEKTORLER = [
  { slug: "bankacilik", ad: "Bankacılık" },
  { slug: "holding", ad: "Holding" },
  { slug: "uretim", ad: "Üretim" },
  { slug: "teknoloji", ad: "Teknoloji" },
  { slug: "saglik", ad: "Sağlık" },
  { slug: "perakende", ad: "Perakende" },
  { slug: "enerji", ad: "Enerji" },
  { slug: "ulasim", ad: "Ulaşım" },
  { slug: "gida", ad: "Gıda" },
];

export default async function Home() {
  const seriler = await Promise.all((await listSeries("yahoo")).map((id) => getSeries(id)));
  const kaynakSayisi = new Set(seriler.map((s) => s.source.name)).size;
  const oneCikan = seriler[0] ?? null;

  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-10">
      <section className="py-16 text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
          Türkiye Ekonomisi ve BIST için{" "}
          <span className="text-accent">Veri ve Grafikler</span>
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-lg text-muted">
          Piyasa verileri günlük olarak toplanır, açık kaynaklardan derlenir ve
          anlaşılır grafiklerle sunulur.
        </p>
      </section>

      <section className="flex flex-wrap justify-center gap-4 py-8">
        <div className="rounded-xl border border-border bg-card px-8 py-5 text-center">
          <p className="text-3xl font-bold text-accent">{seriler.length}</p>
          <p className="text-sm text-muted">Toplam Grafik</p>
        </div>
        <div className="rounded-xl border border-border bg-card px-8 py-5 text-center">
          <p className="text-3xl font-bold text-accent">{kaynakSayisi}</p>
          <p className="text-sm text-muted">Veri Kaynağı</p>
        </div>
      </section>

      <section id="hisseler" className="py-8">
        <h2 className="mb-4 text-xl font-semibold">Sık Takip Edilen Hisseler</h2>
        <div className="flex flex-wrap gap-3">
          {HISSELER.map((sym) => (
            <Link
              key={sym}
              href={`/hisse/${sym.toLowerCase()}`}
              className="rounded-full border border-border bg-card px-4 py-1.5 text-sm text-muted transition-colors hover:border-accent hover:text-accent"
            >
              {sym}
            </Link>
          ))}
        </div>
      </section>

      <section id="sektorler" className="py-8">
        <h2 className="mb-4 text-xl font-semibold">Sık Aranan</h2>
        <div className="flex flex-wrap gap-3">
          {SIK_ARANAN.map((s) => (
            <Link
              key={s.slug}
              href={`/kategori/${s.slug}`}
              className="rounded-full border border-border bg-card px-4 py-1.5 text-sm text-muted transition-colors hover:border-accent hover:text-accent"
            >
              {s.ad}
            </Link>
          ))}
        </div>
      </section>

      <section className="py-8">
        <h2 className="mb-4 text-xl font-semibold">Sektör Sayfaları</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {SEKTORLER.map((s) => (
            <Link
              key={s.slug}
              href={`/sektor/${s.slug}`}
              className="rounded-xl border border-border bg-card p-5 transition-colors hover:border-accent"
            >
              <h3 className="font-medium">{s.ad}</h3>
              <p className="mt-1 text-sm text-muted">Sektör grafikleri — yakında</p>
            </Link>
          ))}
        </div>
      </section>

      <section className="py-8">
        <h2 className="mb-4 text-xl font-semibold">Dikkat Çekenler</h2>
        {oneCikan ? (
          <div className="rounded-xl border border-border bg-card p-6">
            <div className="mb-4 flex items-baseline justify-between">
              <h3 className="text-lg font-medium">{oneCikan.title}</h3>
              <span className="text-sm text-muted">{oneCikan.unit}</span>
            </div>
            <ChartClient series={oneCikan} />
            <div className="mt-4">
              <SourceNote source={oneCikan.source} updated={oneCikan.updated} />
            </div>
          </div>
        ) : (
          <p className="text-muted">Henüz veri yok.</p>
        )}
      </section>
    </div>
  );
}
