# Data Dictionary

## Core Entities

- `source_registry`: machine-readable source metadata.
- `ingest_run`: one fetch or normalization run.
- `raw_file`: archived source files and checksums.
- `source_record`: row/document-level provenance.
- `evidence`: citable source-backed facts.
- `ward`, `ward_version`, `ward_boundary`: old BBMP and new GBA ward context.
- `complaint`: official grievance records.
- `issue_category`: normalized issue taxonomy.
- `asset`: roads, drains, streetlights, SWM assets, parks, lakes, facilities.
- `work`, `payment`, `tender`: public works and money trail.
- `authority`: agencies, departments, officials, and escalation routes.
- `rule_document`, `rule_clause`: rules, circulars, guidelines, and laws.
- `place_memory`: sourced historical or civic-place context.

## Match Tables

- `old_new_ward_mapping`
- `complaint_ward_match`
- `work_ward_match`
- `asset_ward_match`
- `complaint_asset_match`
- `issue_authority_match`

All match tables must include confidence, method, explanation, and evidence.
