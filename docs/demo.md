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

### Bellandur streetlight

```bash
python3 -m civic_data packets build \
  --q "Bellandur streetlight not working, what can I cite and who should I contact?" \
  --format md
```

Expected interpretation: routes to GBA/BBMP civic streetlight maintenance, keeps BESCOM as a boundary contact, cites public work/payment rows as public context, and warns that those rows do not prove field repair.

### Kadubeesanahalli sewage

```bash
python3 -m civic_data packets build \
  --q "Sewage overflowing near Kadubeesanahalli, who should I contact?" \
  --format md
```

Expected interpretation: uses a text-only locality alias as a low-confidence hint toward Bellanduru, routes to BWSSB, avoids unrelated BBMP work rows, and warns not to share account/private details outside official forms.

### Whitefield pothole

```bash
python3 -m civic_data packets build \
  --q "There is a recurring pothole near the main road in Whitefield, what can I cite?"
```

Expected interpretation: resolves Whitefield, routes to GBA/BBMP civic roads, and returns public road/work context when normalized rows match.

### Bellandur power outage

```bash
python3 -m civic_data packets build \
  --q "Power outage and transformer sparks near Bellandur, what should I do?"
```

Expected interpretation: routes to BESCOM, treats sparking/transformer wording as electrical safety, and avoids citing unrelated civic work rows.

### Live xyinfo pin

```bash
python3 -m civic_data packets build \
  --q "streetlight not working near this pin" \
  --lat 12.9352 \
  --lng 77.678
```

Expected interpretation: calls the official `gisapi.bbmpgov.in/xyinfo/{lng}/{lat}` lookup and returns an official jurisdiction match. The checked-in example is a recorded packet generated from this command.

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
```

Expected interpretation: all packet cases pass, public raw-scan rate is zero,
PII leak rate is zero, and agency accuracy is reported for cases that declare an
expected agency. The packet-RAG eval confirms explanation mode, model metadata,
packet-only input, and forbidden unsupported claims.
