"""
プロファイル（FTPアカウント／レンタルサーバー1件分の設定）を SQLite で最大 100,000 件まで保存。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from paths import profiles_db_path, user_config_path

MAX_PROFILES = 100_000


class ProfileStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or profiles_db_path()
        self._lock = threading.Lock()
        self._ensure_db()
        self._migrate_legacy_json_if_empty()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS profiles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        display_name TEXT NOT NULL,
                        config_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_profiles_name ON profiles(display_name);
                    CREATE TABLE IF NOT EXISTS meta (
                        k TEXT PRIMARY KEY,
                        v TEXT NOT NULL
                    );
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def _migrate_legacy_json_if_empty(self) -> None:
        legacy = user_config_path()
        with self._lock:
            conn = self._connect()
            try:
                (n,) = conn.execute("SELECT COUNT(*) FROM profiles").fetchone()
                if n > 0 or not legacy.is_file():
                    return
                try:
                    with legacy.open(encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    return
                now = time.strftime("%Y-%m-%dT%H:%M:%S")
                cur = conn.execute(
                    "INSERT INTO profiles (display_name, config_json, created_at, updated_at) VALUES (?,?,?,?)",
                    ("インポート(config.json)", json.dumps(data, ensure_ascii=False), now, now),
                )
                pid = int(cur.lastrowid)
                conn.execute(
                    "INSERT OR REPLACE INTO meta (k, v) VALUES (?, ?)",
                    ("last_profile_id", str(pid)),
                )
                conn.commit()
            finally:
                conn.close()

    def count(self) -> int:
        with self._lock:
            conn = self._connect()
            try:
                (n,) = conn.execute("SELECT COUNT(*) FROM profiles").fetchone()
                return int(n)
            finally:
                conn.close()

    def search(self, query: str, limit: int = 500) -> list[tuple[int, str]]:
        q = (query or "").strip()
        with self._lock:
            conn = self._connect()
            try:
                if not q:
                    cur = conn.execute(
                        "SELECT id, display_name FROM profiles ORDER BY updated_at DESC LIMIT ?",
                        (limit,),
                    )
                else:
                    like = f"%{q}%"
                    cur = conn.execute(
                        "SELECT id, display_name FROM profiles WHERE LOWER(display_name) LIKE LOWER(?) "
                        "ORDER BY display_name LIMIT ?",
                        (like, limit),
                    )
                return [(int(r[0]), str(r[1])) for r in cur.fetchall()]
            finally:
                conn.close()

    def get(self, profile_id: int) -> tuple[str, dict[str, Any]] | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT display_name, config_json FROM profiles WHERE id = ?",
                    (profile_id,),
                ).fetchone()
                if not row:
                    return None
                return str(row[0]), json.loads(row[1])
            finally:
                conn.close()

    def create(self, display_name: str, config: dict[str, Any]) -> int:
        if self.count() >= MAX_PROFILES:
            raise RuntimeError(
                f"プロファイルは最大 {MAX_PROFILES:,} 件までです（アカウントまたはサーバー登録の合計）。"
            )
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        blob = json.dumps(config, ensure_ascii=False)
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "INSERT INTO profiles (display_name, config_json, created_at, updated_at) VALUES (?,?,?,?)",
                    (display_name.strip() or "無題", blob, now, now),
                )
                pid = int(cur.lastrowid)
                conn.commit()
                return pid
            finally:
                conn.close()

    def update(self, profile_id: int, display_name: str, config: dict[str, Any]) -> None:
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        blob = json.dumps(config, ensure_ascii=False)
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE profiles SET display_name = ?, config_json = ?, updated_at = ? WHERE id = ?",
                    (display_name.strip() or "無題", blob, now, profile_id),
                )
                if conn.total_changes == 0:
                    raise KeyError(f"プロファイル id={profile_id} が見つかりません")
                conn.commit()
            finally:
                conn.close()

    def delete(self, profile_id: int) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
                conn.commit()
            finally:
                conn.close()

    def get_last_profile_id(self) -> int | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT v FROM meta WHERE k = ?", ("last_profile_id",)).fetchone()
                if not row:
                    return None
                return int(row[0])
            finally:
                conn.close()

    def set_last_profile_id(self, profile_id: int | None) -> None:
        with self._lock:
            conn = self._connect()
            try:
                if profile_id is None:
                    conn.execute("DELETE FROM meta WHERE k = ?", ("last_profile_id",))
                else:
                    conn.execute(
                        "INSERT OR REPLACE INTO meta (k, v) VALUES (?, ?)",
                        ("last_profile_id", str(profile_id)),
                    )
                conn.commit()
            finally:
                conn.close()

    def export_config_json(self, profile_id: int, dest: Path) -> None:
        row = self.get(profile_id)
        if row is None:
            raise KeyError(profile_id)
        _name, cfg = row
        with dest.open("w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
