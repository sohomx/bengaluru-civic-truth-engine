# ADR 0001: Packet-First Civic Engine

## Status

Accepted.

## Decision

`CivicActionPacket` is the public fact contract for the project. Packet
generation uses structured normalized public data, deterministic routing,
jurisdiction resolution, evidence matching, provenance, freshness, and claim
policy.

RAG is explanatory only. It may explain an existing packet, cite packet evidence,
and restate caveats. It must not discover civic facts from raw files or override
the packet's allowed/disallowed claims.

## Why

Bengaluru civic workflows need trust more than conversational flourish. A useful
system must show who likely owns an issue, what public evidence exists, where the
evidence came from, how fresh it is, what the citizen can safely claim, and what
remains unknown.

Open311-style request concepts make the packet portable. FixMyStreet-style
location/category routing keeps citizens from needing to know the right agency.
W3C-PROV-style provenance and explicit freshness fields make the project
reviewable as open-source civic infrastructure.

## Consequences

- `/packets/build` remains the trusted product path.
- `/packets/explain`, `packets explain`, and legacy `rag explain-packet` can only use packet data.
- Model-backed explanation is opt-in through `--mode llm` or API `mode: "llm"`; deterministic packet-only explanation remains the default for reproducible local demos.
- `/rag/ask` is retained as a legacy retrieval/debug surface, not the demo source
  of truth.
- Packet evals must fail on raw-scan use, PII leakage, unsupported claims, and
  missing provenance.
- New data sources should improve normalized public evidence before expanding
  chatbot behavior.
