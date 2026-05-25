"""LorcanaChamp Rules Kernel v2.

This package is intentionally independent from the legacy ``lorcana_bot``
runtime. v2 may read normalized Lorcanito card data, but v2 core modules must
not import legacy runtime modules from the v1 engine, effects, targeting, or
static-effect packages.

The public package surface exposes the v2 runtime shell, immutable card catalog,
Lorcanito-style static resources, and the current v2 match-state envelope.

Do not re-export the removed scaffold-era ``CardInstance`` shape here. v2 card
identity belongs in ``CardInstanceRecord`` / ``CardInstanceRegistry`` under
``MatchStaticResources``; mutable zone/meta state belongs in ``MatchState``.
"""

from .cards.catalog import CardCatalog
from .core.commands import CommandEnvelope, MoveInput, SanitizedCommandEnvelope, sanitize_command
from .core.context import (
    EventAPI,
    FrameworkReadAPI,
    FrameworkStateSnapshot,
    FrameworkWriteAPI,
    MoveDefinition,
    MoveEnumerationContext,
    MoveExecutionContext,
    MoveValidationContext,
    RuntimeActorRole,
    RuntimeLifecycleContext,
)
from .core.results import CommandFailure, CommandSuccess, RuntimeValidationResult
from .core.runtime import MatchRuntime
from .core.random import RandomAPI, create_random_api_for_ctx, create_random_api_for_state, seedrandom
from .core.runtime_config import (
    BoardSetupContext,
    InitialStatusConfig,
    MatchInitContext,
    MatchInitResult,
    MatchRuntimeConfig,
    Player,
    RuntimeFlowDefinition,
    RuntimeGameSegment,
    RuntimePhaseDefinition,
    RuntimeTurnDefinition,
    SetupArgs,
    compute_ruleset_hash,
    extract_initial_flow_state,
    generate_game_id,
    generate_match_id,
    initialize_match_state,
)
from .core.state import CtxPriority, CtxRandom, CtxStatus, LorcanaG, MatchState, TCGCtx, TurnMetadata
from .core.static_resources import (
    CardsMaps,
    CardInstanceRecord,
    CardInstanceRegistry,
    MatchStaticResources,
    StaticResourceRefs,
    create_cards_maps_from_static_resources,
    create_match_static_resources_from_cards_maps,
    get_static_resource_refs,
    validate_match_static_resources,
)
from .core.view_filter import (
    FilteredCtxRandom,
    FilteredMatchView,
    FilteredTCGCtx,
    FilteredZoneRuntimeRevealState,
    FilteredZoneRuntimeState,
    PublicZoneViewSummary,
    SecretLeakageCheck,
    ViewRoleContext,
    filter_match_view,
    get_public_zone_summary,
    verify_no_secret_leakage,
)
from .core.zones import ZoneOperations, ZoneRef, create_zone_operations

__all__ = [
    "CardCatalog",
    "CommandEnvelope",
    "CommandFailure",
    "CommandSuccess",
    "CardsMaps",
    "CardInstanceRecord",
    "CardInstanceRegistry",
    "CtxPriority",
    "CtxRandom",
    "CtxStatus",
    "FilteredCtxRandom",
    "FilteredMatchView",
    "FilteredTCGCtx",
    "FilteredZoneRuntimeRevealState",
    "FilteredZoneRuntimeState",
    "EventAPI",
    "LorcanaG",
    "MatchRuntime",
    "MatchState",
    "MatchStaticResources",
    "MoveDefinition",
    "MoveEnumerationContext",
    "MoveExecutionContext",
    "MoveInput",
    "MoveValidationContext",
    "PublicZoneViewSummary",
    "RandomAPI",
    "BoardSetupContext",
    "InitialStatusConfig",
    "MatchInitContext",
    "MatchInitResult",
    "MatchRuntimeConfig",
    "Player",
    "RuntimeFlowDefinition",
    "RuntimeGameSegment",
    "RuntimePhaseDefinition",
    "RuntimeTurnDefinition",
    "RuntimeActorRole",
    "RuntimeLifecycleContext",
    "RuntimeValidationResult",
    "SanitizedCommandEnvelope",
    "SetupArgs",
    "SecretLeakageCheck",
    "TCGCtx",
    "TurnMetadata",
    "ViewRoleContext",
    "ZoneOperations",
    "ZoneRef",
    "FrameworkReadAPI",
    "FrameworkStateSnapshot",
    "FrameworkWriteAPI",
    "StaticResourceRefs",
    "compute_ruleset_hash",
    "create_cards_maps_from_static_resources",
    "create_match_static_resources_from_cards_maps",
    "create_random_api_for_ctx",
    "create_random_api_for_state",
    "create_zone_operations",
    "filter_match_view",
    "extract_initial_flow_state",
    "generate_game_id",
    "generate_match_id",
    "get_public_zone_summary",
    "get_static_resource_refs",
    "initialize_match_state",
    "seedrandom",
    "sanitize_command",
    "verify_no_secret_leakage",
    "validate_match_static_resources",
]
