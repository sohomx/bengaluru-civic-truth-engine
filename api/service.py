from __future__ import annotations

from pathlib import Path
from typing import Any

from civic_data.rag import DEFAULT_RAG_INDEX_NAME, ask_rag, load_rag_index
from civic_data.truth import build_place_truth


class CivicMemoryService:
    def __init__(
        self,
        warehouse_root: Path | str = Path("data/normalized"),
        raw_root: Path | str = Path("data/raw"),
        index_path: Path | str | None = None,
    ) -> None:
        self.warehouse_root = Path(warehouse_root)
        self.raw_root = Path(raw_root)
        self.index_path = Path(index_path) if index_path else self.warehouse_root / DEFAULT_RAG_INDEX_NAME
        self.rag_index = load_rag_index(self.index_path)

    def place_truth(self, query: str) -> dict[str, Any]:
        return build_place_truth(query=query, warehouse_root=self.warehouse_root)

    def rag_answer(self, query: str) -> dict[str, Any]:
        return ask_rag(
            query=query,
            warehouse_root=self.warehouse_root,
            raw_root=self.raw_root,
            index_path=self.index_path,
            rag_index=self.rag_index,
        )
