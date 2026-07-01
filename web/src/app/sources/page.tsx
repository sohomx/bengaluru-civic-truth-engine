import Link from "next/link";
import { SourceExplorer } from "@/components/source-explorer";
import { formatDate, formatNumber, getSourceStatus, getSources } from "@/lib/data";

export default function SourcesPage() {
  const status = getSourceStatus();
  const sources = getSources();

  return (
    <main className="mx-auto min-h-screen max-w-7xl px-5 py-8">
      <Header />
      <section className="py-10">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-civic">Source explorer</p>
        <h1 className="mt-3 max-w-4xl text-5xl font-semibold leading-tight text-ink md:text-7xl">
          The public-record spine behind every claim.
        </h1>
        <p className="mt-5 max-w-2xl text-lg leading-8 text-muted">
          Browse registered sources, archive status, parser status, usage in public claims, and freshness caveats.
        </p>
      </section>

      <section className="mb-8 grid gap-5 border-y border-line py-5 md:grid-cols-4">
        <Metric label="Sources" value={formatNumber(status.summary.total_sources)} />
        <Metric label="Usable archive" value={formatNumber(status.summary.usable)} />
        <Metric label="Needs attention" value={formatNumber(status.summary.partial + status.summary.stale + status.summary.unavailable + status.summary.blocked)} />
        <Metric label="Used in claims" value={formatNumber(status.summary.used_in_public_claims)} />
      </section>

      <p className="mb-4 text-sm text-muted">Generated {formatDate(status.generated_at)}.</p>
      <SourceExplorer sources={sources} />
    </main>
  );
}

function Header() {
  return (
    <nav className="flex flex-wrap items-center justify-between gap-4 border-b border-line pb-4">
      <Link href="/" className="text-sm font-semibold uppercase tracking-[0.22em] text-ink">Civic Truth Engine</Link>
      <div className="flex flex-wrap gap-3 text-sm text-muted">
        <Link href="/places/bellandur" className="hover:text-ink">Places</Link>
        <Link href="/methodology" className="hover:text-ink">Methodology</Link>
        <Link href="/known-gaps" className="hover:text-ink">Known gaps</Link>
      </div>
    </nav>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-3xl font-semibold text-ink">{value}</p>
      <p className="mt-1 text-sm text-muted">{label}</p>
    </div>
  );
}
