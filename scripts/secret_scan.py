from __future__ import annotations

import re
import sys
from pathlib import Path


SECRET_PATTERNS = [
    re.compile(r"\bsk-ant-api[0-9A-Za-z_-]{16,}\b"),
    re.compile(r"\bsk-proj-[0-9A-Za-z_-]{16,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{32,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(
        r"(?m)^\s*(?:export\s+)?(?:OPENAI|ANTHROPIC|RENDER|GITHUB|GOOGLE|AWS|DATABASE|POSTGRES)[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|URL)\s*=\s*['\"]?(?!<|your-|example|test|dummy|placeholder|\\$)[^'\"\s#]{12,}",
    ),
]
SUSPICIOUS_TRACKED_NAMES = [
    re.compile(r"(^|/)\.env($|\.)"),
    re.compile(r"\.(?:pem|key|p12|pfx)$", re.IGNORECASE),
    re.compile(r"(^|/)(?:id_rsa|credentials\.json|token\.json)$", re.IGNORECASE),
    re.compile(r"\.(?:sqlite|db|dump)$", re.IGNORECASE),
]
SKIP_DIRS = {".git", ".context", ".next", "node_modules", "__pycache__", ".venv", "venv", "env"}
SKIP_PREFIXES = {
    (Path("data") / "raw").parts,
    (Path("data") / "eval_runs").parts,
    (Path("data") / "normalized").parts,
    (Path("data") / "warehouse").parts,
}
SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".pdf",
    ".zip",
    ".gz",
    ".sqlite",
    ".db",
    ".pyc",
}


def main() -> int:
    root = Path(".")
    hits: list[str] = []
    hits.extend(_tracked_name_hits(root))
    for path in root.rglob("*"):
        if not path.is_file() or _skip(path):
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for pattern in SECRET_PATTERNS:
            match = pattern.search(text)
            if match:
                hits.append(f"{path}:{_line_number(text, match.start())}: possible secret")
    if hits:
        print("\n".join(hits), file=sys.stderr)
        return 1
    print("secret scan passed")
    return 0


def _tracked_name_hits(root: Path) -> list[str]:
    git_dir = root / ".git"
    if not git_dir.exists():
        return []
    try:
        import subprocess

        tracked = subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        return []
    hits = []
    for relative in tracked:
        if relative == ".env.example":
            continue
        if any(pattern.search(relative) for pattern in SUSPICIOUS_TRACKED_NAMES):
            hits.append(f"{relative}: tracked sensitive-looking filename")
    return hits


def _skip(path: Path) -> bool:
    path_parts = path.parts
    parts = set(path_parts)
    if parts & SKIP_DIRS:
        return True
    for prefix in SKIP_PREFIXES:
        if path_parts[: len(prefix)] == prefix:
            return True
    return path.suffix.lower() in SKIP_SUFFIXES


def _line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


if __name__ == "__main__":
    raise SystemExit(main())
