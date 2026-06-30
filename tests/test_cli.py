import tempfile
import unittest
from pathlib import Path

from civic_data.cli import main


class CliTests(unittest.TestCase):
    def test_registry_validate_command_succeeds(self):
        exit_code = main(["registry", "validate"])

        self.assertEqual(exit_code, 0)

    def test_sources_status_reports_not_fetched_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            exit_code = main(["sources", "status", "--raw-root", str(Path(tmp) / "raw")])

        self.assertEqual(exit_code, 0)

    def test_sources_profile_all_writes_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exit_code = main(
                [
                    "sources",
                    "profile",
                    "--all",
                    "--raw-root",
                    str(root / "raw"),
                    "--export-root",
                    str(root / "exports"),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "exports/parser_backlog.csv").exists())

    def test_fetch_command_accepts_resume_and_resource_retry_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "sources.yaml"
            registry.write_text("[]")

            exit_code = main(
                [
                    "sources",
                    "fetch",
                    "--all",
                    "--registry",
                    str(registry),
                    "--raw-root",
                    str(root / "raw"),
                    "--resume",
                    "--resource-retries",
                    "1",
                    "--retry-delay",
                    "0",
                ]
            )

            self.assertEqual(exit_code, 0)
