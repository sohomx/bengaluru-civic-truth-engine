"use client";

import clsx from "clsx";
import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  FileText,
  Landmark,
  Layers3,
  Search,
  ShieldCheck
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import {
  LENS_OPTIONS,
  evidenceLabel,
  formatDate,
  formatNumber,
  getPlaces,
  topYear,
  type ClaimCard,
  type Evidence,
  type IssueCategory,
  type LensKey,
  type PlaceRecord,
  type TruthPayload
} from "@/lib/data";

type PlaceDossierProps = {
  place: PlaceRecord;
};

export function PlaceDossier({ place }: PlaceDossierProps) {
  const [openEvidence, setOpenEvidence] = useState(false);
  const [lens, setLens] = useState<LensKey>("all");
  const payload = place.payloads[lens];
  const peak = topYear(payload);
  const topIssues = payload.top_issue_categories.slice(0, 3);
  const evidence = useMemo(() => collectEvidence(payload), [payload]);
  const scopeYears = `${payload.record_scope.grievance_year_min ?? "?"}-${payload.record_scope.grievance_year_max ?? "?"}`;

  return (
    <main className="min-h-screen">
      <div className="border-b border-line/80 bg-paper/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-5 py-4 md:flex-row md:items-center md:justify-between">
          <Link href="/places/bellandur" className="text-sm font-semibold uppercase tracking-[0.22em] text-ink">
            Civic Truth Engine
          </Link>
          <nav className="flex flex-wrap gap-2" aria-label="Pilot places">
            {getPlaces().map((item) => (
              <Link
                key={item.slug}
                href={`/places/${item.slug}`}
                className={clsx(
                  "rounded-full px-3 py-1.5 text-sm transition",
                  item.slug === place.slug
                    ? "bg-ink text-paper"
                    : "border border-line bg-paper/70 text-muted hover:border-ink hover:text-ink"
                )}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
      </div>

      <section className="mx-auto grid max-w-7xl gap-8 px-5 py-8 lg:grid-cols-[1fr_380px]">
        <div className="space-y-8">
          <header className="grid min-h-[520px] content-between overflow-hidden rounded-none border-y border-line py-8 md:min-h-[560px]">
            <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
              <div className="flex flex-wrap items-center gap-3 text-sm text-muted">
                <span className="inline-flex items-center gap-2">
                  <Search size={16} /> Place dossier
                </span>
                <span>{payload.evidence_policy}</span>
              </div>
              <div className="flex flex-wrap gap-1 border border-line bg-paper/70 p-1" aria-label="Record lens">
                {LENS_OPTIONS.map((option) => (
                  <button
                    key={option.key}
                    type="button"
                    className={clsx(
                      "px-3 py-1.5 text-sm font-semibold transition",
                      lens === option.key
                        ? "bg-ink text-paper"
                        : "text-muted hover:bg-line/60 hover:text-ink"
                    )}
                    onClick={() => setLens(option.key)}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid gap-8 lg:grid-cols-[1.1fr_0.9fr] lg:items-end">
              <div>
                <p className="mb-3 text-sm font-semibold uppercase tracking-[0.18em] text-civic">
                  Civic memory, {scopeYears}
                </p>
                <h1 className="max-w-3xl text-6xl font-semibold leading-[0.95] tracking-normal text-ink md:text-8xl">
                  {place.label}
                </h1>
                <p className="mt-6 max-w-2xl text-xl leading-8 text-muted">
                  {formatNumber(payload.complaint_summary.total_complaints)} grievance records in the {payload.record_scope.label.toLowerCase()} lens, with ward context, recurring issue patterns, and evidence pointers.
                </p>
                <div className="mt-6 grid max-w-3xl gap-3 border-y border-line py-4 text-sm leading-6 text-muted md:grid-cols-[24px_1fr]">
                  <AlertTriangle size={18} className="mt-1 text-civic" />
                  <div>
                    <p className="font-semibold text-ink">{payload.record_scope.freshness_note}</p>
                    <p>{payload.record_scope.context_note}</p>
                  </div>
                </div>
              </div>
              <CivicMap place={place} payload={payload} />
            </div>
          </header>

          <section className="grid gap-6 md:grid-cols-3">
            <Metric label="Complaints in lens" value={formatNumber(payload.complaint_summary.total_complaints)} detail={payload.record_scope.label} />
            <Metric label="Peak year" value={peak ? `${peak.value}` : "No data"} detail={peak ? `${formatNumber(peak.count)} records` : undefined} />
            <Metric label="Top issue" value={payload.top_issue_categories[0]?.category ?? "No data"} />
          </section>

          <section>
            <SectionLabel icon={<ShieldCheck size={18} />} title="Claim Cards" />
            <div className="mt-6 divide-y divide-line border-y border-line">
              {payload.claim_cards.map((claim, index) => (
                <ClaimCardRow key={`${claim.claim_level}-${index}`} claim={claim} index={index + 1} />
              ))}
            </div>
          </section>

          <section className="grid gap-10 lg:grid-cols-[0.82fr_1.18fr]">
            <div>
              <SectionLabel icon={<Landmark size={18} />} title="Official Context" />
              <div className="mt-5 space-y-4 border-l border-line pl-5">
                <ContextLine title="Old BBMP" candidate={payload.ward_context.old_bbmp_candidates[0]} />
                <ContextLine title="New GBA" candidate={payload.ward_context.new_gba_candidates[0]} />
                {payload.ward_context.area_match_candidates.length > 0 && (
                  <div>
                    <p className="text-sm font-semibold text-ink">Area context</p>
                    <p className="mt-1 text-sm leading-6 text-muted">
                      Includes {payload.ward_context.area_match_candidates.slice(0, 5).map((item) => item.ward_name).filter(Boolean).join(", ")}.
                    </p>
                  </div>
                )}
              </div>
            </div>

            <div>
              <SectionLabel icon={<Layers3 size={18} />} title="Complaint Pattern" />
              <div className="mt-5 space-y-5">
                <TrendBars rows={payload.complaint_summary.by_year} />
                <StatusStrip rows={payload.complaint_summary.by_status} total={payload.complaint_summary.total_complaints} />
              </div>
            </div>
          </section>

          <section>
            <SectionLabel icon={<FileText size={18} />} title="Issue Briefs" />
            <div className="mt-6 divide-y divide-line border-y border-line">
              {topIssues.map((issue, index) => (
                <IssueBrief key={issue.category} issue={issue} index={index + 1} />
              ))}
            </div>
          </section>
        </div>

        <aside className="lg:sticky lg:top-6 lg:self-start">
          <div className="border-y border-line py-6">
            <SectionLabel icon={<ShieldCheck size={18} />} title="Claim Discipline" />
            <ul className="mt-5 space-y-4 text-sm leading-6 text-muted">
              <li>{payload.record_scope.freshness_note}</li>
              <li>{payload.record_scope.context_note}</li>
              <li>Official grievance records show counts and category patterns.</li>
              <li>Closed status is administrative; it does not prove durable repair.</li>
              <li>Ward matching is official-record and text based, not yet geospatially verified.</li>
              <li>Community and social signals are excluded from this Wave 1 view.</li>
            </ul>
          </div>

          <div className="mt-6 border-y border-line py-6">
            <SectionLabel icon={<FileText size={18} />} title="Build Metadata" />
            <dl className="mt-5 space-y-3 text-sm leading-6">
              <MetaLine label="Generated" value={formatDate(payload.build_metadata.generated_at)} />
              <MetaLine label="Record scope" value={`${payload.build_metadata.record_date_min ?? "?"} to ${payload.build_metadata.record_date_max ?? "?"}`} />
              <MetaLine label="Sources used" value={payload.build_metadata.included_sources.join(", ")} />
              <MetaLine label="Code version" value={payload.build_metadata.code_version} />
            </dl>
            {payload.build_metadata.known_gaps.length > 0 && (
              <div className="mt-5 text-sm leading-6 text-muted">
                <p className="font-semibold text-ink">Known gaps</p>
                <ul className="mt-2 list-disc space-y-1 pl-5">
                  {payload.build_metadata.known_gaps.map((gap) => (
                    <li key={gap}>{gap}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <button
            className="mt-6 flex w-full items-center justify-between border-y border-line py-4 text-left text-sm font-semibold text-ink transition hover:border-ink"
            onClick={() => setOpenEvidence((value) => !value)}
          >
            Evidence appendix
            <ArrowUpRight size={18} className={clsx("transition", openEvidence && "rotate-45")} />
          </button>
          {openEvidence && (
            <ol className="mt-4 max-h-[440px] space-y-3 overflow-auto pr-2 text-xs leading-5 text-muted">
              {evidence.map((item, index) => (
                <li key={`${item.source_id}-${item.raw_file}-${item.row_number}`}>
                  <span className="font-semibold text-ink">E{index + 1}</span> {evidenceLabel(item)}
                </li>
              ))}
            </ol>
          )}
        </aside>
      </section>
    </main>
  );
}

function CivicMap({ place, payload }: { place: PlaceRecord; payload: TruthPayload }) {
  const issues = payload.top_issue_categories.slice(0, 5);
  return (
    <div className="relative aspect-[4/3] overflow-hidden border border-line bg-[#eee8dd] shadow-soft">
      <div className="absolute inset-0 opacity-70 [background-image:linear-gradient(35deg,transparent_44%,rgba(15,118,110,0.32)_45%,rgba(15,118,110,0.32)_47%,transparent_48%),linear-gradient(112deg,transparent_35%,rgba(23,23,23,0.16)_36%,rgba(23,23,23,0.16)_37%,transparent_38%)]" />
      {issues.map((issue, index) => (
        <div
          key={issue.category}
          className="absolute rounded-full border border-ink/15 bg-civic/80 transition duration-300 hover:scale-110"
          style={{
            width: `${42 + index * 12}px`,
            height: `${42 + index * 12}px`,
            left: `${16 + (index * 17) % 58}%`,
            top: `${18 + (index * 23) % 52}%`
          }}
          title={`${issue.category}: ${formatNumber(issue.count)}`}
        />
      ))}
      <div className="absolute bottom-4 left-4 right-4 flex items-end justify-between gap-5">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted">Locality signal</p>
          <p className="mt-1 text-2xl font-semibold text-ink">{place.label}</p>
        </div>
        <p className="max-w-36 text-right text-xs leading-5 text-muted">
          Markers reflect the active grievance lens.
        </p>
      </div>
    </div>
  );
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="border-y border-line py-5">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted">{label}</p>
      <p className="mt-3 text-3xl font-semibold leading-tight text-ink">{value}</p>
      {detail && <p className="mt-2 text-sm text-muted">{detail}</p>}
    </div>
  );
}

function ClaimCardRow({ claim, index }: { claim: ClaimCard; index: number }) {
  return (
    <article className="grid gap-5 py-6 md:grid-cols-[88px_1fr]">
      <div className="text-4xl font-semibold text-civic">{String(index).padStart(2, "0")}</div>
      <div>
        <div className="flex flex-wrap gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-muted">
          <span>{claim.claim_level.replaceAll("_", " ")}</span>
          <span>{claim.confidence} confidence</span>
        </div>
        <p className="mt-3 text-2xl font-semibold leading-snug text-ink">{claim.claim}</p>
        <p className="mt-3 text-sm leading-6 text-muted">{claim.caveat}</p>
        <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted">
          <span className="border border-line px-2 py-1">{claim.time_range}</span>
          {claim.citations.slice(0, 3).map((citation) => (
            <Link
              key={`${citation.source_id}-${citation.raw_file}-${citation.row_number}`}
              href={`/sources/${citation.source_id}`}
              className="border border-line px-2 py-1 transition hover:border-civic hover:text-ink"
            >
              {evidenceLabel(citation)}
            </Link>
          ))}
        </div>
      </div>
    </article>
  );
}

function MetaLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[104px_1fr] gap-3">
      <dt className="text-muted">{label}</dt>
      <dd className="break-words font-medium text-ink">{value || "Unavailable"}</dd>
    </div>
  );
}

function SectionLabel({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.18em] text-civic">
      {icon}
      <h2>{title}</h2>
    </div>
  );
}

function ContextLine({ title, candidate }: { title: string; candidate?: { ward_name?: string; ward_number?: string; corporation?: string } }) {
  if (!candidate?.ward_name) {
    return (
      <div>
        <p className="text-sm font-semibold text-ink">{title}</p>
        <p className="mt-1 text-sm text-muted">No direct candidate.</p>
      </div>
    );
  }
  const corp = candidate.corporation ? `, ${candidate.corporation} Corporation` : "";
  return (
    <div>
      <p className="text-sm font-semibold text-ink">{title}</p>
      <p className="mt-1 text-sm leading-6 text-muted">
        {candidate.ward_name} {candidate.ward_number ? `(ward ${candidate.ward_number}${corp})` : ""}
      </p>
    </div>
  );
}

function TrendBars({ rows }: { rows: { value: string; count: number }[] }) {
  const max = Math.max(...rows.map((row) => row.count), 1);
  return (
    <div className="space-y-3">
      {rows.slice(0, 6).map((row) => (
        <div key={row.value} className="grid grid-cols-[52px_1fr_76px] items-center gap-3 text-sm">
          <span className="font-medium text-ink">{row.value}</span>
          <span className="h-2 overflow-hidden bg-line">
            <span className="block h-full bg-civic transition-all" style={{ width: `${(row.count / max) * 100}%` }} />
          </span>
          <span className="text-right text-muted">{formatNumber(row.count)}</span>
        </div>
      ))}
    </div>
  );
}

function StatusStrip({ rows, total }: { rows: { value: string; count: number }[]; total: number }) {
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-2 text-sm text-muted">
      {rows.slice(0, 5).map((row) => (
        <span key={row.value}>
          <span className="font-semibold text-ink">{row.value}</span> {Math.round((row.count / Math.max(total, 1)) * 100)}%
        </span>
      ))}
    </div>
  );
}

function IssueBrief({ issue, index }: { issue: IssueCategory; index: number }) {
  const examples = issue.examples.slice(0, 3);
  const subcategories = Array.from(new Set(examples.map((item) => item.issue_subcategory).filter(Boolean))).join(", ");
  return (
    <article className="grid gap-5 py-6 md:grid-cols-[88px_1fr]">
      <div className="text-4xl font-semibold text-civic">{String(index).padStart(2, "0")}</div>
      <div>
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h3 className="text-2xl font-semibold text-ink">{issue.category}</h3>
            <p className="mt-2 text-sm text-muted">{subcategories || "Representative subcategories unavailable."}</p>
          </div>
          <p className="text-xl font-semibold text-ink">{formatNumber(issue.count)}</p>
        </div>
        <div className="mt-5 grid gap-3">
          {examples.map((example) => (
            <div key={example.external_complaint_id} className="group grid gap-2 border-l border-line pl-4 text-sm transition hover:border-civic">
              <div className="flex flex-wrap items-center gap-2">
                <CheckCircle2 size={15} className="text-civic" />
                <span className="font-semibold text-ink">Complaint {example.external_complaint_id}</span>
                <span className="text-muted">{example.grievance_date}</span>
              </div>
              <p className="text-muted">{example.issue_subcategory} · {example.status} · {evidenceLabel(example.evidence)}</p>
            </div>
          ))}
        </div>
      </div>
    </article>
  );
}

function collectEvidence(payload: TruthPayload): Evidence[] {
  const seen = new Set<string>();
  const items: Evidence[] = [];
  const push = (evidence?: Evidence) => {
    if (!evidence?.source_id) return;
    const key = `${evidence.source_id}|${evidence.raw_file}|${evidence.row_number}`;
    if (seen.has(key)) return;
    seen.add(key);
    items.push(evidence);
  };
  payload.ward_context.old_bbmp_candidates.forEach((item) => push(item.evidence));
  payload.ward_context.new_gba_candidates.forEach((item) => push(item.evidence));
  payload.ward_context.area_match_candidates.slice(0, 8).forEach((item) => push(item.evidence));
  payload.top_issue_categories.slice(0, 8).forEach((issue) => issue.examples.forEach((example) => push(example.evidence)));
  return items;
}
