from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.services.diary_pipeline import DiaryPipeline
from src.services.storage import EntryStatus, EntryType, StorageService

logger = logging.getLogger(__name__)


class CommandHandler:
    """Handles bot slash commands."""

    def __init__(self, storage: StorageService, pipeline: DiaryPipeline) -> None:
        self._storage = storage
        self._pipeline = pipeline

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.effective_message.reply_text(
            "👋 你好！我是你的语音日记助手。\n\n"
            "🎙️ 发送语音 → 自动转写并保存\n"
            "📝 发送文字 → 直接保存为记录\n"
            "📖 /diary → 整理今天的记录为日记并写入 Notion\n"
            "📊 /status → 查看今天的记录状态\n"
            "📋 /list → 列出今天的所有记录"
        )

    async def handle_diary(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        force = bool(context.args and context.args[0].lower() == "force")
        await update.effective_message.reply_text("📖 正在整理今日日记，请稍候...")

        try:
            result = await self._pipeline.generate_diary(force=force)
            await update.effective_message.reply_text(result)
        except Exception as e:
            logger.error("Diary generation failed: %s", e, exc_info=True)
            await update.effective_message.reply_text(f"❌ 日记生成异常：{e}")

    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        today = self._storage._today()
        entries = self._storage.get_day_entries(today)

        if not entries:
            await update.effective_message.reply_text(f"📭 {today.isoformat()} 暂无记录。")
            return

        voice_count = sum(1 for e in entries if e.meta.entry_type == EntryType.VOICE)
        text_count = sum(1 for e in entries if e.meta.entry_type == EntryType.TEXT)
        done_count = sum(1 for e in entries if e.meta.status == EntryStatus.DONE)
        error_count = sum(1 for e in entries if e.meta.status == EntryStatus.ERROR)

        await update.effective_message.reply_text(
            f"📊 {today.isoformat()} 记录状态：\n\n"
            f"🎙️ 语音：{voice_count} 条\n"
            f"📝 文字：{text_count} 条\n"
            f"✅ 成功：{done_count} 条\n"
            f"❌ 失败：{error_count} 条\n"
            f"📋 总计：{len(entries)} 条"
        )

    async def handle_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        today = self._storage._today()
        entries = self._storage.get_day_entries(today)

        if not entries:
            await update.effective_message.reply_text(f"📭 {today.isoformat()} 暂无记录。")
            return

        lines = [f"📋 {today.isoformat()} 记录列表：\n"]
        for entry in entries:
            time_str = ""
            if "T" in entry.meta.timestamp:
                time_str = entry.meta.timestamp.split("T")[1].split(".")[0]

            icon = "🎙️" if entry.meta.entry_type == EntryType.VOICE else "📝"
            status_icon = "✅" if entry.meta.status == EntryStatus.DONE else "❌"

            preview = ""
            if entry.text:
                preview = entry.text[:60] + ("..." if len(entry.text) > 60 else "")
            elif entry.meta.error_message:
                preview = f"[转写失败: {entry.meta.error_message[:40]}]"
            else:
                preview = "[无文本]"

            lines.append(f"{status_icon} {icon} [{time_str}] {preview}")

        await update.effective_message.reply_text("\n".join(lines))
