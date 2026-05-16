# TECHNICAL IMPLEMENTATION BRIEF 2 — Enumerate Legal Actions for Special Pending Requirements

Goal:
Update `GameEngine.legal_actions()` so special pending requirement kinds produce actionable `ACTION_RESOLVE_PENDING_EFFECT` actions instead of a generic action with no required input.

Do not modify `_apply_resolve_pending_effect()` in this brief.
Do not modify `pending_effects.py` in this brief.

---

### 1. Current Incorrect Code

* **File Path:** `lorcana_bot/engine.py`
* **Line Range:** `Lines 248-295`
* **Snippet:**
```python
                if pe.optional and pe.accepted is None:
                    # Optional effect - can accept or decline
                    actions.append(Action(
                        ACTION_RESOLVE_PENDING_EFFECT,
                        actor=player,
                        source=pe.source_id,
                        choice={"pending_effect_id": pe.id, "accept": True}
                    ))
                    actions.append(Action(
                        ACTION_RESOLVE_PENDING_EFFECT,
                        actor=player,
                        source=pe.source_id,
                        choice={"pending_effect_id": pe.id, "accept": False}
                    ))
                elif pe.requires_target_input and requirement is not None:
                    # Target selection required
                    valid_targets = get_valid_targets_for_requirement(state, requirement, player, self)
                    for target in valid_targets:
                        actions.append(Action(
                            ACTION_RESOLVE_PENDING_EFFECT,
                            actor=player,
                            source=pe.source_id,
                            target=target,
                            choice={"pending_effect_id": pe.id}
                        ))
                elif pe.requires_choice_input:
                    # Choice index selection required
                    for choice_idx in range(len(pe.choice_options)):
                        actions.append(Action(
                            ACTION_RESOLVE_PENDING_EFFECT,
                            actor=player,
                            source=pe.source_id,
                            choice={"pending_effect_id": pe.id, "choice_index": choice_idx}
                        ))
                else:
                    # No input required, just resolve
                    actions.append(Action(
                        ACTION_RESOLVE_PENDING_EFFECT,
                        actor=player,
                        source=pe.source_id,
                        choice={"pending_effect_id": pe.id}
                    ))

                actions.append(Action(ACTION_CONCEDE, actor=player))
                return actions
```

### 2. Expected Code (The Solution)

* **Target State:**
```python
                requirement_kind = (pe.raw or {}).get("requirement_kind")
                raw_requirement = (pe.raw or {}).get("requirement")

                if pe.optional and pe.accepted is None:
                    # Optional effect - can accept or decline
                    actions.append(Action(
                        ACTION_RESOLVE_PENDING_EFFECT,
                        actor=player,
                        source=pe.source_id,
                        choice={"pending_effect_id": pe.id, "accept": True}
                    ))
                    actions.append(Action(
                        ACTION_RESOLVE_PENDING_EFFECT,
                        actor=player,
                        source=pe.source_id,
                        choice={"pending_effect_id": pe.id, "accept": False}
                    ))
                elif requirement_kind == "scry_ordering":
                    candidate_ids = tuple(getattr(raw_requirement, "candidate_ids", ()))
                    actions.append(Action(
                        ACTION_RESOLVE_PENDING_EFFECT,
                        actor=player,
                        source=pe.source_id,
                        choice={
                            "pending_effect_id": pe.id,
                            "top_cards": candidate_ids,
                            "bottom_cards": (),
                        }
                    ))
                elif requirement_kind == "search_selection":
                    candidate_ids = tuple(getattr(raw_requirement, "candidate_ids", ()) or pe.choice_options)
                    for selected_card_id in candidate_ids:
                        actions.append(Action(
                            ACTION_RESOLVE_PENDING_EFFECT,
                            actor=player,
                            source=pe.source_id,
                            choice={
                                "pending_effect_id": pe.id,
                                "selected_card_id": selected_card_id,
                            }
                        ))
                elif requirement_kind == "reveal_routing":
                    fixed_destination = getattr(raw_requirement, "destination", None)
                    destination_options = tuple(getattr(raw_requirement, "destination_options", ()) or pe.choice_options)
                    if fixed_destination:
                        actions.append(Action(
                            ACTION_RESOLVE_PENDING_EFFECT,
                            actor=player,
                            source=pe.source_id,
                            choice={
                                "pending_effect_id": pe.id,
                                "destination": fixed_destination,
                            }
                        ))
                    else:
                        for destination in destination_options:
                            actions.append(Action(
                                ACTION_RESOLVE_PENDING_EFFECT,
                                actor=player,
                                source=pe.source_id,
                                choice={
                                    "pending_effect_id": pe.id,
                                    "destination": destination,
                                }
                            ))
                elif requirement_kind == "named_card":
                    valid_names = tuple(getattr(raw_requirement, "valid_card_def_ids", ()) or pe.choice_options)
                    for named_card in valid_names:
                        actions.append(Action(
                            ACTION_RESOLVE_PENDING_EFFECT,
                            actor=player,
                            source=pe.source_id,
                            choice={
                                "pending_effect_id": pe.id,
                                "named_card": named_card,
                            }
                        ))
                elif requirement_kind == "destination":
                    destination_options = tuple(
                        (pe.raw or {}).get("destination_options")
                        or getattr(raw_requirement, "destination_options", ())
                        or getattr(raw_requirement, "options", ())
                        or pe.choice_options
                    )
                    for destination in destination_options:
                        actions.append(Action(
                            ACTION_RESOLVE_PENDING_EFFECT,
                            actor=player,
                            source=pe.source_id,
                            choice={
                                "pending_effect_id": pe.id,
                                "destination": destination,
                            }
                        ))
                elif pe.requires_target_input and requirement is not None:
                    # Target selection required
                    valid_targets = get_valid_targets_for_requirement(state, requirement, player, self)
                    for target in valid_targets:
                        actions.append(Action(
                            ACTION_RESOLVE_PENDING_EFFECT,
                            actor=player,
                            source=pe.source_id,
                            target=target,
                            choice={"pending_effect_id": pe.id}
                        ))
                elif pe.requires_choice_input:
                    # Choice index selection required
                    for choice_idx in range(len(pe.choice_options)):
                        actions.append(Action(
                            ACTION_RESOLVE_PENDING_EFFECT,
                            actor=player,
                            source=pe.source_id,
                            choice={"pending_effect_id": pe.id, "choice_index": choice_idx}
                        ))
                else:
                    # No input required, just resolve
                    actions.append(Action(
                        ACTION_RESOLVE_PENDING_EFFECT,
                        actor=player,
                        source=pe.source_id,
                        choice={"pending_effect_id": pe.id}
                    ))

                actions.append(Action(ACTION_CONCEDE, actor=player))
                return actions
```

### 3. Fixes Needed

* **Action:** `REPLACE`
* **Delta Description:** Replace the pending-effect legal action branch with a `requirement_kind`-aware branch. Scry must emit a default legal ordering action, search must emit one action per candidate, reveal routing must emit fixed or destination-option actions, named-card must emit one action per valid name, and destination must emit one action per destination option. Existing optional/target/choice/generic behavior must remain.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `packages/lorcana/lorcana-engine/src/available-moves.ts`
* **Line Range:** `Available pending resolution move generation sections`
* **Logic Context:**
```typescript
// Available moves expose only legal pending-resolution inputs. If a pending
// effect needs a choice, target, named card, route, or ordering, the move
// carries that specific resolution input.
type PendingResolutionMove = {
  type: "resolvePendingAction";
  pendingEffectId: string;
  resolutionInput: Record<string, unknown>;
};
```

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest -q
```

Manual checks:
```bash
grep -n "requirement_kind == \"scry_ordering\"" lorcana_bot/engine.py
grep -n "selected_card_id" lorcana_bot/engine.py
grep -n "named_card" lorcana_bot/engine.py
```

Expected:
- Legal actions for scry include top_cards/bottom_cards.
- Legal actions for search include selected_card_id.
- Legal actions for reveal routing include destination.
- Existing target/choice pending effect actions still exist.

### 6. Final Response Requirements

The implementation agent must report:
1. Files changed.
2. Requirement kinds now handled in `legal_actions()`.
3. Whether existing optional/target/choice fallback behavior remains.
4. Exact pytest commands run and results.
5. Confirmation that `_apply_resolve_pending_effect()` was not modified.
