# Voice Diary Bot Agent Notes

This repository is public. Keep public project notes free of credentials, account names, host IPs, bot tokens, cloud project IDs, and raw production logs.

## First Thing To Read

If this file exists locally, read it before doing infrastructure or production debugging:

```text
.local-notes/voice-diary-handoff.md
```

That file is intentionally ignored by git and contains machine-specific handoff details such as the active cloud account, VM identity, deployment path, and incident notes. Do not commit it.

## New Session Checklist

1. Read this file and `.local-notes/voice-diary-handoff.md` when it exists.
2. Run `git status --short` and preserve unrelated user changes.
3. For production incidents, verify container health, the active model/resource configuration, recent focused logs, and the affected date's metadata before changing code.
4. Never paste secrets or unfiltered production logs into chat, issues, or committed files.
5. After code changes, compile locally, push, pull on the VM, rebuild Compose, and verify the running container contains the expected code/config.

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
- Production access, exact deployment commands, account selection, and incident-specific retry commands are documented only in the ignored local handoff file.

## Current Runtime Behavior

- ASR uses the Volcengine large-model recording-file turbo API with resource ID `volc.bigasr.auc_turbo`.
- ASR requests use a 300 second timeout and retry up to 3 total attempts.
- Saved failed voice files can be retried with `scripts/retry_failed_asr.py` after the upstream issue is fixed.
- Diary organization uses an OpenAI-compatible LLM endpoint.
- LLM output is constrained to JSON, deep reasoning is disabled, and the output limit is 20,000 tokens.
- Invalid LLM output retries once. If both attempts fail, the diary keeps original text and uses the ISO date as its title.

## Incident Triage

### Voice transcription failures

1. Confirm the voice file and metadata were saved under `data/YYYY-MM-DD/`.
2. Search recent logs for `ASR`, the upstream status code, timeout, and quota messages.
3. Distinguish retryable transport failures from account/resource quota failures.
4. Retry saved entries only after the upstream condition is resolved; retries may consume paid quota.

`status=45000292` with `audio_duration_lifetime` means the speech service's cumulative audio-duration quota is exhausted. Repeated retries do not fix it. Activate paid service or add the matching duration quota first.

### Missing diary keywords

1. Search logs for `Organized: title=`, JSON parsing errors, and the final Notion title.
2. Confirm the running container has JSON mode enabled, reasoning disabled, and the intended model ID.
3. A date-only title means both LLM attempts failed and the fallback behaved as designed.

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
git diff --check
git status --short
```

## Public Repo Hygiene

- `.env`, `data/`, `.local-notes/`, virtualenvs, and bytecode should stay ignored.
- Do not add cloud account names, project IDs, external IPs, host paths, raw logs, or tokens to committed docs.
- Put production-specific handoff notes in `.local-notes/voice-diary-handoff.md`.
