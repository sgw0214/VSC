# Telegram Encoding Contract

Date: 2026-04-01

## Goal

Prevent broken Korean text from being sent to Telegram, and make encoding failures visible in operational checks.

## Runtime Contract

File: `new_strategy/telegram_bridge_service.py`

1. All outgoing Telegram text and captions must pass UTF-8 strict encoding.
2. Outgoing text must be normalized to NFC before send.
3. Outgoing text must not contain suspicious mojibake markers:
   - Unicode replacement character `U+FFFD` (`�`)
   - CJK compatibility ideographs (`U+F900..U+FAFF`)
4. If contract check fails, send is blocked and bridge state records:
   - `last_error_action`
   - `last_error_message`

Applied functions:

- `_prepare_telegram_text(...)`
- `send_text(...)`
- `send_photo(...)`
- `_safe_send_text(...)`
- `_safe_send_photo(...)`

## Log Contract

File: `output/strategy_v2/telegram_bridge/telegram_bridge_message_log.csv`

1. Encoding must be UTF-8 with BOM (`utf-8-sig`).
2. Recent outgoing rows must not contain suspicious mojibake markers.

## Verification Contract

File: `new_strategy/verify_operational_contract.py`

Check name:

- `telegram_encoding_contract`

Pass condition:

1. message log file starts with UTF-8 BOM
2. recent outgoing rows (latest 200) contain no suspicious mojibake markers

Fail condition:

- `message log is not UTF-8 BOM CSV`
- `detected suspicious mojibake rows=<n>`
- `encoding read failed:<Exception>`
