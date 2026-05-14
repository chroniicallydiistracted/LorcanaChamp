# Lorcana Game Engine — Focused Rules, State, and Flow Specification

## Purpose

This document consolidates the gameplay-engine information previously sourced and turns it into a focused implementation reference for a Lorcana TCG rules engine.

This version intentionally excludes frontend layout, animation staging, visual rendering, and UI presentation details.

The focus is:

```text
game definitions
game instances
card instances
player state
turn flow
legal actions
game reducer logic
core rule automation
effect/ability model
trigger model
deck/format validation
AI decision hooks
manual override support
persistence/replay shape
```

## Source Boundary

The strongest extracted runtime source was the Duels.ink game-engine bundle. It exposed runtime card instance state, timer presets, hidden-card handling, player-game hydration, prompt/reveal/trigger structures, and per-card gameplay flags.

The official Disney Lorcana Unity app extraction was strongest for catalog, card, deck, ownership, and card-variant models. It did not expose a complete official duel engine.

The prior Lorcana Online technical specification provided the implementation direction for a local-first game engine.

This document does not claim to reproduce an official Ravensburger game engine. It defines a complete practical engine architecture using the sourced runtime models and the rules structure required for Lorcana gameplay.

---

# 1. Core Engine Philosophy

The rules engine should be:

```text
pure
deterministic
serializable
testable
UI-framework-independent
local-first
manual-override capable
incrementally automatable
```

The engine should not depend on Vue, Nuxt, browser DOM APIs, CSS, rendering, or component state.

All core game logic should live in framework-independent TypeScript modules.

Recommended root:

```text
lib/game/
```

The engine should expose two central functions:

```ts
canTakeAction(state, action, context): ValidationResult
applyAction(state, action, context): GameState
```

Hard rule:

```text
Every game action returns a new GameState.
No reducer mutates the existing state object.
```

---

# 2. Core IDs

```ts
export type GameId = string
export type PlayerId = string
export type CardDefinitionId = string
export type CardInstanceId = string
export type AbilityId = string
export type EffectId = string
export type TriggerId = string
```

Use `CardDefinitionId` for catalog/card database references.

Use `CardInstanceId` for physical copies inside a match.

A single card definition can have many card instances in the same game.

---

# 3. Static Card Definition

A static card definition is data from the catalog. It does not change during a game.

```ts
export type CardType =
  | 'character'
  | 'action'
  | 'song'
  | 'item'
  | 'location'

export type InkColor =
  | 'amber'
  | 'amethyst'
  | 'emerald'
  | 'ruby'
  | 'sapphire'
  | 'steel'

export type CardRarity =
  | 'common'
  | 'uncommon'
  | 'rare'
  | 'super'
  | 'legendary'
  | 'enchanted'
  | 'special'
  | 'epic'
  | 'iconic'

export type CardDefinition = {
  id: CardDefinitionId

  name: string
  title?: string
  fullName: string

  type: CardType
  subtypes: string[]

  colors: InkColor[]
  cost: number
  inkable: boolean

  strength?: number
  willpower?: number
  lore?: number
  moveCost?: number

  rarity: CardRarity

  rulesText?: string
  flavorText?: string

  abilities: AbilityDefinition[]

  deckBuildingId?: string
  deckBuildingLimit?: number

  setCode?: string
  collectorNumber?: string
}
```

## 3.1 Interpretation

The card definition is the immutable rule object.

Examples:

```text
Mickey Mouse - Brave Little Tailor
Ariel - Spectacular Singer
Friends On The Other Side
Magic Broom - Bucket Brigade
The Queen's Castle
```

A card instance copies this definition into the game but tracks runtime state separately.

---

# 4. Runtime Card Instance

A card instance represents a physical copy inside a specific match.

The Duels.ink runtime model confirmed that a card instance needs far more than a definition ID. It needs damage, exertion, temporary effects, flags for once-per-turn behavior, challenge history, location attachment, facedown state, cards-under state, and variant state.

```ts
export type CardVisibility =
  | 'public'
  | 'owner'
  | 'controller'
  | 'hidden'

export type PlayableCardInstance = {
  definitionId: CardDefinitionId
  instanceId: CardInstanceId

  ownerId: PlayerId
  controllerId: PlayerId

  zone: ZoneName
  visibility: CardVisibility

  damage: number
  exerted: boolean
  facedown: boolean

  justPlayed: boolean
  addedToInkThisTurn: boolean
  hasQuestedThisTurn: boolean

  locationInstanceId?: CardInstanceId

  appliedEffects: AppliedEffect[]
  temporaryAbilities: GrantedAbility[]

  cardsUnder: CardUnderEntry[]

  hasUsedBoostThisTurn: boolean
  receivedCardUnderThisTurn: boolean
  usedAbilitiesThisTurn: AbilityId[]

  lastDamageSource?: CardInstanceId | 'effect' | 'challenge'
  lastDamageWasChallenge: boolean
  wasChallengedThisTurn: boolean

  strengthFloor?: number
  strengthFloorSource?: string

  grantedClassifications: string[]

  variant?: CardVariantRef
}
```

## 4.1 Hidden cards under another card

```ts
export type HiddenCardUnder = {
  hidden: true
  instanceId: CardInstanceId
}

export type VisibleCardUnder = {
  hidden: false
  card: PlayableCardInstance
}

export type CardUnderEntry = HiddenCardUnder | VisibleCardUnder
```

## 4.2 Card variant reference

Variant is not rules-critical, but it matters for identifying the displayed physical card copy.

```ts
export type CardVariantType =
  | 'regular'
  | 'foiled'
  | 'starterFoil'

export type CardVariantRef = {
  variantType: CardVariantType
  variantId?: string
}
```

---

# 5. Zones

Zones are part of the engine state. This document does not cover visual zone layout.

```ts
export type ZoneName =
  | 'deck'
  | 'hand'
  | 'field'
  | 'items'
  | 'locations'
  | 'inkwell'
  | 'discard'
  | 'banished'
  | 'revealed'
  | 'removed'
```

## 5.1 Zone visibility defaults

```ts
export const DEFAULT_ZONE_VISIBILITY: Record<ZoneName, CardVisibility> = {
  deck: 'hidden',
  hand: 'owner',
  field: 'public',
  items: 'public',
  locations: 'public',
  inkwell: 'hidden',
  discard: 'public',
  banished: 'public',
  revealed: 'public',
  removed: 'public',
}
```

## 5.2 Inkwell card

The inkwell needs explicit hidden handling.

```ts
export type InkwellCard = {
  instanceId: CardInstanceId
  definitionId?: CardDefinitionId
  hidden: boolean
  ready: boolean
  addedThisTurn: boolean
}
```

The engine should not assume every inkwell card is visible.

---

# 6. Player Game State

```ts
export type PlayerGameState = {
  playerId: PlayerId
  name: string

  lore: number

  deck: PlayableCardInstance[]
  hand: PlayableCardInstance[]

  field: PlayableCardInstance[]
  items: PlayableCardInstance[]
  locations: PlayableCardInstance[]

  inkwell: InkwellCard[]

  discard: PlayableCardInstance[]
  banished: PlayableCardInstance[]
  revealed: PlayableCardInstance[]
  removed: PlayableCardInstance[]

  inkPlayedThisTurn: boolean

  hasKeptOpeningHand: boolean
  mulliganedCardIds: CardInstanceId[]

  turnFlags: PlayerTurnFlags
}
```

## 6.1 Player turn flags

```ts
export type PlayerTurnFlags = {
  drewForTurn: boolean
  playedInk: boolean
  passedTurn: boolean
  tookManualAction: boolean
}
```

---

# 7. Game State

```ts
export type GameFormat =
  | 'constructed'
  | 'sealed'
  | 'draft'
  | 'goldfish'
  | 'bot'
  | 'local'

export type GamePhase =
  | 'setup'
  | 'opening-hand'
  | 'mulligan'
  | 'start-turn'
  | 'main'
  | 'challenge'
  | 'effect-resolution'
  | 'end-turn'
  | 'game-over'

export type WinReason =
  | 'lore'
  | 'deckout'
  | 'concede'
  | 'manual'
  | 'forfeit'
  | 'unknown'

export type GameState = {
  gameId: GameId
  format: GameFormat
  seed: string

  phase: GamePhase
  turnNumber: number

  firstPlayerId: PlayerId
  activePlayerId: PlayerId
  priorityPlayerId?: PlayerId

  hasFirstPlayerSkippedFirstDraw: boolean

  players: Record<PlayerId, PlayerGameState>
  playerOrder: PlayerId[]

  stack: PendingEffect[]
  triggerBag: TriggeredAbility[]

  prompt?: PromptState

  gameLog: GameLogEntry[]

  winnerId?: PlayerId
  winReason?: WinReason
}
```

---

# 8. Game Setup Flow

## 8.1 Initial setup

```text
1. Create GameState.
2. Assign player order.
3. Assign first player.
4. Convert each decklist entry into PlayableCardInstance.
5. Shuffle each deck using deterministic seed.
6. Draw opening hands.
7. Enter mulligan phase.
```

## 8.2 Start game function

```ts
export function startGame(
  players: GameStartPlayer[],
  options: GameStartOptions,
  context: GameContext
): GameState
```

```ts
export type GameStartPlayer = {
  playerId: PlayerId
  name: string
  deck: DeckList
}

export type GameStartOptions = {
  gameId?: GameId
  seed?: string
  format: GameFormat
  firstPlayerId?: PlayerId
}
```

## 8.3 Opening hand

```text
Each player draws 7.
Each player may alter/mulligan their opening hand.
First player skips their first draw step.
```

Recommended mulligan state:

```ts
export type MulliganChoice = {
  playerId: PlayerId
  cardInstanceIds: CardInstanceId[]
  kept: boolean
}
```

---

# 9. Turn Structure

The initial automated engine should use this turn flow:

```text
Start Turn
  Ready Step
  Set Step
  Draw Step

Main Phase
  Player may take legal actions in any order:
    Ink one card
    Play cards
    Quest
    Challenge
    Activate abilities
    Move characters to locations
    Pass turn

End Turn
  Cleanup temporary until-end-of-turn effects
  Advance active player
```

## 9.1 Start turn

```ts
export function startTurn(state: GameState, playerId: PlayerId, context: GameContext): GameState
```

Effects:

```text
Set phase to start-turn.
Ready exerted cards controlled by active player.
Ready inkwell cards.
Clear turn flags on active player's cards.
Clear player turn flags.
Apply start-of-turn triggers.
Proceed to draw step.
```

## 9.2 Ready step

```text
Ready all exerted cards controlled by active player unless a continuous effect prevents readying.
Ready all available ink.
Clear per-turn card flags.
```

Card flags cleared:

```text
hasQuestedThisTurn
addedToInkThisTurn
wasChallengedThisTurn
lastDamageWasChallenge
lastDamageSource
hasUsedBoostThisTurn
receivedCardUnderThisTurn
usedAbilitiesThisTurn
```

## 9.3 Draw step

```text
Active player draws one card.
First player skips draw on their first turn.
If a player must draw and cannot because deck is empty, that player loses.
```

## 9.4 Main phase

The active player may perform any valid action until they pass.

## 9.5 End turn

```text
Remove until-end-of-turn effects.
Clear temporary abilities with end-of-turn duration.
Advance active player.
Increment turn number after all players have taken a turn.
Start next player's turn.
```

---

# 10. Game Actions

```ts
export type GameAction =
  | StartGameAction
  | MulliganAction
  | KeepHandAction
  | DrawAction
  | InkCardAction
  | PlayCardAction
  | PlaySongAction
  | QuestAction
  | ChallengeAction
  | ActivateAbilityAction
  | MoveToLocationAction
  | PassTurnAction
  | ConcedeAction
  | ResolvePromptAction
  | ResolveTriggerAction
  | ManualGameAction
```

## 10.1 Action definitions

```ts
export type StartGameAction = {
  type: 'START_GAME'
  seed?: string
}

export type MulliganAction = {
  type: 'MULLIGAN'
  playerId: PlayerId
  cardInstanceIds: CardInstanceId[]
}

export type KeepHandAction = {
  type: 'KEEP_HAND'
  playerId: PlayerId
}

export type DrawAction = {
  type: 'DRAW'
  playerId: PlayerId
  count: number
}

export type InkCardAction = {
  type: 'INK_CARD'
  playerId: PlayerId
  cardInstanceId: CardInstanceId
}

export type PlayCardAction = {
  type: 'PLAY_CARD'
  playerId: PlayerId
  cardInstanceId: CardInstanceId
  payment?: InkPayment
  targets?: TargetRef[]
}

export type PlaySongAction = {
  type: 'PLAY_SONG'
  playerId: PlayerId
  cardInstanceId: CardInstanceId
  singerInstanceId?: CardInstanceId
  payment?: InkPayment
  targets?: TargetRef[]
}

export type QuestAction = {
  type: 'QUEST'
  playerId: PlayerId
  characterInstanceId: CardInstanceId
}

export type ChallengeAction = {
  type: 'CHALLENGE'
  playerId: PlayerId
  attackerInstanceId: CardInstanceId
  defenderInstanceId: CardInstanceId
}

export type ActivateAbilityAction = {
  type: 'ACTIVATE_ABILITY'
  playerId: PlayerId
  sourceInstanceId: CardInstanceId
  abilityId: AbilityId
  payment?: AbilityPayment
  targets?: TargetRef[]
}

export type MoveToLocationAction = {
  type: 'MOVE_TO_LOCATION'
  playerId: PlayerId
  characterInstanceId: CardInstanceId
  locationInstanceId: CardInstanceId
  payment?: InkPayment
}

export type PassTurnAction = {
  type: 'PASS_TURN'
  playerId: PlayerId
}

export type ConcedeAction = {
  type: 'CONCEDE'
  playerId: PlayerId
}

export type ResolvePromptAction = {
  type: 'RESOLVE_PROMPT'
  playerId: PlayerId
  promptId: string
  choiceIds: string[]
}

export type ResolveTriggerAction = {
  type: 'RESOLVE_TRIGGER'
  playerId: PlayerId
  triggerId: TriggerId
}
```

---

# 11. Validation System

```ts
export type ValidationSeverity = 'error' | 'warning'

export type ValidationIssue = {
  code: string
  message: string
  severity: ValidationSeverity
}

export type ValidationResult = {
  valid: boolean
  issues: ValidationIssue[]
}
```

Main API:

```ts
export function canTakeAction(
  state: GameState,
  action: GameAction,
  context: GameContext
): ValidationResult
```

## 11.1 Game context

```ts
export type GameContext = {
  cardDb: Map<CardDefinitionId, CardDefinition>
  rng: SeededRng
  rules: RulesConfig
}
```

## 11.2 Rules config

```ts
export type RulesConfig = {
  loreToWin: number
  openingHandSize: number
  constructedMinDeckSize: number
  limitedMinDeckSize: number
  maxConstructedInkColors: number
  maxConstructedCopies: number
  allowManualOverride: boolean
  automateCardEffects: boolean
}
```

Recommended defaults:

```ts
export const DEFAULT_RULES_CONFIG: RulesConfig = {
  loreToWin: 20,
  openingHandSize: 7,
  constructedMinDeckSize: 60,
  limitedMinDeckSize: 40,
  maxConstructedInkColors: 2,
  maxConstructedCopies: 4,
  allowManualOverride: true,
  automateCardEffects: false,
}
```

---

# 12. Reducer System

```ts
export function applyAction(
  state: GameState,
  action: GameAction,
  context: GameContext
): GameState {
  const validation = canTakeAction(state, action, context)

  if (!validation.valid) {
    throw new InvalidGameActionError(action, validation)
  }

  switch (action.type) {
    case 'MULLIGAN':
      return applyMulligan(state, action, context)
    case 'KEEP_HAND':
      return applyKeepHand(state, action, context)
    case 'DRAW':
      return applyDraw(state, action, context)
    case 'INK_CARD':
      return applyInkCard(state, action, context)
    case 'PLAY_CARD':
      return applyPlayCard(state, action, context)
    case 'PLAY_SONG':
      return applyPlaySong(state, action, context)
    case 'QUEST':
      return applyQuest(state, action, context)
    case 'CHALLENGE':
      return applyChallenge(state, action, context)
    case 'ACTIVATE_ABILITY':
      return applyActivateAbility(state, action, context)
    case 'MOVE_TO_LOCATION':
      return applyMoveToLocation(state, action, context)
    case 'PASS_TURN':
      return applyPassTurn(state, action, context)
    case 'CONCEDE':
      return applyConcede(state, action, context)
    case 'RESOLVE_PROMPT':
      return applyResolvePrompt(state, action, context)
    case 'RESOLVE_TRIGGER':
      return applyResolveTrigger(state, action, context)
    default:
      return assertNever(action)
  }
}
```

---

# 13. Core Rule Logic

## 13.1 Mulligan / alter hand

Validation:

```text
Player must be in opening-hand/mulligan phase.
Player can only mulligan once according to chosen rules model.
Selected cards must be in that player's hand.
```

Application:

```text
Move selected cards from hand to deck.
Shuffle or place according to selected mulligan model.
Draw replacement cards.
Mark mulligan choice.
When both players keep/finish, begin first player's turn.
```

## 13.2 Draw

Validation:

```text
Player exists.
Count is positive.
If draw is required and deck is empty, player loses.
```

Application:

```text
Move top N cards from deck to hand.
If deck empties before required draw completes, set opponent as winner by deckout.
```

## 13.3 Ink card

Validation:

```text
Player is active player.
Game is in main phase.
Player has not already inked this turn.
Card is in player's hand.
Card is inkable unless effect allows otherwise.
```

Application:

```text
Remove card from hand.
Create inkwell entry.
Set hidden = true.
Set ready according to current rule/effect model.
Mark player.inkPlayedThisTurn = true.
Mark card/ink addedThisTurn = true.
Log action.
```

## 13.4 Pay ink

```ts
export type InkPayment = {
  exertedInkInstanceIds: CardInstanceId[]
  amount: number
}
```

Validation:

```text
Selected ink exists.
Selected ink belongs to player.
Selected ink is ready.
Selected ink count covers required cost after modifiers.
```

Application:

```text
Set selected ink ready = false.
Continue action resolution.
```

## 13.5 Play card

Validation:

```text
Player is active player.
Game is in main phase.
Card is in player's hand.
Player can pay card cost or alternate cost.
Targets are legal if required.
```

Application by type:

```text
Character:
  move hand -> field
  justPlayed = true
  exerted = false unless effect says otherwise
  process on-play triggers

Item:
  move hand -> items
  process on-play triggers

Location:
  move hand -> locations
  process on-play triggers

Action:
  resolve action effect
  move hand -> discard

Song:
  validate singer or payment
  resolve song effect
  move hand -> discard
```

## 13.6 Quest

Validation:

```text
Character belongs to active player.
Character is in field.
Character is ready.
Character is not justPlayed unless Rush/other effect permits.
Character has lore value greater than 0.
Character is not prevented from questing.
```

Application:

```text
Exert character.
Gain lore equal to current lore value.
Set hasQuestedThisTurn = true.
Process on-quest triggers.
Check lore win condition.
```

## 13.7 Challenge

Validation:

```text
Attacker belongs to active player.
Attacker is in field.
Attacker is ready.
Attacker can challenge.
Attacker is not justPlayed unless Rush/other effect permits.
Defender belongs to opponent.
Defender is in field or legal challenge zone.
Defender is exerted unless effect allows ready targets.
Evasive restriction is respected.
Bodyguard restriction is respected.
Ward/targeting restrictions are respected where relevant.
```

Application:

```text
Exert attacker.
Calculate attacker strength.
Calculate defender strength.
Apply attacker strength as damage to defender.
Apply defender strength as damage to attacker.
Set defender.wasChallengedThisTurn = true.
Set lastDamageWasChallenge = true on damaged cards.
Process challenge/damage triggers.
Banish any character with damage >= willpower after damage.
```

## 13.8 Activate ability

Validation:

```text
Source card exists and is controlled by player.
Ability exists on source card or is temporarily granted.
Player can pay ability cost.
Ability timing is legal.
Targets are legal.
Once-per-turn/used ability flags allow activation.
```

Application:

```text
Pay ability cost.
Mark ability as used if needed.
Resolve ability effects or create prompt.
Process resulting triggers.
```

## 13.9 Move to location

Validation:

```text
Character belongs to active player.
Character is in field.
Location is controlled by active player unless effect allows otherwise.
Player can pay move cost.
Character is not already at that location.
```

Application:

```text
Pay move cost.
Set character.locationInstanceId = locationInstanceId.
Process movement/location triggers.
```

## 13.10 Banish

```ts
export function banishCard(
  state: GameState,
  cardInstanceId: CardInstanceId,
  reason: BanishReason,
  context: GameContext
): GameState
```

Application:

```text
Move card to discard unless replacement effect changes destination.
Remove damage and temporary state.
Detach from location.
Handle cards under according to card/effect rules.
Process on-banish triggers.
```

## 13.11 Pass turn

Validation:

```text
Player is active player.
No mandatory prompt is unresolved.
No mandatory trigger is unresolved.
```

Application:

```text
Set phase to end-turn.
Expire until-end-of-turn effects.
Clear temporary abilities with end-of-turn duration.
Advance activePlayerId.
Increment turn number when appropriate.
Start next player's turn.
```

## 13.12 Concede

Application:

```text
Set opponent as winner.
Set winReason = concede.
Set phase = game-over.
Log concession.
```

---

# 14. Damage and Banish Rules

```ts
export type DamageEvent = {
  source?: CardInstanceId | 'effect' | 'challenge'
  target: CardInstanceId
  amount: number
  challengeDamage: boolean
}
```

## 14.1 Apply damage

```text
Apply resist/reduction modifiers.
Apply replacement effects.
Increase target.damage.
Set lastDamageSource.
Set lastDamageWasChallenge.
If damage >= current willpower, queue banish check.
```

## 14.2 Heal damage

```text
Reduce damage by amount.
Damage cannot go below 0.
```

## 14.3 Check banish

```text
Any character with damage greater than or equal to current willpower is banished.
Multiple banishes caused by the same action should be processed together where appropriate.
```

---

# 15. Effective Stats

The engine should never rely only on printed values during gameplay.

Use resolver functions:

```ts
export function getEffectiveStrength(
  state: GameState,
  card: PlayableCardInstance,
  context: GameContext
): number

export function getEffectiveWillpower(
  state: GameState,
  card: PlayableCardInstance,
  context: GameContext
): number

export function getEffectiveLore(
  state: GameState,
  card: PlayableCardInstance,
  context: GameContext
): number

export function getEffectiveCost(
  state: GameState,
  card: PlayableCardInstance,
  context: GameContext
): number

export function hasKeyword(
  state: GameState,
  card: PlayableCardInstance,
  keyword: LorcanaKeyword,
  context: GameContext
): boolean
```

These should account for:

```text
printed stats
damage
continuous effects
temporary modifiers
granted abilities
location effects
challenge-only modifiers
turn-duration effects
replacement effects
```

---

# 16. Ability Model

```ts
export type AbilityTiming =
  | 'static'
  | 'keyword'
  | 'activated'
  | 'triggered'
  | 'replacement'

export type AbilityDefinition = {
  id: AbilityId
  sourceCardId: CardDefinitionId
  timing: AbilityTiming
  name?: string
  text: string
  keyword?: LorcanaKeyword
  costs?: AbilityCost[]
  trigger?: TriggerCondition
  target?: TargetingRule
  effects: EffectDefinition[]
  optional?: boolean
}
```

## 16.1 Keywords

```ts
export type LorcanaKeyword =
  | 'Evasive'
  | 'Bodyguard'
  | 'Resist'
  | 'Challenger'
  | 'Support'
  | 'Ward'
  | 'Rush'
  | 'Singer'
  | 'Shift'
```

## 16.2 Ability costs

```ts
export type AbilityCost =
  | { type: 'INK'; amount: number }
  | { type: 'EXERT_SOURCE' }
  | { type: 'BANISH_SOURCE' }
  | { type: 'DISCARD_CARD'; count: number }
  | { type: 'DAMAGE_SOURCE'; amount: number }
  | { type: 'CUSTOM'; id: string }
```

---

# 17. Effect Model

```ts
export type EffectDefinition =
  | { type: 'DRAW'; player: PlayerSelector; count: number }
  | { type: 'DISCARD'; player: PlayerSelector; count: number; choice: 'controller' | 'opponent' | 'random' }
  | { type: 'DEAL_DAMAGE'; target: TargetSelector; amount: number }
  | { type: 'HEAL_DAMAGE'; target: TargetSelector; amount: number }
  | { type: 'BANISH'; target: TargetSelector }
  | { type: 'READY'; target: TargetSelector }
  | { type: 'EXERT'; target: TargetSelector }
  | { type: 'GAIN_LORE'; player: PlayerSelector; amount: number }
  | { type: 'MODIFY_STRENGTH'; target: TargetSelector; amount: number; duration: EffectDuration }
  | { type: 'MODIFY_WILLPOWER'; target: TargetSelector; amount: number; duration: EffectDuration }
  | { type: 'MODIFY_LORE'; target: TargetSelector; amount: number; duration: EffectDuration }
  | { type: 'MODIFY_COST'; target: TargetSelector; amount: number; duration: EffectDuration }
  | { type: 'GRANT_KEYWORD'; target: TargetSelector; keyword: LorcanaKeyword; duration: EffectDuration }
  | { type: 'MOVE_CARD'; source: ZoneSelector; destination: ZoneSelector; count?: number }
  | { type: 'LOOK_AT_TOP'; player: PlayerSelector; count: number }
  | { type: 'REVEAL_CARDS'; player: PlayerSelector; count: number }
  | { type: 'SEARCH_DECK'; player: PlayerSelector; criteria: SearchCriteria; destination: ZoneName }
  | { type: 'SHUFFLE_DECK'; player: PlayerSelector }
```

## 17.1 Effect duration

```ts
export type EffectDuration =
  | 'instant'
  | 'until-end-of-turn'
  | 'while-source-in-play'
  | 'permanent'
  | 'until-source-leaves'
```

---

# 18. Targeting System

```ts
export type TargetRef =
  | { type: 'card'; instanceId: CardInstanceId }
  | { type: 'player'; playerId: PlayerId }
  | { type: 'zone'; playerId: PlayerId; zone: ZoneName }

export type TargetingRule = {
  min: number
  max: number

  legalCardTypes?: CardType[]
  legalZones?: ZoneName[]

  controller?: 'self' | 'opponent' | 'any'

  mustBeReady?: boolean
  mustBeExerted?: boolean
  mustBeDamaged?: boolean
  mustHaveKeyword?: LorcanaKeyword
  mustNotHaveKeyword?: LorcanaKeyword

  allowWard?: boolean
  allowHidden?: boolean
}
```

Target validation must resolve:

```text
zone
controller
card type
visibility
readiness/exertion
damage state
Ward
Evasive
Bodyguard
custom card restrictions
```

---

# 19. Trigger System

The sourced runtime model included a trigger-bag view and resolving action source card. The engine should model triggers explicitly.

```ts
export type TriggerCondition =
  | { type: 'ON_PLAY' }
  | { type: 'ON_QUEST' }
  | { type: 'ON_CHALLENGE' }
  | { type: 'ON_BANISH' }
  | { type: 'ON_DAMAGE_DEALT' }
  | { type: 'ON_CARD_DRAWN' }
  | { type: 'START_OF_TURN' }
  | { type: 'END_OF_TURN' }
  | { type: 'CARD_MOVED_ZONE'; from?: ZoneName; to?: ZoneName }

export type TriggeredAbility = {
  triggerId: TriggerId
  sourceInstanceId: CardInstanceId
  controllerId: PlayerId
  condition: TriggerCondition
  effects: EffectDefinition[]
  optional: boolean
}
```

## 19.1 Trigger flow

```text
1. An action creates one or more game events.
2. Engine scans active static/triggered abilities.
3. Matching triggered abilities are added to triggerBag.
4. Mandatory triggers must resolve.
5. Optional triggers prompt the controlling player.
6. Trigger resolution may create more events.
7. Repeat until no pending mandatory triggers remain.
```

---

# 20. Replacement and Continuous Effects

## 20.1 Continuous effects

```ts
export type AppliedEffect = {
  effectId: EffectId
  sourceInstanceId?: CardInstanceId
  controllerId: PlayerId
  duration: EffectDuration
  modifier: ContinuousModifier
}

export type ContinuousModifier =
  | { type: 'STRENGTH'; amount: number; target: TargetSelector }
  | { type: 'WILLPOWER'; amount: number; target: TargetSelector }
  | { type: 'LORE'; amount: number; target: TargetSelector }
  | { type: 'COST'; amount: number; target: TargetSelector }
  | { type: 'KEYWORD'; keyword: LorcanaKeyword; target: TargetSelector }
```

## 20.2 Replacement effects

```ts
export type ReplacementEffect = {
  effectId: EffectId
  sourceInstanceId?: CardInstanceId
  controllerId: PlayerId
  replaces: ReplacementCondition
  apply: EffectDefinition[]
}

export type ReplacementCondition =
  | { type: 'WOULD_BE_BANISHED' }
  | { type: 'WOULD_TAKE_DAMAGE' }
  | { type: 'WOULD_DRAW_CARD' }
  | { type: 'WOULD_MOVE_ZONE'; from?: ZoneName; to?: ZoneName }
```

---

# 21. Prompt System

Prompts are required when an action/effect cannot fully resolve automatically.

```ts
export type PromptType =
  | 'choose-target'
  | 'choose-card'
  | 'choose-zone'
  | 'choose-order'
  | 'optional-trigger'
  | 'replacement-choice'
  | 'discard-choice'
  | 'search-choice'

export type PromptState = {
  promptId: string
  type: PromptType
  playerId: PlayerId
  sourceInstanceId?: CardInstanceId
  minChoices: number
  maxChoices: number
  choices: PromptChoice[]
  required: boolean
}

export type PromptChoice = {
  choiceId: string
  label: string
  target?: TargetRef
}
```

The engine should pause unresolved effects until the prompt is resolved.

---

# 22. Deck and Format Validation

## 22.1 Deck list

```ts
export type DeckEntry = {
  cardDefinitionId: CardDefinitionId
  count: number
}

export type DeckList = {
  id?: string
  name: string
  entries: DeckEntry[]
  format: GameFormat
}
```

## 22.2 Constructed rules

```text
Minimum 60 cards.
Maximum 2 ink colors.
Maximum 4 copies of a card by deck-building identity.
Deck must contain only legal cards for the format.
```

## 22.3 Limited rules

```text
Minimum 40 cards.
No ink-color restriction.
No normal copy limit from sealed/draft pool.
Deck must only include cards from the limited pool.
```

## 22.4 Validation API

```ts
export type DeckValidationResult = {
  valid: boolean
  errors: DeckValidationError[]
  warnings: DeckValidationWarning[]
}

export type DeckValidationError = {
  code: string
  message: string
  cardDefinitionId?: CardDefinitionId
}

export type DeckValidationWarning = {
  code: string
  message: string
  cardDefinitionId?: CardDefinitionId
}

export function validateDeck(
  deck: DeckList,
  cardDb: Map<CardDefinitionId, CardDefinition>,
  rules: RulesConfig
): DeckValidationResult
```

---

# 23. Manual Override Actions

Manual override is required from the first playable version.

```ts
export type ManualGameAction =
  | { type: 'MANUAL_ADJUST_LORE'; playerId: PlayerId; delta: number }
  | { type: 'MANUAL_SET_LORE'; playerId: PlayerId; value: number }
  | { type: 'MANUAL_ADJUST_DAMAGE'; targetInstanceId: CardInstanceId; delta: number }
  | { type: 'MANUAL_SET_DAMAGE'; targetInstanceId: CardInstanceId; value: number }
  | { type: 'MANUAL_READY_EXERT'; targetInstanceId: CardInstanceId; exerted: boolean }
  | { type: 'MANUAL_MOVE_CARD'; targetInstanceId: CardInstanceId; toPlayerId?: PlayerId; toZone: ZoneName }
  | { type: 'MANUAL_DRAW'; playerId: PlayerId; count: number }
  | { type: 'MANUAL_DISCARD'; targetInstanceId: CardInstanceId }
  | { type: 'MANUAL_BANISH'; targetInstanceId: CardInstanceId }
  | { type: 'MANUAL_ADD_INK'; playerId: PlayerId; cardInstanceId: CardInstanceId }
  | { type: 'MANUAL_REMOVE_INK'; playerId: PlayerId; inkwellInstanceId: CardInstanceId }
  | { type: 'MANUAL_ADD_NOTE'; message: string }
```

Manual actions:

```text
bypass normal rule validation only when allowManualOverride is true
must be logged
must preserve replay/debug history
must mark game as manually modified
```

---

# 24. Game Log

```ts
export type GameLogEntry = {
  id: string
  timestamp: string
  turnNumber: number
  phase: GamePhase
  playerId?: PlayerId
  actionType: GameAction['type']
  message: string
  payload?: unknown
  manual: boolean
}
```

The log is part of the authoritative game state.

Every applied action should create a log entry.

---

# 25. Serialization and Replay

## 25.1 Serialized game

```ts
export type SerializedGame = {
  version: number
  gameId: GameId
  seed: string
  initialDecks: Record<PlayerId, DeckList>
  initialPlayerOrder: PlayerId[]
  actions: GameAction[]
  finalState?: GameState
}
```

## 25.2 Replay model

A replay should rebuild state by applying actions from the initial game state:

```ts
export function replayGame(
  serialized: SerializedGame,
  context: GameContext
): GameState
```

Benefits:

```text
debugging
deterministic testing
undo/redo
shareable game logs
AI training traces
desync investigation
```

---

# 26. Clock Model

The sourced Duels runtime exposed two timer presets.

```ts
export type GameClockPreset = {
  initialMs: number
  maxMs: number
  incrementMs: number
  recoveryMs: number
  mulliganFirstPlayerMs: number
  mulliganSecondPlayerMs: number
  afkPingEnabled: boolean
  actionIncrementMs: number
}

export const CLOCK_PRESETS = {
  casual: {
    initialMs: 90_000,
    maxMs: 210_000,
    incrementMs: 60_000,
    recoveryMs: 45_000,
    mulliganFirstPlayerMs: 90_000,
    mulliganSecondPlayerMs: 45_000,
    afkPingEnabled: true,
    actionIncrementMs: 10_000,
  },
  standard: {
    initialMs: 60_000,
    maxMs: 120_000,
    incrementMs: 45_000,
    recoveryMs: 45_000,
    mulliganFirstPlayerMs: 60_000,
    mulliganSecondPlayerMs: 45_000,
    afkPingEnabled: true,
    actionIncrementMs: 5_000,
  },
} satisfies Record<'casual' | 'standard', GameClockPreset>
```

Recommended clock state:

```ts
export type PlayerClockState = {
  playerId: PlayerId
  remainingMs: number
  maxMs: number
  active: boolean
  lastStartedAt?: number
}

export type GameClockState = {
  preset: 'casual' | 'standard' | 'none'
  players: Record<PlayerId, PlayerClockState>
}
```

Clock should be separate from the pure game reducer when possible, but clock-affecting events should still be logged.

---

# 27. AI Hooks

## 27.1 Legal action generator

```ts
export function getLegalActions(
  state: GameState,
  playerId: PlayerId,
  context: GameContext
): GameAction[]
```

## 27.2 AI choice

```ts
export type AIDifficulty =
  | 'random'
  | 'heuristic'
  | 'deck-aware'

export type AIEvaluation = {
  action: GameAction
  score: number
  reasons: string[]
}

export function chooseAIAction(
  state: GameState,
  playerId: PlayerId,
  legalActions: GameAction[],
  difficulty: AIDifficulty,
  context: GameContext
): GameAction
```

## 27.3 AI implementation order

```text
1. Random legal AI.
2. Heuristic AI.
3. Deck-aware AI.
```

## 27.4 Heuristic priorities

```text
Win immediately if possible.
Prevent opponent from winning if possible.
Ink early if below curve.
Play efficient cards on curve.
Quest when safe.
Challenge when favorable.
Remove high-threat opposing cards.
Preserve high-lore characters.
Avoid unnecessary trades when ahead in lore.
```

---

# 28. Recommended Engine File Structure

```text
lib/game/
  types/
    ids.ts
    card.ts
    player.ts
    zones.ts
    state.ts
    actions.ts
    effects.ts
    targeting.ts
    triggers.ts
    clocks.ts
    log.ts
    deck.ts

  rules/
    actionValidation.ts
    applyAction.ts
    setup.ts
    mulligan.ts
    turn.ts
    draw.ts
    ink.ts
    costs.ts
    playCard.ts
    quest.ts
    challenge.ts
    damage.ts
    banish.ts
    abilities.ts
    prompts.ts
    triggers.ts
    replacementEffects.ts
    continuousEffects.ts
    winLoss.ts
    deckValidation.ts

  ai/
    legalActions.ts
    randomAI.ts
    heuristicAI.ts
    actionScoring.ts

  serialization/
    serializeGame.ts
    replayGame.ts
    hydrateGame.ts

  testing/
    fixtures.ts
    sampleCards.ts
    sampleDecks.ts
```

---

# 29. Implementation Phases

## Phase 1 — State and reducer foundation

```text
IDs
CardDefinition
PlayableCardInstance
PlayerGameState
GameState
GameAction
ValidationResult
canTakeAction
applyAction
GameLogEntry
manual override actions
```

## Phase 2 — Core playable rules

```text
setup
shuffle
draw opening hand
mulligan/alter hand
first-player skipped draw
ready step
draw step
ink once per turn
pay ink
play vanilla cards
quest
challenge
damage
banish
pass turn
win/loss
concede
```

## Phase 3 — Keywords

```text
Rush
Evasive
Bodyguard
Ward
Resist
Challenger
Support
Singer
Shift
```

## Phase 4 — Effect engine

```text
draw
discard
damage
heal
banish
ready
exert
gain lore
modify strength
modify willpower
modify lore
grant keyword
move card
search/reveal
shuffle
```

## Phase 5 — Triggers and replacement effects

```text
trigger bag
optional triggers
mandatory triggers
start/end turn triggers
on-play
on-quest
on-challenge
on-banish
damage triggers
replacement effects
```

## Phase 6 — AI

```text
random legal actions
heuristic scoring
deck-aware scoring
```

## Phase 7 — Multiplayer readiness

```text
deterministic action log
serialized games
replay from seed/actions
desync detection
clock integration
network action protocol
```

---

# 30. Minimal Test Matrix

## Setup tests

```text
creates two players
creates unique card instances
shuffles deterministically by seed
draws seven-card opening hands
sets first player
enters mulligan phase
```

## Turn tests

```text
first player skips first draw
second player draws on first turn
ready step readies exerted cards
turn flags reset correctly
pass turn advances active player
```

## Ink tests

```text
can ink inkable card from hand
cannot ink twice in a turn
cannot ink non-inkable card without effect
ink moves card to hidden inkwell
```

## Play tests

```text
can play affordable character
cannot play card without enough ink
action resolves then goes to discard
item enters item zone
location enters location zone
song can use singer when legal
```

## Quest tests

```text
ready character can quest
questing exerts character
questing adds lore
just-played character cannot quest without Rush/effect
20 lore wins game
```

## Challenge tests

```text
ready character can challenge legal exerted opposing character
challenge exerts attacker
both characters deal damage
character with lethal damage is banished
Evasive restriction applies
Bodyguard restriction applies
```

## Manual override tests

```text
can adjust lore
can adjust damage
can ready/exert
can move cards between zones
manual action logs as manual
manual action marks game modified
```

---

# 31. Most Important Sourced Facts to Preserve

```text
1. Runtime card instances need damage, exerted, justPlayed, addedToInkThisTurn, facedown, locationInstanceId, appliedEffects, temporaryAbilities, cardsUnder, usedAbilitiesThisTurn, challenge flags, quest flags, and variant.
2. Hidden cards must be first-class objects, especially for inkwell and cards-under.
3. Game flow should include prompt state and trigger bag state.
4. Timers should support casual and standard presets with mulligan timings and action increments.
5. Manual override must be present from the beginning.
6. Engine must be pure and replayable through action logs.
7. Core rules should be automated before card-specific automation.
8. Card-specific automation should use declarative ability/effect definitions.
9. AI should operate through `getLegalActions` and `chooseAIAction`.
10. The game engine should be independent from frontend rendering.
```
