import Link from "next/link";

const claimLevels = [
  ["Official records show", "Used when the source is official or mirrored-official and the claim is directly computed from cited rows."],
  ["Available data suggests", "Used for summaries, rankings, and patterns that depend on coverage, category quality, or matching."],
  ["Possible related record", "Used when a source may be relevant but the current match is not strong enough to state as fact."],
  ["Community signal", "Used only for non-official reports, news, social, or civic projects when they are leads rather than proof."]
];

export default function MethodologyPage() {
  return (
    <main className="mx-auto min-h-screen max-w-5xl px-5 py-8">
      <nav className="flex flex-wrap items-center justify-between gap-4 border-b border-line pb-4">
        <Link href="/" className="text-sm font-semibold uppercase tracking-[0.22em] text-ink">Civic Truth Engine</Link>
        <div className="flex flex-wrap gap-3 text-sm text-muted">
          <Link href="/sources" className="hover:text-ink">Sources</Link>
          <Link href="/known-gaps" className="hover:text-ink">Known gaps</Link>
        </div>
      </nav>

      <section className="py-10">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-civic">Methodology</p>
        <h1 className="mt-3 text-5xl font-semibold leading-tight text-ink md:text-7xl">
          Claims are only as strong as their sources.
        </h1>
        <p className="mt-5 max-w-2xl text-lg leading-8 text-muted">
          This site separates source provenance, fetch freshness, record date range, parser status, and claim wording so a resident can see what the public record proves.
        </p>
      </section>

      <section className="grid gap-10 border-y border-line py-8 md:grid-cols-[0.7fr_1.3fr]">
        <h2 className="text-2xl font-semibold text-ink">Source tiers</h2>
        <div className="space-y-4 text-sm leading-6 text-muted">
          <p><strong className="text-ink">Tier 1:</strong> official or mirrored-official structured data. Used for strongest public claims.</p>
          <p><strong className="text-ink">Tier 2:</strong> official PDFs and circulars. Used for rules, budgets, SOPs, and notices.</p>
          <p><strong className="text-ink">Tier 3:</strong> official portals requiring scraping. Archived cautiously and labeled by parser reliability.</p>
          <p><strong className="text-ink">Tier 4:</strong> civic/crowd projects. Used as community signals, not official proof.</p>
          <p><strong className="text-ink">Tier 5:</strong> Reddit, news, and social sources. Used as leads and launch research only.</p>
        </div>
      </section>

      <section className="grid gap-10 border-b border-line py-8 md:grid-cols-[0.7fr_1.3fr]">
        <h2 className="text-2xl font-semibold text-ink">Claim wording</h2>
        <div className="divide-y divide-line border-y border-line">
          {claimLevels.map(([label, detail]) => (
            <div key={label} className="py-4">
              <p className="font-semibold text-ink">{label}</p>
              <p className="mt-1 text-sm leading-6 text-muted">{detail}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="grid gap-10 py-8 md:grid-cols-[0.7fr_1.3fr]">
        <h2 className="text-2xl font-semibold text-ink">Limits</h2>
        <div className="space-y-4 text-sm leading-6 text-muted">
          <p>Complaint records are administrative records. They do not prove total civic severity, durable repair, or the full lived reality of a place.</p>
          <p>Closed status is treated as administrative status, not proof that an issue was fixed on the ground.</p>
          <p>The first public build is a historical civic-memory product, not a live complaint dashboard and not a complaint submission system.</p>
        </div>
      </section>
    </main>
  );
}
