const RAPORLAR = [
  {
    ad: "Piyasa Özeti & Öne Çıkanlar",
    frekans: "Günlük otomatik",
    aciklama:
      "Günün en çok hareket eden hisseleri, sektör dağılımı ve öne çıkan piyasa gelişmeleri.",
  },
  {
    ad: "Sektörel Trend Raporu",
    frekans: "Haftalık trend",
    aciklama:
      "Sektör bazında haftalık performans, hacim ve trend analizleri.",
  },
];

export default function AiRaporlariPage() {
  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-10">
      <h1 className="mb-2 text-3xl font-bold">AI Raporları</h1>
      <p className="mb-8 text-muted">
        Otomatik üretilen piyasa ve sektör raporları.
      </p>
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        {RAPORLAR.map((r) => (
          <div
            key={r.ad}
            className="flex flex-col rounded-xl border border-border bg-card p-6"
          >
            <span className="mb-3 w-fit rounded-full border border-border px-3 py-1 text-xs text-muted">
              {r.frekans}
            </span>
            <h2 className="text-lg font-medium">{r.ad}</h2>
            <p className="mt-2 flex-1 text-sm text-muted">{r.aciklama}</p>
            <p className="mt-4 text-sm font-medium text-accent">
              Yakında aktif olacak
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
