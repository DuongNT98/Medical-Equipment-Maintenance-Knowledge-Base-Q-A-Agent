"""AgentCore Platform v1.0 — HCR-C2-015 equipment inventory lookup"""

# Deterministic, no-side-effect domain service. Called by EquipmentLookupNode
# (inner subgraph). No agenticstar imports; no external network calls here —
# a hospital deployment injects a real inventory backend (per-manufacturer
# equipment master) at construction time; this default is an in-memory
# reference dataset used for local dev/testing.

from __future__ import annotations

from typing import Any

# Reference equipment inventory — a real deployment overrides this via the
# constructor with the hospital's per-manufacturer equipment master dataset.
_DEFAULT_INVENTORY: dict[str, dict[str, Any]] = {
    "VENT-3000": {
        "equipment_id": "EQ-VENT-3000-001",
        "kb_namespace": "manufacturer_a/vent-3000",
        "manufacturer": "Manufacturer A",
    },
    "INFUSION-PUMP-X1": {
        "equipment_id": "EQ-PUMP-X1-014",
        "kb_namespace": "manufacturer_b/infusion-pump-x1",
        "manufacturer": "Manufacturer B",
    },
    "DIALYSIS-D200": {
        "equipment_id": "EQ-DIALYSIS-D200-007",
        "kb_namespace": "manufacturer_c/dialysis-d200",
        "manufacturer": "Manufacturer C",
    },
}


class EquipmentInventoryService:
    """Validates an equipment model against the maintained inventory."""

    def __init__(self, inventory: dict[str, dict[str, Any]] | None = None) -> None:
        self._inventory = inventory if inventory is not None else _DEFAULT_INVENTORY

    def lookup(self, equipment_model: str) -> dict[str, Any] | None:
        """Return the inventory record for equipment_model, or None if unknown."""
        if not equipment_model:
            return None
        return self._inventory.get(equipment_model.strip().upper())
