"""アプリデータパス（インストール版・開発版共通）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False) and hasattr(sys, "executable"))


def app_data_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "FTPAutoSync"
    return Path.home() / ".ftp_auto_sync"


def user_config_path() -> Path:
    d = app_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "config.json"


def profiles_db_path() -> Path:
    d = app_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "profiles.db"


def bundled_example_config() -> Path | None:
    """PyInstaller onefile/onedir で同梱された例設定。"""
    if is_frozen():
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        p = base / "config.example.json"
        return p if p.is_file() else None
    here = Path(__file__).resolve().parent
    p = here / "config.example.json"
    return p if p.is_file() else None
