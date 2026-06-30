import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from civic_data.fetch import fetch_all_sources, fetch_source
from civic_data.profile import profile_archives


class FakeHttpClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = {}

    def get_bytes(self, url):
        self.calls[url] = self.calls.get(url, 0) + 1
        value = self.responses[url]
        if isinstance(value, Exception):
            raise value
        if isinstance(value, list):
            next_value = value.pop(0)
            if isinstance(next_value, Exception):
                raise next_value
            body, headers = next_value
            return body, headers
        body, headers = value
        return body, headers

    def get_json(self, url):
        body, _headers = self.get_bytes(url)
        return json.loads(body.decode("utf-8"))


class FetchArchiveProfileTests(unittest.TestCase):
    def test_fetch_all_archives_ckan_resources_and_failure_manifests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = [
                {
                    "id": "ckan_source",
                    "name": "CKAN Source",
                    "url": "https://data.opencity.in/dataset/example",
                    "access_method": "opencity_ckan",
                    "enabled": True,
                    "domain": "wards",
                    "format": "ckan_package",
                },
                {
                    "id": "broken_source",
                    "name": "Broken Source",
                    "url": "https://example.invalid/broken.csv",
                    "access_method": "direct_file",
                    "enabled": True,
                    "domain": "roads",
                    "format": "csv",
                },
            ]
            package = {
                "success": True,
                "result": {
                    "name": "example",
                    "resources": [
                        {
                            "id": "resource-1",
                            "name": "Rows",
                            "url": "https://files.example/rows.csv",
                            "format": "CSV",
                            "state": "active",
                        }
                    ],
                },
            }
            http = FakeHttpClient(
                {
                    "https://data.opencity.in/api/3/action/package_show?id=example": (
                        json.dumps(package).encode("utf-8"),
                        {"content-type": "application/json"},
                    ),
                    "https://files.example/rows.csv": (
                        b"name,value\nA,1\n",
                        {"content-type": "text/csv"},
                    ),
                    "https://example.invalid/broken.csv": RuntimeError("network down"),
                }
            )

            results = fetch_all_sources(
                sources,
                raw_root=root / "data" / "raw",
                registry_hash_value="abc123",
                http_client=http,
                timestamp="2026-06-12T00-00-00Z",
            )

            self.assertEqual([result.status for result in results], ["success", "failed"])
            success_manifest = json.loads(
                (root / "data/raw/ckan_source/2026-06-12T00-00-00Z/manifest.json").read_text()
            )
            failed_manifest = json.loads(
                (root / "data/raw/broken_source/2026-06-12T00-00-00Z/manifest.json").read_text()
            )

            self.assertEqual(success_manifest["status"], "success")
            self.assertEqual(success_manifest["registry_version_hash"], "abc123")
            self.assertEqual(len(success_manifest["files"]), 2)
            self.assertTrue(
                (root / "data/raw/ckan_source/2026-06-12T00-00-00Z/original/resource-1.csv").exists()
            )
            self.assertEqual(failed_manifest["status"], "failed")
            self.assertIn("network down", failed_manifest["errors"][0])
            self.assertTrue(
                (root / "data/raw/ckan_source/2026-06-12T00-00-00Z/checksums.sha256").exists()
            )

    def test_profile_archives_writes_parser_backlog(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "data/raw/sample/2026-06-12T00-00-00Z"
            (run_dir / "original").mkdir(parents=True)
            (run_dir / "original/rows.csv").write_text("a,b\n1,2\n3,4\n")
            (run_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "source_id": "sample",
                        "status": "success",
                        "files": [{"path": "original/rows.csv", "bytes": 12}],
                        "errors": [],
                    }
                )
            )

            profile_archives(
                sources=[{"id": "sample", "domain": "wards", "format": "csv"}],
                raw_root=root / "data/raw",
                export_root=root / "data/exports",
            )

            backlog = root / "data/exports/parser_backlog.csv"
            with backlog.open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["source_id"], "sample")
            self.assertEqual(rows[0]["detected_columns"], "a|b")
            self.assertEqual(rows[0]["row_count_if_tabular"], "2")
            self.assertEqual(rows[0]["parser_difficulty"], "easy_structured")

    def test_profile_infers_resource_counts_for_v1_ckan_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "data/raw/sample/2026-06-12T00-00-00Z"
            (run_dir / "original").mkdir(parents=True)
            (run_dir / "original/ckan_package.json").write_text(
                json.dumps(
                    {
                        "result": {
                            "resources": [
                                {"id": "r1", "state": "active"},
                                {"id": "r2", "state": "active"},
                                {"id": "old", "state": "deleted"},
                            ]
                        }
                    }
                )
            )
            (run_dir / "original/r1.csv").write_text("a\n1\n")
            (run_dir / "original/r2.csv").write_text("a\n2\n")
            (run_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "source_id": "sample",
                        "status": "success",
                        "files": [
                            {"path": "original/ckan_package.json", "bytes": 100},
                            {"path": "original/r1.csv", "bytes": 4},
                            {"path": "original/r2.csv", "bytes": 4},
                        ],
                        "errors": [],
                    }
                )
            )

            rows = profile_archives(
                sources=[{"id": "sample", "domain": "wards", "format": "ckan_package"}],
                raw_root=root / "data/raw",
                export_root=root / "data/exports",
            )

            self.assertEqual(rows[0]["expected_resource_count"], "2")
            self.assertEqual(rows[0]["fetched_resource_count"], "2")

    def test_ckan_manifest_records_each_resource_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = {
                "success": True,
                "result": {
                    "name": "example",
                    "resources": [
                        {"id": "r1", "name": "One", "url": "https://files/r1.csv", "format": "CSV", "state": "active"},
                        {"id": "r2", "name": "Two", "url": "https://files/r2.csv", "format": "CSV", "state": "active"},
                        {"id": "r3", "name": "Three", "url": "https://files/r3.csv", "format": "CSV", "state": "active"},
                    ],
                },
            }
            http = FakeHttpClient(
                {
                    "https://data.opencity.in/api/3/action/package_show?id=example": (
                        json.dumps(package).encode("utf-8"),
                        {"content-type": "application/json"},
                    ),
                    "https://files/r1.csv": (b"a\n1\n", {"content-type": "text/csv"}),
                    "https://files/r2.csv": RuntimeError("resource down"),
                    "https://files/r3.csv": (b"a\n3\n", {"content-type": "text/csv"}),
                }
            )

            result = fetch_source(
                {"id": "ckan_source", "url": "https://data.opencity.in/dataset/example", "access_method": "opencity_ckan"},
                raw_root=root / "raw",
                registry_hash_value="hash",
                http_client=http,
                timestamp="2026-06-12T00-00-00Z",
            )

            manifest = json.loads((result.run_dir / "manifest.json").read_text())
            records = manifest["ckan_resources"]["records"]
            self.assertEqual(result.status, "partial")
            self.assertEqual(manifest["manifest_version"], 2)
            self.assertEqual(manifest["ckan_resources"]["total"], 3)
            self.assertEqual(manifest["ckan_resources"]["completed"], 2)
            self.assertEqual(manifest["ckan_resources"]["failed"], 1)
            self.assertEqual([record["status"] for record in records], ["success", "failed", "success"])
            self.assertIn("resource down", records[1]["error"])

    def test_resume_reuses_verified_resources_and_fetches_missing_resource(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = {
                "id": "ckan_source",
                "url": "https://data.opencity.in/dataset/example",
                "access_method": "opencity_ckan",
            }
            package = {
                "success": True,
                "result": {
                    "name": "example",
                    "resources": [
                        {"id": "r1", "name": "One", "url": "https://files/r1.csv", "format": "CSV", "state": "active"},
                        {"id": "r2", "name": "Two", "url": "https://files/r2.csv", "format": "CSV", "state": "active"},
                    ],
                },
            }
            first_http = FakeHttpClient(
                {
                    "https://data.opencity.in/api/3/action/package_show?id=example": (
                        json.dumps(package).encode("utf-8"),
                        {"content-type": "application/json"},
                    ),
                    "https://files/r1.csv": (b"a\n1\n", {"content-type": "text/csv"}),
                    "https://files/r2.csv": RuntimeError("first failure"),
                }
            )
            first = fetch_source(
                source,
                raw_root=root / "raw",
                registry_hash_value="hash",
                http_client=first_http,
                timestamp="2026-06-12T00-00-00Z",
            )

            second_http = FakeHttpClient(
                {
                    "https://data.opencity.in/api/3/action/package_show?id=example": (
                        json.dumps(package).encode("utf-8"),
                        {"content-type": "application/json"},
                    ),
                    "https://files/r1.csv": RuntimeError("should not refetch r1"),
                    "https://files/r2.csv": (b"a\n2\n", {"content-type": "text/csv"}),
                }
            )
            second = fetch_source(
                source,
                raw_root=root / "raw",
                registry_hash_value="hash",
                http_client=second_http,
                timestamp="2026-06-12T00-01-00Z",
                resume_from=first.run_dir,
            )

            manifest = json.loads((second.run_dir / "manifest.json").read_text())
            records = manifest["ckan_resources"]["records"]
            self.assertEqual(second.status, "success")
            self.assertEqual([record["status"] for record in records], ["reused", "success"])
            self.assertEqual(second_http.calls.get("https://files/r1.csv"), None)
            self.assertTrue((second.run_dir / records[0]["path"]).exists())
            self.assertEqual(hashlib.sha256((second.run_dir / records[0]["path"]).read_bytes()).hexdigest(), records[0]["sha256"])

    def test_resource_retry_records_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = {
                "success": True,
                "result": {
                    "name": "example",
                    "resources": [
                        {"id": "r1", "name": "One", "url": "https://files/r1.csv", "format": "CSV", "state": "active"},
                    ],
                },
            }
            http = FakeHttpClient(
                {
                    "https://data.opencity.in/api/3/action/package_show?id=example": (
                        json.dumps(package).encode("utf-8"),
                        {"content-type": "application/json"},
                    ),
                    "https://files/r1.csv": [
                        RuntimeError("temporary failure"),
                        (b"a\n1\n", {"content-type": "text/csv"}),
                    ],
                }
            )

            result = fetch_source(
                {"id": "ckan_source", "url": "https://data.opencity.in/dataset/example", "access_method": "opencity_ckan"},
                raw_root=root / "raw",
                registry_hash_value="hash",
                http_client=http,
                timestamp="2026-06-12T00-00-00Z",
                resource_retries=1,
                retry_delay_seconds=0,
            )

            manifest = json.loads((result.run_dir / "manifest.json").read_text())
            record = manifest["ckan_resources"]["records"][0]
            self.assertEqual(result.status, "success")
            self.assertEqual(record["attempts"], 2)
            self.assertEqual(record["status"], "success")
