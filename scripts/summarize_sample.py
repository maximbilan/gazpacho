#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize sample Telegram messages.")
    parser.add_argument("sample_json", help="JSON file with messages/images arrays")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    from src.common.config import config_from_env
    from src.reader.models import DownloadedImage, NormalizedMessage
    from src.summarizer.summarizer import Summarizer

    payload = json.loads(Path(args.sample_json).read_text(encoding="utf-8"))
    messages = [NormalizedMessage.model_validate(item) for item in payload.get("messages", [])]
    images = [DownloadedImage.model_validate(item) for item in payload.get("images", [])]

    config = config_from_env()
    summarizer = Summarizer(config, openai_api_key=os.getenv("OPENAI_API_KEY"))
    print(summarizer.summarize(messages, images))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
