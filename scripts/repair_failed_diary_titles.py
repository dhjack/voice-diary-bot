from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import AppConfig
from src.services.notion_writer import NotionWriter
from src.services.organizer import OrganizerService
from src.services.storage import StorageService


async def repair_dates(date_values: list[str]) -> int:
    config = AppConfig.from_env()
    storage = StorageService(config.data_dir, tz=config.schedule.timezone)
    organizer = OrganizerService(config.llm)
    notion = NotionWriter(config.notion)
    failures = 0

    try:
        for value in date_values:
            day = date.fromisoformat(value)
            entries = storage.get_day_entries(day)
            if not any(entry.text for entry in entries):
                print(f"{value}: no text entries; skipped")
                failures += 1
                continue

            result = await organizer.organize(entries)
            page_ids = await notion.find_diary_pages_by_title(value)
            if len(page_ids) != 1:
                print(f"{value}: expected 1 date-titled page, found {len(page_ids)}; skipped")
                failures += 1
                continue

            await notion.update_diary_title(page_ids[0], result.title)
            print(f"{value}: {result.title}")
    finally:
        await organizer.close()
        await notion.close()

    return failures


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regenerate keyword titles for date-titled fallback diary pages."
    )
    parser.add_argument("dates", nargs="+", help="Diary dates in YYYY-MM-DD format")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(repair_dates(args.dates)))


if __name__ == "__main__":
    main()
