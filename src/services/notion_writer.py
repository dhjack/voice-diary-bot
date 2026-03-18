from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

from src.config import NotionConfig

logger = logging.getLogger(__name__)

NOTION_VERSION = "2026-03-11"
NOTION_BASE_URL = "https://api.notion.com/v1"


class NotionWriteError(Exception):
    pass


@dataclass
class DiaryEntry:
    """A single entry to be written to Notion."""
    time_str: str
    text: str
    voice_upload_id: str | None = None


class NotionWriter:
    """Writes diary pages to Notion with structured entry blocks and voice uploads."""

    def __init__(self, config: NotionConfig) -> None:
        self._config = config
        self._client = httpx.AsyncClient(
            timeout=60.0,
            headers={
                "Authorization": f"Bearer {config.token}",
                "Notion-Version": NOTION_VERSION,
            },
        )

    async def upload_file(self, file_path: Path) -> str:
        """Upload a file to Notion via File Upload API. Returns the file_upload id."""
        create_resp = await self._client.post(
            f"{NOTION_BASE_URL}/file_uploads",
            json={},
            headers={"Content-Type": "application/json"},
        )
        if create_resp.status_code != 200:
            raise NotionWriteError(f"Failed to create file upload: {create_resp.status_code} {create_resp.text}")

        upload_data = create_resp.json()
        file_upload_id = upload_data["id"]
        upload_url = upload_data["upload_url"]

        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "audio/ogg")}
            send_resp = await self._client.post(upload_url, files=files)

        if send_resp.status_code != 200:
            raise NotionWriteError(f"Failed to send file: {send_resp.status_code} {send_resp.text}")

        logger.info("Uploaded file %s -> file_upload id=%s", file_path.name, file_upload_id)
        return file_upload_id

    async def create_diary_page(self, title: str, diary_entries: list[DiaryEntry]) -> str:
        """Create a diary page with format:
        - Body: [HH:MM:SS] polished text (one paragraph per entry)
        - Bottom: collapsible heading with all voice recordings inside
        Returns the page id.
        """
        children: list[dict] = []

        for entry in diary_entries:
            line = f"[{entry.time_str}] {entry.text}"
            for chunk in _chunk_text(line, 2000):
                children.append(_paragraph_block(chunk))

        voice_ids = [e.voice_upload_id for e in diary_entries if e.voice_upload_id]
        if voice_ids:
            audio_children = [_audio_block(vid) for vid in voice_ids]
            children.append(_toggle_heading_block("语音原始录音", audio_children))

        payload = {
            "parent": {"database_id": self._config.database_id},
            "properties": {
                "title": {
                    "title": [{"text": {"content": title}}],
                },
            },
            "children": children,
        }

        resp = await self._client.post(
            f"{NOTION_BASE_URL}/pages",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

        if resp.status_code != 200:
            raise NotionWriteError(f"Failed to create page: {resp.status_code} {resp.text}")

        page_id = resp.json()["id"]
        logger.info("Created Notion diary page: %s (title=%s)", page_id, title)
        return page_id

    async def close(self) -> None:
        await self._client.aclose()


def _paragraph_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": text}}],
        },
    }


def _audio_block(file_upload_id: str) -> dict:
    return {
        "object": "block",
        "type": "audio",
        "audio": {
            "type": "file_upload",
            "file_upload": {"id": file_upload_id},
        },
    }


def _toggle_heading_block(text: str, children: list[dict]) -> dict:
    """A heading_3 with children becomes a collapsible toggle heading in Notion."""
    return {
        "object": "block",
        "type": "heading_3",
        "heading_3": {
            "rich_text": [{"type": "text", "text": {"content": text}}],
            "is_toggleable": True,
            "children": children,
        },
    }


def _chunk_text(text: str, max_len: int) -> list[str]:
    chunks: list[str] = []
    while len(text) > max_len:
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks
