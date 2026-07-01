import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError

from civic_data.geo_boundary import (
    build_boundary_geojson,
    load_boundaries,
    point_in_polygon,
    resolve_boundary,
)
from civic_data.packet import build_evidence_packet


class GeoBoundaryTests(unittest.TestCase):
    def test_point_in_polygon_inside_outside_and_edge(self):
        ring = [[77.0, 12.0], [77.1, 12.0], [77.1, 12.1], [77.0, 12.1], [77.0, 12.0]]

        self.assertEqual(point_in_polygon(77.05, 12.05, ring), "inside")
        self.assertEqual(point_in_polygon(77.2, 12.05, ring), "outside")
        self.assertEqual(point_in_polygon(77.0, 12.05, ring), "edge")

    def test_build_boundary_geojson_from_existing_gba_kml(self):
        if not (Path("data/raw") / "gba_wards_delimitation_2025").exists():
            self.skipTest("raw GBA ward-boundary archive is not checked into the public repo")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "ward_boundaries.geojson"

            payload = build_boundary_geojson(Path("data/raw"), output)

            self.assertEqual(payload["type"], "FeatureCollection")
            self.assertGreaterEqual(len(payload["features"]), 368)
            self.assertTrue(output.exists())
            first = payload["features"][0]
            self.assertIn(first["geometry"]["type"], {"Polygon", "MultiPolygon"})
            self.assertIn("ward_number", first["properties"])
            self.assertIn("ward_name", first["properties"])
            self.assertEqual(first["properties"]["source_id"], "gba_wards_delimitation_2025")

    def test_resolve_boundary_inside_and_outside(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "boundaries.geojson"
            path.write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "geometry": {
                                    "type": "Polygon",
                                    "coordinates": [
                                        [
                                            [77.0, 12.0],
                                            [77.1, 12.0],
                                            [77.1, 12.1],
                                            [77.0, 12.1],
                                            [77.0, 12.0],
                                        ]
                                    ],
                                },
                                "properties": {
                                    "source_id": "gba_wards_delimitation_2025",
                                    "source_file": "original/test.kml",
                                    "run_id": "test-run",
                                    "ward_number": "46",
                                    "ward_name": "Yamalur",
                                    "normalized_ward_name": "yamalur",
                                    "corporation": "East",
                                    "assembly_constituency": "Mahadevapura",
                                    "assembly_constituency_number": "174",
                                    "ward_regime": "368_or_369",
                                    "version": "gba_2025",
                                    "fetched_at": "test-run",
                                },
                            }
                        ],
                    }
                )
            )

            inside = resolve_boundary(12.05, 77.05, path)
            outside = resolve_boundary(13.0, 78.0, path)

            self.assertIsNotNone(inside)
            self.assertEqual(inside["source"], "boundary_contains")
            self.assertEqual(inside["ward_number"], "46")
            self.assertIsNone(outside)

    def test_packet_falls_back_to_boundary_after_xyinfo_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "boundaries.geojson"
            path.write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "geometry": {
                                    "type": "Polygon",
                                    "coordinates": [
                                        [
                                            [77.0, 12.0],
                                            [77.1, 12.0],
                                            [77.1, 12.1],
                                            [77.0, 12.1],
                                            [77.0, 12.0],
                                        ]
                                    ],
                                },
                                "properties": {
                                    "source_id": "gba_wards_delimitation_2025",
                                    "source_file": "original/test.kml",
                                    "run_id": "test-run",
                                    "ward_number": "46",
                                    "ward_name": "Yamalur",
                                    "normalized_ward_name": "yamalur",
                                    "corporation": "East",
                                    "assembly_constituency": "Mahadevapura",
                                    "assembly_constituency_number": "174",
                                    "ward_regime": "368_or_369",
                                    "version": "gba_2025",
                                    "fetched_at": "test-run",
                                },
                            }
                        ],
                    }
                )
            )

            packet = build_evidence_packet(
                "streetlight near this pin",
                warehouse_root="data/normalized",
                lat=12.05,
                lng=77.05,
                xyinfo_client=lambda _lng, _lat: (_ for _ in ()).throw(URLError("offline")),
                boundary_path=path,
            )

            self.assertEqual(packet["jurisdiction"]["source"], "boundary_contains")
            self.assertEqual(packet["audit"]["resolver_source"], "boundary_contains")
            self.assertEqual(packet["place"]["source"], "boundary_contains")

    def test_malformed_boundary_file_does_not_crash_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.geojson"
            path.write_text("{not-json")

            packet = build_evidence_packet(
                "Bellandur streetlight not working",
                warehouse_root="data/normalized",
                lat=12.9,
                lng=77.6,
                xyinfo_client=lambda _lng, _lat: (_ for _ in ()).throw(URLError("offline")),
                boundary_path=path,
            )

            self.assertNotEqual(packet["jurisdiction"]["source"], "boundary_contains")
            self.assertIn("Boundary lookup failed", packet["jurisdiction"]["caveat"])

    def test_load_boundaries_rejects_missing_file(self):
        self.assertEqual(load_boundaries(Path("/tmp/does-not-exist-boundaries.geojson")), [])


if __name__ == "__main__":
    unittest.main()
