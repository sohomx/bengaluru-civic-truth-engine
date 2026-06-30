# Bengaluru Civic Action Packet Demo

This demo shows the core product: a deterministic civic action packet, not a generic chatbot.

Each command returns a `civic_action_packet` with jurisdiction, responsible agency, public evidence, caveats, and a citizen-ready message draft. Packet generation is structured and sets `audit.used_rag` to `false`.

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
python3 -m civic_data rag explain-packet \
  --packet examples/packets/bellandur-streetlight.json \
  --q "What should I do next?"
```

Expected interpretation: explains only the packet data, cites the packet's public evidence, preserves caveats, and reports `used_packet_only: true`.
