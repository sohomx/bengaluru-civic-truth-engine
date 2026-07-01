# Bengaluru Civic Truth Engine

[![CI](https://github.com/sohomx/bengaluru-civic-truth-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/sohomx/bengaluru-civic-truth-engine/actions/workflows/ci.yml)
[![GitHub Pages](https://github.com/sohomx/bengaluru-civic-truth-engine/actions/workflows/pages.yml/badge.svg)](https://github.com/sohomx/bengaluru-civic-truth-engine/actions/workflows/pages.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

An open-source civic action engine for Bengaluru.

The core product is a provenance-backed `CivicActionPacket`: given a citizen issue,
the system resolves the likely place, routes the issue to the likely public body,
attaches public evidence, states what can and cannot be claimed, and drafts the
next action.

This is not a generic chatbot over scraped data. Packet generation is structured
and deterministic. RAG is limited to explaining an existing packet and must not
discover civic facts from raw files.

Public demo: https://sohomx.github.io/bengaluru-civic-truth-engine/

The GitHub Pages demo is static and uses prebuilt sample packets. Arbitrary
packet generation is available through the CLI or local/API deployment.

## What It Does

- Resolves jurisdiction from official `xyinfo` lat/lng lookup when available,
  then offline ward data, then low-confidence locality aliases.
- Routes issues such as potholes, garbage, sewage, power, traffic, and
  streetlights to the likely agency.
- Matches sanitized public work/payment/contact records as administrative
  context.
- Emits claim boundaries: public rows do not prove field completion, current
  field condition, corruption, or official resolution.
- Records provenance, freshness, routing policy IDs, and packet traces for
  auditability.
- Monitors source archives and states what each source can and cannot currently
  prove.

## Quick Demo

```bash
python3 -m civic_data packets build \
  --q "There is a recurring pothole near the main road in Whitefield, what can I cite?" \
  --format md

python3 -m civic_data packets build \
  --q "Sewage overflowing near Kadubeesanahalli, who should I contact?" \
  --format md

python3 -m civic_data packets explain \
  --packet examples/packets/bellandur-streetlight.json \
  --q "What should I do next?"

python3 -m civic_data sources monitor \
  --registry registry/sources.yaml \
  --raw-root data/raw \
  --format json
```

The trusted public path is:

```text
normalized public data -> civic_action_packet -> packet-only explanation/UI
```

`packets explain` defaults to deterministic packet-only explanation for
reproducible local demos. To run model-backed Packet-RAG, set `OPENAI_API_KEY`
and use:

```bash
python3 -m civic_data packets explain \
  --packet examples/packets/bellandur-streetlight.json \
  --q "What should I do next?" \
  --mode llm
```

The default LLM config is `CIVIC_LLM_MODEL=gpt-5.4-mini`,
`CIVIC_EMBEDDING_MODEL=text-embedding-3-small`, and
`CIVIC_RAG_RETRIEVAL=packet_lexical`. The current LLM path uses packet-only
lexical chunks for retrieval and the OpenAI Responses API for structured
generation; it does not read raw CSVs or discover facts outside the packet.

Anthropic is also supported:

```bash
CIVIC_LLM_PROVIDER=anthropic \
ANTHROPIC_MODEL=claude-haiku-4-5-20251001 \
python3 -m civic_data packets explain \
  --packet examples/packets/bellandur-streetlight.json \
  --q "What should I do next?" \
  --mode llm
```

The public product path is `/packets/build` and `/packets/explain`.
Retrieval debugging lives under `/diagnostics/rag/ask`. The legacy `/rag/ask`
path is retained temporarily with deprecation metadata for older evals; it is
not the source of truth for the civic action packet demo.

## Verification

```bash
python3 -m unittest discover -s tests

python3 -m civic_data eval packets \
  --suite tests/fixtures/packet_eval/civic_packets_v1.jsonl \
  --warehouse-root data/normalized \
  --raw-root data/raw \
  --report \
  --output data/eval_runs/packet_eval_report.json

python3 -m civic_data eval packet-rag \
  --suite tests/fixtures/packet_eval/packet_rag_v1.jsonl \
  --mode deterministic

cd web && npm run build

cd web && GITHUB_PAGES=true NEXT_PUBLIC_STATIC_DEMO=true npm run build
```

The packet eval report includes release-gate metrics for agency accuracy,
public raw-scan use, PII leakage, and packet-only behavior.

## Data Policy

Raw data is not committed to Git. The repository tracks source registry entries,
schemas, normalizers, tests, migrations, docs, demo fixtures, and small public
examples.

- Raw archives: `data/raw/`
- Normalized reproducible read model: `data/normalized/`
- Locality and routing policy config: `data/config/`
- Demo packets: `examples/packets/`
- Production-oriented migrations: `warehouse/migrations/`

Official public sources and mirrored official datasets outrank community or
news sources. Private complaint tracking, OTP/login flows, account-linked forms,
and automated complaint filing are intentionally out of scope.

Public launch and GitHub Pages notes live in
[`docs/public-launch.md`](docs/public-launch.md).

## Architecture

The current open-source read model is JSON under `data/normalized`. Postgres,
PostGIS, and vector migrations exist as the production backend direction, but
the packet demo remains reproducible without external infrastructure.

Key boundaries:

- `civic_data/packet.py`: public packet API facade.
- `civic_data/packet_builder.py`: deterministic packet orchestration.
- `civic_data/contracts.py`: packet contract metadata and validation.
- `civic_data/provenance.py`: public evidence provenance ledger.
- `civic_data/freshness.py`: shared source freshness policy.
- `civic_data/trace.py`: packet trace IDs and audit stages.
- `civic_data/packet_explainer.py`: packet-only deterministic and model-backed explanation layer.
- `civic_data/packet_rag.py`: compatibility import for older callers.
- `data/config/issue_routing_policy.json`: auditable routing policy metadata.

## Known Limits

- Offline ward matching is not filing-critical proof; use official lat/lng
  lookup where possible.
- Public work/payment rows are administrative context, not proof of repair
  quality or current field condition.
- Garbage, sewage, and power cases often route well but may have little
  issue-specific public evidence until more official datasets are normalized.
- The legacy RAG retriever is not the demo source of truth.
