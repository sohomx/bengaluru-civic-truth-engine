from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WebRagSurfaceTests(unittest.TestCase):
    def test_home_page_is_simple_packet_entrypoint(self):
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

    def test_ask_component_is_packet_first_case_desk(self):
        component = (ROOT / "web" / "src" / "components" / "ask-civic-record.tsx").read_text()

        self.assertIn("<textarea", component)
        self.assertIn("CivicPacket", component)
        self.assertIn("Case summary", component)
        self.assertIn("What to do next", component)
        self.assertIn("Best public evidence", component)
        self.assertIn("Simple message", component)
        self.assertIn("What not to claim", component)
        self.assertIn("Facts: public records", component)
        self.assertIn("AI: explains packet only", component)
        self.assertIn("Why this answer?", component)
        self.assertIn("Show more evidence", component)
        self.assertIn("/packets/explain", component)
        self.assertIn("primary_action", component)
        self.assertIn("escalation_action", component)
        self.assertIn("legal_or_rti_action", component)
        self.assertIn("evidence_summary", component)
        self.assertIn("evidence_strength", component)
        self.assertIn("used_rag", component)
        self.assertIn("fetch(", component)
        self.assertIn("/packets/build", component)
        self.assertIn("NEXT_PUBLIC_CIVIC_API_BASE", component)
        self.assertIn("127.0.0.1:8017", component)
        self.assertIn("lucide-react", component)
        self.assertIn("formatSourceLabel", component)
        self.assertIn("formatMatchLabel", component)
        self.assertNotIn("offline_normalized_wards", component)
        self.assertNotIn("place_text_and_issue_terms", component)
        self.assertNotIn("generated_answer", component)
        self.assertNotIn("answer_brief", component)
        self.assertNotIn("RAG: ", component)
        self.assertNotIn("buildRagAnswer", component)
        self.assertNotIn("SearchIndexEntry", component)
        self.assertNotIn("getRagExamples", component)
        self.assertNotIn("Static evidence index generated", component)
        self.assertNotIn("Retrieved context", component)
        self.assertNotIn("Primary retrieved record", component)
        self.assertNotIn("Citations", component)
        self.assertNotIn("Source IDs retrieved", component)
        self.assertNotIn("Inspect retrieved record", component)

    def test_static_client_side_rag_helper_is_removed(self):
        self.assertFalse((ROOT / "web" / "src" / "lib" / "rag.ts").exists())

    def test_next_rewrites_packet_and_rag_paths_to_backend(self):
        config = (ROOT / "web" / "next.config.mjs").read_text()

        self.assertIn("async rewrites()", config)
        self.assertIn("/rag/:path*", config)
        self.assertIn("/packets/:path*", config)
        self.assertIn("CIVIC_API_BASE", config)

    def test_api_allows_local_frontend_cors(self):
        app = (ROOT / "api" / "app.py").read_text()

        self.assertIn("CORSMiddleware", app)
        self.assertIn("127.0.0.1:3017", app)
        self.assertIn('@app.get("/packets/build")', app)
        self.assertIn('@app.post("/packets/explain")', app)
