from __future__ import annotations

import base64
import logging
import uuid
from dataclasses import dataclass

import httpx

from src.config import ASRConfig

logger = logging.getLogger(__name__)

MAX_RETRIES = 1
RETRY_DELAY_SECONDS = 2


class ASRError(Exception):
    pass


@dataclass
class ASRResult:
    text: str
    duration_ms: int | None = None


class ASRService:
    """Speech-to-text using Volcengine BigModel Flash API (base64 upload)."""

    def __init__(self, config: ASRConfig) -> None:
        self._config = config
        self._client = httpx.AsyncClient(timeout=60.0)

    async def transcribe(self, audio_data: bytes) -> ASRResult:
        """Transcribe audio bytes with automatic retry on failure."""
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                return await self._do_transcribe(audio_data)
            except ASRError as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    logger.warning("ASR attempt %d failed: %s, retrying...", attempt + 1, e)
                    import asyncio
                    await asyncio.sleep(RETRY_DELAY_SECONDS)

        raise ASRError(f"ASR failed after {MAX_RETRIES + 1} attempts: {last_error}")

    async def _do_transcribe(self, audio_data: bytes) -> ASRResult:
        audio_b64 = base64.b64encode(audio_data).decode("ascii")

        headers = {
            "X-Api-App-Key": self._config.app_key,
            "X-Api-Access-Key": self._config.access_token,
            "X-Api-Resource-Id": self._config.resource_id,
            "X-Api-Request-Id": str(uuid.uuid4()),
            "X-Api-Sequence": "-1",
        }

        payload = {
            "user": {"uid": self._config.app_key},
            "audio": {"data": audio_b64},
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
            },
        }

        response = await self._client.post(
            self._config.endpoint,
            json=payload,
            headers=headers,
        )

        status_code = response.headers.get("X-Api-Status-Code", "")
        message = response.headers.get("X-Api-Message", "")

        if status_code != "20000000":
            raise ASRError(f"ASR recognition failed: status={status_code}, message={message}")

        data = response.json()
        result = data.get("result", {})
        text = result.get("text", "")

        if not text:
            utterances = result.get("utterances", [])
            text = " ".join(u.get("text", "") for u in utterances if u.get("text"))

        if not text:
            raise ASRError("ASR returned empty text (possibly silent audio)")

        duration_ms = data.get("audio_info", {}).get("duration")

        logger.info("ASR transcription succeeded: %d chars, duration=%s ms", len(text), duration_ms)
        return ASRResult(text=text, duration_ms=duration_ms)

    async def close(self) -> None:
        await self._client.aclose()
