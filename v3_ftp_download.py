"""
Ver3: FTP（レンタルサーバー）→ ローカルへの再帰ダウンロード（逆同期）。
サーバー上に存在するディレクトリ・ファイルのみを取得します（ローカルの余分なファイルは削除しません）。
"""
from __future__ import annotations

import logging
from ftplib import FTP
from pathlib import Path
from typing import Any

from anchor_sync import _cwd_create_chain
from ftp_util import ftp_connection

LOG = logging.getLogger(__name__)


def _safe_name(name: str) -> bool:
    if not name or name in (".", ".."):
        return False
    if "/" in name or "\\" in name:
        return False
    return True


def _is_dir(ftp: FTP, name: str) -> bool:
    try:
        ftp.cwd(name)
        ftp.cwd("..")
        return True
    except Exception:
        return False


def list_dir_entries(ftp: FTP) -> list[tuple[str, bool]]:
    """(名前, ディレクトリか) のリスト。MLSD が使えなければ NLST + 試行。"""
    try:
        out: list[tuple[str, bool]] = []
        for name, facts in ftp.mlsd():
            if not _safe_name(name):
                continue
            t = (facts.get("type") or "").lower()
            if t == "dir":
                out.append((name, True))
            elif t == "file":
                out.append((name, False))
            elif t in ("cdir", "pdir"):
                continue
            else:
                out.append((name, _is_dir(ftp, name)))
        return out
    except Exception as e:
        LOG.debug("MLSD 利用不可のため NLST にフォールバックします: %s", e)
        return _list_entries_nlst(ftp)


def _list_entries_nlst(ftp: FTP) -> list[tuple[str, bool]]:
    try:
        raw = ftp.nlst()
    except Exception:
        return []
    names = sorted({Path(x).name for x in raw if _safe_name(Path(x).name)})
    out: list[tuple[str, bool]] = []
    for name in names:
        out.append((name, _is_dir(ftp, name)))
    return out


def _download_recursive(ftp: FTP, local_dir: Path) -> tuple[int, int]:
    """現在の FTP cwd の内容を local_dir に再帰コピー。戻り値: (ファイル数, 作成したディレクトリ数)。"""
    files_n = 0
    dirs_n = 0
    local_dir.mkdir(parents=True, exist_ok=True)

    try:
        entries = list_dir_entries(ftp)
    except Exception as e:
        LOG.warning("ディレクトリ一覧の取得に失敗しました (%s): %s", local_dir, e)
        return 0, 0

    for name, is_dir in entries:
        if not _safe_name(name):
            continue
        if is_dir:
            try:
                ftp.cwd(name)
            except Exception as e:
                LOG.warning("フォルダに入れませんでした（スキップ）: %s / %s", name, e)
                continue
            sub_local = local_dir / name
            df, dd = _download_recursive(ftp, sub_local)
            files_n += df
            dirs_n += dd + 1
            try:
                ftp.cwd("..")
            except Exception:
                LOG.exception("親ディレクトリへ戻れませんでした")
                raise
        else:
            dest = local_dir / name
            part = dest.with_suffix(dest.suffix + ".part")
            try:
                with part.open("wb") as fh:
                    ftp.retrbinary(f"RETR {name}", fh.write, blocksize=65536)
                part.replace(dest)
                files_n += 1
                LOG.info("GET %s", dest)
            except Exception as e:
                LOG.warning("ファイル取得に失敗しました（スキップ）: %s — %s", dest, e)
                try:
                    if part.is_file():
                        part.unlink()
                except OSError:
                    pass

    return files_n, dirs_n


def remote_path_to_segments(remote_unix_path: str) -> list[str]:
    s = (remote_unix_path or "").strip().replace("\\", "/").strip("/")
    return [x for x in s.split("/") if x]


def run_reverse_sync(
    ftp_cfg: dict[str, Any],
    remote_unix_path: str,
    local_destination: Path,
) -> tuple[int, int, str | None]:
    """
    サーバー上の remote_unix_path を起点に、配下をすべてローカルへダウンロードする。
    戻り値: (取得ファイル数, 作成したディレクトリ数, 致命的エラー時メッセージ)
    """
    local_destination = local_destination.expanduser().resolve()
    segs = remote_path_to_segments(remote_unix_path)

    try:
        local_destination.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return 0, 0, f"ローカル保存先を作成できません: {local_destination}\n{e}"

    try:
        with ftp_connection(ftp_cfg) as ftp:
            try:
                _cwd_create_chain(ftp, segs)
            except Exception as e:
                return 0, 0, f"FTP 上の起点パスへ移動できません: {remote_unix_path or '(ログイン先)'}\n{e}"
            LOG.info(
                "Ver3 逆同期開始: リモート cwd=%s → ローカル %s",
                ftp.pwd(),
                local_destination,
            )
            fc, dc = _download_recursive(ftp, local_destination)
            return fc, dc, None
    except RuntimeError as e:
        return 0, 0, str(e)
    except Exception as e:
        LOG.exception("Ver3 逆同期")
        return 0, 0, str(e)
