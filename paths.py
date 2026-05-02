"""アプリデータパス（インストール版・開発版共通）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# プロファイル DB・アンカー承認などを保存する親フォルダ。
# 未設定時は %LOCALAPPDATA%\\FTPAutoSync 。
# Google ドライブ等に共有したい場合は例:
#   set FTP_AUTOSYNC_DATA_DIR=G:\マイドライブ\FTPAutoSyncData
# （ドライブ文字や「マイドライブ」名は環境で異なります）
_ENV_DATA_DIR = "FTP_AUTOSYNC_DATA_DIR"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False) and hasattr(sys, "executable"))


def app_data_dir() -> Path:
    override = (os.environ.get(_ENV_DATA_DIR) or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "FTPAutoSync"
    return Path.home() / ".ftp_auto_sync"


def data_dir_env_var_name() -> str:
    return _ENV_DATA_DIR


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
