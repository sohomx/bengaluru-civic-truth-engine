# Source Policy

## Source Tiers

- Tier 1: official or mirrored-official structured data. Use for strongest product claims.
- Tier 2: official PDFs and circulars. Use for rules, budgets, SOPs, and notices.
- Tier 3: official portals requiring scraping. Archive cautiously and label parser reliability.
- Tier 4: civic/crowd projects. Use as community signals, not official proof.
- Tier 5: Reddit, news, and social sources. Use as leads, sentiment, and launch research.

## Public Claim Wording

- High confidence: "Official records show..."
- Medium confidence: "The available ward-level data suggests..."
- Low confidence: "Possible related record; needs verification..."
- Non-official: "Community-reported signal, not official proof..."

## Evidence Rules

Every public claim must link to source metadata, raw file, source row or document,
fetch timestamp, and parser/matcher version where applicable.

Uncertain matches must live in match tables with confidence, method, and
explanation. They must not be written as canonical facts.

## Archive-First Source Monitor

The v1 source monitor is deterministic and archive-first. It reads the registry,
`data/raw`, and optional profile rows; it does not call publisher URLs. The public
artifact is still `web/src/data/generated/source_status.json`, enriched with
`archive_status`, `monitor_status`, proof boundaries, parser status, usage, and
archive freshness.

```bash
python3 -m civic_data sources monitor \
  --registry registry/sources.yaml \
  --raw-root data/raw \
  --format json
```

The monitor answers what the current archive can support:

- `wards`: can prove ward/corporation/jurisdiction context; cannot prove field condition, agency action, or issue resolution.
- `grievances`: can prove complaint memory present in available records; cannot prove live complaint status, ground truth prevalence, or resolution quality.
- `works_payments_tenders`: can prove public administrative work/payment/tender rows exist; cannot prove field completion, quality, corruption, negligence, or current condition.
- Routing/contact pages: can prove route/contact metadata; cannot prove ownership for the exact incident or live ticket status.
- Community or unofficial sources: leads/context only; not official proof.
- High-PII, disabled, manual/private/account-linked sources: blocked from public-output proof.

Use "last archived", "archive usable", and "historical/admin context" in public
copy. Do not describe this monitor as live issue status or live ground truth.
