# Bengaluru Civic Truth Engine

A provenance-first civic memory system for Bengaluru.

The project starts by registering and archiving every source listed in the local
overview, then normalizes the data into a civic warehouse with row-level
provenance.

## First Slice

The first implementation slice was **Fetch All First**:

1. Validate the source registry.
2. Fetch every enabled source into immutable raw archives.
3. Produce fetch status and parser backlog exports.
4. Normalize structured sources in waves after the raw archive is proven.

The current implementation also includes **Wave 1 normalization**:

1. Normalize old BBMP and new GBA ward context.
2. Normalize BBMP grievance rows from archived CSV resources.
3. Generate a first place truth report with ward context, grievance trends, and
   evidence pointers.

## Commands

```bash
python3 -m unittest discover -s tests
python3 -m civic_data registry validate
python3 -m civic_data sources status
python3 -m civic_data sources fetch --all
python3 -m civic_data sources fetch --all --resume --resource-retries 2
python3 -m civic_data sources profile --all
python3 -m civic_data normalize wards
python3 -m civic_data normalize grievances
python3 -m civic_data places truth --q Bellandur --output data/exports/truth-bellandur.json
python3 -m civic_data dossiers create --place Bellandur --output data/exports/dossier-bellandur.md
python3 -m civic_data warehouse export
python3 -m uvicorn api.app:app --host 127.0.0.1 --port 8000
cd web && npm install
cd web && npm run dev -- -H 127.0.0.1 --port 3001
cd web && npm run build
```

If `psql` is installed and a Postgres database is available, load Wave 1 with:

```bash
python3 -m civic_data warehouse load --database-url "$DATABASE_URL"
```

The `civic-data` console script is also declared in `pyproject.toml` for
installed environments.

## Data Policy

Raw data is not committed to Git. The repository tracks schemas, code, docs,
tests, migrations, and small fixtures. Fetch outputs live under `data/raw/`,
normalization outputs under `data/normalized/`, exports under `data/exports/`,
and parser staging outputs under `data/parsed/`.

CKAN package fetches are resource-resumable. New manifests include a
`ckan_resources` ledger so a partial run can be retried without redownloading
already verified files.
