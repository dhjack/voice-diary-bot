from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class EntryType(str, Enum):
    VOICE = "voice"
    TEXT = "text"


class EntryStatus(str, Enum):
    DONE = "done"
    ERROR = "error"


@dataclass
class EntryMeta:
    index: int
    entry_type: EntryType
    status: EntryStatus
    timestamp: str
    duration: float | None = None
    error_message: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["entry_type"] = self.entry_type.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> EntryMeta:
        return cls(
            index=data["index"],
            entry_type=EntryType(data["entry_type"]),
            status=EntryStatus(data["status"]),
            timestamp=data["timestamp"],
            duration=data.get("duration"),
            error_message=data.get("error_message"),
        )


@dataclass
class DayEntry:
    meta: EntryMeta
    text: str | None = None
    voice_path: Path | None = None


class StorageService:
    """Manages local file storage organized by date directories."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def _date_dir(self, day: date) -> Path:
        d = self._data_dir / day.isoformat()
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _next_index(self, day: date) -> int:
        date_dir = self._date_dir(day)
        existing = list(date_dir.glob("*_meta.json"))
        return len(existing) + 1

    def save_voice_entry(
        self,
        voice_data: bytes,
        transcript: str | None,
        duration: float | None = None,
        error_message: str | None = None,
    ) -> EntryMeta:
        today = date.today()
        idx = self._next_index(today)
        date_dir = self._date_dir(today)
        prefix = f"{idx:03d}"

        voice_path = date_dir / f"{prefix}_voice.ogg"
        voice_path.write_bytes(voice_data)

        status = EntryStatus.DONE if transcript else EntryStatus.ERROR

        if transcript:
            transcript_path = date_dir / f"{prefix}_transcript.txt"
            transcript_path.write_text(transcript, encoding="utf-8")

        meta = EntryMeta(
            index=idx,
            entry_type=EntryType.VOICE,
            status=status,
            timestamp=datetime.now().isoformat(),
            duration=duration,
            error_message=error_message,
        )
        meta_path = date_dir / f"{prefix}_meta.json"
        meta_path.write_text(json.dumps(meta.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info("Saved voice entry %s for %s (status=%s)", prefix, today, status.value)
        return meta

    def save_text_entry(self, text: str) -> EntryMeta:
        today = date.today()
        idx = self._next_index(today)
        date_dir = self._date_dir(today)
        prefix = f"{idx:03d}"

        text_path = date_dir / f"{prefix}_text.txt"
        text_path.write_text(text, encoding="utf-8")

        meta = EntryMeta(
            index=idx,
            entry_type=EntryType.TEXT,
            status=EntryStatus.DONE,
            timestamp=datetime.now().isoformat(),
        )
        meta_path = date_dir / f"{prefix}_meta.json"
        meta_path.write_text(json.dumps(meta.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info("Saved text entry %s for %s", prefix, today)
        return meta

    def get_day_entries(self, day: date | None = None) -> list[DayEntry]:
        day = day or date.today()
        date_dir = self._data_dir / day.isoformat()
        if not date_dir.exists():
            return []

        entries: list[DayEntry] = []
        for meta_file in sorted(date_dir.glob("*_meta.json")):
            try:
                meta = EntryMeta.from_dict(json.loads(
                    meta_file.read_text(encoding="utf-8", errors="replace")
                ))
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning("Skipping corrupted meta file %s: %s", meta_file, e)
                continue

            prefix = f"{meta.index:03d}"
            text: str | None = None
            voice_path: Path | None = None

            try:
                if meta.entry_type == EntryType.VOICE:
                    voice_file = date_dir / f"{prefix}_voice.ogg"
                    if voice_file.exists():
                        voice_path = voice_file
                    transcript_file = date_dir / f"{prefix}_transcript.txt"
                    if transcript_file.exists():
                        text = transcript_file.read_text(encoding="utf-8", errors="replace")
                elif meta.entry_type == EntryType.TEXT:
                    text_file = date_dir / f"{prefix}_text.txt"
                    if text_file.exists():
                        text = text_file.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                logger.warning("Failed to read files for entry %s: %s", prefix, e)

            entries.append(DayEntry(meta=meta, text=text, voice_path=voice_path))

        return entries

    def save_diary_markdown(self, content: str, day: date | None = None) -> Path:
        """Save organized diary as local markdown fallback."""
        day = day or date.today()
        path = self._data_dir / f"diary_{day.isoformat()}.md"
        path.write_text(content, encoding="utf-8")
        logger.info("Saved diary markdown for %s", day)
        return path
