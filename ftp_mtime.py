"""FTP MDTM とローカル更新日時の比較（ローカルの方が新しいときだけアップロード）。"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ftplib import FTP

LOG = logging.getLogger(__name__)

_MDTM_RE = re.compile(r"^213\s+(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})")


def ftp_mdtm_unix(ftp: FTP, filename: str) -> float | None:
    """リモートファイルの更新時刻（UTC epoch）。無い／失敗時は None。"""
    try:
        resp = ftp.sendcmd(f"MDTM {filename}")
    except Exception:
        return None
    m = _MDTM_RE.match(str(resp).strip())
    if not m:
        return None
    y, mo, d, h, mi, s = (int(x) for x in m.groups())
    try:
        dt = datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def should_upload_local_newer(
    ftp: FTP,
    filename: str,
    local_path: Path,
    sync_cfg: dict[str, Any],
) -> bool:
    """only_upload_if_local_newer が真のとき、ローカルがリモートより明らかに新しい場合のみ True（既定 True / V3.5）。"""
    if not bool(sync_cfg.get("only_upload_if_local_newer", True)):
        return True
    try:
        local_ts = local_path.stat().st_mtime
    except OSError:
        return False
    remote_ts = ftp_mdtm_unix(ftp, filename)
    if remote_ts is None:
        return True
    skew = float(sync_cfg.get("upload_time_skew_seconds") or 2.0)
    if local_ts > remote_ts + skew:
        return True
    LOG.info(
        "SKIP UPLOAD（サーバー上の方が新しいか同時刻）: %s local=%s remote_utc=%s",
        local_path,
        time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(local_ts)),
        time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(remote_ts)),
    )
    return False
