import Link from "next/link";
import { formatDate, getBuildReport } from "@/lib/data";

const standingGaps = [
  "This is not a live complaint dashboard; official grievance records are bounded by the latest available normalized record date.",
  "Works, payments, tenders, geospatial joins, and source-to-source matching are registered as future product layers.",
  "Community, social, and news sources are not used as official proof in the current public claim cards.",
  "Ward/place matching is based on normalized ward names, area context, and official mapping rows; deeper PostGIS matching is deferred."
];

export default function KnownGapsPage() {
  const report = getBuildReport();

  return (
    <main className="mx-auto min-h-screen max-w-5xl px-5 py-8">
      <nav className="flex flex-wrap items-center justify-between gap-4 border-b border-line pb-4">
        <Link href="/" className="text-sm font-semibold uppercase tracking-[0.22em] text-ink">Civic Truth Engine</Link>
        <div className="flex flex-wrap gap-3 text-sm text-muted">
          <Link href="/sources" className="hover:text-ink">Sources</Link>
          <Link href="/methodology" className="hover:text-ink">Methodology</Link>
        </div>
      </nav>

      <section className="py-10">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-civic">Known gaps</p>
        <h1 className="mt-3 text-5xl font-semibold leading-tight text-ink md:text-7xl">
          What the current record does not prove.
        </h1>
        <p className="mt-5 max-w-2xl text-lg leading-8 text-muted">
          Generated {formatDate(report.generated_at)}. Gaps are displayed because missing or stale evidence is product information, not a footnote.
        </p>
      </section>

      <section className="grid gap-10 border-y border-line py-8 md:grid-cols-[0.7fr_1.3fr]">
        <h2 className="text-2xl font-semibold text-ink">Generated gaps</h2>
        <ul className="space-y-3 text-sm leading-6 text-muted">
          {report.known_gaps.map((gap) => (
            <li key={gap} className="border-l border-line pl-4">{gap}</li>
          ))}
        </ul>
      </section>

      <section className="grid gap-10 border-b border-line py-8 md:grid-cols-[0.7fr_1.3fr]">
        <h2 className="text-2xl font-semibold text-ink">Standing limits</h2>
        <ul className="space-y-3 text-sm leading-6 text-muted">
          {standingGaps.map((gap) => (
            <li key={gap} className="border-l border-line pl-4">{gap}</li>
          ))}
        </ul>
      </section>

      {report.warnings.length > 0 && (
        <section className="grid gap-10 py-8 md:grid-cols-[0.7fr_1.3fr]">
          <h2 className="text-2xl font-semibold text-ink">Build warnings</h2>
          <ul className="space-y-3 text-sm leading-6 text-muted">
            {report.warnings.map((warning) => (
              <li key={warning} className="border-l border-civic pl-4">{warning}</li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
