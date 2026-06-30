from __future__ import annotations

import re
import sys
from pathlib import Path


SECRET_PATTERNS = [
    re.compile(r"\bsk-ant-api[0-9A-Za-z_-]{12,}\b"),
    re.compile(r"\bsk-proj-[0-9A-Za-z_-]{12,}\b"),
    re.compile(r"\bOPENAI_API_KEY\s*=\s*['\"]?sk-[0-9A-Za-z_-]{12,}"),
    re.compile(r"\bANTHROPIC_API_KEY\s*=\s*['\"]?sk-ant-[0-9A-Za-z_-]{12,}"),
]
SKIP_DIRS = {".git", ".context", ".next", "node_modules", "__pycache__"}
SKIP_PREFIXES = {(Path("data") / "raw").parts, (Path("data") / "eval_runs").parts}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".gz", ".sqlite", ".db"}


def main() -> int:
    root = Path(".")
    hits: list[str] = []
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
