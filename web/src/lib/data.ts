import buildReportJson from "@/data/generated/build_report.json";
import placesJson from "@/data/generated/places.json";
import searchIndexJson from "@/data/generated/search_index.json";
import sourceStatusJson from "@/data/generated/source_status.json";
import bellandurAll from "@/data/generated/truth/bellandur/all.json";
import bellandurRecent from "@/data/generated/truth/bellandur/recent.json";
import bellandur2025 from "@/data/generated/truth/bellandur/y2025.json";
import mahadevapuraAll from "@/data/generated/truth/mahadevapura/all.json";
import mahadevapuraRecent from "@/data/generated/truth/mahadevapura/recent.json";
import mahadevapura2025 from "@/data/generated/truth/mahadevapura/y2025.json";
import varthurAll from "@/data/generated/truth/varthur/all.json";
import varthurRecent from "@/data/generated/truth/varthur/recent.json";
import varthur2025 from "@/data/generated/truth/varthur/y2025.json";
import whitefieldAll from "@/data/generated/truth/whitefield/all.json";
import whitefieldRecent from "@/data/generated/truth/whitefield/recent.json";
import whitefield2025 from "@/data/generated/truth/whitefield/y2025.json";

export type LensKey = "all" | "recent" | "y2025";

export type LensOption = {
  key: LensKey;
  label: string;
};

export const LENS_OPTIONS: LensOption[] = [
  { key: "all", label: "All years" },
  { key: "recent", label: "Recent: 2024-2025" },
  { key: "y2025", label: "2025 only" }
];

export type Evidence = {
  source_id?: string;
  raw_file?: string;
  row_number?: number;
  run_id?: string;
};

export type ClaimCard = {
  claim: string;
  claim_level: string;
  time_range: string;
  confidence: string;
  citations: Evidence[];
  caveat: string;
};

export type BuildMetadata = {
  generated_at: string;
  code_version: string;
  source_snapshot_id: string;
  included_sources: string[];
  excluded_sources: string[];
  record_date_min: string | null;
  record_date_max: string | null;
  known_gaps: string[];
};

export type WardCandidate = {
  ward_name?: string;
  ward_number?: string;
  corporation?: string;
  zone?: string;
  match_score?: number;
  match_method?: string;
  matched_area_context?: string;
  evidence?: Evidence;
};

export type ComplaintExample = {
  external_complaint_id?: string;
  issue_subcategory?: string;
  grievance_date?: string;
  status?: string;
  staff_name?: string;
  evidence?: Evidence;
};

export type IssueCategory = {
  category: string;
  count: number;
  examples: ComplaintExample[];
};

export type CountRow = {
  value: string;
  count: number;
};

export type TruthPayload = {
  query: string;
  normalized_query: string;
  build_metadata: BuildMetadata;
  claim_cards: ClaimCard[];
  record_scope: {
    label: string;
    grievance_year_min: number | null;
    grievance_year_max: number | null;
    grievance_date_min: string | null;
    grievance_date_max: string | null;
    active_year_from: number | null;
    active_year_to: number | null;
    freshness_note: string;
    context_note: string;
  };
  ward_context: {
    old_bbmp_candidates: WardCandidate[];
    new_gba_candidates: WardCandidate[];
    area_match_candidates: WardCandidate[];
    old_new_mappings: Record<string, unknown>[];
  };
  complaint_summary: {
    total_complaints: number;
    by_year: CountRow[];
    by_status: CountRow[];
  };
  top_issue_categories: IssueCategory[];
  evidence_policy: string;
};

export type PlaceRecord = {
  slug: string;
  label: string;
  payloads: Record<LensKey, TruthPayload>;
};

export type SourceStatusRow = {
  source_id: string;
  name: string;
  url: string;
  domain: string;
  agency: string;
  publisher: string;
  source_tier: number;
  official_status: string;
  format: string;
  access_method: string;
  parser_type: string;
  license: string;
  freshness_policy_days: number;
  reliability_score: number;
  pii_risk: string;
  enabled: boolean;
  notes: string;
  latest_fetch_status: string;
  latest_successful_run: string | null;
  latest_run: string | null;
  latest_fetched_at: string | null;
  file_count: number;
  parser_status: string;
  freshness_label: string;
  caveats: string[];
  normalized_usage_status: string;
};

export type SourceStatus = {
  generated_at: string;
  source_snapshot_id: string;
  summary: {
    total_sources: number;
    successful_fetches: number;
    not_fetched: number;
    used_in_public_claims: number;
  };
  sources: SourceStatusRow[];
};

export type BuildReport = {
  generated_at: string;
  code_version: string;
  source_snapshot_id: string;
  counts: {
    sources: number;
    truth_payloads: number;
    pilot_places: number;
    known_gaps: number;
  };
  known_gaps: string[];
  warnings: string[];
};

export type GeneratedPlaceSummary = {
  name: string;
  slug: string;
  lenses: { key: LensKey; label: string; total_complaints: number; record_date_max: string | null }[];
};

export type SearchIndexEntry = {
  id: string;
  kind: "place" | "source";
  answer_focus:
    | "place_memory"
    | "money_trail"
    | "budget_context"
    | "complaint_memory"
    | "service_issue"
    | "ward_context"
    | "source_context";
  title: string;
  href: string;
  summary: string;
  keywords: string[];
  freshness_note: string;
  record_date_max: string | null;
  total_complaints: number | null;
  top_issues: { category: string; count: number }[];
  claim_cards: ClaimCard[];
  retrieval_note: string;
};

export type SearchIndex = {
  generated_at: string;
  source_snapshot_id: string;
  entries: SearchIndexEntry[];
};

const places: PlaceRecord[] = [
  {
    slug: "bellandur",
    label: "Bellandur",
    payloads: {
      all: bellandurAll as TruthPayload,
      recent: bellandurRecent as TruthPayload,
      y2025: bellandur2025 as TruthPayload
    }
  },
  {
    slug: "mahadevapura",
    label: "Mahadevapura",
    payloads: {
      all: mahadevapuraAll as TruthPayload,
      recent: mahadevapuraRecent as TruthPayload,
      y2025: mahadevapura2025 as TruthPayload
    }
  },
  {
    slug: "varthur",
    label: "Varthur",
    payloads: {
      all: varthurAll as TruthPayload,
      recent: varthurRecent as TruthPayload,
      y2025: varthur2025 as TruthPayload
    }
  },
  {
    slug: "whitefield",
    label: "Whitefield",
    payloads: {
      all: whitefieldAll as TruthPayload,
      recent: whitefieldRecent as TruthPayload,
      y2025: whitefield2025 as TruthPayload
    }
  }
];

export function getPlaces(): PlaceRecord[] {
  return places;
}

export function getPlace(slug: string): PlaceRecord | undefined {
  return places.find((place) => place.slug === slug.toLowerCase());
}

export function getSourceStatus(): SourceStatus {
  return sourceStatusJson as SourceStatus;
}

export function getSources(): SourceStatusRow[] {
  return getSourceStatus().sources;
}

export function getSource(sourceId: string): SourceStatusRow | undefined {
  return getSources().find((source) => source.source_id === sourceId);
}

export function getBuildReport(): BuildReport {
  return buildReportJson as BuildReport;
}

export function getGeneratedPlaceSummaries(): GeneratedPlaceSummary[] {
  return (placesJson as { places: GeneratedPlaceSummary[] }).places;
}

export function getSearchIndex(): SearchIndex {
  return searchIndexJson as SearchIndex;
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-IN").format(value);
}

export function formatDate(value?: string | null): string {
  if (!value) return "Unavailable";
  return value.replace("T", " ").replace("Z", " UTC");
}

export function topYear(payload: TruthPayload): CountRow | undefined {
  return [...payload.complaint_summary.by_year].sort((a, b) => b.count - a.count)[0];
}

export function evidenceLabel(evidence?: Evidence): string {
  if (!evidence?.source_id) return "No evidence pointer";
  const row = evidence.row_number ? ` row ${evidence.row_number}` : "";
  return `${evidence.source_id}${row}`;
}

export function sourceStatusLabel(value: string): string {
  return value.replaceAll("_", " ");
}
