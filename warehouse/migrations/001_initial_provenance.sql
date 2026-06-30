create extension if not exists postgis;

create table if not exists source_registry (
  source_id text primary key,
  name text not null,
  url text not null,
  domain text not null,
  agency text not null,
  publisher text not null,
  source_tier integer not null,
  official_status text not null,
  format text not null,
  access_method text not null,
  parser_type text not null,
  reliability_score numeric not null,
  enabled boolean not null,
  last_checked_at timestamptz,
  last_successful_ingest_at timestamptz
);

create table if not exists ingest_run (
  ingest_run_id uuid primary key,
  source_id text not null references source_registry(source_id),
  started_at timestamptz not null,
  finished_at timestamptz,
  status text not null,
  manifest jsonb not null
);

create table if not exists raw_file (
  raw_file_id uuid primary key,
  ingest_run_id uuid not null references ingest_run(ingest_run_id),
  path text not null,
  sha256 text not null,
  bytes bigint not null,
  content_type text
);

create table if not exists source_record (
  source_record_id uuid primary key,
  raw_file_id uuid references raw_file(raw_file_id),
  source_id text not null references source_registry(source_id),
  external_id text,
  record_index integer,
  payload jsonb not null
);

create table if not exists evidence (
  evidence_id uuid primary key,
  source_record_id uuid references source_record(source_record_id),
  source_id text not null references source_registry(source_id),
  evidence_type text not null,
  claim_text text,
  citation jsonb not null,
  confidence numeric not null
);

create table if not exists qa_check (
  qa_check_id uuid primary key,
  ingest_run_id uuid references ingest_run(ingest_run_id),
  check_name text not null,
  status text not null,
  details jsonb not null
);
