# Architecture

The system builds a packet from normalized public civic records, then explains
only that packet. RAG and LLMs never become the source of civic facts.

```text
Query + optional lat/lng
          |
          v
  +----------------+
  | CLI / FastAPI  |
  +-------+--------+
          |
          v
  +--------------------------+
  | packet_builder.build     |
  +------------+-------------+
               |
    +----------+----------+------------------+
    |                     |                  |
    v                     v                  v
+-----------+     +---------------+   +---------------+
| resolver  |     | issue router  |   | evidence      |
| xyinfo -> |     | policy JSON   |   | matcher       |
| boundary  |     +-------+-------+   +-------+-------+
| -> alias  |             |                   |
+-----+-----+             |                   |
      |                   |                   |
      +-------------------+-------------------+
                          |
                          v
             +---------------------------+
             | claims, provenance,       |
             | freshness, trace          |
             +-------------+-------------+
                           |
                           v
             +---------------------------+
             | CivicActionPacket         |
             +-------------+-------------+
                           |
             +-------------+-------------+
             |                           |
             v                           v
   +--------------------+      +-----------------------+
   | UI / markdown CLI  |      | packet-only explain   |
   +--------------------+      +-----------------------+
```

```mermaid
flowchart LR
  Q[User query + optional lat/lng] --> API[CLI or /packets/build]
  API --> PB[packet_builder.build_packet]
  PB --> JR[jurisdiction.resolve_jurisdiction]
  JR --> XY[official xyinfo]
  JR --> GB[geo_boundary boundary_contains]
  JR --> TXT[text ward / mapping / alias]
  PB --> IR[issue_router.route_issue]
  PB --> EM[evidence_matcher.match_work_records]
  EM --> WH[Normalized JSON warehouse]
  PB --> CPF[claims + provenance + freshness]
  CPF --> CAP[CivicActionPacket]
  CAP --> EX[/packets/explain]
  EX --> PR[packet_retrieval packet-only chunks]
  PR --> PE[packet_explainer deterministic or LLM]
  CAP --> TR[trace_writer JSONL]
```

## Resolver Order

1. `official_xyinfo` when `lat/lng` are present and the live lookup succeeds.
2. `boundary_contains` or `boundary_edge` from `data/geo/ward_boundaries.geojson` when `xyinfo` fails.
3. Text ward match against normalized wards.
4. Locality alias from `data/config/locality_aliases.json`.
5. Old/new ward mapping.
6. Unresolved.

The boundary data is generated from public GBA KML under `data/raw/gba_wards_delimitation_2025/.../original/*.kml` with:

```bash
python3 -m civic_data geo build-boundaries \
  --raw-root data/raw \
  --output data/geo/ward_boundaries.geojson
```

## Packet Evidence

`civic_data.evidence_matcher.action_evidence` emits stable IDs in the form `ev_<entity_type>_<sha1-prefix>`. The old positional ID is retained as `legacy_evidence_id` for older examples and qrels.

## Debugging

Packet builds and explanations write JSONL traces to `.context/traces/packets.jsonl` by default. Inspect them without raw private query text:

```bash
python3 -m civic_data traces list --trace-path .context/traces/packets.jsonl --limit 10
python3 -m civic_data traces inspect --trace-id <trace_id> --format md
```
