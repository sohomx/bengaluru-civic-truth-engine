# Known Limitations

This project is a civic evidence and routing layer, not an official complaint
system.

## What The Packet Can Say

- A likely agency route based on issue type and place.
- Ward/corporation context from official lookup, offline public ward data, or a
  low-confidence locality alias.
- Public work/payment/contact records that may help frame a complaint.
- What evidence to attach and what not to claim.

## What The Packet Cannot Say Yet

- That an issue is currently present on the ground.
- That an agency legally accepted responsibility for this exact issue.
- That a contractor caused a problem.
- That a work order was completed well or badly.
- That an official closure means verified real-world resolution.
- That private complaint tracking or account-linked status is available.

## Data Gaps

- `data/geo/ward_boundaries.geojson` is derived from public GBA KML. It is not
  live gazette proof, and boundary-edge matches require official confirmation.
- Ward aliases are useful hints but not filing-critical proof.
- Data coverage is strongest for roads and streetlights. Garbage, sewage, power,
  and some footpath cases often need deeper official datasets.
- Model matrix live providers are optional. Missing OpenAI or Anthropic keys are
  recorded as `skipped_missing_key`, not as release blockers.
- Some official portals are dynamic, account-linked, OTP-protected, or unsafe for
  public scraping and are intentionally excluded.
- The legacy RAG retriever can inspect broader retrieval data, but it is not the
  trusted packet fact path.
