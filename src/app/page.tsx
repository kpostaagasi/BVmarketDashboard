import Link from "next/link";
import { getSeries, listSeries } from "@/lib/data";
import ChartClient from "@/components/ChartClient";
import SourceNote from "@/components/SourceNote";

const HISSeler = ["TUPRS", "THYAO", "FROTO", "KARSN", "TTRAK", "MGROS", "TOASO", "EBEBK"];
const SIK_ARANAN = ["İhracat", "Enflasyon", "Altın", "Brent Petrol", "Bankacılık", "Sigorta"];
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
  const tumu = await listSeries("yahoo");
  const kaynakSayisi = new Set(tumu.map((s) => s.split("/")[0])).size;

  const odneCikan = tumu.length > 0 ? await getSeries(tumu[0]) : null;

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
          <p className="text-3xl font-bold text-accent">{tumu.length}</p>
          <p className="text-sm text-muted">Toplam Grafik</p>
        </div>
        <div className="rounded-xl border border-border bg-card px-8 py-5 text-center">
          <p className="text-3xl font-bold text-accent">{kaynakSayisi}</p>
          <p className="text-sm text-muted">Veri Kaynağı</p>
        </div>
      </section>

      <section className="py-8">
        <h2 className="mb-4 text-xl font-semibold">Sık Takip Edilen Hisseler</h2>
        <div className="flex flex-wrap gap-3">
          {HISSeler.map((sym) => (
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

      <section className="py-8">
        <h2 className="mb-4 text-xl font-semibold">Sık Aranan</h2>
        <div className="flex flex-wrap gap-3">
          {SIK_ARANAN.map((ad) => (
            <Link
              key={ad}
              href={`/kategori/${ad.toLowerCase()}`}
              className="rounded-full border border-border bg-card px-4 py-1.5 text-sm text-muted transition-colors hover:border-accent hover:text-accent"
            >
              {ad}
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
        {odneCikan ? (
          <div className="rounded-xl border border-border bg-card p-6">
            <div className="mb-4 flex items-baseline justify-between">
              <h3 className="text-lg font-medium">{odneCikan.title}</h3>
              <span className="text-sm text-muted">{odneCikan.unit}</span>
            </div>
            <ChartClient series={odneCikan} />
            <div className="mt-4">
              <SourceNote source={odneCikan.source} updated={odneCikan.updated} />
            </div>
          </div>
        ) : (
          <p className="text-muted">Henüz veri yok.</p>
        )}
      </section>
    </div>
  );
}
