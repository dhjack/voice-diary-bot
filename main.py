from __future__ import annotations

import logging

from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CommandHandler as TGCommandHandler,
    ContextTypes,
    MessageHandler as TGMessageHandler,
    filters,
)

from src.config import AppConfig
from src.handlers.command_handler import CommandHandler
from src.handlers.message_handler import MessageHandler
from src.services.asr import ASRService
from src.services.diary_pipeline import DiaryPipeline
from src.services.notion_writer import NotionWriter
from src.services.organizer import OrganizerService
from src.services.storage import StorageService

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    config = AppConfig.from_env()

    storage = StorageService(config.data_dir)
    asr = ASRService(config.asr)
    organizer = OrganizerService(config.llm)
    notion = NotionWriter(config.notion)
    pipeline = DiaryPipeline(storage, organizer, notion)

    msg_handler = MessageHandler(storage, asr)
    cmd_handler = CommandHandler(storage, pipeline)

    app = Application.builder().token(config.telegram.bot_token).build()

    user_filter = filters.User(user_id=config.telegram.allowed_user_id)

    async def _reject_unauthorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message:
            await update.effective_message.reply_text("⛔ 无权限访问此 Bot。")

    app.add_handler(TGCommandHandler("start", cmd_handler.handle_start, filters=user_filter))
    app.add_handler(TGCommandHandler("diary", cmd_handler.handle_diary, filters=user_filter))
    app.add_handler(TGCommandHandler("status", cmd_handler.handle_status, filters=user_filter))
    app.add_handler(TGCommandHandler("list", cmd_handler.handle_list, filters=user_filter))

    app.add_handler(TGMessageHandler(filters.VOICE & user_filter, msg_handler.handle_voice))
    app.add_handler(TGMessageHandler(filters.TEXT & ~filters.COMMAND & user_filter, msg_handler.handle_text))

    app.add_handler(TGMessageHandler(filters.ALL & ~user_filter, _reject_unauthorized))

    if config.schedule.hour is not None:
        _setup_scheduler(app, pipeline, config)

    async def _on_startup(application: Application) -> None:
        await application.bot.set_my_commands([
            BotCommand("diary", "整理今日记录为日记并写入 Notion"),
            BotCommand("status", "查看今天的记录状态"),
            BotCommand("list", "列出今天所有记录"),
            BotCommand("start", "显示帮助信息"),
        ])
        logger.info("Bot commands menu registered")

    app.post_init = _chain_post_init(app.post_init, _on_startup)

    logger.info("Bot starting... (schedule: %02d:%02d)", config.schedule.hour, config.schedule.minute)
    app.run_polling(drop_pending_updates=True)


def _chain_post_init(
    existing: object | None,
    new_callback: object,
) -> object:
    """Chain multiple post_init callbacks together."""
    if existing is None:
        return new_callback

    async def chained(application: Application) -> None:
        await existing(application)
        await new_callback(application)

    return chained


def _setup_scheduler(app: Application, pipeline: DiaryPipeline, config: AppConfig) -> None:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = AsyncIOScheduler()

    async def scheduled_diary() -> None:
        logger.info("Scheduled diary generation triggered")
        try:
            result = await pipeline.generate_diary()
            logger.info("Scheduled diary result: %s", result)
        except Exception as e:
            logger.error("Scheduled diary generation failed: %s", e, exc_info=True)

    scheduler.add_job(
        scheduled_diary,
        trigger=CronTrigger(hour=config.schedule.hour, minute=config.schedule.minute),
        id="daily_diary",
        replace_existing=True,
    )

    async def start_scheduler(_: Application) -> None:
        scheduler.start()
        logger.info("Scheduler started: diary at %02d:%02d", config.schedule.hour, config.schedule.minute)

    async def stop_scheduler(_: Application) -> None:
        scheduler.shutdown()
        logger.info("Scheduler stopped")

    app.post_init = _chain_post_init(app.post_init, start_scheduler)
    app.post_shutdown = stop_scheduler


if __name__ == "__main__":
    main()
