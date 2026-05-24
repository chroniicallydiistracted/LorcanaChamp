# LorcanaChamp Rules Kernel v2 — Dependency Rules

## Forbidden Direct Imports

No file under `lorcana_engine_v2/` may import:

```text
lorcana_bot.engine
lorcana_bot.effects
lorcana_bot.static_effects
lorcana_bot.targeting
lorcana_bot.replacement_effects
lorcana_bot.triggers
lorcana_bot.pending_effects
```

## Adapter Exception

Files under `lorcana_engine_v2/adapters/` may eventually understand v1 shapes,
but should still avoid automatic runtime imports where possible.

## Source of Truth

Lorcanito source is the source of truth for:

```text
game model
state projection
move flow
target resolution
static materialization
condition evaluation
amount resolution
effect resolution
trigger/bag/replacement flow
```

v1 LorcanaChamp source is reference only.
