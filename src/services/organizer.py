from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from src.config import LLMConfig
from src.services.storage import DayEntry, EntryType

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个日记整理助手。你的任务是：

1. 提取 2~5 个核心关键词作为标题，关键词之间用逗号隔开。要求精炼，不要重复近义词，不要过于笼统
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

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            max_tokens=2000,
        )

        raw = (response.choices[0].message.content or "").strip()
        return self._parse_response(raw, len(entries_with_text))

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
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM JSON response, using fallback")
            return OrganizeResult(title="日记", polished_texts=[])

        title = str(data.get("title", "日记")).strip().strip('"\'')
        polished = data.get("entries", [])

        if not isinstance(polished, list) or len(polished) != expected_count:
            logger.warning(
                "LLM returned %d entries, expected %d; falling back to original texts",
                len(polished) if isinstance(polished, list) else 0,
                expected_count,
            )
            return OrganizeResult(title=title, polished_texts=[])

        logger.info("Organized: title=%s, %d entries polished", title, len(polished))
        return OrganizeResult(title=title, polished_texts=[str(t) for t in polished])

    async def close(self) -> None:
        await self._client.close()
