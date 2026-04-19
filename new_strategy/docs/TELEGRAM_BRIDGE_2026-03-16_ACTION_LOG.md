# Telegram Bridge Action Log

Date: 2026-03-16

## Scope

This log covers only `T1` Telegram bridge work. It does not change `L1` live strategy logic or `M1` MA breakout research logic.

## Confirmed Decisions

1. `/tomorrow` is not needed as a separate command.
   - It is treated as an alias of `/latest`.
2. The bridge should prioritize short operational guidance over free-form chat.
3. Pre-market proactive messaging is needed.
   - Two windows:
     - `08:28 ~ 08:33` pre-market first response
     - `09:20 ~ 09:25` regular-session second response
   - Use them as operational response briefings for the current focus universe.
4. Symbols outside the active strategy universe must not be described like active candidates.
5. Health checks should use state and CSV logs first, not `bridge_stdout.log`.

## Implemented Changes

### Command behavior

- `/tomorrow` now routes to `/latest`.
- `/latest` keeps the action-oriented summary format.
- `/status` now includes bridge state timestamps from the state file.

### Symbol handling

- `005390 ?좎꽦?듭긽` is hard-excluded from active strategy symbol responses.
- More generally:
  - if a symbol has price history but is not in the latest strategy signal/feature snapshot,
  - the bridge responds that the symbol is outside the current strategy universe.

### Timeout and response structure

- Reply timeout is `15` seconds.
- Slow requests return a deterministic timeout fallback message.

### Pre-open proactive briefing

- New internal scheduled windows:
  - `08:28 ~ 08:33` (`?꾨━??)
  - `09:20 ~ 09:25` (`蹂몄옣`)
- Message now covers the full focus set, not a truncated top-N list.
- Message sections are grouped as:
  - `留ㅼ닔/愿???꾨낫`
  - `蹂댁쑀 ?먭?`
  - `留ㅻ룄/寃쎄퀬`

### Bridge state tracking

The bridge state file now records:

- `last_loop_at`
- `last_incoming_at`
- `last_outgoing_at`
- `last_error_at`
- `last_early_session_brief_at`

These values are surfaced in `/status`.

## Primary Operational Diagnostics

Use these in order:

1. `output/strategy_v2/telegram_bridge/telegram_bridge_state.json`
2. `output/strategy_v2/telegram_bridge/telegram_bridge_message_log.csv`
3. `output/strategy_v2/telegram_bridge/telegram_bridge_job_log.csv`
4. `output/strategy_v2/telegram_bridge/telegram_bridge_unhandled_log.csv`

`bridge_stdout.log` is not the primary source for current bridge health because it can retain stale exceptions from earlier runs.

## Current Intent

`T1` remains isolated from `M1`.

- Telegram bridge code may read live strategy outputs from `output/strategy_v2/`
- Telegram bridge work must not directly modify MA breakout research code or outputs
- Any future optimal-MA exposure in Telegram must be consumed through `L1` published outputs only

## 2026-03-17 Overnight Follow-up

### Real-operation alignment

- Bridge signal queries now use real holdings first.
- If a chat has no real holdings, `/latest` shows only buy-side actionable candidates.
- Hold/sell-side warnings are only surfaced for symbols that exist in that chat's manual portfolio.

### Price basis

- Action-guide price basis is now previous close, not intraday live price.
- Live price is still shown separately as current market information.

### Issue logging

- Messages starting with `湲곕줉]` are now treated as stored issue/question notes.
- Notes are appended to:
  - `output/strategy_v2/telegram_bridge/telegram_bridge_notes.csv`
- These notes are intentionally stored without GPT handling at ingest time.

