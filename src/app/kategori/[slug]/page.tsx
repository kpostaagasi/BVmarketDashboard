import Link from "next/link";
import { notFound } from "next/navigation";
import { getSeries, listSeries } from "@/lib/data";
import ChartClient from "@/components/ChartClient";
import SourceNote from "@/components/SourceNote";

export default async function KategoriPage({
  params,
}: PageProps<"/kategori/[slug]">) {
  const { slug } = await params;
  const seriesIds = await listSeries(slug);
  if (seriesIds.length === 0) {
    notFound();
  }

  const series = await Promise.all(seriesIds.map((id) => getSeries(id)));

  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-10">
      <h1 className="mb-2 text-3xl font-bold capitalize">{slug}</h1>
      <p className="mb-8 text-muted">{series.length} grafik</p>
      <div className="flex flex-col gap-8">
        {series.map((s) => (
          <div key={s.id} className="rounded-xl border border-border bg-card p-6">
            <div className="mb-4 flex items-baseline justify-between">
              <h2 className="text-lg font-medium">{s.title}</h2>
              <span className="text-sm text-muted">{s.unit}</span>
            </div>
            <ChartClient series={s} />
            <div className="mt-4">
              <SourceNote source={s.source} updated={s.updated} />
            </div>
          </div>
        ))}
      </div>
      <div className="mt-10">
        <Link href="/" className="text-sm text-muted transition-colors hover:text-accent">
          ← Ana Sayfa
        </Link>
      </div>
    </div>
  );
}
