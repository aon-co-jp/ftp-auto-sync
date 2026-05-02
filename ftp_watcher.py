"""
Watch a local directory and upload changed files to FTP (debounced).
上書き前にリモートの同名ファイルを「名前-YYYY-MM-DD-HHmm.拡張子」へリネームする。
アンカー同期モード時は anchor_sync のマッピングでリモートパスを決める。
"""

from __future__ import annotations

import argparse
import json
import logging
from queue import Queue
import sys
import threading
import time
from datetime import datetime
from ftplib import FTP, error_perm
from pathlib import Path
from typing import Any

from anchor_sync import pick_anchor_auto, split_local_at_anchor, upload_path_parts_for_file
from dotenv import load_dotenv
from ftp_util import ftp_connection
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

LOG = logging.getLogger("ftp_watcher")


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def max_sync_directory_depth_limit(sync_cfg: dict[str, Any]) -> int | None:
    v = sync_cfg.get("max_sync_directory_depth")
    if v is None:
        return None
    try:
        i = int(v)
    except (TypeError, ValueError):
        return None
    if i < 0:
        return None
    return min(i, 10_000)


def _depth_exceeds_sync_limit(
    path: Path,
    local_root: Path,
    sync_cfg: dict[str, Any],
    sync_mapping: dict[str, Any] | None,
) -> bool:
    lim = max_sync_directory_depth_limit(sync_cfg)
    if lim is None:
        return False
    try:
        path.resolve().relative_to(local_root.resolve())
    except ValueError:
        return True
    if sync_mapping and sync_mapping.get("type") == "anchor_auto":
        picked = pick_anchor_auto(path, local_root, sync_mapping)
        if picked is None:
            return True
        _full, _fn, tail_dirs = picked
        return len(tail_dirs) > lim
    if sync_mapping and sync_mapping.get("type") == "anchor":
        an = sync_mapping.get("anchor_name") or ""
        sp = split_local_at_anchor(path, local_root, an) if an else None
        if sp is None:
            return True
        tail_dirs, _fname = sp
        return len(tail_dirs) > lim
    rel = path.resolve().relative_to(local_root.resolve())
    parts = rel.parts
    dir_depth = max(0, len(parts) - 1)
    return dir_depth > lim


def should_skip(
    path: Path,
    local_root: Path,
    cfg: dict[str, Any],
    sync_mapping: dict[str, Any] | None = None,
) -> bool:
    if sync_mapping and sync_mapping.get("type") in ("anchor", "anchor_auto"):
        if upload_path_parts_for_file(path, local_root, sync_mapping) is None:
            return True
    if _depth_exceeds_sync_limit(path, local_root, cfg, sync_mapping):
        return True
    try:
        rel = path.relative_to(local_root)
    except ValueError:
        return True
    parts = rel.parts
    exclude_names = set(cfg.get("exclude_names") or [])
    if any(p in exclude_names for p in parts):
        return True
    ext = path.suffix.lower()
    for e in cfg.get("exclude_extensions") or []:
        if ext == e.lower():
            return True
    return False


def _cwd_create_chain(ftp: FTP, segments: list[str]) -> None:
    for name in segments:
        if not name:
            continue
        try:
            ftp.cwd(name)
        except error_perm:
            try:
                ftp.mkd(name)
            except error_perm:
                pass
            ftp.cwd(name)


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
    LOG.info("リモートの旧版を退避: %s -> %s", filename, candidate)


def upload_file(
    ftp: FTP,
    local_path: Path,
    local_root: Path,
    sync_mapping: dict[str, Any],
    backup_remote_previous: bool = True,
) -> bool:
    parts = upload_path_parts_for_file(local_path, local_root, sync_mapping)
    if parts is None:
        LOG.debug("アップロード対象外（アンカー外など）: %s", local_path)
        return False
    dir_parts, filename = parts

    start = ftp.pwd()
    try:
        _cwd_create_chain(ftp, dir_parts)
        if backup_remote_previous:
            try:
                _archive_remote_previous_version(ftp, filename)
            except Exception:
                LOG.warning(
                    "リモート旧版の退避に失敗しました（そのまま上書きアップロードを試みます）: %s",
                    filename,
                    exc_info=True,
                )
        remote_display = "/".join(dir_parts + [filename])
        LOG.info(
            "UPLOAD %s -> %s (cwd=%s STOR %s)",
            local_path,
            remote_display,
            ftp.pwd(),
            filename,
        )
        with local_path.open("rb") as fh:
            ftp.storbinary(f"STOR {filename}", fh, blocksize=65536)
    finally:
        try:
            ftp.cwd(start)
        except Exception:
            pass
    return True


class DebouncedUploader:
    def __init__(
        self,
        ftp_cfg: dict[str, Any],
        sync_cfg: dict[str, Any],
        local_root: Path,
        sync_mapping: dict[str, Any],
        v2_event_queue: Queue | None = None,
    ) -> None:
        self._ftp_cfg = ftp_cfg
        self._sync_cfg = sync_cfg
        self._local_root = local_root.resolve()
        self._sync_mapping = sync_mapping
        self._v2_event_queue = v2_event_queue
        self._debounce = float(sync_cfg.get("debounce_seconds") or 1.0)
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()
        self._upload_lock = threading.Lock()

    def cancel_all(self) -> None:
        with self._lock:
            for t in self._timers.values():
                t.cancel()
            self._timers.clear()

    def schedule(self, local_path: Path) -> None:
        if not local_path.is_file():
            return
        if should_skip(local_path, self._local_root, self._sync_cfg, self._sync_mapping):
            return
        key = str(local_path.resolve())

        def run() -> None:
            with self._lock:
                self._timers.pop(key, None)
            self._do_upload(local_path)

        with self._lock:
            old = self._timers.pop(key, None)
            if old is not None:
                old.cancel()
            t = threading.Timer(self._debounce, run)
            self._timers[key] = t
            t.daemon = True
            t.start()

    def _do_upload(self, local_path: Path) -> None:
        with self._upload_lock:
            try:
                with ftp_connection(self._ftp_cfg) as ftp:
                    backup = bool(self._sync_cfg.get("backup_remote_previous", True))
                    ok = upload_file(
                        ftp,
                        local_path,
                        self._local_root,
                        self._sync_mapping,
                        backup_remote_previous=backup,
                    )
                    if (
                        ok
                        and self._v2_event_queue is not None
                        and self._sync_cfg.get("v2_git_ai_prompt")
                    ):
                        try:
                            self._v2_event_queue.put_nowait(
                                {"kind": "upload", "path": str(local_path.resolve())}
                            )
                        except Exception:
                            pass
            except Exception:
                LOG.exception("アップロード失敗: %s", local_path)


class SyncEventHandler(FileSystemEventHandler):
    def __init__(
        self,
        uploader: DebouncedUploader,
        local_root: Path,
        sync_cfg: dict[str, Any],
        v2_event_queue: Queue | None,
    ) -> None:
        super().__init__()
        self._uploader = uploader
        self._local_root = local_root.resolve()
        self._sync_cfg = sync_cfg
        self._v2_event_queue = v2_event_queue

    def on_any_event(self, event: FileSystemEvent) -> None:
        if (
            self._v2_event_queue is not None
            and self._sync_cfg.get("v2_git_ai_prompt")
            and event.event_type == "moved"
        ):
            try:
                src_p = Path(event.src_path)
                dest_p = Path(event.dest_path)
                lr = str(self._local_root)
                if str(src_p.resolve()).startswith(lr) or str(dest_p.resolve()).startswith(
                    lr
                ):
                    self._v2_event_queue.put_nowait(
                        {
                            "kind": "rename",
                            "src": str(src_p),
                            "dest": str(dest_p),
                            "is_dir": event.is_directory,
                        }
                    )
            except Exception:
                LOG.exception("Ver2 rename queue")

        if event.is_directory:
            return
        if event.event_type not in ("modified", "created", "moved"):
            return
        path = Path(event.dest_path if event.event_type == "moved" else event.src_path)
        if not str(path.resolve()).startswith(str(self._local_root)):
            return
        self._uploader.schedule(path)


class WatcherService:
    """GUI / CLI: sync_mapping は呼び出し元で prepare_anchor_sync_or_legacy 済み。"""

    def __init__(
        self,
        config_source: Path | dict[str, Any],
        sync_mapping: dict[str, Any],
        v2_event_queue: Queue | None = None,
    ) -> None:
        self._config_source = config_source
        self._sync_mapping = sync_mapping
        self._v2_event_queue = v2_event_queue
        self._observer: Observer | None = None
        self._uploader: DebouncedUploader | None = None

    def _load_raw_config(self) -> dict[str, Any]:
        if isinstance(self._config_source, dict):
            return dict(self._config_source)
        return load_config(self._config_source)

    def start(self) -> None:
        load_dotenv()
        raw = self._load_raw_config()
        ftp_cfg = raw["ftp"]
        sync_cfg = raw["sync"]
        local_root = Path(sync_cfg["local_root"]).expanduser().resolve()
        if not local_root.is_dir():
            raise RuntimeError(f"local_root が存在しません: {local_root}")

        self._uploader = DebouncedUploader(
            ftp_cfg,
            sync_cfg,
            local_root,
            self._sync_mapping,
            v2_event_queue=self._v2_event_queue,
        )
        handler = SyncEventHandler(
            self._uploader,
            local_root,
            sync_cfg,
            self._v2_event_queue,
        )
        observer = Observer()
        recursive = bool(sync_cfg.get("recursive", True))
        observer.schedule(handler, str(local_root), recursive=recursive)
        observer.start()
        self._observer = observer
        mode = self._sync_mapping.get("type", "legacy")
        LOG.info(
            "監視開始: %s (recursive=%s) mode=%s -> FTP %s:%s",
            local_root,
            recursive,
            mode,
            ftp_cfg["host"],
            ftp_cfg.get("port") or 21,
        )

    def stop(self) -> None:
        if self._uploader is not None:
            self._uploader.cancel_all()
            self._uploader = None
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=20)
            self._observer = None
        LOG.info("監視を終了しました。")


def _cli_ask_yes_no(title: str, message: str) -> bool:
    print("\n" + "=" * 60)
    print(title)
    print(message)
    print("=" * 60)
    a = input("続行しますか？ [y/N]: ").strip().lower()
    return a in ("y", "yes")


def run_watcher(config_path: Path) -> None:
    load_dotenv()
    cfg = load_config(config_path)
    from anchor_sync import prepare_anchor_sync_or_legacy

    mapping = prepare_anchor_sync_or_legacy(cfg, _cli_ask_yes_no, profile_id=None)
    if mapping is None:
        LOG.info("ユーザーがキャンセルしたため終了します。")
        return
    svc = WatcherService(config_path, mapping)
    svc.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        LOG.info("終了します…")
    finally:
        svc.stop()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    p = argparse.ArgumentParser(description="ローカル変更をFTPへ自動アップロード（CLI）")
    p.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent / "config.json",
        help="設定JSONのパス",
    )
    args = p.parse_args()
    if not args.config.is_file():
        LOG.error("設定ファイルがありません: %s", args.config)
        LOG.error("config.example.json をコピーして config.json を作成するか、GUI で保存してください。")
        sys.exit(1)
    run_watcher(args.config)


if __name__ == "__main__":
    main()
