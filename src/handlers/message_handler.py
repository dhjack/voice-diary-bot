from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.services.asr import ASRError, ASRService
from src.services.storage import StorageService

logger = logging.getLogger(__name__)


class MessageHandler:
    """Handles incoming voice and text messages."""

    def __init__(self, storage: StorageService, asr: ASRService) -> None:
        self._storage = storage
        self._asr = asr

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if not message or not message.voice:
            return

        await message.reply_text("🎙️ 收到语音，正在转写...")

        try:
            voice_file = await context.bot.get_file(message.voice.file_id)
            voice_bytes = await voice_file.download_as_bytearray()
        except Exception as e:
            logger.error("Failed to download voice file: %s", e)
            await message.reply_text("❌ 语音文件下载失败，请重新发送。")
            return

        duration = message.voice.duration

        try:
            result = await self._asr.transcribe(bytes(voice_bytes))
            self._storage.save_voice_entry(
                voice_data=bytes(voice_bytes),
                transcript=result.text,
                duration=duration,
            )
            await message.reply_text(f"✅ 转写完成：\n\n{result.text}")
        except ASRError as e:
            logger.error("ASR transcription failed: %s", e)
            self._storage.save_voice_entry(
                voice_data=bytes(voice_bytes),
                transcript=None,
                duration=duration,
                error_message=str(e),
            )
            await message.reply_text(f"⚠️ 转写失败，语音已保存。\n错误：{e}")
        except Exception as e:
            logger.error("Unexpected error in voice handler: %s", e, exc_info=True)
            self._storage.save_voice_entry(
                voice_data=bytes(voice_bytes),
                transcript=None,
                duration=duration,
                error_message=str(e),
            )
            await message.reply_text(f"❌ 处理异常：{e}\n语音已保存，稍后可重试。")

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if not message or not message.text:
            return

        text = message.text.strip()
        if not text or text.startswith("/"):
            return

        self._storage.save_text_entry(text)
        await message.reply_text(f"📝 已记录：{text[:50]}{'...' if len(text) > 50 else ''}")
