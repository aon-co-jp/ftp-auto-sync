"""FTP 接続（watchdog 同期・探索で共用）。"""
from __future__ import annotations

import os
from contextlib import contextmanager
from ftplib import FTP, FTP_TLS
from typing import Any


def resolve_ftp_password(ftp_cfg: dict[str, Any]) -> str:
    pw = ftp_cfg.get("password")
    if pw is not None and str(pw).strip():
        return str(pw)
    env_key = ftp_cfg.get("password_env") or "FTP_PASSWORD"
    return os.environ.get(env_key, "")


@contextmanager
def ftp_connection(ftp_cfg: dict[str, Any]):
    host = ftp_cfg["host"]
    port = int(ftp_cfg.get("port") or 21)
    user = ftp_cfg["username"]
    password = resolve_ftp_password(ftp_cfg)
    if not password:
        env_key = ftp_cfg.get("password_env") or "FTP_PASSWORD"
        raise RuntimeError(
            f"FTP パスワードがありません。設定の password か環境変数 {env_key} を設定してください。"
        )
    timeout = int(ftp_cfg.get("timeout") or 60)
    use_tls = bool(ftp_cfg.get("use_tls"))
    passive = bool(ftp_cfg.get("passive", True))

    if use_tls:
        client: FTP | FTP_TLS = FTP_TLS()
        client.connect(host, port, timeout=timeout)
        client.login(user, password)
        client.prot_p()
    else:
        client = FTP()
        client.connect(host, port, timeout=timeout)
        client.login(user, password)

    client.set_pasv(passive)
    try:
        yield client
    finally:
        try:
            client.quit()
        except Exception:
            client.close()
