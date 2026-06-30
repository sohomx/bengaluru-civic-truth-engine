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
