# System Design

This document explains the thinking behind Bengaluru Civic Truth Engine. It
covers product architecture, data architecture, evidence design, and source
strategy.

The core design question was:

```text
How can a citizen use public records without claiming more than those records
can prove?
```

That question shaped the whole system.

## 1. Problem Framing

A civic issue usually starts as an unstructured sentence:

```text
sewage overflowing near the main road in JP Nagar
```

A useful answer needs several different kinds of knowledge:

- issue type: sewage, road, garbage, power, traffic, streetlight;
- place: locality, ward, corporation, zone;
- likely agency: BWSSB, BESCOM, BTP, GBA, BSWML, others;
- public evidence: work rows, payment rows, complaint memories, routes;
- source freshness: when the evidence was archived or checked;
- proof boundary: what the evidence can support and what it cannot support.

The hard part is not text generation. The hard part is civic uncertainty.

```text
Citizen wording
     |
     v
+--------------------+
| Many possible gaps |
+--------------------+
| vague place        |
| overlapping agency |
| stale source       |
| weak public record |
| private complaint  |
| no field proof     |
+--------------------+
     |
     v
Design goal: useful next action with bounded claims
```

## 2. Product Principle

The product should be useful even when evidence is incomplete.

It should say:

- "File with this likely agency."
- "Use this ward/corporation context."
- "These public rows may be relevant administrative context."
- "These sources were last archived at this time."
- "Do not claim repair, negligence, corruption, or live status from this row."

It should not invent certainty.

That is why the main object is a packet, not a chat answer.

## 3. Why A Packet

Chat answers mix reasoning, evidence, wording, and action in one surface. That is
hard to audit. The packet separates those pieces.

```text
                 +----------------------+
                 | CivicActionPacket    |
                 +----------+-----------+
                            |
  +------------+------------+-------------+-------------+
  |            |            |             |             |
  v            v            v             v             v
issue        place      agency route   evidence      limits
type         context    and policy     records       caveats
                                                        |
                                                        v
                                                  safe action
                                                  message draft
```

A reviewer can inspect the packet before reading any explanation. The UI and RAG
layer then become renderers of a structured object.

## 4. Source Strategy

The source registry is the root of the data design. It contains 114 sources.
Each source has a domain, tier, official status, access method, parser type,
freshness policy, reliability score, PII risk, and notes.

The registry is intentionally broader than the first normalized product. It
shows the research map and gives every future claim a place to attach proof.

Current registry shape:

```text
114 sources
|
+-- 88 tier-1 official or mirrored-official sources
+--  4 tier-2 official PDFs/circulars
+-- 12 tier-3 official portals to scrape cautiously
+--  7 tier-4 civic/community sources
`--  3 tier-5 news/social/reference sources

Official status
|
+-- 80 mirrored_official
+-- 14 official
+-- 10 official_reference
+--  5 community_signal
+--  3 external_reference
`--  2 unofficial
```

Source domains:

```text
wards                       12
solid waste                 12
traffic/mobility            12
public facilities           12
roads                       11
water/sewage                 9
community signals            9
works/payments/tenders       8
stormwater/flooding          8
streetlights                 8
budgets/governance           8
grievances                   3
rules                        2
```

The design treats sources as evidence with permissions. A source can support
some claims and block others.

## 5. Source Tiers

The source tier is a product decision, not just metadata.

```text
+------+-------------------------------+------------------------------+
| Tier | Source type                   | Product use                  |
+------+-------------------------------+------------------------------+
| 1    | official / mirrored official  | strongest public claims      |
| 2    | official PDFs and circulars   | rules, notices, budgets      |
| 3    | official portals              | archive with parser caveats  |
| 4    | civic and community projects  | leads and context            |
| 5    | news, Reddit, social sources  | research signals only        |
+------+-------------------------------+------------------------------+
```

The source tier prevents a common civic-tech mistake: treating a community map,
news article, official portal, ward boundary file, and payment CSV as if they
had the same proof value.

## 6. Evidence Taxonomy

The system uses source domain to decide proof boundaries.

```text
+------------------------+-------------------------+--------------------------+
| Domain                 | Can prove               | Cannot prove             |
+------------------------+-------------------------+--------------------------+
| wards                  | jurisdiction context    | field condition          |
| grievances             | complaint memory exists | live complaint status    |
| works/payments/tenders | admin row exists        | completion or quality    |
| routing/contact pages  | route/contact metadata  | ownership of incident    |
| community signals      | lead or context         | official claim           |
+------------------------+-------------------------+--------------------------+
```

This taxonomy appears in packets, source pages, and provenance records. The same
boundary travels with the evidence.

## 7. Data Flow

The data pipeline follows a simple rule: preserve provenance before normalizing.

```text
registry/sources.yaml
        |
        v
raw archive run
manifest + original files + checksums
        |
        v
profile parser output
success, partial, failed, file counts
        |
        v
normalized read models
wards, works, payments, contacts, categories
        |
        v
packet builder
query-specific evidence and action
        |
        v
site/API/CLI
public-safe output
```

Raw archive runs are timestamped. Failed and partial archives still matter
because they explain data gaps.

## 8. Jurisdiction Design

Place resolution uses a ladder. Stronger signals come first.

```text
lat/lng supplied?
   |
   +-- yes -> official xyinfo lookup
   |           |
   |           +-- success -> official ward/corporation context
   |           `-- fail    -> boundary contains / boundary edge
   |
   `-- no  -> text ward match
             -> locality alias
             -> old/new ward mapping
             -> unresolved
```

The resolver returns confidence and caveats. The system can still help when a
query says "JP Nagar" instead of giving coordinates, but it labels that as
offline ward context and asks the user to verify exact lat/lng for filing.

## 9. Routing Design

Routing uses a versioned policy file:

```text
data/config/issue_routing_policy.json
```

The policy maps issue types to agencies:

```text
garbage       -> BSWML
water/sewage  -> BWSSB
power         -> BESCOM
traffic       -> BTP
streetlight   -> GBA
road          -> GBA
civic fallback-> GBA
```

The packet records the policy id, version, and rule ids. That makes routing
auditable. If a reviewer disagrees with an agency decision, they can inspect the
policy instead of reverse-engineering model output.

## 10. Evidence Matching Design

Evidence matching is conservative. It looks for public administrative context,
then caps what the UI can say about that context.

```text
query + issue + place
        |
        v
candidate work/payment/contact rows
        |
        v
specificity check
same place? same issue group? usable text?
        |
        v
top public evidence rows
        |
        v
claim boundary added before output
```

A matched work row improves the citizen's evidence packet. It still does not
prove the road was repaired, the contractor did good work, or corruption
occurred.

## 11. Claim Boundary Design

The system treats unsafe overclaiming as a product bug.

```text
Public row exists
      |
      v
Allowed claim:
"A public administrative row exists for this ward/work/payment context."
      |
      v
Blocked claims:
"The issue is fixed."
"The agency accepted this incident."
"The work quality is good or bad."
"There was negligence or corruption."
```

This is why packets include `what_not_to_claim`, `limits`, source proof
boundaries, and provenance evidence records.

## 12. RAG Design

The project uses RAG only after the packet exists.

```text
Bad shape:
raw files -> retriever -> LLM -> civic answer

Chosen shape:
raw files -> normalized records -> packet -> packet chunks -> explanation
```

The chosen shape makes model behavior less risky. The model sees the packet,
allowed claims, disallowed claims, and retrieved packet chunks. It does not get
permission to discover civic facts from raw archives.

## 13. Source Freshness Design

The source monitor answers a practical reviewer question:

```text
Do we know what this source can currently support?
```

It is archive-first. It does not call live publisher URLs during site render or
packet generation.

```text
source registry
      |
      v
latest archive manifest
      |
      v
parser/profile row
      |
      v
public usage check
      |
      v
monitor_status + proof boundary
```

The monitor can return `usable`, `partial`, `stale`, `unavailable`, or
`blocked`. High-PII, private, manual, account-linked, disabled, and unsafe
sources cannot support public output unless safe metadata exists.

## 14. Public Safety Design

The public repo intentionally separates data classes.

```text
Committed
|
+-- source registry
+-- code and tests
+-- docs
+-- generated static site data
+-- public_api normalized read model

Ignored
|
+-- raw archives
+-- local normalized warehouse
+-- eval runs
+-- trace logs
+-- databases
+-- env files and keys
```

This lets someone deploy and inspect the product without exposing raw scrape
runs or local machine state.

## 15. Evaluation Design

The eval suite follows the product risk model.

```text
Risk                            Gate
----                            ----
wrong agency                    packet eval
unsupported field claim         packet eval + safety checks
private data in output          PII leak checks
RAG invents facts               packet-only RAG eval
bad retrieval                   qrels precision/recall eval
stale source hidden             freshness disclosure gate
public repo unsafe              launch readiness + secret scan
```

The tests are part of the architecture. They encode the claims the project is
allowed to make.

## 16. Why This Design Shows Engineering Judgment

The project makes a few deliberate tradeoffs:

- It chooses structured packets over free-form answers.
- It uses source tiers before public claims.
- It keeps deterministic behavior as the default path.
- It lets LLMs explain, not decide truth.
- It treats freshness and provenance as first-class fields.
- It ships a public-safe read model instead of raw archives.
- It puts limits inside the product instead of leaving them in a disclaimer.

The result is smaller than a full civic platform, but it is harder to fake. A
reviewer can trace a citizen-facing sentence back to routing policy, source
metadata, evidence rows, freshness, and proof boundaries.
