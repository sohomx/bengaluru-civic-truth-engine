create extension if not exists postgis;
create extension if not exists pg_trgm;
create extension if not exists vector;

create table if not exists place_alias (
  place_alias_id uuid primary key,
  alias text not null,
  normalized_alias text not null,
  ward_id uuid references ward(ward_id),
  source_id text references source_registry(source_id),
  confidence numeric not null default 1.0,
  metadata jsonb not null default '{}'::jsonb
);

create table if not exists contact_channel (
  contact_channel_id uuid primary key,
  agency text not null,
  issue_key text,
  channel_type text not null,
  label text not null,
  value text not null,
  source_id text references source_registry(source_id),
  citation jsonb not null,
  valid_from date,
  valid_to date
);

create table if not exists retrieval_snapshot (
  retrieval_snapshot_id uuid primary key,
  built_at timestamptz not null,
  source_manifest_hash text not null,
  chunk_count integer not null,
  embedding_model text,
  metadata jsonb not null default '{}'::jsonb
);

create table if not exists evidence_chunk (
  evidence_chunk_id uuid primary key,
  retrieval_snapshot_id uuid references retrieval_snapshot(retrieval_snapshot_id),
  source_record_id uuid references source_record(source_record_id),
  evidence_id uuid references evidence(evidence_id),
  entity_type text not null,
  entity_id uuid,
  ward_id uuid references ward(ward_id),
  issue_category_id uuid references issue_category(issue_category_id),
  source_id text not null references source_registry(source_id),
  source_tier integer not null,
  title text not null,
  body text not null,
  event_date date,
  amount numeric,
  contractor text,
  external_ref text,
  citation jsonb not null,
  metadata jsonb not null default '{}'::jsonb,
  search_vector tsvector generated always as (
    setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(body, '')), 'B') ||
    setweight(to_tsvector('simple', coalesce(contractor, '')), 'C') ||
    setweight(to_tsvector('simple', coalesce(external_ref, '')), 'C')
  ) stored,
  embedding vector(1536)
);

create table if not exists answer_eval_case (
  answer_eval_case_id uuid primary key,
  suite text not null,
  query text not null,
  expected_place text,
  expected_issue text,
  required_claim_types text[] not null default '{}',
  required_source_ids text[] not null default '{}',
  metadata jsonb not null default '{}'::jsonb
);

create table if not exists answer_eval_result (
  answer_eval_result_id uuid primary key,
  answer_eval_case_id uuid references answer_eval_case(answer_eval_case_id),
  retrieval_snapshot_id uuid references retrieval_snapshot(retrieval_snapshot_id),
  ran_at timestamptz not null,
  status text not null,
  metrics jsonb not null,
  answer_payload jsonb not null
);

create index if not exists place_alias_normalized_trgm_idx
  on place_alias using gin (normalized_alias gin_trgm_ops);

create index if not exists contact_channel_issue_idx
  on contact_channel(issue_key, agency);

create index if not exists evidence_chunk_ward_type_date_idx
  on evidence_chunk(ward_id, entity_type, event_date desc);

create index if not exists evidence_chunk_source_idx
  on evidence_chunk(source_id, source_tier);

create index if not exists evidence_chunk_search_idx
  on evidence_chunk using gin(search_vector);

create index if not exists evidence_chunk_embedding_idx
  on evidence_chunk using ivfflat (embedding vector_cosine_ops) with (lists = 100);

create index if not exists answer_eval_case_suite_idx
  on answer_eval_case(suite);
