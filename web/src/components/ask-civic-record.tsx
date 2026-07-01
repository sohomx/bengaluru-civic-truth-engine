"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { Clipboard, FileText, Loader2, LocateFixed, Search, ShieldCheck } from "lucide-react";

type CivicPacket = {
  contract?: {
    name?: string;
    version?: string;
    source_of_truth?: string;
  };
  packet_type?: string;
  packet_status?: string;
  evidence_strength?: "none" | "weak" | "public_row" | "official_lookup" | string;
  input?: {
    query?: string;
    lat?: number | null;
    lng?: number | null;
  };
  issue?: {
    type?: string;
    urgency?: string;
    matched_terms?: string[];
  };
  place?: {
    normalized_place?: string | null;
    ward_name?: string | null;
    ward_number?: string | null;
    corporation?: string | null;
    confidence?: number | null;
    source?: string | null;
    caveat?: string | null;
  };
  responsibility?: {
    primary_agency?: {
      name?: string;
      agency_id?: string;
    };
    fallback_agency?: {
      name?: string;
      agency_id?: string;
    };
    ownership_caveat?: string;
    routing_decision?: {
      policy_id?: string;
      policy_version?: string;
      rule_ids?: string[];
    };
  };
  evidence_summary?: {
    shown_count?: number;
    total_matches?: number;
    hidden_count?: number;
  };
  action?: {
    primary_action?: string;
    escalation_action?: string;
    legal_or_rti_action?: string;
    message_draft?: string;
    evidence_to_attach?: string[];
    what_not_to_claim?: string[];
    who_to_contact?: string[];
  };
  evidence?: EvidenceRow[];
  evidence_table?: LegacyEvidenceRow[];
  trace?: {
    trace_id?: string;
    resolver_source?: string;
    routing_policy_id?: string;
    routing_policy_version?: string;
    routing_rule_ids?: string[];
  };
  provenance?: {
    model?: string;
    evidence_records?: {
      source_id?: string;
      source_tier?: string;
      run_id?: string;
      raw_file?: string;
      row_or_page_id?: string;
      parser_version?: string;
      fetched_at?: string;
      record_date?: string;
      freshness_status?: string;
      publishable?: boolean;
      can_prove?: string[];
      cannot_prove?: string[];
      freshness_scope?: string;
    }[];
  };
  limits?: string[];
  audit?: {
    source_of_truth?: string;
    legacy_rag_status?: string;
    query_hash?: string;
    used_rag?: boolean;
    used_raw_scan?: boolean;
    resolver_source?: string | null;
    routing_policy_id?: string | null;
    routing_policy_version?: string | null;
    routing_rule_ids?: string[];
  };
};

type PacketExplanation = {
  what_the_packet_says?: string;
  why_this_agency?: string;
  what_to_cite?: string[];
  what_not_to_claim?: string[];
  audit?: {
    used_packet_only?: boolean;
    used_raw_scan?: boolean;
    used_private_data?: boolean;
  };
};

type EvidenceRow = {
  evidence_id?: string;
  entity_type?: string;
  source_id?: string;
  row_number?: number | string;
  claim?: string;
  display_claim?: string;
  relevance_label?: string;
  proof_note?: string;
  claim_class?: string;
  match_confidence?: number;
  match_method?: string;
  allowed_claims?: string[];
  disallowed_claims?: string[];
};

type LegacyEvidenceRow = {
  kind?: string;
  label?: string;
  source?: string;
  match_strength?: string;
  match_reason?: string;
};

type ProofBoundary = {
  source_id: string;
  can_prove: string[];
  cannot_prove: string[];
  freshness_scope: string;
};

const EXAMPLE_QUERIES = [
  "Bellandur streetlight not working",
  "Kadubeesanahalli sewage overflowing",
  "Whitefield recurring pothole",
  "Bellandur power outage"
];

export function AskCivicRecord({
  initialQuery = "",
  autoFocus = false
}: {
  initialQuery?: string;
  autoFocus?: boolean;
}) {
  const [query, setQuery] = useState(initialQuery);
  const [submittedQuery, setSubmittedQuery] = useState(initialQuery.trim());
  const [packet, setPacket] = useState<CivicPacket | null>(null);
  const [explanation, setExplanation] = useState<PacketExplanation | null>(null);
  const [error, setError] = useState("");
  const [explanationError, setExplanationError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isExplaining, setIsExplaining] = useState(false);
  const [location, setLocation] = useState<{ lat: number; lng: number } | null>(null);
  const [locationStatus, setLocationStatus] = useState("");
  const [copied, setCopied] = useState(false);
  const hasQuery = query.trim().length > 0;
  const apiBase =
    process.env.NEXT_PUBLIC_CIVIC_API_BASE ??
    (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8017" : "");

  async function buildPacket(nextQuery: string) {
    const q = nextQuery.trim();
    if (!q) return;
    setIsLoading(true);
    setError("");
    setExplanation(null);
    setExplanationError("");
    setCopied(false);
    try {
      const params = new URLSearchParams({ q });
      if (location) {
        params.set("lat", String(location.lat));
        params.set("lng", String(location.lng));
      }
      const response = await fetch(`${apiBase}/packets/build?${params.toString()}`, {
        headers: { Accept: "application/json" }
      });
      if (!response.ok) {
        throw new Error(`Request failed with ${response.status}`);
      }
      setPacket((await response.json()) as CivicPacket);
      setSubmittedQuery(q);
    } catch (caught) {
      setPacket(null);
      setError(caught instanceof Error ? caught.message : "Could not build a civic action packet.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (initialQuery.trim()) {
      void buildPacket(initialQuery);
    }
  }, [initialQuery]);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void buildPacket(query);
  }

  function requestLocation() {
    if (!navigator.geolocation) {
      setLocationStatus("Location is not available in this browser.");
      return;
    }
    setLocationStatus("Requesting location...");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocation({
          lat: Number(position.coords.latitude.toFixed(6)),
          lng: Number(position.coords.longitude.toFixed(6))
        });
        setLocationStatus("Pin added for official ward lookup.");
      },
      () => setLocationStatus("Location was not added."),
      { enableHighAccuracy: true, timeout: 8000 }
    );
  }

  async function copyMessage() {
    const message = packet?.action?.message_draft;
    if (!message) return;
    await navigator.clipboard.writeText(message);
    setCopied(true);
  }

  async function explainPacket() {
    if (!packet) return;
    setIsExplaining(true);
    setExplanationError("");
    try {
      const response = await fetch(`${apiBase}/packets/explain`, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          packet,
          question: "Explain why this agency was chosen and what evidence can be cited."
        })
      });
      if (!response.ok) {
        throw new Error(`Explanation failed with ${response.status}`);
      }
      setExplanation((await response.json()) as PacketExplanation);
    } catch (caught) {
      setExplanation(null);
      setExplanationError(caught instanceof Error ? caught.message : "Could not explain this packet.");
    } finally {
      setIsExplaining(false);
    }
  }

  return (
    <section className="mx-auto flex min-h-[calc(100vh-2rem)] w-full max-w-5xl items-center px-0 py-4 sm:px-4">
      <div className="w-full border border-line bg-paper shadow-soft">
        <div className="flex items-center justify-between border-b border-line px-4 py-3 sm:px-6">
          <div>
            <p className="text-sm font-semibold text-ink">Bengaluru Civic Truth Engine</p>
            <p className="text-xs text-muted">Civic action packet</p>
          </div>
          <div className="flex items-center gap-2 text-xs text-muted">
            <ShieldCheck aria-hidden className="h-4 w-4 text-civic" />
            <span>Public-safe</span>
          </div>
        </div>

        <form className="border-b border-line px-4 py-4 sm:px-6" action="/ask" onSubmit={onSubmit}>
          <div className="flex flex-col gap-3 sm:flex-row">
            <textarea
              name="q"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Describe the issue and place..."
              autoFocus={autoFocus}
              rows={2}
              className="min-h-20 flex-1 resize-none border border-line bg-white px-4 py-3 text-base leading-6 text-ink outline-none transition focus:border-ink"
            />
            <div className="flex gap-2 sm:flex-col">
              <button
                type="submit"
                disabled={!hasQuery || isLoading}
                className="inline-flex h-11 flex-1 items-center justify-center gap-2 bg-ink px-4 text-sm font-medium text-white transition hover:bg-civic disabled:cursor-not-allowed disabled:bg-line disabled:text-muted sm:flex-none"
              >
                {isLoading ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Search aria-hidden className="h-4 w-4" />}
                Build
              </button>
              <button
                type="button"
                onClick={requestLocation}
                className="inline-flex h-11 flex-1 items-center justify-center gap-2 border border-line px-4 text-sm font-medium text-ink transition hover:border-civic hover:text-civic sm:flex-none"
              >
                <LocateFixed aria-hidden className="h-4 w-4" />
                Pin
              </button>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            {EXAMPLE_QUERIES.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => {
                  setQuery(example);
                  void buildPacket(example);
                }}
                className="border border-line px-2.5 py-1 text-xs text-muted transition hover:border-civic hover:text-ink"
              >
                {example}
              </button>
            ))}
          </div>

          {locationStatus ? <p className="mt-2 text-xs text-muted">{locationStatus}</p> : null}
        </form>

        <div className="px-4 py-5 sm:px-6 sm:py-6">
          {isLoading ? <LoadingState /> : null}
          {error ? <p className="text-sm leading-6 text-muted">{error}</p> : null}
          {hasQuery && packet && !isLoading && submittedQuery === query.trim() ? (
            <PacketCaseDesk
              packet={packet}
              explanation={explanation}
              explanationError={explanationError}
              isExplaining={isExplaining}
              onCopyMessage={copyMessage}
              onExplainPacket={explainPacket}
              copied={copied}
            />
          ) : null}
          {!packet && !isLoading && !error ? <EmptyState /> : null}
        </div>
      </div>
    </section>
  );
}

function PacketCaseDesk({
  packet,
  explanation,
  explanationError,
  isExplaining,
  onCopyMessage,
  onExplainPacket,
  copied
}: {
  packet: CivicPacket;
  explanation: PacketExplanation | null;
  explanationError: string;
  isExplaining: boolean;
  onCopyMessage: () => void;
  onExplainPacket: () => void;
  copied: boolean;
}) {
  const placeLabel = formatPlace(packet);
  const owner = packet.responsibility?.primary_agency?.name ?? "Ownership unresolved";
  const evidenceRows = useMemo(() => normalizedEvidenceRows(packet), [packet]);
  const proofBoundaries = useMemo(() => sourceProofBoundaries(packet), [packet]);
  const notToClaim = packet.action?.what_not_to_claim?.length ? packet.action.what_not_to_claim : packet.limits ?? [];
  const [showMoreEvidence, setShowMoreEvidence] = useState(false);

  return (
    <div className="space-y-6 text-ink">
      <section>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <StatusPill value={packet.packet_status ?? "unknown"} />
          <StatusPill value={`Evidence: ${formatEvidenceStrength(packet.evidence_strength)}`} quiet />
          <StatusPill value="Facts: public records" quiet />
          <StatusPill value={explanation ? "AI: explains packet only" : "AI: optional"} quiet />
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h1 className="text-xl font-semibold tracking-normal text-ink sm:text-2xl">Case summary</h1>
          <button
            type="button"
            onClick={onExplainPacket}
            disabled={isExplaining}
            className="inline-flex h-9 items-center justify-center gap-2 border border-line px-3 text-xs font-medium text-ink transition hover:border-civic hover:text-civic disabled:cursor-not-allowed disabled:text-muted"
          >
            {isExplaining ? <Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin" /> : <FileText aria-hidden className="h-3.5 w-3.5" />}
            {isExplaining ? "Explaining" : "Why this answer?"}
          </button>
        </div>
        <div className="mt-4 grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
          <SummaryItem label="Issue" value={formatIssue(packet)} />
          <SummaryItem label="Place" value={placeLabel} />
          <SummaryItem label="Owner" value={owner} />
          <SummaryItem label="Ward source" value={formatSourceLabel(packet.place?.source ?? packet.audit?.resolver_source)} />
        </div>
        {packet.responsibility?.ownership_caveat ? (
          <p className="mt-4 max-w-3xl text-sm leading-6 text-muted">{packet.responsibility.ownership_caveat}</p>
        ) : null}
        <p className="mt-3 max-w-3xl text-xs leading-5 text-muted">
          Facts come from public records and resolver data; AI only explains this packet.
        </p>
        {explanationError ? <p className="mt-3 text-sm leading-6 text-muted">{explanationError}</p> : null}
      </section>

      {explanation ? (
        <>
          <Divider />
          <section>
            <h2 className="section-title">Why this route</h2>
            <div className="mt-3 grid gap-4 lg:grid-cols-2">
              <div className="border-l border-line pl-4">
                <p className="text-xs font-medium uppercase text-muted">Packet reading</p>
                <p className="mt-1 text-sm leading-6 text-ink">{explanation.what_the_packet_says}</p>
              </div>
              <div className="border-l border-line pl-4">
                <p className="text-xs font-medium uppercase text-muted">Agency choice</p>
                <p className="mt-1 text-sm leading-6 text-ink">{explanation.why_this_agency}</p>
              </div>
            </div>
            {explanation.what_to_cite?.length ? (
              <p className="mt-4 text-sm leading-6 text-muted">
                Cite: {explanation.what_to_cite.slice(0, 2).join(" ")}
              </p>
            ) : null}
          </section>
        </>
      ) : null}

      <Divider />

      <section>
        <h2 className="section-title">What to do next</h2>
        <div className="mt-3 grid gap-4 lg:grid-cols-3">
          <ActionStep number="1" title="Primary action" text={packet.action?.primary_action} />
          <ActionStep number="2" title="Escalate" text={packet.action?.escalation_action} />
          <ActionStep number="3" title="Records / RTI" text={packet.action?.legal_or_rti_action} />
        </div>
        {packet.action?.evidence_to_attach?.length ? (
          <p className="mt-4 text-sm leading-6 text-muted">
            Attach: {packet.action.evidence_to_attach.join(", ")}.
          </p>
        ) : null}
      </section>

      <Divider />

      <section>
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <h2 className="section-title">Best public evidence</h2>
            <p className="mt-1 text-xs text-muted">{formatEvidenceSummary(packet, evidenceRows)}</p>
          </div>
        </div>
        <EvidenceTable
          rows={evidenceRows}
          expanded={showMoreEvidence}
          onToggleExpanded={() => setShowMoreEvidence((value) => !value)}
        />
      </section>

      {proofBoundaries.length ? (
        <>
          <Divider />
          <section>
            <h2 className="section-title">Source proof boundaries</h2>
            <div className="mt-3 grid gap-4 lg:grid-cols-2">
              {proofBoundaries.slice(0, 4).map((boundary) => (
                <div key={boundary.source_id} className="border-l border-line pl-4">
                  <p className="text-xs font-medium uppercase text-muted">{formatPublicSource(boundary.source_id)}</p>
                  <p className="mt-1 text-sm leading-6 text-ink">{boundary.can_prove[0]}</p>
                  <p className="mt-1 text-xs leading-5 text-muted">Cannot prove: {boundary.cannot_prove[0]}</p>
                  <p className="mt-1 text-xs leading-5 text-muted">{boundary.freshness_scope}</p>
                </div>
              ))}
            </div>
          </section>
        </>
      ) : null}

      <Divider />

      <section className="grid gap-6 lg:grid-cols-[1.3fr_0.7fr]">
        <div>
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="section-title">Simple message</h2>
            <button
              type="button"
              onClick={onCopyMessage}
              disabled={!packet.action?.message_draft}
              className="inline-flex h-9 items-center gap-2 border border-line px-3 text-xs font-medium text-ink transition hover:border-civic hover:text-civic disabled:cursor-not-allowed disabled:text-muted"
            >
              <Clipboard aria-hidden className="h-3.5 w-3.5" />
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <p className="whitespace-pre-wrap border-l border-line pl-4 text-sm leading-6 text-ink">
            {packet.action?.message_draft ?? "No message draft was generated for this packet."}
          </p>
        </div>

        <div>
          <h2 className="section-title">What not to claim</h2>
          <ul className="mt-3 space-y-2 text-sm leading-6 text-muted">
            {notToClaim.length ? (
              notToClaim.slice(0, 5).map((item) => <li key={item}>- {item}</li>)
            ) : (
              <li>- Do not claim field resolution unless the packet has proof.</li>
            )}
          </ul>
        </div>
      </section>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="py-10 text-sm leading-6 text-muted">
      <p>Start with a civic issue and a place. The packet will show the case summary, next action, evidence, and proof limits.</p>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex items-center gap-3 py-10 text-sm text-muted">
      <Loader2 aria-hidden className="h-4 w-4 animate-spin text-civic" />
      Building a public-safe action packet...
    </div>
  );
}

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-xs font-medium uppercase text-muted">{label}</p>
      <p className="mt-1 break-words text-sm font-medium leading-6 text-ink">{value}</p>
    </div>
  );
}

function ActionStep({ number, title, text }: { number: string; title: string; text?: string }) {
  return (
    <div className="border-l border-line pl-4">
      <p className="text-xs font-medium uppercase text-muted">{number} / {title}</p>
      <p className="mt-1 text-sm leading-6 text-ink">{text ?? "No action was generated."}</p>
    </div>
  );
}

function EvidenceTable({
  rows,
  expanded,
  onToggleExpanded
}: {
  rows: EvidenceRow[];
  expanded: boolean;
  onToggleExpanded: () => void;
}) {
  if (!rows.length) {
    return (
      <p className="border-l border-line pl-4 text-sm leading-6 text-muted">
        No matching public work/payment row was found. Use the official channel and jurisdiction as the basis for filing.
      </p>
    );
  }

  const visibleRows = expanded ? rows.slice(0, 6) : rows.slice(0, 3);
  const canExpand = rows.length > 3;

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-line text-xs uppercase text-muted">
              <th className="py-2 pr-4 font-medium">Public record</th>
              <th className="py-2 pr-4 font-medium">Type</th>
              <th className="py-2 pr-4 font-medium">Match</th>
              <th className="py-2 font-medium">What it supports</th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row, index) => (
              <tr key={`${row.source_id ?? "evidence"}-${row.row_number ?? index}`} className="border-b border-line/70 align-top last:border-0">
                <td className="py-3 pr-4 text-muted">
                  <span className="block text-ink">{formatPublicSource(row.source_id)}</span>
                  {row.row_number ? <span className="block text-xs">row {row.row_number}</span> : null}
                </td>
                <td className="py-3 pr-4 text-muted">{formatEntityType(row.entity_type)}</td>
                <td className="py-3 pr-4 text-muted">{formatMatchLabel(row)}</td>
                <td className="py-3 text-ink">
                  <p className="leading-6">{row.display_claim ?? row.claim ?? "A public record exists."}</p>
                  <p className="mt-1 text-xs leading-5 text-muted">
                    {row.proof_note ?? row.disallowed_claims?.[0] ?? "Public context only; not proof of field resolution."}
                  </p>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {canExpand ? (
        <button
          type="button"
          onClick={onToggleExpanded}
          className="mt-3 border border-line px-3 py-1.5 text-xs font-medium text-ink transition hover:border-civic hover:text-civic"
        >
          {expanded ? "Show top evidence" : "Show more evidence"}
        </button>
      ) : null}
    </div>
  );
}

function StatusPill({ value, quiet = false }: { value: string; quiet?: boolean }) {
  return (
    <span className={`border px-2.5 py-1 text-xs ${quiet ? "border-line text-muted" : "border-civic text-civic"}`}>
      {value}
    </span>
  );
}

function Divider() {
  return <div className="h-px w-full bg-line" />;
}

function normalizedEvidenceRows(packet: CivicPacket): EvidenceRow[] {
  if (packet.evidence?.length) return packet.evidence;
  return (packet.evidence_table ?? []).map((row, index) => ({
    evidence_id: `legacy-${index}`,
    entity_type: row.kind,
    source_id: row.source,
    claim: row.label,
    claim_class: row.match_strength,
    match_method: row.match_reason
  }));
}

function sourceProofBoundaries(packet: CivicPacket): ProofBoundary[] {
  const records = packet.provenance?.evidence_records ?? [];
  const bySource = new Map<string, ProofBoundary>();
  for (const record of records) {
    if (!record.source_id || bySource.has(record.source_id)) continue;
    const canProve = record.can_prove?.filter(Boolean) ?? [];
    const cannotProve = record.cannot_prove?.filter(Boolean) ?? [];
    if (!canProve.length && !cannotProve.length && !record.freshness_scope) continue;
    bySource.set(record.source_id, {
      source_id: record.source_id,
      can_prove: canProve.length ? canProve : ["Public context present in the packet evidence."],
      cannot_prove: cannotProve.length ? cannotProve : ["Live civic status or current ground truth."],
      freshness_scope: record.freshness_scope ?? "Available packet evidence only; not live issue status."
    });
  }
  return Array.from(bySource.values());
}

function formatIssue(packet: CivicPacket) {
  return packet.issue?.type ? titleCase(packet.issue.type) : "Unresolved civic issue";
}

function formatPlace(packet: CivicPacket) {
  const place = packet.place;
  if (!place) return "Place unresolved";
  const ward = place.ward_name ? `${place.ward_number ? `${place.ward_number} ` : ""}${place.ward_name}` : place.normalized_place;
  return [ward, place.corporation].filter(Boolean).join(" / ") || "Place unresolved";
}

function formatEvidenceStrength(value: CivicPacket["evidence_strength"]) {
  if (!value) return "none";
  return value.replaceAll("_", " ");
}

function formatEvidenceSummary(packet: CivicPacket, rows: EvidenceRow[]) {
  if (!rows.length) return "No public work/payment row matched.";
  const total = packet.evidence_summary?.total_matches ?? rows.length;
  const shown = Math.min(packet.evidence_summary?.shown_count ?? 3, total);
  if (total <= shown) return `Showing ${total} matched public row${total === 1 ? "" : "s"}.`;
  return `Showing top ${shown} of ${total} matched public rows.`;
}

function formatSourceLabel(source?: string | null) {
  const value = (source ?? "").toLowerCase();
  if (!value) return "Unresolved";
  if (value.includes("xyinfo")) return "Official BBMP/GBA coordinate lookup";
  if (value.includes("offline") && value.includes("ward")) return "Offline public ward data";
  if (value.includes("alias")) return "Locality hint";
  return titleCase(source ?? "public source");
}

function formatPublicSource(source?: string) {
  const value = (source ?? "").toLowerCase();
  if (value.includes("work_orders")) return "BBMP/GBA work orders";
  if (value.includes("bescom")) return "BESCOM public channel";
  if (value.includes("bwssb")) return "BWSSB public channel";
  if (value.includes("btp")) return "BTP public source";
  return source ? titleCase(source) : "Public source";
}

function formatEntityType(value?: string) {
  if (!value) return "Evidence";
  return titleCase(value);
}

function formatMatchLabel(row: EvidenceRow) {
  if (row.relevance_label) return row.relevance_label;
  const method = (row.match_method ?? "").toLowerCase();
  if (method.includes("ward") && method.includes("issue")) return "Ward + issue match";
  if (method.includes("place") && method.includes("issue")) return "Strong locality + issue match";
  if (typeof row.match_confidence === "number" && row.match_confidence >= 0.8) return "Strong public-record match";
  return row.claim_class ? titleCase(row.claim_class) : "Source-backed";
}

function titleCase(value: string) {
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}
