create table if not exists ward (
  ward_id uuid primary key,
  ward_code text,
  name text not null,
  corporation text,
  zone text
);

create table if not exists ward_version (
  ward_version_id uuid primary key,
  name text not null,
  valid_from date,
  valid_to date,
  source_id text references source_registry(source_id)
);

create table if not exists ward_boundary (
  ward_boundary_id uuid primary key,
  ward_id uuid references ward(ward_id),
  ward_version_id uuid references ward_version(ward_version_id),
  geom geometry(MultiPolygon, 4326) not null,
  source_record_id uuid references source_record(source_record_id)
);

create table if not exists issue_category (
  issue_category_id uuid primary key,
  name text not null,
  parent_issue_category_id uuid references issue_category(issue_category_id)
);

create table if not exists complaint (
  complaint_id uuid primary key,
  external_complaint_id text,
  issue_category_id uuid references issue_category(issue_category_id),
  grievance_date date,
  ward_name_raw text,
  status text,
  staff_remarks text,
  source_record_id uuid references source_record(source_record_id)
);

create table if not exists asset (
  asset_id uuid primary key,
  asset_type text not null,
  name text,
  geom geometry(Geometry, 4326),
  source_record_id uuid references source_record(source_record_id)
);

create table if not exists work (
  work_id uuid primary key,
  description text not null,
  contractor text,
  amount numeric,
  status text,
  source_record_id uuid references source_record(source_record_id)
);

create table if not exists payment (
  payment_id uuid primary key,
  work_id uuid references work(work_id),
  amount numeric,
  paid_at date,
  source_record_id uuid references source_record(source_record_id)
);

create table if not exists tender (
  tender_id uuid primary key,
  title text not null,
  amount numeric,
  status text,
  source_record_id uuid references source_record(source_record_id)
);

create table if not exists authority (
  authority_id uuid primary key,
  name text not null,
  authority_type text not null,
  jurisdiction text
);

create table if not exists rule_document (
  rule_document_id uuid primary key,
  title text not null,
  source_record_id uuid references source_record(source_record_id)
);

create table if not exists rule_clause (
  rule_clause_id uuid primary key,
  rule_document_id uuid references rule_document(rule_document_id),
  clause_ref text,
  text text not null
);

create table if not exists place_memory (
  place_memory_id uuid primary key,
  place_name text not null,
  fact text not null,
  source_record_id uuid references source_record(source_record_id),
  confidence numeric not null
);
