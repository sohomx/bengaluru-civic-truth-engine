# Data Architecture

## Flow

```text
Source Registry
  -> Raw Archive
  -> Parsed Staging
  -> Postgres + PostGIS Warehouse
  -> Entity Matching Jobs
  -> QA / Provenance Checks
  -> Civic Memory API
  -> Ward Truth Page / Issue Truth Page / Escalation Dossier
```

## Raw Archive

Raw archive runs are immutable and timestamped:

```text
data/raw/<source_id>/<fetch_timestamp>/
  manifest.json
  original/
  metadata/
  checksums.sha256
  fetch.log
```

Failed fetches still produce manifests so gaps are inspectable.

CKAN manifests use an additive v2 resource ledger:

```text
manifest.json
  manifest_version: 2
  files: [...]
  ckan_resources:
    total
    completed
    failed
    pending
    records[]
```

Each resource record stores resource id, URL, filename, status, attempts, path,
SHA-256, byte count, content type, error text, and reuse provenance. Resume runs
create a new immutable run directory and copy previously verified files into it;
old raw runs are never mutated.

## Warehouse

The warehouse uses PostgreSQL + PostGIS. Core tables preserve provenance,
normalized civic entities, and uncertainty-aware matches.

Low-confidence spatial, text, and locality matches are signals until manually
reviewed or corroborated by stronger evidence.

## Wave 1 Normalized Files

Before PostGIS is required for local inspection, Wave 1 writes deterministic JSON
artifacts under ignored `data/normalized/`:

```text
data/normalized/
  wards.json
  old_new_ward_mappings.json
  ward_rejections.json
  complaints.json
  issue_categories.json
  complaint_rejections.json
```

Each normalized ward and complaint keeps an `evidence` object pointing back to
the archived source id, run id, raw file, and CSV row number. Rejected rows are
kept in rejection files with a reason.

The first truth reports are generated from this local normalized warehouse:

```bash
python3 -m civic_data places truth --q Bellandur --output data/exports/truth-bellandur.json
```

Area queries can match ward name, official old/new ward mappings, and area
context fields such as BBMP zone, corporation, and assembly constituency.

## Civic Truth Dossiers

`python3 -m civic_data dossiers create --place Bellandur --output data/exports/dossier-bellandur.md`
turns a place-truth payload into a shareable Markdown dossier.

The dossier includes:

- an executive summary with bounded claims
- official ward context
- complaint totals by year and status
- recurring issue categories
- issue briefs for the top recurring categories
- cited complaint examples with compact citation ids
- staff/department clues where present
- quality warnings for ward matching, closure status, and reporting bias
- claim-discipline notes that separate supported claims from unsupported
  interpretation
- an evidence appendix with source id, raw file, and row references

## Wave 1 Postgres Load Artifacts

`python3 -m civic_data warehouse export` converts the normalized JSON files into
Postgres-ready CSV files and a load script under ignored `data/warehouse/`:

```text
data/warehouse/
  ward.csv
  old_new_ward_mapping.csv
  issue_category.csv
  complaint.csv
  load_wave1.sql
  manifest.json
```

The load script creates a `civic_wave1` schema and imports the four Wave 1
tables with JSON evidence columns intact. It is intentionally separate from the
long-term PostGIS migrations so the first useful warehouse can be loaded and
inspected before spatial normalization is complete.

## Civic Memory API

The first API surface is a thin wrapper over the same truth service used by the
CLI:

```text
GET /places/search?q=
GET /places/truth?q=
```

`/places/search` returns candidate ward and area context. `/places/truth`
returns the full cited report.
