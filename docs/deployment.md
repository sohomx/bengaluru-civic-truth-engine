# Deployment

The project has two deployable surfaces:

- a static frontend on GitHub Pages;
- a FastAPI backend packaged as a Docker image.

GitHub can host the repo, the static site, CI, and the backend container image.
It cannot run the FastAPI service from GitHub Pages. Use Render, Fly.io, Railway,
or a VPS for the live API runtime.

## Deployment Shape

```text
                 +-----------------------------+
                 | GitHub repository           |
                 | code, docs, tests, data     |
                 +--------------+--------------+
                                |
          +---------------------+----------------------+
          |                                            |
          v                                            v
+---------------------+                    +--------------------------+
| GitHub Pages        |                    | GitHub Container Registry|
| static frontend     |                    | backend Docker image     |
| /bengaluru...       |                    | ghcr.io/...:latest       |
+----------+----------+                    +------------+-------------+
           |                                            |
           | NEXT_PUBLIC_CIVIC_API_BASE                 |
           v                                            v
+---------------------------------------------------------------+
| Render/Fly/Railway/VPS                                        |
| FastAPI: /healthz, /packets/build, /packets/explain           |
+---------------------------------------------------------------+
```

## 1. Verify The Repo Locally

```bash
python3 -m unittest discover -s tests
python3 scripts/secret_scan.py
cd web && GITHUB_PAGES=true NEXT_PUBLIC_STATIC_DEMO=true npm run build
```

## 2. Run The API Locally

```bash
CIVIC_WAREHOUSE_ROOT=data/public_api/normalized \
uvicorn api.app:app --host 127.0.0.1 --port 8017
```

Smoke test:

```bash
curl http://127.0.0.1:8017/healthz
curl "http://127.0.0.1:8017/packets/build?q=Whitefield%20recurring%20pothole"
```

## 3. Run The Container Locally

```bash
docker build -t bengaluru-civic-truth-engine-api .
docker run --rm -p 8017:8000 bengaluru-civic-truth-engine-api
```

The container defaults to:

```text
CIVIC_WAREHOUSE_ROOT=data/public_api/normalized
CIVIC_RAW_ROOT=data/raw
```

## 4. GitHub Pages Frontend

The Pages workflow lives at `.github/workflows/pages.yml`.

By default, the public site builds in static demo mode:

```text
NEXT_PUBLIC_STATIC_DEMO=true
```

When a live API exists, set this repository Actions variable:

```text
CIVIC_API_BASE=https://<your-api-host>
```

Then rerun the `deploy-github-pages` workflow. The frontend build will embed
`NEXT_PUBLIC_CIVIC_API_BASE` and call the live API for arbitrary packet
generation.

## 5. GitHub Container Registry

The backend image workflow lives at `.github/workflows/backend-image.yml`.

On pushes to `main`, GitHub publishes:

```text
ghcr.io/sohomx/bengaluru-civic-truth-engine-api:latest
ghcr.io/sohomx/bengaluru-civic-truth-engine-api:<commit-sha>
```

If a host can deploy directly from GHCR, use the `latest` tag for the demo and a
commit SHA tag for a pinned deployment.

## 6. Render Deployment

Render can deploy this repo either from `render.yaml` or through a manual web
service.

Choose:

```text
New -> Web Service
```

Use these settings:

```text
Runtime: Docker
Branch: main
Health check path: /healthz
Plan: Free is enough for a portfolio demo
```

Environment variables:

```text
CIVIC_WAREHOUSE_ROOT=data/public_api/normalized
CIVIC_RAW_ROOT=data/raw
CIVIC_CORS_ORIGINS=https://sohomx.github.io
```

After Render gives you a service URL, test:

```bash
curl https://<render-service>/healthz
curl "https://<render-service>/packets/build?q=Bellandur%20streetlight%20not%20working"
```

Then set the GitHub repository Actions variable:

```text
CIVIC_API_BASE=https://<render-service>
```

Rerun GitHub Pages. The public UI should stop showing static-demo language for
arbitrary queries and call the API instead.

## 7. CORS Notes

CORS origins are scheme + host + optional port. Do not include the path.

Use:

```text
https://sohomx.github.io
```

Do not use:

```text
https://sohomx.github.io/bengaluru-civic-truth-engine
```

The browser sends the first value as the `Origin` header.

## 8. Public-Safety Checks Before A Demo

```bash
python3 scripts/secret_scan.py
python3 -m unittest tests.test_public_launch_readiness
git status --short
```

The public API data package should contain normalized public read models only:

```text
data/public_api/normalized/
|-- agencies.json
|-- complaint_channels.json
|-- contact_channels.json
|-- issue_categories.json
|-- old_new_ward_mappings.json
|-- payments.json
|-- rag_index.json
|-- wards.json
`-- works.json
```

Do not commit `data/raw/`, `data/normalized/`, `.env`, database dumps, local
trace logs, or API keys.
