import Link from "next/link";
import type { SourceMeta } from "@/lib/types";

interface SourceNoteProps {
  source: SourceMeta;
  updated: string;
}

export default function SourceNote({ source, updated }: SourceNoteProps) {
  const formatted = new Date(updated).toLocaleDateString("tr-TR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: "UTC",
  });
  return (
    <p className="text-sm text-muted">
      Kaynak:{" "}
      <Link
        href={source.url}
        target="_blank"
        rel="noopener noreferrer"
        className="transition-colors hover:text-accent"
      >
        {source.name} <span aria-hidden="true">↗</span>
      </Link>
      <span className="mx-2">·</span>
      Son güncelleme: {formatted}
    </p>
  );
}
