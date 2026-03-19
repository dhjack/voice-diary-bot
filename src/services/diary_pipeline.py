from __future__ import annotations

import logging

from src.services.notion_writer import DiaryEntry, NotionWriteError, NotionWriter
from src.services.organizer import OrganizeResult, OrganizerService
from src.services.storage import DayEntry, EntryType, StorageService

logger = logging.getLogger(__name__)


class DiaryPipeline:
    """Coordinates the full diary flow: collect entries -> extract title -> upload voices -> write to Notion."""

    def __init__(
        self,
        storage: StorageService,
        organizer: OrganizerService,
        notion: NotionWriter,
    ) -> None:
        self._storage = storage
        self._organizer = organizer
        self._notion = notion

    async def generate_diary(self, force: bool = False) -> str:
        """Generate and publish diary for today. Set force=True to regenerate even if already done."""
        day = self._storage._today()

        if not force and self._storage.is_diary_generated(day):
            return f"📋 {day.isoformat()} 的日记已经生成过了。如需重新生成，请使用 /diary force"

        entries = self._storage.get_day_entries(day)

        if not entries:
            return f"📭 {day.isoformat()} 没有任何记录。"

        entries_with_text = [e for e in entries if e.text]
        if not entries_with_text:
            return f"⚠️ {day.isoformat()} 有 {len(entries)} 条记录，但都没有文本内容（可能转写失败）。"

        try:
            organize_result = await self._organizer.organize(entries)
        except Exception as e:
            logger.error("LLM organize failed: %s", e)
            organize_result = OrganizeResult(title=day.isoformat(), polished_texts=[])

        diary_entries = await self._build_diary_entries(entries, organize_result)

        title = organize_result.title

        try:
            page_id = await self._notion.create_diary_page(title=title, diary_entries=diary_entries)
            self._storage.mark_diary_generated(day)
            voice_count = sum(1 for de in diary_entries if de.voice_upload_id)
            return (
                f"✅ 日记已写入 Notion！\n"
                f"📝 标题：{title}\n"
                f"🎙️ 语音附件：{voice_count} 个\n"
                f"📊 共 {len(diary_entries)} 条记录"
            )
        except NotionWriteError as e:
            logger.error("Notion write failed: %s", e)
            self._save_fallback(title, diary_entries, day)
            return (
                f"❌ Notion 写入失败：{e}\n"
                f"📁 日记已保存到本地\n"
                f"可稍后重试 /diary"
            )

    async def _build_diary_entries(
        self, entries: list[DayEntry], organize_result: OrganizeResult,
    ) -> list[DiaryEntry]:
        """Convert storage entries to Notion diary entries, using polished texts when available."""
        diary_entries: list[DiaryEntry] = []
        text_entries = [e for e in entries if e.text]
        polished = organize_result.polished_texts

        for i, entry in enumerate(text_entries):
            text = polished[i] if i < len(polished) and polished[i] else entry.text
            time_str = self._format_time(entry.meta.timestamp)
            voice_upload_id: str | None = None

            if entry.meta.entry_type == EntryType.VOICE and entry.voice_path:
                try:
                    voice_upload_id = await self._notion.upload_file(entry.voice_path)
                except NotionWriteError as e:
                    logger.warning("Failed to upload voice %s: %s", entry.voice_path, e)

            diary_entries.append(DiaryEntry(
                time_str=time_str,
                text=text,
                voice_upload_id=voice_upload_id,
            ))

        return diary_entries

    def _save_fallback(self, title: str, diary_entries: list[DiaryEntry], day: date) -> None:
        lines = [f"# {title}\n"]
        for de in diary_entries:
            lines.append(f"**{de.time_str}**\n{de.text}\n")
        self._storage.save_diary_markdown("\n".join(lines), day)

    @staticmethod
    def _format_time(timestamp: str) -> str:
        if "T" in timestamp:
            return timestamp.split("T")[1].split(".")[0]
        return timestamp
