import Link from "next/link";

const footerLinks = [
  { href: "#", label: "Hakkında" },
  { href: "#", label: "Veri Kaynakları" },
  { href: "#", label: "Metodoloji" },
  { href: "/ai-raporlari", label: "AI Raporları" },
];

export default function Footer() {
  return (
    <footer className="border-t border-border bg-card">
      <div className="mx-auto flex w-full max-w-7xl flex-col items-center justify-between gap-3 px-6 py-6 text-sm text-muted sm:flex-row">
        <p>© BV Market Dashboard</p>
        <nav className="flex items-center gap-5">
          {footerLinks.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              className="transition-colors hover:text-accent"
            >
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
    </footer>
  );
}
