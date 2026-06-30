import { ArrowUpRight } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { formatDate, getSource, getSources, sourceStatusLabel } from "@/lib/data";

export function generateStaticParams() {
  return getSources().map((source) => ({ source: source.source_id }));
}

export default async function SourceDetailPage({ params }: { params: Promise<{ source: string }> }) {
  const { source: sourceId } = await params;
  const source = getSource(sourceId);
  if (!source) notFound();

  return (
    <main className="mx-auto min-h-screen max-w-5xl px-5 py-8">
      <nav className="flex flex-wrap items-center justify-between gap-4 border-b border-line pb-4">
        <Link href="/sources" className="text-sm font-semibold uppercase tracking-[0.22em] text-ink">Sources</Link>
        <Link href="/" className="text-sm text-muted hover:text-ink">Home</Link>
      </nav>

      <section className="py-10">
        <div className="flex flex-wrap gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-muted">
          <span>{sourceStatusLabel(source.domain)}</span>
          <span>tier {source.source_tier}</span>
          <span>{sourceStatusLabel(source.official_status)}</span>
        </div>
        <h1 className="mt-4 text-5xl font-semibold leading-tight text-ink md:text-7xl">{source.name}</h1>
        <p className="mt-5 break-all text-sm text-muted">{source.source_id}</p>
        <a href={source.url} target="_blank" rel="noreferrer" className="mt-6 inline-flex items-center gap-2 border border-line px-4 py-3 text-sm font-semibold text-ink transition hover:border-ink">
          Open publisher source <ArrowUpRight size={17} />
        </a>
      </section>

      <section className="grid gap-8 border-y border-line py-6 md:grid-cols-2">
        <div className="space-y-3">
          <MetaLine label="Publisher" value={source.publisher} />
          <MetaLine label="Agency" value={source.agency} />
          <MetaLine label="Access" value={sourceStatusLabel(source.access_method)} />
          <MetaLine label="Format" value={source.format} />
          <MetaLine label="License" value={source.license || "Unavailable"} />
          <MetaLine label="PII risk" value={sourceStatusLabel(source.pii_risk)} />
        </div>
        <div className="space-y-3">
          <MetaLine label="Fetch status" value={sourceStatusLabel(source.latest_fetch_status)} />
          <MetaLine label="Latest fetch" value={formatDate(source.latest_fetched_at)} />
          <MetaLine label="Latest run" value={source.latest_run ?? "Unavailable"} />
          <MetaLine label="Parser status" value={sourceStatusLabel(source.parser_status)} />
          <MetaLine label="Usage" value={sourceStatusLabel(source.normalized_usage_status)} />
          <MetaLine label="Files" value={String(source.file_count)} />
        </div>
      </section>

      <section className="py-8">
        <h2 className="text-2xl font-semibold text-ink">Caveats</h2>
        {source.caveats.length > 0 ? (
          <ul className="mt-4 list-disc space-y-2 pl-5 text-sm leading-6 text-muted">
            {source.caveats.map((caveat) => <li key={caveat}>{caveat}</li>)}
          </ul>
        ) : (
          <p className="mt-4 text-sm leading-6 text-muted">No source-specific caveat was emitted by the latest site build.</p>
        )}
      </section>

      <section className="border-y border-line py-6">
        <h2 className="text-2xl font-semibold text-ink">Registry notes</h2>
        <p className="mt-4 text-sm leading-6 text-muted">{source.notes || "No registry notes provided."}</p>
      </section>
    </main>
  );
}

function MetaLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[128px_1fr] gap-3 text-sm leading-6">
      <dt className="text-muted">{label}</dt>
      <dd className="break-words font-medium text-ink">{value}</dd>
    </div>
  );
}
