from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from src.config import LLMConfig
from src.services.storage import DayEntry, EntryType

logger = logging.getLogger(__name__)

MAX_ORGANIZE_ATTEMPTS = 2
ORGANIZE_RETRY_DELAY_SECONDS = 3

SYSTEM_PROMPT = """你是一个日记整理助手。你的任务是：

1. 提取 1~6 个核心关键词作为标题，关键词之间用逗号隔开
   - 关键词优先提取当天发生的具体事件、人物、地点、组织、项目名、产品名、会议名、任务名等专有或可检索的名词
   - 优先使用文本里真实出现过的具体名词，不要为了概括而改写成抽象词
   - 如果同一天发生了明确事件，优先用“事件/对象”相关关键词，不要优先输出“思考”“推进”“安排”“沟通”“复盘”“感受”这类空泛词
   - 只有在确实缺少具体名词时，才允许补充较抽象的总结词
   - 不要重复近义词，不要过于笼统，不要使用完整句子
   - 好的示例：张三，产品评审，浦东机场，Notion API，GCP 迁移
   - 不好的示例：工作，生活，想法，沟通，处理事情，总结
2. 对每条记录的文本进行润色：
   - 去掉口语化冗余（如"嗯""那个""就是说"等）
   - 修正可能的语音识别错误（根据上下文推断正确用词）
   - 保持原意不变，使文字更通顺书面化
   - 不要合并或重新组织条目，每条单独润色

请严格按以下 JSON 格式输出，不要输出其他内容：
{
  "title": "关键词1，关键词2，关键词3",
  "entries": ["润色后的第1条", "润色后的第2条", ...]
}

entries 数组的顺序和数量必须与输入的记录一一对应。"""


@dataclass
class OrganizeResult:
    title: str
    polished_texts: list[str]


class OrganizerResponseError(Exception):
    """Raised when the model response does not match the diary JSON contract."""


class OrganizerService:
    """Polishes diary entries and extracts title using LLM."""

    def __init__(self, config: LLMConfig) -> None:
        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
        )
        self._model = config.model

    async def organize(self, entries: list[DayEntry]) -> OrganizeResult:
        """Polish each entry's text and extract a title in one LLM call."""
        entries_with_text = [e for e in entries if e.text]
        if not entries_with_text:
            raise ValueError("No entries with text content to organize")

        user_content = self._build_user_prompt(entries_with_text)

        for attempt in range(1, MAX_ORGANIZE_ATTEMPTS + 1):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,
                    max_tokens=2000,
                )

                raw = (response.choices[0].message.content or "").strip()
                return self._parse_response(raw, len(entries_with_text))
            except Exception as error:
                if attempt == MAX_ORGANIZE_ATTEMPTS:
                    raise
                logger.warning(
                    "LLM organize attempt %d/%d failed: %s; retrying",
                    attempt,
                    MAX_ORGANIZE_ATTEMPTS,
                    error,
                )
                await asyncio.sleep(ORGANIZE_RETRY_DELAY_SECONDS)

        raise RuntimeError("LLM organize attempts exhausted")

    def _build_user_prompt(self, entries: list[DayEntry]) -> str:
        lines: list[str] = []
        for i, entry in enumerate(entries, 1):
            source = "语音转写" if entry.meta.entry_type == EntryType.VOICE else "文字输入"
            lines.append(f"第{i}条（{source}）：{entry.text}")
        return "\n".join(lines)

    def _parse_response(self, raw: str, expected_count: int) -> OrganizeResult:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as error:
            raise OrganizerResponseError("LLM returned invalid JSON") from error

        if not isinstance(data, dict):
            raise OrganizerResponseError("LLM JSON response is not an object")

        title = str(data.get("title", "")).strip().strip('"\'')
        if not title:
            raise OrganizerResponseError("LLM JSON response has no title")
        polished = data.get("entries", [])

        if not isinstance(polished, list) or len(polished) != expected_count:
            actual_count = len(polished) if isinstance(polished, list) else 0
            raise OrganizerResponseError(
                f"LLM returned {actual_count} entries, expected {expected_count}"
            )

        logger.info("Organized: title=%s, %d entries polished", title, len(polished))
        return OrganizeResult(title=title, polished_texts=[str(t) for t in polished])

    async def close(self) -> None:
        await self._client.close()
