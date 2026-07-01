# Public Launch Checklist

This repository is intended to be public-safe, reproducible, and explicit about
what the Bengaluru Civic Truth Engine can and cannot prove.

## Public Safety

- No raw archives are committed. `data/raw/`, `data/normalized/`, local exports,
  database dumps, and virtual environments are ignored.
- The committed website uses generated public artifacts under
  `web/src/data/generated/`.
- Source monitor output is archive-first. It reports what the local archive can
  support; it does not probe live government systems during page render.
- Private complaint tracking, OTP/login flows, account-linked forms, automated
  complaint filing, and citizen PII are intentionally out of scope.

Before making the repository public:

```bash
python3 scripts/secret_scan.py
python3 -m unittest tests.test_public_launch_readiness
git ls-files | rg '(^|/)(\\.env|.*\\.pem|.*\\.key|.*\\.sqlite|.*\\.db)$'
```

For a private repository with unknown history, also run a history-aware secret
scanner before flipping visibility. If history is not clean, publish from a
fresh public mirror instead of exposing the private repository history.

## GitHub Pages

GitHub Pages serves the frontend as a static site:

```bash
cd web
GITHUB_PAGES=true NEXT_PUBLIC_STATIC_DEMO=true npm run build
```

The static Pages build serves prebuilt demo packets only. Arbitrary packet
generation still requires the API or CLI:

```bash
python3 -m uvicorn api.app:app --host 127.0.0.1 --port 8017
cd web && npm run dev
```

When a live API host exists, set the repository Actions variable
`CIVIC_API_BASE` to that origin and rerun the Pages workflow. The static export
will then call `/packets/build` on the deployed API.

Deployment details live in [`deployment.md`](deployment.md).

## Public Claim Boundary

The public demo may say:

- Public records contain a ward, route, work, payment, tender, or complaint
  memory row.
- A source was last archived or checked at a specific time.
- A source can provide administrative, routing, jurisdiction, or historical
  context.

The public demo must not say:

- An issue is live on the ground right now.
- A public body has accepted ownership for a specific incident.
- A complaint is resolved or unresolved unless a public record explicitly says so.
- A work row proves field completion, quality, negligence, corruption, or current
  condition.

This is the point of the product: useful civic action without pretending public
archives prove more than they can.
