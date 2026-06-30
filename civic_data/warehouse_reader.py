from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PACKET_INPUT_FILES = (
    "wards.json",
    "works.json",
    "payments.json",
    "complaint_channels.json",
    "contact_channels.json",
)


@dataclass(frozen=True)
class WarehouseCapabilities:
    packet_inputs_present: bool
    missing_packet_inputs: list[str]


@dataclass(frozen=True)
class NormalizedWarehouse:
    root: Path

    @classmethod
    def open(cls, root: Path | str) -> "NormalizedWarehouse":
        return cls(Path(root))

    def capabilities(self) -> WarehouseCapabilities:
        missing = [name for name in PACKET_INPUT_FILES if not (self.root / name).exists()]
        return WarehouseCapabilities(packet_inputs_present=not missing, missing_packet_inputs=missing)

    def load_wards(self) -> list[dict[str, Any]]:
        return self._read_json_list("wards.json")

    def load_old_new_ward_mappings(self) -> list[dict[str, Any]]:
        return self._read_json_list("old_new_ward_mappings.json")

    def load_works(self) -> list[dict[str, Any]]:
        return self._read_json_list("works.json")

    def load_payments(self) -> list[dict[str, Any]]:
        return self._read_json_list("payments.json")

    def load_complaint_channels(self) -> list[dict[str, Any]]:
        return self._read_json_list("complaint_channels.json")

    def load_contact_channels(self) -> list[dict[str, Any]]:
        return self._read_json_list("contact_channels.json")

    def _read_json_list(self, name: str) -> list[dict[str, Any]]:
        path = self.root / name
        if not path.exists():
            return []
        data = path.read_text()
        if not data.strip():
            return []
        parsed = json.loads(data)
        return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []
