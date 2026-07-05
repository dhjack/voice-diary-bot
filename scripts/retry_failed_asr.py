from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import date
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import AppConfig
from src.services.asr import ASRError, ASRService
from src.services.storage import EntryStatus, EntryType


logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retry failed voice ASR entries for a day.")
    parser.add_argument("--date", help="Date to retry, in YYYY-MM-DD. Defaults to today in configured TZ.")
    parser.add_argument(
        "--indexes",
        nargs="*",
        type=int,
        help="Specific entry indexes to retry. Defaults to all failed voice entries.",
    )
    return parser.parse_args()


def _load_meta(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save_meta(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _error_message(error: Exception) -> str:
    message = str(error)
    return message if message else repr(error)


async def _retry() -> int:
    args = _parse_args()
    config = AppConfig.from_env()
    target_date = date.fromisoformat(args.date) if args.date else datetime.now(config.schedule.timezone).date()
    date_dir = config.data_dir / target_date.isoformat()

    if not date_dir.exists():
        logger.info("No data directory for %s", target_date)
        return 0

    requested_indexes = set(args.indexes or [])
    asr = ASRService(config.asr)
    retried = 0
    succeeded = 0

    try:
        for meta_path in sorted(date_dir.glob("[0-9]*_meta.json")):
            meta = _load_meta(meta_path)
            index = int(meta["index"])

            if requested_indexes and index not in requested_indexes:
                continue
            if meta.get("entry_type") != EntryType.VOICE.value:
                continue
            if meta.get("status") != EntryStatus.ERROR.value:
                continue

            voice_path = date_dir / f"{index:03d}_voice.ogg"
            if not voice_path.exists():
                logger.warning("Skipping %03d: missing %s", index, voice_path.name)
                continue

            retried += 1
            logger.info("Retrying ASR for %03d (%s)", index, voice_path.name)

            try:
                result = await asr.transcribe(voice_path.read_bytes())
            except ASRError as e:
                meta["error_message"] = _error_message(e)
                _save_meta(meta_path, meta)
                logger.error("Retry failed for %03d: %s", index, meta["error_message"])
                continue

            transcript_path = date_dir / f"{index:03d}_transcript.txt"
            transcript_path.write_text(result.text, encoding="utf-8")
            meta["status"] = EntryStatus.DONE.value
            meta["error_message"] = None
            if result.duration_ms is not None:
                meta["asr_duration_ms"] = result.duration_ms
            _save_meta(meta_path, meta)
            succeeded += 1
            logger.info("Retry succeeded for %03d: %d chars", index, len(result.text))
    finally:
        await asr.close()

    logger.info("Retry complete: %d/%d succeeded", succeeded, retried)
    return 0 if retried == succeeded else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_retry()))
