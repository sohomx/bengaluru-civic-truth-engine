create table if not exists old_new_ward_mapping (
  old_new_ward_mapping_id uuid primary key,
  old_ward_id uuid references ward(ward_id),
  new_ward_id uuid references ward(ward_id),
  confidence numeric not null,
  method text not null,
  explanation text not null,
  evidence_id uuid references evidence(evidence_id)
);

create table if not exists complaint_ward_match (
  complaint_ward_match_id uuid primary key,
  complaint_id uuid references complaint(complaint_id),
  ward_id uuid references ward(ward_id),
  ward_version_id uuid references ward_version(ward_version_id),
  confidence numeric not null,
  method text not null,
  explanation text not null,
  evidence_id uuid references evidence(evidence_id)
);

create table if not exists work_ward_match (
  work_ward_match_id uuid primary key,
  work_id uuid references work(work_id),
  ward_id uuid references ward(ward_id),
  ward_version_id uuid references ward_version(ward_version_id),
  confidence numeric not null,
  method text not null,
  explanation text not null,
  evidence_id uuid references evidence(evidence_id)
);

create table if not exists asset_ward_match (
  asset_ward_match_id uuid primary key,
  asset_id uuid references asset(asset_id),
  ward_id uuid references ward(ward_id),
  confidence numeric not null,
  method text not null,
  explanation text not null,
  evidence_id uuid references evidence(evidence_id)
);

create table if not exists complaint_asset_match (
  complaint_asset_match_id uuid primary key,
  complaint_id uuid references complaint(complaint_id),
  asset_id uuid references asset(asset_id),
  confidence numeric not null,
  method text not null,
  explanation text not null,
  evidence_id uuid references evidence(evidence_id)
);

create table if not exists issue_authority_match (
  issue_authority_match_id uuid primary key,
  issue_category_id uuid references issue_category(issue_category_id),
  authority_id uuid references authority(authority_id),
  confidence numeric not null,
  method text not null,
  explanation text not null,
  evidence_id uuid references evidence(evidence_id)
);
