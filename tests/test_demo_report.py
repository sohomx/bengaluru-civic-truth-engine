import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from civic_data.cli import main


class DemoReportTests(unittest.TestCase):
    def test_hiring_demo_report_generates_markdown_for_ten_prompts(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "hiring_demo_report.md"
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                exit_code = main(
                    [
                        "demo",
                        "report",
                        "--warehouse-root",
                        "data/normalized",
                        "--raw-root",
                        "data/raw",
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["prompt_count"], 10)
            self.assertEqual(payload["generation_mode"], "deterministic")
            report = output_path.read_text()
            self.assertIn("Public product path", report)
            self.assertIn("RAG explains packets only", report)
            self.assertIn("Whitefield pothole", report)
            self.assertIn("Known Failures", report)


if __name__ == "__main__":
    unittest.main()
