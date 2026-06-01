# Gazpacho

Personal Telegram digest bot for Spanish school updates, summarized in Ukrainian.

Gazpacho has two separate Telegram identities:

- A Telegram user client, implemented with Telethon/MTProto, logs in as the parent's own account and reads the three school chats. This is required because a Telegram bot cannot fetch chat history for chats where it is not present.
- A normal Telegram bot sends the weekly digest and receives follow-up questions in the parent's private chat.

The interactive Telegram user login happens only once on a local machine. Cloud code receives a pre-created Telethon `StringSession` from AWS Secrets Manager and never asks for a phone number, login code, or 2FA password.

## Current Phase

Phase 3 is complete in code: the Telethon reader can fetch recent chat history and download image notices. A real-chat run still requires local credentials and a valid `StringSession`.

## Architecture

Weekly digest flow:

```text
EventBridge weekly cron
  -> WeeklyDigest Lambda container image
       -> Telethon user client reads the last LOOKBACK_DAYS from source chats
       -> downloads photo/image notices to /tmp
       -> Anthropic vision model summarizes and translates into Ukrainian
       -> Telegram Bot API sends digest to TARGET_CHAT_ID
       -> DynamoDB stores raw messages and generated digest
```

Q&A flow:

```text
Telegram bot webhook
  -> API Gateway HTTP API
  -> Webhook Lambda zip
       -> verifies Telegram secret-token header
       -> reads latest digest, raw messages, and short chat history from DynamoDB
       -> Anthropic answers in Ukrainian
       -> Telegram Bot API replies
```

The webhook Lambda must not import Telethon or have access to Telegram account credentials.

## Defaults

Anthropic model IDs are configurable through environment variables. The default routine weekly summary model is `claude-haiku-4-5-20251001`; the default Q&A model is `claude-sonnet-4-6`.

## Layout

```text
src/common        config, secrets loader, shared clients
src/reader        Telethon reader
src/summarizer    prompt builder, LLM calls, image handling
src/notifier      Telegram Bot API sender and message splitting
src/handlers      AWS Lambda entrypoints
scripts           local operator scripts
infra             SAM template and container Dockerfile
tests             focused unit tests
```

## Local Setup

1. Create a Telegram app at `my.telegram.org` and get `api_id` and `api_hash`.
2. Create the bot via `@BotFather` and get the bot token.
3. Copy `.env.example` to `.env` and fill in non-secret config values.
4. Run `python scripts/login.py` locally, enter the phone number, Telegram login code, and 2FA password if set, then copy the printed `StringSession`.
5. Store secrets in AWS Secrets Manager as one JSON object:

```json
{
  "telegram_api_id": 123456,
  "telegram_api_hash": "from-my.telegram.org",
  "telethon_string_session": "printed-by-scripts-login",
  "telegram_bot_token": "from-botfather",
  "telegram_webhook_secret": "random-secret-token",
  "anthropic_api_key": "sk-ant-..."
}
```

6. Build and push the reader container image, then run `sam deploy` from the SAM stack once infra is added.
7. Run `scripts/set_webhook.py` to point Telegram at the API Gateway URL with the secret token.
8. Message the bot with `/start` to confirm the private chat's `chat_id`, then set `TARGET_CHAT_ID`.

AWS SSM Parameter Store `SecureString` can replace Secrets Manager later if you want the cheapest possible secret storage at this scale.

## Environment

`SOURCE_CHAT_IDS` accepts comma-separated values or a JSON list. Values can be `@username`, numeric IDs, or invite links that Telethon can resolve.

Required local/cloud config:

- `SOURCE_CHAT_IDS`
- `TARGET_CHAT_ID`
- `TIMEZONE`, default `Europe/Madrid`
- `SOURCE_LANG`, default `es`
- `OUTPUT_LANG`, default `uk`
- `LOOKBACK_DAYS`, default `7`
- `LLM_PROVIDER`, default `anthropic`
- `LLM_MODEL_SUMMARY`
- `LLM_MODEL_QA`
- `SECRETS_MANAGER_SECRET_ID`
- `DYNAMODB_TABLE_NAME`
- `WEEKLY_DIGEST_FUNCTION_NAME`

## Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## One-Time Telegram Login

The Telethon login must run locally because Telegram sends an interactive login code and may require the account's 2FA password. The script uses an in-memory `StringSession`, so it does not create a `.session` file.

Provide `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` in `.env`, or pass them as flags:

```bash
python scripts/login.py --api-id 123456 --api-hash abcdef123456
```

The script prints the `StringSession` after successful login. Store that exact value as `telethon_string_session` in AWS Secrets Manager.

If Telegram does not send a login code, use QR login from an already logged-in Telegram mobile app:

```bash
python scripts/login.py --qr
```

Scan the terminal QR code from Telegram mobile using **Settings > Devices > Link Desktop Device**. If the account has 2FA enabled, the script will still ask for the 2FA password after the QR scan.

## Local Reader Smoke Test

After generating a `StringSession`, put `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELETHON_STRING_SESSION`, and `SOURCE_CHAT_IDS` in `.env`, then run:

```bash
python scripts/read_chats.py
```

The script prints one normalized JSON message per line and a final JSON object with `message_count`, `image_count`, and the image download directory.

## Security Notes

- Never commit `.env` or any secret values.
- Do not log the Telethon string session, bot token, webhook secret, or Anthropic API key.
- Do not log full school message bodies at info level.
- The Q&A Lambda needs only bot, webhook, Anthropic, and DynamoDB access. It must not receive Telegram account credentials.

## Build Phases

1. Repo skeleton, pydantic config, secrets loader, README with setup steps, `.env.example`.
2. `scripts/login.py`, one-time interactive Telethon login that prints a usable `StringSession`.
3. Reader: local run against real chats, normalized messages, image count.
4. Summarizer: Ukrainian digest from sample data, including image OCR through a vision model.
5. Notifier plus `weekly_digest_handler`: full local weekly run.
6. SAM infra: scheduled container Lambda, DynamoDB write verification.
7. Webhook handler, Q&A bot, and `scripts/set_webhook.py`.
8. Hardening: error handling, splitting, FloodWait handling, empty-week note, tests, and cost notes.
