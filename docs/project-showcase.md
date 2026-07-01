# Project Showcase

Bengaluru Civic Truth Engine is a civic-tech project with a narrow product
contract: help a citizen turn a messy local issue into a public-safe action
packet. The system does not try to be a general government chatbot. It answers a
smaller question with stronger guarantees:

> What can the available public records support, what can they not support, and
> what should the citizen do next?

That boundary drives the architecture.

## Product Contract

The system accepts a query such as:

```text
sewage overflowing near the main road in JP Nagar
```

It returns a `CivicActionPacket` with:

- issue classification;
- likely ward/corporation context;
- likely public agency;
- public evidence, when matching rows exist;
- source proof boundaries;
- safe message draft;
- escalation and RTI guidance;
- trace, freshness, and provenance metadata.

The packet can say "public records contain a related work/payment row." It
cannot say "the road was fixed" unless a public source explicitly proves that.

## High-Level Flow

```text
User query
   |
   v
+---------------------+
| Packet build API    |  CLI: python3 -m civic_data packets build
| /packets/build      |  HTTP: FastAPI route
+----------+----------+
           |
           v
+---------------------+       +-----------------------+
| Issue router        |       | Jurisdiction resolver |
| policy-backed rules |       | xyinfo -> boundary -> |
|                     |       | ward text -> alias    |
+----------+----------+       +-----------+-----------+
           |                              |
           +--------------+---------------+
                          |
                          v
             +---------------------------+
             | Public evidence matcher   |
             | works, payments, routes   |
             +-------------+-------------+
                           |
                           v
             +---------------------------+
             | Claim and provenance      |
             | proof boundaries, trace   |
             +-------------+-------------+
                           |
                           v
             +---------------------------+
             | CivicActionPacket v3      |
             +-------------+-------------+
                           |
          +----------------+----------------+
          |                                 |
          v                                 v
+---------------------+          +-------------------------+
| Static/React UI     |          | Packet explanation      |
| source explorer     |          | deterministic or LLM    |
+---------------------+          +-------------------------+
```

## Repository Map

```text
bengaluru-civic-truth-engine/
|-- api/
|   `-- app.py                    FastAPI routes and CORS/deploy settings
|-- civic_data/
|   |-- packet_builder.py         deterministic packet orchestration
|   |-- jurisdiction.py           resolver order and place confidence
|   |-- issue_router.py           policy-backed agency routing
|   |-- evidence_matcher.py       public work/payment/contact matching
|   |-- provenance.py             evidence records and proof boundaries
|   |-- source_monitor.py         archive-first source status read model
|   |-- packet_explainer.py       packet-only deterministic/LLM explanations
|   |-- packet_eval.py            release-gate packet evaluation
|   `-- retrieval_eval.py         qrels-style evidence retrieval evaluation
|-- data/
|   |-- config/                   routing, locality, policy config
|   |-- geo/                      generated ward boundary read model
|   `-- public_api/normalized/    public-safe data package for deployment
|-- registry/
|   `-- sources.yaml              source registry and public proof metadata
|-- tests/                        contract, safety, eval, CLI, site tests
|-- web/
|   `-- src/                      static site and source explorer
|-- docs/
|   |-- architecture.md
|   |-- source-policy.md
|   |-- evaluation.md
|   |-- deployment.md
|   `-- public-launch.md
|-- Dockerfile
|-- render.yaml
`-- .github/workflows/
    |-- ci.yml
    |-- pages.yml
    `-- backend-image.yml
```

## Build Sequence

The project grew in layers. Each layer made the next one safer to build.

```text
1. Source registry
   |
   +-- source IDs, tiers, formats, access methods, PII risk
   |
2. Archive and normalize
   |
   +-- public JSON read models for wards, works, payments, contacts
   |
3. Packet contract
   |
   +-- deterministic route, place, evidence, action, caveats
   |
4. Packet-only explanation
   |
   +-- deterministic mode first, LLM mode behind the same contract
   |
5. Source monitor
   |
   +-- archive freshness, parser status, proof boundaries
   |
6. Static site and API
   |
   +-- source explorer, packet UI, FastAPI, Docker, GHCR, Render config
   |
7. Release gates
   |
   +-- unit tests, packet eval, RAG eval, retrieval qrels, public launch checks
```

That order kept the system from turning into a chatbot over raw files. The
source policy came before public claims. The packet contract came before prose.
The eval gates came before deployment.

## Design Decisions

### 1. Packet-first, not chatbot-first

The packet builder creates structured civic facts before any explanation step
runs. The explanation layer receives a packet and packet-derived chunks. It
cannot scan raw archives for new facts.

This makes the system reviewable. A reviewer can inspect the packet fields,
source IDs, caveats, and trace before trusting the prose.

### 2. Deterministic core, optional LLM

The core path works without an LLM:

```text
query -> packet -> deterministic explanation -> UI/CLI
```

Model-backed explanation exists, but it uses the same packet-only contract. The
LLM can improve wording. It cannot expand the evidence base.

### 3. Source freshness is archive-first

The source monitor does not pretend to know live ground truth. It reads the
source registry, local raw archive manifests, parser profile rows, and public
usage. For each source, it reports:

- last archive run;
- latest successful fetch;
- archive age;
- parser status;
- whether public claims use the source;
- what the source can and cannot prove.

```text
registry/sources.yaml       data/raw/<source>/runs       profile rows
          |                         |                         |
          +-------------+-----------+------------+------------+
                        |                        |
                        v                        v
                +--------------------------------------+
                | source_monitor.py                   |
                | archive status + proof contract     |
                +------------------+-------------------+
                                   |
                                   v
                web/src/data/generated/source_status.json
```

This choice matters because civic data ages fast. The product should say "last
archived on this date" instead of implying live operational status.

### 4. Public-safe deployment data

Raw archives stay out of Git. The deployed API uses a smaller public-safe read
model under `data/public_api/normalized/`.

```text
raw archives              normalized local warehouse       public API package
data/raw/          --->   data/normalized/           --->  data/public_api/
ignored                  ignored for local rebuild         committed subset
```

That split keeps the repo deployable without publishing raw scrape output,
private complaint traces, database dumps, or local machine paths.

### 5. Evaluation gates match product risk

The tests are not just unit tests around functions. They encode product claims:

- packet contract shape;
- agency routing quality;
- no raw-scan fact generation in public output;
- no PII leakage;
- freshness disclosure when required;
- source monitor proof fields;
- packet-only RAG behavior;
- retrieval precision/recall on qrels fixtures;
- GitHub Pages and public-launch readiness.

## Public Surface

```text
GitHub repository
   |
   +-- source code, tests, docs
   |
   +-- GitHub Pages
   |     static site, source explorer, sample packets
   |
   +-- GitHub Container Registry
   |     ghcr.io/sohomx/bengaluru-civic-truth-engine-api:latest
   |
   `-- Render/Fly/Railway/VPS
         live FastAPI runtime for arbitrary packet generation
```

GitHub Pages can host the frontend. It cannot run FastAPI. The backend image is
published to GHCR and can run on Render or another container host.

## What A Reviewer Should Notice

The interesting engineering work is not a flashy UI. It is the discipline around
claim boundaries:

- public administrative records are useful but limited;
- source metadata affects what the product may say;
- live-ish freshness means archive awareness, not live ground truth;
- model output sits behind a structured packet contract;
- deployment separates public read models from raw archives.

## Commands Worth Running

```bash
python3 -m unittest discover -s tests
python3 scripts/secret_scan.py
python3 -m civic_data registry validate

python3 -m civic_data packets build \
  --q "Whitefield recurring pothole" \
  --format md

python3 -m civic_data sources monitor \
  --registry registry/sources.yaml \
  --raw-root data/raw \
  --format json

docker build -t bengaluru-civic-truth-engine-api .
docker run --rm -p 8017:8000 bengaluru-civic-truth-engine-api
```

## Current Limits

- Offline ward matching helps triage, but filing-critical routing should use
  exact lat/lng against the official lookup when possible.
- Public work/payment rows provide administrative context. They do not prove
  current field condition or repair quality.
- The open-source package includes a public-safe API read model, not the full raw
  archive.
- GitHub Pages remains static until a live API host is configured through
  `CIVIC_API_BASE`.

Those limits are part of the product contract. The engine should be useful
without sounding more certain than the evidence allows.
