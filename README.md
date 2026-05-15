# LorcanaChamp — Disney Lorcana Bot Player

A Python rules-valid bot engine for Disney Lorcana with automation, deck management, and ML-ready training pipelines.

**Core architecture:** deterministic game engine → legal action enumeration → bot ranking → execution. Bots receive observations and legal actions; they never construct arbitrary moves.

## Quick Start

```bash
# Install
python -m venv .venv && source .venv/bin/activate
pip install -e . pytest

# Run tests
pytest -q

# Play a demo game
python -m lorcana_bot.cli --bot0 heuristic --bot1 greedy --seed 11 --max-actions 200

# Export decision traces for ML training
python scripts/export_decision_traces.py --games 10 --out traces.jsonl

# Train a linear policy
python scripts/train_linear_policy.py --generations 4 --population 8 --games-per-candidate 4 --seed 3
```

## Project Structure

```
lorcana_bot/
├── engine.py          # Core game engine, state management, action execution
├── state.py           # Game state data structures
├── actions.py         # Action definitions and execution
├── effects.py         # Effect resolution system
├── triggers.py        # Trigger detection and execution
├── costs.py           # Cost validation (ink, etc.)
├── conditions.py      # Condition evaluation
├── static_effects.py  # Static effect system (Evasive, Bodyguard, Ward, Resist, etc.)
├── pending_effects.py # Pending effect queue for sequential resolution
├── replacement_effects.py  # Replacement/prevention hook system
├── bots.py            # Bot implementations (RandomBot, GreedyBot, HeuristicBot)
├── env.py             # Gym-like RL environment for self-play training
├── training.py        # Training utilities
├── traces.py          # Decision trace export for imitation learning
├── automation/       # Action enumeration, validation, and strategy
├── card_logic/       # Card ability mapping and effect helpers
├── decks/            # Deck loading, validation, and real deck support
└── importers/        # Lorcanito source card import and mapping

data/
├── demo_cards.json    # Demo card database for engine testing
├── cards/setdata.*.json  # Official card data by set
├── lorcanito_extracted/  # Lorcanito source extraction with mapping reports
└── decks/             # Real deck suite for gauntlet testing

docs/
├── IMPLEMENTATION_STATUS.md  # Verified commands and test coverage
├── LORCANITO_INTEGRATION_AUDIT.md  # Reference model alignment
└── LORCANA_GAME_ENGINE_RULES_ONLY_SPEC.md  # Engine specification

scripts/
├── export_decision_traces.py   # Export JSONL training data
├── train_linear_policy.py      # Evolutionary policy trainer
├── extract_lorcanito_source_cards.py  # Source card extraction
├── run_real_deck_gauntlet.py   # Deck suite gauntlet testing
└── report_*.py                 # Various reporting scripts

tests/              # 9,700+ lines of pytest coverage
```

## Implemented Features

### Game Engine
- 2-player game state with turn management
- Deck validation for Core Constructed constraints
- Initial hand draw and first-player opening-turn draw
- Once-per-turn inking and ink payment
- Character play with dry/exert state
- Questing and lore accumulation
- Challenge mechanics (simultaneous damage, Evasive restriction, Bodyguard blocking)
- Location movement, lore gain, and challenge damage
- Location banish on willpower damage
- Banish mechanics (characters, locations, actions)
- Bodyguard target restriction (character and location challenges)
- Evasive challenge restriction
- Ward target filtering for opposing effects
- Resist damage reduction
- Scry, search, reveal, and deck routing effects
- Draw, lore gain, and damage action effects
- Win by lore threshold and deck-out handling
- Bag/trigger placeholder hooks
- Replacement/prevention effect system

### Card Data
- Demo card database for engine testing
- Lorcanito source card extraction with fidelity reports
- Card ability mapping coverage reports
- Official setdata support (Sets 1-12, Q1, Q2)
- Real deck loader with validation
- Deck resolver for card name mapping
- Deck mapping coverage reports
- Trigger blocker analysis reports
- Gauntlet testing for deck suites

### Automation System
- Legal action enumeration with candidate validation
- Actor resolution for trigger context
- Strategy registry (heuristic, greedy, linear-policy, ranked)
- Deck profiling utilities
- Move adapter for game state updates
- Target priority scoring

### ML/RL Support
- Decision trace export (legal action candidates, selected index, observation)
- Gym-like environment (`LorcanaEnv`) for self-play
- ML feature extraction (`ml_features.py`)
- Linear policy evolutionary trainer
- Ranked strategy with learned weights
- Hidden-safe JSONL format for supervised/imitation learning

## Not Yet Implemented

- Full structured card effect resolver for all abilities
- Bag ordering and player choice resolution for complex effects
- Activated abilities
- Shift, Singer/Song mechanics
- Support mechanics
- Challenger/Evasive edge cases beyond simple interactions
- Complex targeting families
- Full deck-aware strategy registry
- Neural action scorer with card embeddings
- Neural PPO/AlphaZero training

## Why Demo Card Data

The included `data/demo_cards.json` is non-official placeholder card data for engine testing. Replace it with a licensed or user-provided card database before attempting full real-card play.

Official rules and tournament documents:
- https://www.disneylorcana.com/en-GB/resources

## Bot Contract

Bots receive observations and legal actions. They return an index into the legal-action list:

```python
class Bot:
    def choose_action(self, observation, legal_actions, engine) -> int:
        ...
```

The engine owns legality. Bots do not construct arbitrary moves.

## Engine Usage

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

## Engine with Real Decks

```python
from lorcana_bot.importers.lorcanito_importer import LorcanitoImporter
from lorcana_bot.decks.deck_loader import load_real_deck
from lorcana_bot.decks.deck_validator import DeckValidator
from lorcana_bot.engine import GameEngine, GameRunner
from lorcana_bot.bots import HeuristicBot

# Load card database
importer = LorcanitoImporter()
db = importer.load_database()

# Load and validate a real deck
deck = load_real_deck("data/decks/real_core/your_deck.txt", db)
validator = DeckValidator()
if not validator.validate(deck, db):
    print("Invalid deck:", validator.errors)

# Play a game
engine = GameEngine(db)
state = engine.setup_game([deck, make_demo_deck(size=60)], seed=7)
result = GameRunner(engine).play(state, (HeuristicBot(), GreedyLoreBot()))
```

## Next Development Priorities

1. Add declarative card scripting coverage by set
2. Expand rules tests with official examples/rulings
3. Implement full bag ordering and player choice prompts
4. Add activated ability support
5. Add Shift and Singer/Song mechanics
6. Add neural action scorer with card embeddings
7. Add PPO self-play training
8. Add MCTS-guided policy/value training after simulator is faster