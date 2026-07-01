import json
import unittest
from pathlib import Path

from civic_data.registry import load_sources, registry_url_report, validate_registry


OVERVIEW = Path("tests/fixtures/registry/overview_sample.md")


class RegistryTests(unittest.TestCase):
    def test_registry_validates_required_fields_and_enums(self):
        sources = load_sources(Path("registry/sources.yaml"))

        result = validate_registry(sources, Path("registry/source_schema.json"))

        self.assertEqual(result, [])
        self.assertGreaterEqual(len(sources), 80)

    def test_registry_covers_every_overview_url_once_as_canonical_or_alias(self):
        sources = load_sources(Path("registry/sources.yaml"))

        report = registry_url_report(sources, OVERVIEW)

        self.assertEqual(report["missing"], [])
        self.assertEqual(report["duplicate_unaliased"], [])

    def test_source_schema_is_json_schema_like_document(self):
        schema = json.loads(Path("registry/source_schema.json").read_text())

        self.assertEqual(schema["type"], "array")
        self.assertIn("id", schema["items"]["required"])
        self.assertIn("opencity_ckan", schema["items"]["properties"]["access_method"]["enum"])
