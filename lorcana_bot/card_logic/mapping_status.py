from __future__ import annotations


class MappingStatus:
    RAW_PRESERVED = "raw_preserved"
    STRUCTURALLY_MAPPED = "structurally_mapped"
    PARTIALLY_MAPPED = "partially_mapped"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class ExecutionStatus:
    EXECUTABLE = "executable"
    MAPPED_NOT_EXECUTABLE = "mapped_not_executable"
    CLASSIFIED_ONLY = "classified_only"
    UNSUPPORTED_ENGINE_MECHANIC = "unsupported_engine_mechanic"
    UNSUPPORTED_TARGETING = "unsupported_targeting"
    UNSUPPORTED_CONDITION = "unsupported_condition"
    UNSUPPORTED_COST = "unsupported_cost"
    UNSUPPORTED_CHOICE = "unsupported_choice"
    UNSUPPORTED_STATIC_EFFECT = "unsupported_static_effect"
    UNSUPPORTED_REPLACEMENT_EFFECT = "unsupported_replacement_effect"
    UNSUPPORTED_TRIGGER = "unsupported_trigger"
    UNKNOWN = "unknown"

