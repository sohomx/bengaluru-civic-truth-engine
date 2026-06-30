import contextlib
import io
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from civic_data.cli import main


class ModelMatrixTests(unittest.TestCase):
    def test_packet_rag_matrix_runs_deterministic_and_skips_missing_keys(self):
        previous = {key: os.environ.get(key) for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")}
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        try:
            with TemporaryDirectory() as tmp:
                output = Path(tmp) / "matrix"
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "eval",
                            "packet-rag-matrix",
                            "--suite",
                            "tests/fixtures/packet_eval/packet_rag_v1.jsonl",
                            "--providers",
                            "deterministic,anthropic,openai",
                            "--output",
                            str(output),
                        ]
                    )

                self.assertEqual(exit_code, 0)
                self.assertTrue((output / "matrix.json").exists())
                self.assertTrue((output / "matrix.md").exists())
                payload = json.loads((output / "matrix.json").read_text())
                by_provider = {item["provider"]: item for item in payload["providers"]}
                self.assertEqual(by_provider["deterministic"]["status"], "completed")
                self.assertEqual(by_provider["anthropic"]["status"], "skipped_missing_key")
                self.assertEqual(by_provider["openai"]["status"], "skipped_missing_key")
                self.assertIn("token_usage", by_provider["deterministic"])
                self.assertIn("prompt_version", by_provider["deterministic"])
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
