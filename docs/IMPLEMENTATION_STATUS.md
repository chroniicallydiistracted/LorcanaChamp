# Implementation Status

## Verified commands

```bash
cd /mnt/data/LorcanaChamp
pytest -q
```

Result:

```text
49 passed
```

```bash
python -m lorcana_bot.cli --bot0 heuristic --bot1 greedy --seed 11 --max-actions 200
```

Result:

```text
GameResult(winner=0, turns=11, final_lore=(20, 10), reason='opponent_reached_lore_threshold', action_count=59)
```

```bash
python scripts/train_linear_policy.py --generations 1 --population 2 --games-per-candidate 1 --seed 3 --out /mnt/data/linear_policy_result_v2.json
```

Result:

```text
TrainingResult(generations=1, best_score=0.963, weights=[0.25, 0.7, 1.4, 0.8, -0.4, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], evaluation=EvaluationResult(games=1, wins=1, losses=0, draws=0, win_rate=1.0, average_actions=37.0))
```

```bash
python scripts/export_decision_traces.py --games 1 --max-actions 10 --out /mnt/data/sample_traces.jsonl
```

Result:

```text
wrote 10 decision traces to /mnt/data/sample_traces.jsonl
```

## Test coverage

- deck validation
- official setdata loader
- initial draw
- turn transition draw
- once-per-turn inking
- ink payment
- character play/drying
- questing
- lore win
- challenge damage
- character banish
- location movement
- location lore gain
- location challenge damage
- location banish
- Bodyguard versus character and location targets
- Evasive
- Ward target filtering
- Resist damage reduction
- action damage effect
- bot legal index contract
- game runner completion
- env reset/step/rollout
- decision trace export
- linear trainer smoke test

## B4: Scry, Search, Reveal, and Deck Routing (MICRO PROMPT 05)

### Effect kinds implemented
- scry
- look_at_top
- reveal_top_card
- reveal_hand
- reveal_cards
- search_deck
- put_card_in_hand
- put_card_on_top
- put_card_on_bottom
- put_card_in_discard
- shuffle_deck
- name_a_card
- reveal_and_route

### Privacy rules enforced
- look_at_top emits private event with `private: True` flag
- reveal effects mark cards as revealed and emit public CARD_REVEALED events
- scry/search create pending effects for player input, no direct reveal

### Supported features
- Scry creates pending effect for ordering input
- Search deck creates pending effect for card selection
- Reveal top card marks card public and routes to destination
- Deck routing (top/bottom/hand) via put_card_* effects
- Deterministic shuffle using game seed

### Trigger blocker report updates
- scry_ordering requirement maps to scry_search_reveal work
- reveal_routing requirement maps to scry_search_reveal work
- named_card requirement maps to scry_search_reveal work
- New effect kinds in SUPPORTED_TRIGGER_ENGINE_EFFECT_KINDS
