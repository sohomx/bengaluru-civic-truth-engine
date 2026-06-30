# Evaluation Plan

The release gate is packet-first. A passing demo must show correct routing,
safe evidence use, provenance, freshness, and readable citizen action.

## Current Gate

```bash
python3 -m civic_data eval packets \
  --suite tests/fixtures/packet_eval/civic_packets_v1.jsonl \
  --warehouse-root data/normalized \
  --raw-root data/raw \
  --report \
  --output data/eval_runs/packet_eval_report.json
```

The report tracks:

- `agency_accuracy`
- `unsafe_raw_scan_rate`
- `pii_leak_rate`
- `packet_only_rate`

The gate fails if packet cases fail, public output uses raw scan, or public text
leaks PII.

## Packet-RAG Gate

```bash
python3 -m civic_data eval packet-rag \
  --suite tests/fixtures/packet_eval/packet_rag_v1.jsonl \
  --mode deterministic
```

This gate evaluates the explanation layer separately from packet generation. It
records generation mode, provider, model, embedding configuration, prompt
version, retrieval mode, and confirms explanations use packet data only.

Model-backed runs are explicit:

```bash
OPENAI_API_KEY=... python3 -m civic_data eval packet-rag \
  --suite tests/fixtures/packet_eval/packet_rag_v1.jsonl \
  --mode llm
```

The current LLM path uses packet-only lexical retrieval plus the OpenAI
Responses API for structured generation. Embedding configuration is audited, but
embedding retrieval is not yet enabled.

Anthropic eval runs use the same packet-only path:

```bash
CIVIC_LLM_PROVIDER=anthropic \
ANTHROPIC_MODEL=claude-haiku-4-5-20251001 \
ANTHROPIC_API_KEY=... \
python3 -m civic_data eval packet-rag \
  --suite tests/fixtures/packet_eval/packet_rag_v1.jsonl \
  --mode llm
```

## Benchmark Suites To Grow

- `routing_v1`: agency and mixed-path routing.
- `jurisdiction_v1`: official xyinfo, offline ward, locality alias, unresolved.
- `evidence_qrels_v1`: evidence precision@3, recall@5, wrong-locality rate.
- `grounding_v1`: every claim must be supported by cited packet evidence.
- `abstention_v1`: say unknown when evidence is insufficient.
- `confidence_calibration_v1`: confidence labels match observed correctness.
- `safety_redteam_v1`: no private data, defamatory claims, fake status, or source-policy override.
- `demo_readability_v1`: packet output is citizen-readable and reviewer-friendly.

## Non-Negotiable Failure Modes

- Claiming a public work row proves field repair or current ground condition.
- Treating official closure as verified resolution.
- Citing private complaint/account/OTP flows.
- Letting RAG discover facts outside the packet.
- Hiding weak locality or agency confidence.
