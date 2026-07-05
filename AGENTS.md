# Voice Diary Bot Agent Notes

This repository is public. Keep public project notes free of credentials, account names, host IPs, bot tokens, cloud project IDs, and raw production logs.

## First Thing To Read

If this file exists locally, read it before doing infrastructure or production debugging:

```text
.local-notes/voice-diary-handoff.md
```

That file is intentionally ignored by git and contains machine-specific handoff details such as the active cloud account, VM identity, deployment path, and incident notes. Do not commit it.

## Project Shape

- Telegram voice diary bot.
- Runtime: Python 3.13 with `uv`.
- Deployment: Docker Compose.
- Persistent data: mounted `data/` directory.
- Main entrypoint: `main.py`.
- Key modules:
  - `src/handlers/message_handler.py`: Telegram voice/text handling.
  - `src/handlers/command_handler.py`: slash commands.
  - `src/services/asr.py`: speech-to-text integration.
  - `src/services/storage.py`: local day-based data storage.
  - `src/services/diary_pipeline.py`: diary generation flow.
  - `src/services/notion_writer.py`: Notion writes/uploads.
  - `scripts/retry_failed_asr.py`: retry saved failed voice transcriptions.

## Operational Defaults

- Push code changes first, then deploy by pulling on the server and rebuilding Docker Compose.
- Some production Docker/data operations may require `sudo`.
- Do not paste raw old production logs into chat or tickets; older logs may contain Telegram API URLs with bot token material.
- Current code suppresses `httpx` and `httpcore` request logs in `main.py`.

## ASR Failure Context

There was a production issue on 2026-07-05 where long voice entries failed because the ASR HTTP request exceeded the old 60 second client timeout. The deployed fix:

- Raises default ASR timeout to 300 seconds via `ASR_TIMEOUT_SECONDS`.
- Wraps `httpx.TimeoutException` and `httpx.HTTPError` as `ASRError`.
- Retries ASR up to 3 total attempts.
- Saves non-empty error details using a `repr(error)` fallback.
- Adds `scripts/retry_failed_asr.py` for retrying already saved failed voice files.

## Useful Local Checks

```bash
python3 -m compileall main.py src scripts
git status --short
```

## Public Repo Hygiene

- `.env`, `data/`, `.local-notes/`, virtualenvs, and bytecode should stay ignored.
- Do not add cloud account names, project IDs, external IPs, host paths, raw logs, or tokens to committed docs.
- Put production-specific handoff notes in `.local-notes/voice-diary-handoff.md`.

