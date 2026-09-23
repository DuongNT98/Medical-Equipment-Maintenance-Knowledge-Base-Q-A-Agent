"""AgentCore Platform v1.0 — HCR-C2-015 equipment manual KB retrieval"""

# Deterministic, no-side-effect domain service (VectorRAG pattern: retrieval
# without an LLM in this hop). Called by ManualKBRetrieveNode (inner
# subgraph). A hospital deployment injects a real vector-store-backed
# manual KB (per-manufacturer equipment manuals) at construction time; this
# default is an in-memory reference dataset covering the reference
# equipment inventory used for local dev/testing.

from __future__ import annotations

from typing import Any

_DEFAULT_MANUALS: dict[str, dict[str, dict[str, Any]]] = {
    "manufacturer_a/vent-3000": {
        "quarterly_inspection": {
            "procedure_raw": [
                "Power down the ventilator and disconnect from the patient circuit.",
                "Inspect the air filter housing for particulate buildup; replace filter if discolored.",
                "Verify inspiratory/expiratory valve seating and check for cracks in tubing.",
                "Run the built-in self-test (BIST) and record the pass/fail code.",
            ],
            "tools_required": ["Phillips screwdriver", "filter replacement kit", "BIST calibration key"],
            "safety_warnings": [
                "WARNING: Do not perform this inspection while the ventilator is connected to a patient.",
                "WARNING: Disconnect mains power before opening the filter housing to avoid electric shock.",
            ],
            "kb_source_ref": "manufacturer_a/vent-3000/manual-v4#sec-6.2-quarterly",
        },
    },
    "manufacturer_b/infusion-pump-x1": {
        "battery_replacement": {
            "procedure_raw": [
                "Confirm the pump is not actively infusing before starting battery replacement.",
                "Slide open the battery compartment latch on the rear panel.",
                "Remove the depleted battery pack and insert the replacement, matching polarity markers.",
                "Close the compartment and run the power-on self-test before returning to service.",
            ],
            "tools_required": ["manufacturer-approved battery pack", "anti-static wrist strap"],
            "safety_warnings": [
                "WARNING: Never replace the battery while an infusion is in progress — stop the pump first.",
                "CAUTION: Use only manufacturer-approved battery packs; substitutes can cause thermal runaway.",
            ],
            "kb_source_ref": "manufacturer_b/infusion-pump-x1/manual-v2#sec-4.1-battery",
        },
    },
    "manufacturer_c/dialysis-d200": {
        "disinfection_cycle": {
            "procedure_raw": [
                "Drain the dialysate circuit fully before starting the disinfection cycle.",
                "Load the disinfectant cartridge and select the standard thermal-chemical program.",
                "Confirm the cycle completion indicator before reconnecting patient lines.",
            ],
            "tools_required": ["disinfectant cartridge (manufacturer-approved)", "circuit drain kit"],
            "safety_warnings": [
                "WARNING: Do not connect a patient line until the disinfection cycle reports COMPLETE.",
                "WARNING: Disinfectant concentrate is corrosive — wear gloves and eye protection.",
            ],
            "kb_source_ref": "manufacturer_c/dialysis-d200/manual-v3#sec-8.0-disinfection",
        },
    },
}


class ManualKBService:
    """Retrieves procedure / tools / safety-warning sections from the
    per-manufacturer equipment manual KB for a given (kb_namespace,
    maintenance_task) pair.
    """

    def __init__(self, manuals: dict[str, dict[str, dict[str, Any]]] | None = None) -> None:
        self._manuals = manuals if manuals is not None else _DEFAULT_MANUALS

    def retrieve(self, kb_namespace: str, maintenance_task: str) -> dict[str, Any] | None:
        """Return the manual section dict, or None if not found in the KB."""
        if not kb_namespace or not maintenance_task:
            return None
        namespace_entries = self._manuals.get(kb_namespace)
        if not namespace_entries:
            return None
        return namespace_entries.get(maintenance_task.strip().lower())
