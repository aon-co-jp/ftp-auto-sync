"""
マルチデプロイ: 最大50ターゲットへ、条件に合うファイルを書き換えたうえで FTP アップロード。
メインのマッピング（アンカー等）に remote_append_path を足し込む。

置換ルール（各行）: 左側に「検索文字列1|検索文字列2|…」、TAB、右に置換後。
左の各セグメントを順に同じ置換後へ str.replace する。旧形式（| なし1語）もそのまま有効。
"""
from __future__ import annotations

import fnmatch
import logging
from datetime import datetime
from ftplib import FTP, error_perm
from io import BytesIO
from pathlib import Path
from typing import Any

from ai_upload_rewrite import maybe_ai_rewrite_bytes
from anchor_sync import _cwd_create_chain, upload_path_parts_for_file
from ftp_mtime import should_upload_local_newer
from ftp_util import ftp_connection

LOG = logging.getLogger(__name__)

MAX_DEPLOY_TARGETS = 50

_DEFAULT_TEXT_EXT = frozenset(
    {
        ".html",
        ".htm",
        ".php",
        ".css",
        ".js",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",
        ".jsx",
        ".txt",
        ".json",
        ".xml",
        ".md",
        ".env",
        ".vue",
        ".svelte",
        ".scss",
        ".less",
        ".yaml",
        ".yml",
    }
)


def normalize_deploy_targets(raw: Any) -> list[dict[str, Any]]:
    """最大50件に整形。欠けているキーを補う。"""
    if not isinstance(raw, list):
        return [_empty_slot(i) for i in range(MAX_DEPLOY_TARGETS)]
    out: list[dict[str, Any]] = []
    for i, item in enumerate(raw[:MAX_DEPLOY_TARGETS]):
        if not isinstance(item, dict):
            out.append(_empty_slot(i))
            continue
        d = dict(item)
        d.setdefault("enabled", False)
        d.setdefault("label", f"指定{i + 1}")
        d.setdefault("use_main_ftp", True)
        d.setdefault("host", "")
        d.setdefault("port", 21)
        d.setdefault("username", "")
        d.setdefault("password", "")
        d.setdefault("use_tls", False)
        d.setdefault("passive", True)
        d.setdefault("remote_append_path", "")
        d.setdefault("local_path_contains", "")
        d.setdefault("local_path_prefix", "")
        d.setdefault("filename_glob", "")
        d.setdefault("rewrite_pairs", [])
        d.setdefault("rewrite_extensions", "")
        out.append(d)
    while len(out) < MAX_DEPLOY_TARGETS:
        out.append(_empty_slot(len(out)))
    return out[:MAX_DEPLOY_TARGETS]


def _empty_slot(index: int) -> dict[str, Any]:
    return {
        "enabled": False,
        "label": f"指定{index + 1}",
        "use_main_ftp": True,
        "host": "",
        "port": 21,
        "username": "",
        "password": "",
        "use_tls": False,
        "passive": True,
        "remote_append_path": "",
        "local_path_contains": "",
        "local_path_prefix": "",
        "filename_glob": "",
        "rewrite_pairs": [],
        "rewrite_extensions": "",
    }


def target_matches(target: dict[str, Any], rel_posix: str, filename: str) -> bool:
    if not target.get("enabled"):
        return False
    rel_norm = rel_posix.replace("\\", "/")
    sub = (target.get("local_path_contains") or "").strip()
    if sub and sub.lower() not in rel_norm.lower():
        return False
    pref = (target.get("local_path_prefix") or "").strip().replace("\\", "/")
    if pref:
        pref = pref.strip("/")
        rel_cmp = rel_norm.strip()
        if pref and not (
            rel_cmp == pref or rel_cmp.startswith(pref + "/")
        ):
            return False
    globs = (target.get("filename_glob") or "").strip()
    if globs:
        ok = False
        for pat in globs.split(";"):
            pat = pat.strip()
            if not pat:
                continue
            if fnmatch.fnmatch(filename, pat):
                ok = True
                break
        if not ok:
            return False
    return True


def merged_ftp_cfg(main_ftp: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    if target.get("use_main_ftp", True):
        return dict(main_ftp)
    out = dict(main_ftp)
    if (target.get("host") or "").strip():
        out["host"] = str(target["host"]).strip()
    try:
        out["port"] = int(target.get("port") or 21)
    except (TypeError, ValueError):
        out["port"] = 21
    if (target.get("username") or "").strip():
        out["username"] = str(target["username"]).strip()
    pw = target.get("password")
    if pw is not None and str(pw).strip():
        out["password"] = str(pw)
    out["use_tls"] = bool(target.get("use_tls"))
    out["passive"] = bool(target.get("passive", True))
    return out


def append_remote_segments(dir_parts: list[str], target: dict[str, Any]) -> list[str]:
    app = (target.get("remote_append_path") or "").strip().replace("\\", "/").strip("/")
    if not app:
        return list(dir_parts)
    extra = [x for x in app.split("/") if x]
    return list(dir_parts) + extra


def _should_rewrite_body(filename: str, target: dict[str, Any]) -> bool:
    raw_ext = Path(filename).suffix.lower()
    custom = (target.get("rewrite_extensions") or "").strip()
    if custom:
        allowed = set()
        for x in custom.split(","):
            x = x.strip().lower()
            if not x:
                continue
            allowed.add(x if x.startswith(".") else f".{x}")
        return raw_ext in allowed
    return raw_ext in _DEFAULT_TEXT_EXT


def build_payload(
    local_path: Path,
    target: dict[str, Any],
    *,
    rel_posix: str,
    sync_cfg: dict[str, Any] | None = None,
    ai_cfg: dict[str, Any] | None = None,
    deploy_label: str | None = None,
) -> bytes:
    data = local_path.read_bytes()
    pairs = target.get("rewrite_pairs") or []
    if pairs and _should_rewrite_body(local_path.name, target):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            LOG.debug("UTF-8 でないため書き換えスキップ: %s", local_path)
        else:
            for pair in pairs:
                if not isinstance(pair, dict):
                    continue
                find_block = pair.get("find")
                if find_block is None:
                    continue
                rep = pair.get("replace")
                if rep is None:
                    rep = ""
                rep_s = str(rep)
                for seg in str(find_block).split("|"):
                    seg = seg.strip()
                    if seg:
                        text = text.replace(seg, rep_s)
            data = text.encode("utf-8")
    if sync_cfg is not None and ai_cfg is not None:
        data = maybe_ai_rewrite_bytes(
            data,
            local_path.name,
            rel_posix,
            sync_cfg,
            ai_cfg,
            deploy_context=deploy_label,
            source_path=local_path,
        )
    return data


def _remote_file_exists(ftp: FTP, name: str) -> bool:
    try:
        s = ftp.size(name)
        if s is not None and s >= 0:
            return True
    except Exception:
        pass
    try:
        nl = ftp.nlst()
        if name in nl:
            return True
        return any(Path(x).name == name for x in nl)
    except Exception:
        return False


def _ftp_rename(ftp: FTP, old: str, new: str) -> None:
    resp = ftp.sendcmd(f"RNFR {old}")
    if not str(resp).startswith("350"):
        raise error_perm(resp)
    ftp.voidcmd(f"RNTO {new}")


def _archive_remote_previous_version(ftp: FTP, filename: str) -> None:
    if not _remote_file_exists(ftp, filename):
        return
    p = Path(filename)
    stem, suff = p.stem, p.suffix
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    candidate = f"{stem}-{stamp}{suff}"
    seq = 0
    while _remote_file_exists(ftp, candidate):
        seq += 1
        candidate = f"{stem}-{stamp}-{seq}{suff}"
    _ftp_rename(ftp, filename, candidate)
    LOG.info("マルチデプロイ: リモート旧版を退避 %s -> %s", filename, candidate)


def upload_payload(
    ftp: FTP,
    dir_parts: list[str],
    filename: str,
    payload: bytes,
    backup_remote_previous: bool,
    *,
    local_path: Path | None = None,
    sync_cfg: dict[str, Any] | None = None,
) -> bool:
    """True = STOR した。False = 新しさ条件でスキップ。"""
    start = ftp.pwd()
    try:
        _cwd_create_chain(ftp, dir_parts)
        if local_path is not None and sync_cfg is not None:
            if not should_upload_local_newer(ftp, filename, local_path, sync_cfg):
                return False
        if backup_remote_previous:
            try:
                _archive_remote_previous_version(ftp, filename)
            except Exception:
                LOG.warning(
                    "マルチデプロイ: リモート旧版退避に失敗（上書き継続）: %s",
                    filename,
                    exc_info=True,
                )
        rd = "/".join(dir_parts + [filename])
        LOG.info(
            "MULTI-UPLOAD cwd=%s STOR %s -> %s",
            ftp.pwd(),
            filename,
            rd,
        )
        bio = BytesIO(payload)
        ftp.storbinary(f"STOR {filename}", bio, blocksize=65536)
        return True
    finally:
        try:
            ftp.cwd(start)
        except Exception:
            pass


def run_multi_deploy_uploads(
    main_ftp_cfg: dict[str, Any],
    sync_cfg: dict[str, Any],
    local_root: Path,
    sync_mapping: dict[str, Any],
    local_path: Path,
    *,
    backup_remote_previous: bool,
    mode: str,
    ai_cfg: dict[str, Any] | None = None,
) -> tuple[int, int, list[str]]:
    """
    mode: additional | targets_only
    戻り値: (成功した転送回数, 試行したターゲット数, エラー文言リスト)
    """
    targets = normalize_deploy_targets(sync_cfg.get("deploy_targets"))
    parts = upload_path_parts_for_file(local_path, local_root, sync_mapping)
    if parts is None:
        return 0, 0, ["マッピング対象外のためマルチデプロイできません。"]

    base_dir, filename = parts
    try:
        rel = local_path.resolve().relative_to(local_root.resolve()).as_posix()
    except ValueError:
        rel = local_path.name

    matching = [t for t in targets if target_matches(t, rel, filename)]
    errors: list[str] = []
    ok_count = 0
    attempts = 0

    def do_default_upload() -> bool:
        nonlocal ok_count
        try:
            with ftp_connection(main_ftp_cfg) as ftp:
                payload = build_payload(
                    local_path,
                    {},
                    rel_posix=rel,
                    sync_cfg=sync_cfg,
                    ai_cfg=ai_cfg or {},
                    deploy_label="default FTP",
                )
                did = upload_payload(
                    ftp,
                    list(base_dir),
                    filename,
                    payload,
                    backup_remote_previous,
                    local_path=local_path,
                    sync_cfg=sync_cfg,
                )
            if did:
                ok_count += 1
            return True
        except Exception as e:
            errors.append(f"既定FTP: {e}")
            LOG.exception("マルチデプロイ: 既定アップロード失敗")
            return False

    if mode == "additional":
        attempts += 1
        do_default_upload()

    for t in matching:
        attempts += 1
        label = (t.get("label") or "?").strip()
        try:
            cfg = merged_ftp_cfg(main_ftp_cfg, t)
            dir_parts = append_remote_segments(list(base_dir), t)
            payload = build_payload(
                local_path,
                t,
                rel_posix=rel,
                sync_cfg=sync_cfg,
                ai_cfg=ai_cfg or {},
                deploy_label=label,
            )
            with ftp_connection(cfg) as ftp:
                did = upload_payload(
                    ftp,
                    dir_parts,
                    filename,
                    payload,
                    backup_remote_previous,
                    local_path=local_path,
                    sync_cfg=sync_cfg,
                )
            if did:
                ok_count += 1
                LOG.info("マルチデプロイ成功: %s", label)
        except Exception as e:
            errors.append(f"{label}: {e}")
            LOG.warning("マルチデプロイ失敗 (%s): %s", label, e, exc_info=True)

    if mode == "targets_only" and not matching:
        errors.append("条件に合うターゲットがありません（既定FTPにも送らない設定です）。")

    return ok_count, attempts, errors
