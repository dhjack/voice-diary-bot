from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    allowed_user_id: int


@dataclass(frozen=True)
class ASRConfig:
    app_key: str
    access_token: str
    endpoint: str = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"
    resource_id: str = "volc.bigasr.auc_turbo"


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    model: str = "deepseek-v3-2-251201"


@dataclass(frozen=True)
class NotionConfig:
    token: str
    database_id: str


@dataclass(frozen=True)
class ScheduleConfig:
    hour: int = 22
    minute: int = 0


@dataclass(frozen=True)
class AppConfig:
    telegram: TelegramConfig
    asr: ASRConfig
    llm: LLMConfig
    notion: NotionConfig
    schedule: ScheduleConfig
    data_dir: Path = field(default_factory=lambda: Path("./data"))

    @classmethod
    def from_env(cls, env_path: str | Path | None = None) -> AppConfig:
        load_dotenv(env_path)

        def _require(key: str) -> str:
            value = os.getenv(key)
            if not value:
                raise ValueError(f"Missing required environment variable: {key}")
            return value

        return cls(
            telegram=TelegramConfig(
                bot_token=_require("TELEGRAM_BOT_TOKEN"),
                allowed_user_id=int(_require("TELEGRAM_ALLOWED_USER_ID")),
            ),
            asr=ASRConfig(
                app_key=_require("ASR_APP_KEY"),
                access_token=_require("ASR_ACCESS_TOKEN"),
            ),
            llm=LLMConfig(
                api_key=_require("LLM_API_KEY"),
                base_url=os.getenv("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
                model=os.getenv("LLM_MODEL", "deepseek-v3-2-251201"),
            ),
            notion=NotionConfig(
                token=_require("NOTION_TOKEN"),
                database_id=_require("NOTION_DATABASE_ID"),
            ),
            schedule=ScheduleConfig(
                hour=int(os.getenv("DIARY_SCHEDULE_HOUR", "22")),
                minute=int(os.getenv("DIARY_SCHEDULE_MINUTE", "0")),
            ),
            data_dir=Path(os.getenv("DATA_DIR", "./data")),
        )
