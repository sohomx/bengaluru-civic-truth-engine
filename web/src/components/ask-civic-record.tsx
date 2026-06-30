"use client";

import { FormEvent, useEffect, useState } from "react";

type RagAnswer = {
  generated_answer: string;
  answer_brief?: AnswerBrief;
  question?: string;
  normalized_place?: string | null;
  normalized_issue?: string | null;
  answer_type?: string;
  confidence_label?: string;
  claims?: Claim[];
  citations?: Citation[];
  what_to_do_next?: string[];
  retrieval_trace?: {
    retrieval_snapshot_id?: string;
    retrieval_backend?: string;
    stage_timings_ms?: Record<string, number>;
  };
  jurisdiction?: {
    agency?: string;
    ward?: string | null;
    ward_number?: string | null;
    match_method?: string;
  };
  civic_triage?: {
    civic_interpretation?: string;
    who_to_contact?: string[];
    what_to_do_next?: string[];
    cause_boundary?: string;
    complaint_memory?: {
      count?: number;
      latest_record_date?: string | null;
      status_breakdown?: Record<string, number>;
      example_ids?: string[];
      scope_note?: string;
    };
    evidence_library?: {
      complaints?: EvidenceEntry[];
      work_payments?: EvidenceEntry[];
      tenders?: EvidenceEntry[];
      assets?: EvidenceEntry[];
    };
    issue_tracks?: IssueTrack[];
  };
  extractive_answer?: {
    summary?: string;
  };
  coverage_gaps?: string[];
  freshness?: {
    latest_record_date?: string | null;
  };
};

type AnswerBrief = {
  short_answer?: string;
  records_show?: string[];
  what_to_cite?: string[];
  who_to_contact?: string[];
  related_works?: string[];
  limits?: string[];
  evidence_table?: BriefEvidenceRow[];
};

type BriefEvidenceRow = {
  kind?: string;
  label?: string;
  source?: string;
  match_strength?: string;
  match_reason?: string;
};

type Claim = {
  text?: string;
  claim_type?: string;
  citation_ids?: string[];
  support_level?: string;
};

type Citation = {
  id?: string;
  source_id?: string | null;
  source_tier?: number;
  evidence_type?: string;
  raw_file?: string | null;
  row_number?: number | string | null;
};

type EvidenceEntry = {
  text?: string;
  match_strength?: string;
  match_reason?: string;
  fields?: Record<string, string | number | null | undefined>;
  citation?: {
    source_id?: string | null;
    raw_file?: string | null;
    row_number?: number | string | null;
  };
};

type IssueTrack = {
  issue_key?: string;
  title?: string;
  summary?: string;
  complaint_example_ids?: string[];
  support_types?: string[];
  gap?: string | null;
};

export function AskCivicRecord({
  initialQuery = "",
  autoFocus = false
}: {
  initialQuery?: string;
  autoFocus?: boolean;
}) {
  const [query, setQuery] = useState(initialQuery);
  const [submittedQuery, setSubmittedQuery] = useState(initialQuery.trim());
  const [answer, setAnswer] = useState<RagAnswer | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const hasQuery = query.trim().length > 0;
  const apiBase =
    process.env.NEXT_PUBLIC_CIVIC_API_BASE ??
    (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8017" : "");

  async function askBackend(nextQuery: string) {
    const q = nextQuery.trim();
    if (!q) return;
    setIsLoading(true);
    setError("");
    try {
      const response = await fetch(`${apiBase}/rag/ask?q=${encodeURIComponent(q)}`, {
        headers: { Accept: "application/json" }
      });
      if (!response.ok) {
        throw new Error(`Request failed with ${response.status}`);
      }
      setAnswer((await response.json()) as RagAnswer);
      setSubmittedQuery(q);
    } catch (caught) {
      setAnswer(null);
      setError(caught instanceof Error ? caught.message : "Could not ask the civic record.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (initialQuery.trim()) {
      void askBackend(initialQuery);
    }
  }, [initialQuery]);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void askBackend(query);
  }

  return (
    <section className="mx-auto flex min-h-[calc(100vh-2rem)] w-full max-w-3xl flex-col justify-center gap-5">
      <form action="/ask" onSubmit={onSubmit}>
        <input
          name="q"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Ask anything"
          autoFocus={autoFocus}
          className="w-full border border-line bg-paper px-5 py-4 text-lg text-ink outline-none transition focus:border-ink"
        />
      </form>

      {isLoading && <p className="text-base leading-7 text-muted">Searching the civic record...</p>}

      {error && <p className="text-base leading-7 text-muted">{error}</p>}

      {hasQuery && answer && !isLoading && submittedQuery === query.trim() && (
        <CivicAnswer answer={answer} />
      )}
    </section>
  );
}

function CivicAnswer({ answer }: { answer: RagAnswer }) {
  const triage = answer.civic_triage;
  const brief = answer.answer_brief;
  const memory = triage?.complaint_memory;
  const library = triage?.evidence_library;

  if (!triage) {
    return (
      <div className="text-base leading-7 text-ink">
        <p>{answer.generated_answer}</p>
      </div>
    );
  }

  if (brief) {
    return (
      <div className="space-y-6 text-base leading-7 text-ink">
        <section className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Short answer</h2>
          <p>{brief.short_answer ?? answer.generated_answer}</p>
        </section>

        <BriefList title="What records show" items={brief.records_show ?? []} />
        <BriefList title="What you can cite" items={brief.what_to_cite ?? []} />
        <BriefList title="Who to contact" items={brief.who_to_contact ?? []} />
        <BriefList title="Related works and payments" items={brief.related_works ?? []} />
        <BriefList title="What this does not prove" items={brief.limits ?? []} muted />

        {brief.evidence_table?.length ? (
          <section className="space-y-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Evidence table</h2>
            <ul className="space-y-3">
              {brief.evidence_table.slice(0, 6).map((row, index) => (
                <li key={`${row.source ?? "evidence"}-${index}`} className="border-l border-line pl-4 text-sm leading-6">
                  <p className="font-medium text-ink">
                    {row.kind ?? "Evidence"} · {row.match_strength ?? "source-backed"}
                  </p>
                  <p>{row.label}</p>
                  {row.match_reason ? <p className="text-muted">{row.match_reason}</p> : null}
                  {row.source ? <p className="text-muted">{row.source}</p> : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-5 text-base leading-7 text-ink">
      <p>{triage.civic_interpretation ?? answer.generated_answer}</p>

      {triage.who_to_contact?.length ? (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Who to contact / call path</h2>
          <ul className="list-disc space-y-1 pl-5">
            {triage.who_to_contact.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {triage.issue_tracks?.length && triage.issue_tracks.length > 1 ? (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Issue tracks</h2>
          <ul className="list-disc space-y-1 pl-5">
            {triage.issue_tracks.map((track) => (
              <li key={track.issue_key ?? track.title}>
                <span className="font-medium">{track.title ?? track.issue_key}:</span> {track.summary}
                {track.complaint_example_ids?.length ? ` Examples: ${track.complaint_example_ids.join(", ")}.` : ""}
                {track.gap ? ` ${track.gap}` : ""}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {triage.what_to_do_next?.length ? (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">What to say when you call</h2>
          <ul className="list-disc space-y-1 pl-5">
            {triage.what_to_do_next.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {memory ? (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Complaint memory</h2>
          <p>
            {formatCount(memory.count)} matching complaint records
            {memory.latest_record_date ? `; latest record ${memory.latest_record_date}` : ""}.
          </p>
          {memory.example_ids?.length ? (
            <p className="text-sm leading-6 text-muted">Example IDs: {memory.example_ids.join(", ")}</p>
          ) : null}
          {memory.scope_note ? (
            <p className="text-sm leading-6 text-muted">{memory.scope_note}</p>
          ) : null}
          {memory.status_breakdown ? (
            <p className="text-sm leading-6 text-muted">Status breakdown: {formatStatusBreakdown(memory.status_breakdown)}</p>
          ) : null}
        </section>
      ) : null}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Public evidence library</h2>
        <EvidenceList title="Related public works and spending" entries={[...(library?.work_payments ?? []), ...(library?.tenders ?? [])]} />
        <EvidenceList title="Complaint examples" entries={library?.complaints ?? []} />
      </section>

      <section className="space-y-2 text-sm leading-6 text-muted">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Neutrality note</h2>
        <p>
          These records do not prove corruption, negligence, or the exact cause of this specific issue. They show the
          public record around the issue so you can inspect it and draw your own conclusion.
        </p>
        {triage.cause_boundary ? <p>{triage.cause_boundary}</p> : null}
        {answer.coverage_gaps?.length ? <p>{answer.coverage_gaps.join(" ")}</p> : null}
        {answer.freshness?.latest_record_date ? <p>Latest cited record: {answer.freshness.latest_record_date}</p> : null}
        {answer.retrieval_trace ? (
          <p>
            Retrieval: {answer.retrieval_trace.retrieval_backend ?? "unknown"} ·{" "}
            {answer.retrieval_trace.retrieval_snapshot_id ?? "no snapshot"}
          </p>
        ) : null}
      </section>
    </div>
  );
}

function EvidenceList({ title, entries }: { title: string; entries: EvidenceEntry[] }) {
  if (!entries.length) return null;

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-ink">{title}</h3>
      <ul className="space-y-3">
        {entries.slice(0, 4).map((entry, index) => (
          <li key={`${title}-${index}`} className="border-l border-line pl-4 text-sm leading-6">
            {entry.match_strength ? (
              <p className="mb-1 font-medium text-ink">
                {entry.match_strength}
                {entry.match_reason ? ` · ${entry.match_reason}` : ""}
              </p>
            ) : null}
            <p>{entry.text}</p>
            {entry.citation?.source_id ? (
              <p className="mt-1 text-muted">
                {entry.citation.source_id}
                {entry.citation.row_number ? ` row ${entry.citation.row_number}` : ""}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function BriefList({ title, items, muted = false }: { title: string; items: string[]; muted?: boolean }) {
  if (!items.length) return null;

  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">{title}</h2>
      <ul className="list-disc space-y-1 pl-5">
        {items.map((item) => (
          <li key={item} className={muted ? "text-muted" : undefined}>
            {item}
          </li>
        ))}
      </ul>
    </section>
  );
}

function formatCount(value: number | undefined) {
  return typeof value === "number" ? value.toLocaleString("en-IN") : "0";
}

function formatStatusBreakdown(value: Record<string, number>) {
  return Object.entries(value)
    .map(([status, count]) => `${status}: ${count}`)
    .join(", ");
}
