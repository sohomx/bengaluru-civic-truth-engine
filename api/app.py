from __future__ import annotations

import os
from pathlib import Path

from civic_data import __version__
from api.service import CivicMemoryService

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
except ImportError as exc:  # pragma: no cover - exercised only when serving the API.
    raise RuntimeError(
        "FastAPI is required to run the web API. Install project dependencies first."
    ) from exc


def create_app(
    warehouse_root: Path | str | None = None,
    raw_root: Path | str | None = None,
    index_path: Path | str | None = None,
) -> FastAPI:
    root = Path(warehouse_root or os.environ.get("CIVIC_WAREHOUSE_ROOT", "data/normalized"))
    raw = Path(raw_root or os.environ.get("CIVIC_RAW_ROOT", "data/raw"))
    index = index_path or os.environ.get("CIVIC_RAG_INDEX")
    service = CivicMemoryService(warehouse_root=root, raw_root=raw, index_path=index)
    app = FastAPI(title="Bengaluru Civic Truth Engine")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3001",
            "http://127.0.0.1:3017",
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:3017",
        ],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/version")
    def version() -> dict[str, str]:
        return {"name": "bengaluru-civic-truth-engine", "version": __version__}

    @app.get("/places/search")
    def places_search(q: str) -> dict[str, object]:
        truth = service.place_truth(q)
        return {
            "query": truth["query"],
            "normalized_query": truth["normalized_query"],
            "old_bbmp_candidates": truth["ward_context"]["old_bbmp_candidates"],
            "new_gba_candidates": truth["ward_context"]["new_gba_candidates"],
            "area_match_candidates": truth["ward_context"]["area_match_candidates"],
        }

    @app.get("/places/truth")
    def places_truth(q: str) -> dict[str, object]:
        if not q.strip():
            raise HTTPException(status_code=400, detail="q must not be empty")
        return service.place_truth(q)

    @app.get("/rag/ask")
    def rag_ask(q: str) -> dict[str, object]:
        if not q.strip():
            raise HTTPException(status_code=400, detail="q must not be empty")
        return service.rag_answer(q)

    return app


app = create_app()
