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
