from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from civic_data.packet_builder import build_packet


def build_evidence_packet(
    query: str,
    warehouse_root: Path | str = Path("data/normalized"),
    raw_root: Path | str = Path("data/raw"),
    index_path: Path | str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    xyinfo_client: Callable[[float, float], Any] | None = None,
    locality_alias_path: Path | str | None = Path("data/config/locality_aliases.json"),
    boundary_path: Path | str | None = Path("data/geo/ward_boundaries.geojson"),
) -> dict[str, Any]:
    packet = build_packet(
        query=query,
        warehouse_root=warehouse_root,
        lat=lat,
        lng=lng,
        xyinfo_client=xyinfo_client,
        locality_alias_path=locality_alias_path,
        boundary_path=boundary_path,
    )
    audit = packet.setdefault("audit", {})
    if isinstance(audit, dict):
        audit["compatibility_inputs"] = {
            "raw_root": str(raw_root),
            "index_path": str(index_path) if index_path else "",
            "used_for_fact_generation": False,
            "note": "Packet generation reads normalized public data only; raw and RAG index inputs are compatibility parameters.",
        }
    return packet
