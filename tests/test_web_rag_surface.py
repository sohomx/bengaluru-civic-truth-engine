from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WebRagSurfaceTests(unittest.TestCase):
    def test_home_page_is_simple_rag_entrypoint(self):
        page = (ROOT / "web" / "src" / "app" / "page.tsx").read_text()

        self.assertIn("AskCivicRecord", page)
        self.assertNotIn("getSearchIndex", page)
        self.assertNotIn("from \"next/link\"", page)
        self.assertNotIn("getRagExamples", page)
        self.assertNotIn("<nav", page)
        self.assertNotIn("<h1", page)
        self.assertNotIn("Current retrieval scope", page)
        self.assertNotIn("Try these queries", page)
        self.assertNotIn("Pilot dossiers", page)
        self.assertNotIn("Open Bellandur", page)
        self.assertNotIn("Browse sources", page)

    def test_ask_page_has_no_chrome(self):
        page = (ROOT / "web" / "src" / "app" / "ask" / "page.tsx").read_text()

        self.assertNotIn("getSearchIndex", page)
        self.assertNotIn("from \"next/link\"", page)
        self.assertNotIn("<nav", page)
        self.assertNotIn("<h1", page)
        self.assertNotIn("Sources", page)
        self.assertNotIn("Methodology", page)
        self.assertNotIn("Known gaps", page)

    def test_ask_component_is_only_question_box_and_plain_answer(self):
        component = (ROOT / "web" / "src" / "components" / "ask-civic-record.tsx").read_text()

        self.assertIn("<input", component)
        self.assertIn("generated_answer", component)
        self.assertIn("answer_brief", component)
        self.assertIn("Short answer", component)
        self.assertIn("What records show", component)
        self.assertIn("What you can cite", component)
        self.assertIn("Who to contact", component)
        self.assertIn("Related works and payments", component)
        self.assertIn("What this does not prove", component)
        self.assertIn("Evidence table", component)
        self.assertIn("claims", component)
        self.assertIn("citations", component)
        self.assertIn("retrieval_trace", component)
        self.assertNotIn("Answer contract", component)
        self.assertNotIn("Source-backed claims", component)
        self.assertIn("civic_triage", component)
        self.assertIn("civic_interpretation", component)
        self.assertIn("who_to_contact", component)
        self.assertIn("what_to_do_next", component)
        self.assertIn("evidence_library", component)
        self.assertIn("Public evidence library", component)
        self.assertIn("Related public works and spending", component)
        self.assertIn("Neutrality note", component)
        self.assertIn("fetch(", component)
        self.assertIn("/rag/ask", component)
        self.assertIn("NEXT_PUBLIC_CIVIC_API_BASE", component)
        self.assertIn("127.0.0.1:8017", component)
        self.assertNotIn("buildRagAnswer", component)
        self.assertNotIn("SearchIndexEntry", component)
        self.assertNotIn("getRagExamples", component)
        self.assertNotIn("Static evidence index generated", component)
        self.assertNotIn("Retrieved context", component)
        self.assertNotIn("Primary retrieved record", component)
        self.assertNotIn("Citations", component)
        self.assertNotIn("Source IDs retrieved", component)
        self.assertNotIn("Inspect retrieved record", component)
        self.assertNotIn("lucide-react", component)

    def test_static_client_side_rag_helper_is_removed(self):
        self.assertFalse((ROOT / "web" / "src" / "lib" / "rag.ts").exists())

    def test_next_rewrites_rag_path_to_backend(self):
        config = (ROOT / "web" / "next.config.mjs").read_text()

        self.assertIn("async rewrites()", config)
        self.assertIn("/rag/:path*", config)
        self.assertIn("CIVIC_API_BASE", config)

    def test_api_allows_local_frontend_cors(self):
        app = (ROOT / "api" / "app.py").read_text()

        self.assertIn("CORSMiddleware", app)
        self.assertIn("127.0.0.1:3017", app)
