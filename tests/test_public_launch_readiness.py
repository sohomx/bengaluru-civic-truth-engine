import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PublicLaunchReadinessTests(unittest.TestCase):
    def test_public_repo_hygiene_files_exist(self):
        required_paths = [
            "LICENSE",
            "SECURITY.md",
            "docs/public-launch.md",
            "web/public/.nojekyll",
            ".github/workflows/pages.yml",
        ]

        for relative_path in required_paths:
            with self.subTest(path=relative_path):
                self.assertTrue((ROOT / relative_path).exists())

    def test_next_config_has_github_pages_static_export_mode(self):
        config = (ROOT / "web" / "next.config.mjs").read_text()

        self.assertIn("GITHUB_PAGES", config)
        self.assertIn('output: "export"', config)
        self.assertIn("basePath", config)
        self.assertIn("assetPrefix", config)
        self.assertIn("images", config)
        self.assertIn("unoptimized: true", config)

    def test_pages_workflow_deploys_static_export_artifact(self):
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text()

        self.assertIn("actions/configure-pages", workflow)
        self.assertIn("actions/upload-pages-artifact", workflow)
        self.assertIn("actions/deploy-pages", workflow)
        self.assertIn("GITHUB_PAGES: \"true\"", workflow)
        self.assertIn("path: web/out", workflow)
        self.assertIn("npm run build", workflow)

    def test_no_personal_absolute_paths_in_tracked_public_files(self):
        home_prefix = "/" + "Users" + "/" + "sohom"
        var_folders_prefix = "/" + "var" + "/" + "folders"
        private_var_prefix = "/" + "private" + "/" + "var"
        forbidden = [
            re.compile(re.escape(home_prefix) + r"\b"),
            re.compile(re.escape(var_folders_prefix) + r"\b"),
            re.compile(re.escape(private_var_prefix) + r"\b"),
        ]

        tracked = subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()

        for relative in tracked:
            path = ROOT / relative
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            for pattern in forbidden:
                with self.subTest(path=relative, pattern=pattern.pattern):
                    self.assertIsNone(pattern.search(text))
