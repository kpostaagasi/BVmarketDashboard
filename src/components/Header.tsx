import Link from "next/link";

const navLinks = [
  { href: "/", label: "Ana Sayfa" },
  { href: "/#sektorler", label: "Sektörler" },
  { href: "/#hisseler", label: "Hisse" },
  { href: "/ai-raporlari", label: "AI Raporları" },
];

export default function Header() {
  return (
    <header className="sticky top-0 z-50 border-b border-border bg-[#0F1E33]/90 backdrop-blur">
      <div className="mx-auto flex h-16 w-full max-w-7xl items-center justify-between px-6">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          BV <span className="text-accent">Market</span> Dashboard
        </Link>
        <nav className="hidden items-center gap-6 text-sm sm:flex">
          {navLinks.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              className="text-muted transition-colors hover:text-accent"
            >
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
