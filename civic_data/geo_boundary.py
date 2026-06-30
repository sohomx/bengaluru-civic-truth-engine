from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from civic_data.normalize import normalize_name


SOURCE_ID = "gba_wards_delimitation_2025"
BOUNDARY_VERSION = "gba_2025"
EDGE_EPSILON = 1e-10


@dataclass(frozen=True)
class BoundaryFeature:
    geometry: dict[str, Any]
    properties: dict[str, Any]


def build_boundary_geojson(raw_root: Path, output: Path) -> dict[str, Any]:
    kml_path = _select_boundary_kml(raw_root)
    run_dir = kml_path.parent.parent
    manifest = _read_manifest(run_dir / "manifest.json")
    fetched_at = str(manifest.get("fetched_at") or manifest.get("completed_at") or run_dir.name)
    features = parse_kml_boundaries(
        kml_path,
        source_id=SOURCE_ID,
        run_id=run_dir.name,
        fetched_at=fetched_at,
    )
    payload = {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "source_id": SOURCE_ID,
            "source_file": str(kml_path.relative_to(run_dir)),
            "run_id": run_dir.name,
            "feature_count": len(features),
            "version": BOUNDARY_VERSION,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def parse_kml_boundaries(kml_path: Path, source_id: str, run_id: str, fetched_at: str) -> list[dict[str, Any]]:
    root = ET.parse(kml_path).getroot()
    ns = {"k": "http://www.opengis.net/kml/2.2"}
    features: list[dict[str, Any]] = []
    for placemark in root.findall(".//k:Placemark", ns):
        fields = {
            str(item.attrib.get("name") or ""): (item.text or "").strip()
            for item in placemark.findall(".//k:SimpleData", ns)
            if item.attrib.get("name")
        }
        polygons = _placemark_polygons(placemark, ns)
        if not polygons:
            continue
        ward_name = fields.get("ward_name") or fields.get("Ward_Name") or fields.get("name") or ""
        ward_number = fields.get("ward_id") or fields.get("ward_no") or fields.get("ward_number") or _leading_number(ward_name)
        if " - " in ward_name:
            ward_name = ward_name.split(" - ", 1)[1].strip()
        geometry: dict[str, Any]
        if len(polygons) == 1:
            geometry = {"type": "Polygon", "coordinates": polygons[0]}
        else:
            geometry = {"type": "MultiPolygon", "coordinates": polygons}
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "source_id": source_id,
                    "source_file": str(kml_path.parent.name + "/" + kml_path.name),
                    "run_id": run_id,
                    "ward_number": str(ward_number or ""),
                    "ward_name": ward_name,
                    "normalized_ward_name": normalize_name(ward_name),
                    "corporation": fields.get("Corporation") or fields.get("corporation") or "",
                    "assembly_constituency": fields.get("ac") or fields.get("Assembly") or "",
                    "assembly_constituency_number": fields.get("ac_no") or "",
                    "ward_regime": "369" if _placemark_count(kml_path) == 369 else "368_or_369",
                    "version": BOUNDARY_VERSION,
                    "fetched_at": fetched_at,
                },
            }
        )
    return features


def load_boundaries(path: Path) -> list[BoundaryFeature]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        return []
    features = payload.get("features")
    if not isinstance(features, list):
        return []
    result: list[BoundaryFeature] = []
    for item in features:
        if not isinstance(item, dict):
            continue
        geometry = item.get("geometry") if isinstance(item.get("geometry"), dict) else {}
        properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
        if geometry and properties:
            result.append(BoundaryFeature(geometry=geometry, properties=properties))
    return result


def resolve_boundary(lat: float, lng: float, boundary_path: Path) -> dict[str, Any] | None:
    boundaries = load_boundaries(boundary_path)
    inside_matches: list[BoundaryFeature] = []
    edge_matches: list[BoundaryFeature] = []
    for feature in boundaries:
        status = point_in_multipolygon(lng, lat, feature.geometry)
        if status == "inside":
            inside_matches.append(feature)
        elif status == "edge":
            edge_matches.append(feature)
    if inside_matches:
        return _boundary_result(inside_matches[0], "boundary_contains", 0.97, inside_matches)
    if edge_matches:
        return _boundary_result(edge_matches[0], "boundary_edge", 0.88, edge_matches)
    return None


def point_in_multipolygon(lng: float, lat: float, geometry: dict[str, Any]) -> str:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon" and isinstance(coordinates, list):
        return _point_in_polygon_with_holes(lng, lat, coordinates)
    if geometry_type == "MultiPolygon" and isinstance(coordinates, list):
        saw_edge = False
        for polygon in coordinates:
            if not isinstance(polygon, list):
                continue
            status = _point_in_polygon_with_holes(lng, lat, polygon)
            if status == "inside":
                return "inside"
            if status == "edge":
                saw_edge = True
        return "edge" if saw_edge else "outside"
    return "outside"


def point_in_polygon(lng: float, lat: float, ring: list[list[float]]) -> str:
    if len(ring) < 4:
        return "outside"
    inside = False
    j = len(ring) - 1
    for i, current in enumerate(ring):
        previous = ring[j]
        if _on_segment(lng, lat, previous, current):
            return "edge"
        xi, yi = float(current[0]), float(current[1])
        xj, yj = float(previous[0]), float(previous[1])
        intersects = ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / ((yj - yi) or EDGE_EPSILON) + xi)
        if intersects:
            inside = not inside
        j = i
    return "inside" if inside else "outside"


def _select_boundary_kml(raw_root: Path) -> Path:
    source_root = raw_root / SOURCE_ID
    if not source_root.exists():
        raise FileNotFoundError(f"Missing raw source root: {source_root}")
    candidates: list[tuple[int, str, Path]] = []
    for run_dir in source_root.iterdir():
        if not run_dir.is_dir():
            continue
        status = str(_read_manifest(run_dir / "manifest.json").get("status") or "")
        if status and status != "success":
            continue
        for path in (run_dir / "original").glob("*.kml"):
            count = _placemark_count(path)
            if count >= 300:
                preference = 0 if count == 369 else 1 if count == 368 else 2
                candidates.append((preference, run_dir.name, path))
    if not candidates:
        raise FileNotFoundError(f"No ward boundary KML found under {source_root}")
    return sorted(candidates, key=lambda item: (item[0], item[1], item[2].name), reverse=False)[0][2]


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _placemark_count(path: Path) -> int:
    try:
        text = path.read_text(errors="ignore")
    except OSError:
        return 0
    return text.count("<Placemark")


def _placemark_polygons(placemark: ET.Element, ns: dict[str, str]) -> list[list[list[list[float]]]]:
    polygons: list[list[list[list[float]]]] = []
    for polygon in placemark.findall(".//k:Polygon", ns):
        rings: list[list[list[float]]] = []
        outer = polygon.find(".//k:outerBoundaryIs/k:LinearRing/k:coordinates", ns)
        outer_ring = _parse_coordinates(outer.text if outer is not None else "")
        if len(outer_ring) < 4:
            continue
        rings.append(outer_ring)
        for inner in polygon.findall(".//k:innerBoundaryIs/k:LinearRing/k:coordinates", ns):
            inner_ring = _parse_coordinates(inner.text or "")
            if len(inner_ring) >= 4:
                rings.append(inner_ring)
        polygons.append(rings)
    return polygons


def _parse_coordinates(value: str) -> list[list[float]]:
    ring: list[list[float]] = []
    for token in value.split():
        parts = token.split(",")
        if len(parts) < 2:
            continue
        try:
            ring.append([float(parts[0]), float(parts[1])])
        except ValueError:
            continue
    if ring and ring[0] != ring[-1]:
        ring.append(list(ring[0]))
    return ring


def _point_in_polygon_with_holes(lng: float, lat: float, polygon: list[Any]) -> str:
    if not polygon or not isinstance(polygon[0], list):
        return "outside"
    outer = point_in_polygon(lng, lat, polygon[0])
    if outer != "inside":
        return outer
    for hole in polygon[1:]:
        if not isinstance(hole, list):
            continue
        status = point_in_polygon(lng, lat, hole)
        if status == "edge":
            return "edge"
        if status == "inside":
            return "outside"
    return "inside"


def _boundary_result(feature: BoundaryFeature, source: str, confidence: float, matches: list[BoundaryFeature]) -> dict[str, Any]:
    props = feature.properties
    ambiguous = matches[1:]
    if source == "boundary_contains" and ambiguous:
        confidence = 0.9
    caveat = (
        "Point lies on or very near a boundary; confirm official lookup."
        if source == "boundary_edge"
        else "Offline public ward boundary match; confirm official lookup for filing-critical routing."
    )
    evidence = {
        "source_id": props.get("source_id") or SOURCE_ID,
        "source_file": props.get("source_file") or "",
        "run_id": props.get("run_id") or "",
        "fetched_at": props.get("fetched_at") or "",
        "boundary_version": props.get("version") or BOUNDARY_VERSION,
    }
    return {
        "source": source,
        "source_url": "",
        "official_endpoint_pattern": "",
        "source_id": evidence["source_id"],
        "source_authority": "mirrored_official",
        "ward_number": str(props.get("ward_number") or ""),
        "ward_name": str(props.get("ward_name") or ""),
        "normalized_ward_name": str(props.get("normalized_ward_name") or normalize_name(str(props.get("ward_name") or ""))),
        "corporation": str(props.get("corporation") or ""),
        "zone": str(props.get("zone") or ""),
        "assembly_constituency": str(props.get("assembly_constituency") or ""),
        "assembly_constituency_number": str(props.get("assembly_constituency_number") or ""),
        "ward_regime": str(props.get("ward_regime") or "368_or_369"),
        "confidence": confidence,
        "caveat": caveat,
        "evidence": evidence,
        "ambiguous_boundary_matches": [
            {
                "ward_number": str(item.properties.get("ward_number") or ""),
                "ward_name": str(item.properties.get("ward_name") or ""),
            }
            for item in ambiguous
        ],
    }


def _on_segment(lng: float, lat: float, start: list[float], end: list[float]) -> bool:
    x1, y1 = float(start[0]), float(start[1])
    x2, y2 = float(end[0]), float(end[1])
    cross = (lat - y1) * (x2 - x1) - (lng - x1) * (y2 - y1)
    if abs(cross) > EDGE_EPSILON:
        return False
    return min(x1, x2) - EDGE_EPSILON <= lng <= max(x1, x2) + EDGE_EPSILON and min(y1, y2) - EDGE_EPSILON <= lat <= max(y1, y2) + EDGE_EPSILON


def _leading_number(value: str) -> str:
    digits = []
    for char in value.strip():
        if char.isdigit():
            digits.append(char)
        elif digits:
            break
    return "".join(digits)
