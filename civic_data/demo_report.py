from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from civic_data.packet import build_evidence_packet
from civic_data.packet_explainer import explain_packet


DEMO_PROMPTS = [
    "Bellandur streetlight not working for a week",
    "Kadubeesanahalli sewage overflowing near the apartment gate",
    "Whitefield pothole at ITPL back gate keeps returning",
    "Bellandur power outage with transformer sparks",
    "Garbage pile near Bellandur service road",
    "Whitefield road drain is broken and water stays on the road",
    "Road blocked near Whitefield because of traffic diversion and digging",
    "Streetlight near this pin",
    "Can I claim the Whitefield pothole row proves corruption?",
    "Is Bellandur power outage live right now?",
]


def generate_hiring_demo_report(
    *,
    warehouse_root: Path,
    raw_root: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    output = output_path or Path("data/eval_runs/hiring_demo_report.md")
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for prompt in DEMO_PROMPTS:
        lat = 12.9352 if prompt == "Streetlight near this pin" else None
        lng = 77.678 if prompt == "Streetlight near this pin" else None
        packet = build_evidence_packet(prompt, warehouse_root=warehouse_root, raw_root=raw_root, lat=lat, lng=lng)
        explanation = explain_packet(packet, question="What should a citizen do next?")
        rows.append({"prompt": prompt, "packet": packet, "explanation": explanation})
    output.write_text(_render(rows) + "\n")
    return {
        "output": str(output),
        "prompt_count": len(rows),
        "model_provider": rows[0]["explanation"]["audit"].get("llm_provider") if rows else "none",
        "generation_mode": rows[0]["explanation"]["audit"].get("generation_mode") if rows else "deterministic",
        "known_failures": _known_failures(rows),
    }


def _render(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Bengaluru Civic Action Engine Hiring Demo",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "Public product path: `packets build` -> `packets explain`.",
        "RAG explains packets only; it does not discover civic facts from raw data.",
        "",
        "## Summary",
        "",
        "| # | Prompt | Issue | Place | Agency | Evidence | Caveat |",
        "|---|---|---|---|---|---|---|",
    ]
    for index, row in enumerate(rows, start=1):
        packet = row["packet"]
        issue = packet.get("issue", {}).get("display_type") if isinstance(packet.get("issue"), dict) else packet.get("normalized_issue")
        place = packet.get("place", {}).get("ward_name") if isinstance(packet.get("place"), dict) else packet.get("normalized_place")
        caveat = "; ".join(str(item) for item in packet.get("limits", [])[:1])
        lines.append(
            "| {index} | {prompt} | {issue} | {place} | {agency} | {evidence} | {caveat} |".format(
                index=index,
                prompt=_cell(row["prompt"]),
                issue=_cell(issue),
                place=_cell(place or "unresolved"),
                agency=_cell(_agency_label(packet)),
                evidence=_cell(packet.get("evidence_strength")),
                caveat=_cell(caveat),
            )
        )
    lines.extend(["", "## Demo Details", ""])
    for index, row in enumerate(rows, start=1):
        packet = row["packet"]
        explanation = row["explanation"]
        lines.extend(
            [
                f"### {index}. {row['prompt']}",
                "",
                f"- Packet status: `{packet.get('packet_status')}`",
                f"- Evidence strength: `{packet.get('evidence_strength')}`",
                f"- Trace: `{packet.get('trace', {}).get('trace_id')}`",
                f"- Model/provider: `{explanation.get('audit', {}).get('generation_mode')}` / `{explanation.get('audit', {}).get('llm_provider')}`",
                f"- Next action: {explanation.get('answer')}",
                f"- Caveat: {'; '.join(str(item) for item in explanation.get('caveats', [])[:2])}",
                "",
            ]
        )
    failures = _known_failures(rows)
    lines.extend(["## Known Failures", ""])
    if failures:
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.append("- No release-gate failures in this deterministic demo report.")
    return "\n".join(lines)


def _known_failures(rows: list[dict[str, Any]]) -> list[str]:
    failures = []
    for row in rows:
        packet = row["packet"]
        if packet.get("audit", {}).get("contract_validation_failures"):
            failures.append(f"{row['prompt']}: contract validation failure")
        if packet.get("audit", {}).get("used_raw_scan"):
            failures.append(f"{row['prompt']}: raw scan used")
    return failures


def _cell(value: object) -> str:
    return str(value or "").replace("|", "/").replace("\n", " ")[:160]


def _agency_label(packet: dict[str, Any]) -> str:
    responsibility = packet.get("responsibility")
    if not isinstance(responsibility, dict):
        return ""
    primary = responsibility.get("primary_agency")
    names = []
    if isinstance(primary, dict) and primary.get("name"):
        names.append(str(primary["name"]))
    for agency in responsibility.get("secondary_agencies", []):
        if isinstance(agency, dict) and agency.get("name"):
            names.append(str(agency["name"]))
    return " + ".join(names)
