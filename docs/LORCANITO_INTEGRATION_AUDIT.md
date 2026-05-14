# Lorcanito Source Integration Audit

## Current decision

Use the Python project as the local ML/bot sandbox, but keep the Lorcanito source under `references/lorcana-simulator` as the rule-engine reference model.

The Python bot now mirrors the most important Lorcanito engine boundary:

```text
engine enumerates legal actions -> bot ranks legal actions -> engine executes selected action
```

The bot must not construct arbitrary moves.

## Reference source paths

High-value Lorcanito paths now included in the archive:

```text
references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/
references/lorcana-simulator/packages/lorcana/lorcana-engine/src/automation/
references/lorcana-simulator/packages/lorcana/lorcana-cards/src/cards/
references/lorcana-simulator/packages/lorcana/lorcana-cards/src/data/
```

Useful matching concepts:

```text
moveCharacterToLocation -> ACTION_MOVE_TO_LOCATION
challenge vs locations -> ACTION_CHALLENGE with location target
location lore at turn start -> EVENT_LOCATION_LORE_GAINED
Ward target filter -> target enumeration restriction
Resist damage reduction -> damage finalization hook
Decision trace export -> supervised/imitation training data
```

## Implemented from this pass

```text
- character movement to friendly locations
- movement cost payment
- exerted character can move to a location
- location lore gain when that player's turn starts
- locations are challengeable without being exerted
- locations take challenge damage and banish at willpower damage
- locations do not deal return challenge damage
- Bodyguard blocks location challenges when a legal bodyguard exists
- Ward blocks opposing effect targeting but not challenges
- Resist reduces challenge and action-effect damage
- move-to-location added to bot scoring and ML feature action type
- hidden-safe decision trace exporter added
```

## Remaining deltas versus Lorcanito

```text
- full structured card effect resolver
- bag ordering/choice resolution
- activated abilities
- shift/sing/sing-together
- support
- challenger/evasive edge cases from static effects
- replacement/prevention effects
- complex targeting families
- static continuous effects
- full location/player/character restrictions
- full deck-aware strategy registry
- neural candidate scorer
```

## ML direction

Use `lorcana_bot.traces.rollout_with_traces` and `scripts/export_decision_traces.py` to generate JSONL rows with:

```text
- acting player
- public/fair observation summary
- legal action candidates
- selected action index
- selected action summary
```

This is now suitable for supervised imitation of heuristic bots before PPO/self-play.
