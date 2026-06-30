import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from civic_data.cli import main
from tests.test_portfolio_packet_productization import _warehouse


class FakePacketLlmClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create_packet_explanation(self, *, prompt: dict[str, object], schema: dict[str, object], config: object) -> dict[str, object]:
        self.calls.append({"prompt": prompt, "schema": schema, "config": config})
        return {
            "answer": "File a civic streetlight complaint and cite the public streetlight row as context only.",
            "next_action": "File through the official civic channel with pole number, photo, and location.",
            "citations": ["evidence-1", "jurisdiction-1"],
            "refusals": ["Do not claim the work row proves the light was fixed."],
            "unsupported_claims": ["real-world resolution"],
            "confidence": "source_backed_partial",
        }


class PacketLlmRagTests(unittest.TestCase):
    def test_default_packet_explainer_is_deterministic_and_names_model_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            from civic_data.packet import build_evidence_packet
            from civic_data.packet_explainer import explain_packet

            packet = build_evidence_packet("Bellandur streetlight not working", warehouse_root=_warehouse(Path(tmp)))
            explanation = explain_packet(packet, question="What should I do?")

            self.assertEqual(explanation["audit"]["generation_mode"], "deterministic")
            self.assertEqual(explanation["audit"]["llm_provider"], "none")
            self.assertEqual(explanation["audit"]["llm_model"], "")
            self.assertEqual(explanation["audit"]["prompt_version"], "packet-explainer-deterministic-v1")
            self.assertTrue(explanation["audit"]["used_packet_only"])

    def test_llm_mode_requires_api_key_unless_client_is_injected(self):
        with tempfile.TemporaryDirectory() as tmp:
            from civic_data.packet import build_evidence_packet
            from civic_data.packet_explainer import explain_packet

            packet = build_evidence_packet("Bellandur streetlight not working", warehouse_root=_warehouse(Path(tmp)))
            previous = {key: os.environ.get(key) for key in ("OPENAI_API_KEY", "CIVIC_OPENAI_API_KEY", "CIVIC_LLM_PROVIDER")}
            try:
                os.environ.pop("OPENAI_API_KEY", None)
                os.environ.pop("CIVIC_OPENAI_API_KEY", None)
                os.environ.pop("CIVIC_LLM_PROVIDER", None)
                with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                    explain_packet(packet, question="What should I do?", mode="llm")
            finally:
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_llm_packet_explainer_uses_packet_chunks_and_structured_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            from civic_data.packet import build_evidence_packet
            from civic_data.packet_explainer import explain_packet

            packet = build_evidence_packet("Bellandur streetlight not working", warehouse_root=_warehouse(Path(tmp)))
            fake = FakePacketLlmClient()
            explanation = explain_packet(packet, question="Can I cite this?", mode="llm", llm_client=fake)

            self.assertEqual(explanation["audit"]["generation_mode"], "llm")
            self.assertEqual(explanation["audit"]["llm_provider"], "openai")
            self.assertEqual(explanation["audit"]["llm_model"], "gpt-5.4-mini")
            self.assertEqual(explanation["audit"]["embedding_model"], "text-embedding-3-small")
            self.assertEqual(explanation["audit"]["prompt_version"], "packet-explainer-v1")
            self.assertFalse(explanation["audit"]["used_raw_scan"])
            self.assertTrue(explanation["retrieved_chunks"])
            self.assertEqual(explanation["answer"], "File a civic streetlight complaint and cite the public streetlight row as context only.")
            self.assertIn("evidence-1", explanation["citations"])
            prompt = fake.calls[0]["prompt"]
            self.assertIn("allowed_claims", json.dumps(prompt))
            self.assertNotIn("raw_root", json.dumps(prompt))

    def test_anthropic_llm_config_uses_anthropic_env_names(self):
        from civic_data.llm_config import PacketRagConfig

        previous = {
            "CIVIC_LLM_PROVIDER": os.environ.get("CIVIC_LLM_PROVIDER"),
            "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY"),
            "ANTHROPIC_MODEL": os.environ.get("ANTHROPIC_MODEL"),
        }
        try:
            os.environ["CIVIC_LLM_PROVIDER"] = "anthropic"
            os.environ["ANTHROPIC_API_KEY"] = "test-anthropic-key"
            os.environ["ANTHROPIC_MODEL"] = "claude-haiku-4-5-20251001"

            config = PacketRagConfig.from_env("llm")

            self.assertEqual(config.provider, "anthropic")
            self.assertEqual(config.api_key, "test-anthropic-key")
            self.assertEqual(config.llm_model, "claude-haiku-4-5-20251001")
            config.require_llm_key()
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_anthropic_packet_client_parses_json_text_response(self):
        from civic_data.anthropic_packet_client import AnthropicMessagesPacketClient
        from civic_data.llm_config import PacketRagConfig

        calls: list[dict[str, object]] = []

        def fake_transport(request: object, timeout: int = 30) -> dict[str, object]:
            calls.append({"request": request, "timeout": timeout})
            return {
                "id": "msg_test",
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "answer": "Use the packet action and cite evidence-1 only as public context.",
                                "next_action": "File through the official channel.",
                                "citations": ["evidence-1"],
                                "refusals": [],
                                "unsupported_claims": ["field resolution"],
                                "confidence": "source_backed_partial",
                            }
                        ),
                    }
                ],
                "usage": {"input_tokens": 10, "output_tokens": 12},
            }

        client = AnthropicMessagesPacketClient(transport=fake_transport)
        config = PacketRagConfig(
            generation_mode="llm",
            provider="anthropic",
            llm_model="claude-haiku-4-5-20251001",
            embedding_model="",
            prompt_version="packet-explainer-v1",
            api_key="test-key",
        )

        result = client.create_packet_explanation(
            prompt={"system": "system prompt", "user": {"question": "What now?"}},
            schema={"type": "object"},
            config=config,
        )

        self.assertEqual(result["answer"], "Use the packet action and cite evidence-1 only as public context.")
        self.assertEqual(result["_llm_response_id"], "msg_test")
        self.assertEqual(calls[0]["timeout"], 30)

    def test_cli_packet_explain_supports_llm_mode_with_deterministic_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            from civic_data.packet import build_evidence_packet

            packet_path = root / "packet.json"
            packet_path.write_text(json.dumps(build_evidence_packet("Bellandur streetlight not working", warehouse_root=_warehouse(root))))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(["packets", "explain", "--packet", str(packet_path), "--q", "What now?"])

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["audit"]["generation_mode"], "deterministic")

    def test_packet_rag_eval_reports_model_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet_path = root / "packet.json"
            suite = root / "packet_rag_eval.jsonl"
            from civic_data.packet import build_evidence_packet

            packet_path.write_text(json.dumps(build_evidence_packet("Bellandur streetlight not working", warehouse_root=_warehouse(root))))
            suite.write_text(json.dumps({"id": "streetlight-explain", "packet": str(packet_path), "question": "What now?", "must_contain": ["streetlight"], "forbidden": ["corruption"]}) + "\n")

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(["eval", "packet-rag", "--suite", str(suite), "--mode", "deterministic"])

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["passed"], 1)
            self.assertEqual(payload["model_config"]["generation_mode"], "deterministic")
            self.assertEqual(payload["model_config"]["prompt_version"], "packet-explainer-deterministic-v1")

    def test_packet_explainer_refuses_unsupported_blame_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            from civic_data.packet import build_evidence_packet
            from civic_data.packet_explainer import explain_packet

            packet = build_evidence_packet("Garbage black spot keeps returning near Varthur Kodi", warehouse_root=_warehouse(Path(tmp)))
            explanation = explain_packet(packet, question="Can I say the authorities ignored it?")

            self.assertEqual(explanation["refusal"]["status"], "refused_unsupported_claim")
            self.assertIn("ignored", json.dumps(explanation["what_not_to_claim"]).lower())

    def test_packet_explainer_limits_citations_to_best_packet_chunks(self):
        with tempfile.TemporaryDirectory() as tmp:
            from civic_data.packet import build_evidence_packet
            from civic_data.packet_explainer import explain_packet

            packet = build_evidence_packet("Bellandur streetlight not working", warehouse_root=_warehouse(Path(tmp)))
            explanation = explain_packet(packet, question="What evidence can I cite?")

            self.assertLessEqual(len(explanation["what_to_cite"]), 3)
            self.assertTrue(explanation["retrieved_chunks"])


if __name__ == "__main__":
    unittest.main()
