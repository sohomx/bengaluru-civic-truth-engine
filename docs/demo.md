# Bengaluru Civic Action Packet Demo

This demo shows the core product: a deterministic civic action packet, not a generic chatbot.

Each command returns a `civic_action_packet` with jurisdiction, responsible agency, public evidence, caveats, and a citizen-ready message draft. Packet generation is structured and sets `audit.used_rag` to `false`.

The v3 packet also includes:

- `contract`: stable `CivicActionPacket` metadata.
- `trace`: resolver, router, matcher, and rule IDs.
- `provenance`: public evidence records with source/run/row identity.
- `freshness`: shared source freshness policy.
- `audit`: explicit packet-only source-of-truth flags.

## Regenerate the demo packets

```bash
mkdir -p examples/packets

python3 -m civic_data packets build \
  --q "Bellandur streetlight not working, what can I cite and who should I contact?" \
  --warehouse-root data/normalized \
  --raw-root data/raw \
  --output examples/packets/bellandur-streetlight.json

python3 -m civic_data packets build \
  --q "Sewage overflowing near Kadubeesanahalli, who should I contact?" \
  --warehouse-root data/normalized \
  --raw-root data/raw \
  --output examples/packets/kadubeesanahalli-sewage.json

python3 -m civic_data packets build \
  --q "There is a recurring pothole near the main road in Whitefield, what can I cite?" \
  --warehouse-root data/normalized \
  --raw-root data/raw \
  --output examples/packets/whitefield-pothole.json

python3 -m civic_data packets build \
  --q "Power outage and transformer sparks near Bellandur, what should I do?" \
  --warehouse-root data/normalized \
  --raw-root data/raw \
  --output examples/packets/bellandur-power.json

python3 -m civic_data packets build \
  --q "streetlight not working near this pin" \
  --lat 12.9352 \
  --lng 77.678 \
  --warehouse-root data/normalized \
  --raw-root data/raw \
  --output examples/packets/live-xyinfo-yamalur.json
```

## Gold examples

### 1. Strong routing: Whitefield pothole

```bash
python3 -m civic_data packets build \
  --q "Whitefield recurring pothole at ITPL back gate" \
  --format md
```

Expected interpretation: resolves Whitefield, routes to GBA/BBMP civic roads, cites road/pothole public rows, and warns that public rows are not proof of field condition or repair.

### 2. Ambiguous location: Ecospace streetlight

```bash
python3 -m civic_data packets build \
  --q "streetlight not working near Ecospace" \
  --format md
```

Expected interpretation: uses locality alias or, with a pin, boundary resolution. The packet keeps a caveat when the place was inferred rather than confirmed by official xyinfo.

Boundary fallback demo:

```bash
python3 - <<'PY'
from pathlib import Path
from urllib.error import URLError
from civic_data.packet import build_evidence_packet

packet = build_evidence_packet(
    "Whitefield recurring pothole at ITPL back gate",
    lat=12.9698,
    lng=77.7499,
    xyinfo_client=lambda _lng, _lat: (_ for _ in ()).throw(URLError("demo offline xyinfo")),
    boundary_path=Path("data/geo/ward_boundaries.geojson"),
)
print(packet["audit"]["resolver_source"])
print(packet["jurisdiction"]["ward_name"])
PY
```

Expected output includes `boundary_contains` and `Whitefield`.

### 3. No evidence: garbage

```bash
python3 -m civic_data packets build \
  --q "garbage pile near my house Bellandur" \
  --format md
```

Expected interpretation: routes to BSWML/SWM or GBA/Sahaaya, but abstains from claiming matching public work/payment evidence.

### 4. Wrong-agency trap: traffic plus digging

```bash
python3 -m civic_data packets build \
  --q "road blocked because of traffic diversion and digging near Whitefield" \
  --format md
```

Expected interpretation: shows BTP for immediate obstruction/traffic safety and GBA/BBMP for digging or roadwork follow-up.

### 5. Unsupported corruption claim refusal

```bash
python3 -m civic_data packets explain \
  --packet examples/packets/whitefield-pothole.json \
  --q "Can I claim this pothole row proves corruption?"
```

Expected interpretation: refuses the unsupported corruption claim and gives a safe next action.

### Live xyinfo pin

```bash
python3 -m civic_data packets build \
  --q "streetlight not working near this pin" \
  --lat 12.9352 \
  --lng 77.678
```

Expected interpretation: calls the official `gisapi.bbmpgov.in/xyinfo/{lng}/{lat}` lookup and returns an official jurisdiction match when the service is reachable. If it fails, local boundary resolution runs before text fallback.

## Explain a packet

```bash
python3 -m civic_data packets explain \
  --packet examples/packets/bellandur-streetlight.json \
  --q "What should I do next?"
```

Expected interpretation: explains only the packet data, cites the packet's public evidence, preserves caveats, and reports `used_packet_only: true`.

For model-backed explanation, set `OPENAI_API_KEY` and add `--mode llm`. This
uses the OpenAI Responses API with `CIVIC_LLM_MODEL` defaulting to
`gpt-5.4-mini`. It still receives only sanitized packet fields and retrieved
packet chunks.

To use Anthropic instead, set `CIVIC_LLM_PROVIDER=anthropic`,
`ANTHROPIC_API_KEY`, and `ANTHROPIC_MODEL=claude-haiku-4-5-20251001`.

## Release gate

```bash
python3 -m civic_data eval packets \
  --suite tests/fixtures/packet_eval/civic_packets_v1.jsonl \
  --warehouse-root data/normalized \
  --raw-root data/raw \
  --report \
  --output data/eval_runs/packet_eval_report.json

python3 -m civic_data eval packet-rag \
  --suite tests/fixtures/packet_eval/packet_rag_v1.jsonl \
  --mode deterministic

python3 -m civic_data eval retrieval \
  --suite tests/fixtures/packet_eval/evidence_qrels_v2.jsonl \
  --warehouse-root data/normalized \
  --raw-root data/raw

python3 -m civic_data eval packet-rag-matrix \
  --suite tests/fixtures/packet_eval/packet_rag_v1.jsonl \
  --providers deterministic,anthropic,openai \
  --output data/eval_runs/model_matrix_latest
```

Expected interpretation: all packet cases pass, public raw-scan rate is zero,
PII leak rate is zero, and agency accuracy is reported for cases that declare an
expected agency. The packet-RAG eval confirms explanation mode, model metadata,
packet-only input, and forbidden unsupported claims. The retrieval eval reports
qrels v2 precision/recall/forbidden metrics, and the matrix report treats
missing live API keys as skipped rather than failed.
