"""同期時に Cursor エディタを起動（Windows 想定・CURSOR_EXE で上書き可）。"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

LOG = logging.getLogger(__name__)


def find_cursor_executable() -> Path | None:
    env = (os.environ.get("CURSOR_EXE") or "").strip()
    if env:
        p = Path(env).expanduser()
        if p.is_file():
            return p
    local = os.environ.get("LOCALAPPDATA")
    if local:
        p = Path(local) / "Programs" / "cursor" / "Cursor.exe"
        if p.is_file():
            return p
    for pf in (os.environ.get("PROGRAMFILES"), os.environ.get("ProgramFiles(x86)")):
        if not pf:
            continue
        p = Path(pf) / "Cursor" / "Cursor.exe"
        if p.is_file():
            return p
    for name in ("cursor", "Cursor"):
        w = shutil.which(name)
        if w:
            return Path(w)
    return None


def try_launch_cursor_for_file(path: Path) -> bool:
    """対象ファイルを Cursor で開く。成功時 True。"""
    exe = find_cursor_executable()
    if exe is None:
        LOG.warning(
            "Cursor が見つかりません。https://cursor.com からインストールするか、"
            "環境変数 CURSOR_EXE に Cursor.exe のフルパスを指定してください。"
        )
        return False
    fp = path.resolve()
    if not fp.is_file():
        LOG.debug("Cursor 起動スキップ（ファイルでない）: %s", fp)
        return False
    try:
        if os.name == "nt":
            creation = 0
            if hasattr(subprocess, "DETACHED_PROCESS"):
                creation |= subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
            if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                creation |= subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            subprocess.Popen(
                [str(exe), str(fp)],
                close_fds=True,
                creationflags=creation,
            )
        else:
            subprocess.Popen([str(exe), str(fp)], start_new_session=True)
        LOG.info("Cursor を起動しました: %s", fp)
        return True
    except Exception as e:
        LOG.warning("Cursor 起動に失敗しました: %s", e)
        return False
