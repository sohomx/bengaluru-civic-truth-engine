# Bengaluru Civic Truth Engine Data Execution Plan

## Summary

Build the project as a provenance-first civic data system. The first slice is
Fetch All First: register and archive every source from the overview before deep
normalization or frontend work.

Execution order:

1. Create repo scaffold, source policy, and registry schema.
2. Convert every source in the overview into machine-readable registry entries.
3. Build fetchers for OpenCity CKAN, direct files, official HTML pages, PDFs, and GitHub/community references.
4. Fetch/archive every reachable source with immutable manifests, checksums, metadata, and failure reports.
5. Profile all fetched data and classify parser difficulty.
6. Normalize in waves: wards/grievances first, then works/roads/drains/SWM/streetlights, then rules/budgets/portals/community signals.
7. Build PostGIS warehouse, matching layer, Civic Memory API, then UI.

## Current Implementation

- `registry/sources.yaml` contains all canonical overview source URLs.
- `registry/source_schema.json` defines the required registry contract.
- `python3 -m civic_data registry validate` validates the registry.
- `python3 -m civic_data sources fetch --all` archives enabled sources.
- `python3 -m civic_data sources profile --all` writes parser backlog exports.
- CKAN fetches are resource-resumable with `--resume`, `--resource-retries`,
  and manifest v2 `ckan_resources` records.

## Next Waves

1. Load source registry and ingest runs into Postgres.
2. Normalize wards and GBA/BBMP ward boundaries.
3. Normalize grievances and complaint categories.
4. Normalize works/payments and road datasets.
5. Add matching jobs with confidence labels.
6. Add Civic Memory API and product UI.
