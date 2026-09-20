"""Safe, local configuration loading for StockRadar."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def find_workspace_env() -> Path:
    """Find the nearest workspace .env without logging its contents."""
    for directory in Path(__file__).resolve().parents:
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    raise RuntimeError("找不到工作區 .env；請在 Cooperation 根目錄建立它。")


@dataclass(frozen=True)
class Settings:
    api_key: str
    secret_key: str
    production: bool


def load_settings(*, allow_production: bool = False) -> Settings:
    load_dotenv(find_workspace_env(), override=False)
    api_key = os.getenv("SJ_API_KEY", "").strip()
    secret_key = os.getenv("SJ_SEC_KEY", "").strip()
    production = os.getenv("SJ_PRODUCTION", "false").strip().lower() == "true"

    if not api_key or not secret_key:
        raise RuntimeError(".env 缺少 SJ_API_KEY 或 SJ_SEC_KEY。")
    if production and not allow_production:
        raise RuntimeError("Phase 0 僅允許模擬模式；請將 SJ_PRODUCTION 設為 false。")
    return Settings(api_key=api_key, secret_key=secret_key, production=production)
