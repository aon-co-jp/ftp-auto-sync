"""
監視ルート相対パスに対する「既定で同期しない／★除外／〻同期」の判定。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from paths import app_data_dir


def _norm_rel(s: str) -> str:
    return s.strip().replace("\\", "/").strip("/")


def _roots_from_cfg(raw: Any) -> list[str]:
    if isinstance(raw, str):
        lines = [ln.strip() for ln in raw.replace("\r\n", "\n").split("\n")]
        return [_norm_rel(x) for x in lines if _norm_rel(x)]
    if isinstance(raw, list):
        return [_norm_rel(str(x)) for x in raw if _norm_rel(str(x))]
    return []


def _under_prefix(rel: str, root: str) -> bool:
    r = _norm_rel(rel)
    p = _norm_rel(root)
    if not p:
        return False
    return r == p or r.startswith(p + "/")


def rel_posix_under_root(path: Path, local_root: Path) -> str | None:
    try:
        return path.resolve().relative_to(local_root.resolve()).as_posix()
    except ValueError:
        return None


def is_under_app_datadir(path: Path) -> bool:
    try:
        path.resolve().relative_to(app_data_dir().resolve())
        return True
    except ValueError:
        return False


def _dir_segments_for_rel(rel: str, path_is_file: bool) -> list[str]:
    parts = [p for p in rel.split("/") if p]
    if not parts:
        return []
    if path_is_file and len(parts) >= 1:
        return parts[:-1]
    return parts


def _rel_has_domain_like_folder(rel: str, path_is_file: bool) -> bool:
    """フォルダ名に . を含む階層（例: example.com）がパス上にあれば真。"""
    for seg in _dir_segments_for_rel(rel, path_is_file):
        if "." in seg:
            return True
    return False


def should_skip_sync_scope(
    path: Path,
    local_root: Path,
    sync_cfg: dict[str, Any],
) -> bool:
    """
    True のとき自動同期（アップロード）の対象外。
    優先: ★除外リスト → アプリデータ配下スキップ → 〻同期でドメイン要件免除。
    sync_default_domain_scope が真のときのみ、ドメイン風フォルダ（名前に「.」を含む階層）が無いパスを除外。
    """
    rel = rel_posix_under_root(path, local_root)
    if rel is None:
        return True

    stars = _roots_from_cfg(sync_cfg.get("sync_star_exclude_rel_roots"))
    for star in stars:
        if _under_prefix(rel, star):
            return True

    marks = _roots_from_cfg(sync_cfg.get("sync_mark_include_rel_roots"))
    for m in marks:
        if _under_prefix(rel, m):
            return False

    if bool(sync_cfg.get("sync_skip_under_app_datadir", True)):
        if is_under_app_datadir(path):
            return True

    # 既定 False: ドメイン風フォルダが無いだけで同期しないと、一般プロジェクトで一切アップロードされない
    if bool(sync_cfg.get("sync_default_domain_scope", False)):
        if not _rel_has_domain_like_folder(rel, path.is_file()):
            return True

    return False
