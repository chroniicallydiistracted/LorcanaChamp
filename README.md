# Lorcana Core Constructed Bot Player

A Python implementation scaffold for a Disney Lorcana Core Constructed bot player.

This repository prioritizes correctness architecture over premature model complexity:

1. deterministic rules engine
2. legal-action generation
3. baseline bots
4. ML-ready environment
5. tests that validate engine behavior
6. card-data layer that can be replaced with a licensed/user-provided database

## Current status

Implemented:

- 2-player game state
- deck validation helper for Core Constructed constraints
- initial hand draw
- first-player opening-turn draw handling by setup/start-turn model
- once-per-turn inking
- ink payment
- playing characters
- playing simple actions
- questing
- challenge legality
- simultaneous challenge damage
- banishing characters and locations
- location movement by paying move cost
- location lore gain on turn start
- location challenge damage
- Evasive challenge restriction
- Rush challenge exception while drying
- Bodyguard target restriction, including location challenge blocking
- Ward target filtering for opposing simple effects
- Resist damage reduction for simple damage events
- basic action effects:
  - draw
  - gain lore
  - deal damage to target
- win by lore threshold
- conservative deck-out handling
- bag/trigger placeholder hook
- random, greedy, heuristic, and linear-policy bots
- gym-like self-play environment
- tiny evolutionary trainer for the linear policy bot
- hidden-safe JSONL decision trace exporter for imitation learning
- pytest suite

Not yet fully implemented:

- official complete card database
- all individual card scripts
- full official bag ordering choices
- replacement/prevention effects
- Singer/Song rules
- Shift rules
- Support, Resist, Ward, Reckless edge cases beyond simple Reckless quest block
- full location-specific static/triggered interactions beyond movement, lore gain, and challenge damage
- mulligan policy
- tournament match structure
- sideboarding if a future format requires it
- neural PPO/AlphaZero training

## Why card data is demo-only

The included `data/demo_cards.json` is non-official placeholder card data for engine testing. Replace it with a licensed or user-provided card database before attempting full real-card play.

Official rules and tournament documents should be treated as the authority:

- https://www.disneylorcana.com/en-GB/resources

## Install

```bash
cd lorcana-core-bot
python -m venv .venv
source .venv/bin/activate
pip install -e . pytest
```

## Run tests

```bash
pytest -q
```

Expected result after the current integration pass:

```text
49 passed
```

## Run a demo game

```bash
python -m lorcana_bot.cli --bot0 heuristic --bot1 greedy --seed 11 --max-actions 200
```

Example output:

```text
GameResult(winner=0, turns=11, final_lore=(20, 10), reason='opponent_reached_lore_threshold', action_count=59)
```

## Export decision traces

```bash
python scripts/export_decision_traces.py --games 10 --out traces.jsonl
```

This writes legal-action candidate rows for supervised imitation or offline ranker training.

## Train the demo linear policy

```bash
python scripts/train_linear_policy.py --generations 4 --population 8 --games-per-candidate 4 --seed 3 --out linear_policy_result.json
```

This is a smoke trainer. It validates the full action-mask/self-play/evaluation loop. It is not intended to be the final high-strength model.

## Engine usage

```python
from lorcana_bot.cards import load_demo_database, make_demo_deck
from lorcana_bot.engine import GameEngine, GameRunner
from lorcana_bot.bots import HeuristicBot, GreedyLoreBot

db = load_demo_database()
engine = GameEngine(db)
state = engine.setup_game([
    make_demo_deck(size=60),
    make_demo_deck(size=60),
], seed=7)

result = GameRunner(engine).play(state, (HeuristicBot(), GreedyLoreBot()))
print(result)
```

## Bot contract

Bots receive observations and legal actions. They return an index into the legal-action list.

```python
class Bot:
    def choose_action(self, observation, legal_actions, engine) -> int:
        ...
```

Bots do not construct arbitrary moves. The engine owns legality.

## Next development priorities

1. Add a real card database importer.
2. Add declarative card scripting coverage by set.
3. Expand rules tests with official examples/rulings.
4. Implement full bag ordering and player choice prompts.
5. Add mulligan state and policy.
6. Add neural action scorer with card embeddings.
7. Add PPO self-play training.
8. Add MCTS-guided policy/value training after the simulator is faster.
