"""FTP 接続（watchdog 同期・探索で共用）。"""
from __future__ import annotations

import os
import socket
from contextlib import contextmanager
from ftplib import FTP, FTP_TLS, error_perm
from typing import Any


def resolve_ftp_password(ftp_cfg: dict[str, Any]) -> str:
    pw = ftp_cfg.get("password")
    if pw is not None and str(pw).strip():
        return str(pw)
    env_key = ftp_cfg.get("password_env") or "FTP_PASSWORD"
    return os.environ.get(env_key, "")


def resolve_ftp_auth_key(ftp_cfg: dict[str, Any]) -> str:
    """FTP ACCT（第二認証・ホストが要求する認証キー）。プロファイルまたは環境変数。"""
    ak = ftp_cfg.get("auth_key")
    if ak is not None and str(ak).strip():
        return str(ak).strip()
    env_key = (ftp_cfg.get("auth_key_env") or "FTP_AUTH_KEY").strip() or "FTP_AUTH_KEY"
    return os.environ.get(env_key, "")


def _is_anonymous_user(username: str) -> bool:
    u = (username or "").strip().lower()
    return u in ("anonymous", "ftp")


def format_ftp_login_error(exc: Exception, *, host: str) -> str:
    """接続失敗など（ログイン前）のユーザー向けメッセージ。"""
    if isinstance(exc, (socket.gaierror, OSError)):
        return (
            f"サーバー「{host}」に接続できませんでした（ホスト名の誤り・ネットワーク・ファイアウォール等を確認してください）。\n"
            f"詳細: {exc}"
        )
    return f"FTP エラー: {exc}"


def _format_error_perm_login(raw: str, low: str, auth_key_env: str) -> str:
    if "332" in raw or "need account" in low:
        return (
            "追加の認証（認証キー / ACCT）が必要です。接続設定の「認証キー」に入力するか、"
            f"環境変数 {auth_key_env} に設定してください。\n"
            f"サーバー応答: {raw}"
        )
    if "530" in raw or "not logged in" in low or "authentication" in low or "incorrect" in low:
        return (
            "FTP のログインに失敗しました。ユーザー名またはパスワードが間違っている可能性があります。\n"
            f"サーバー応答: {raw}"
        )
    return f"FTP ログインが拒否されました: {raw}"


def test_ftp_login(ftp_cfg: dict[str, Any]) -> tuple[bool, str]:
    """接続テスト。成功時 (True, 'OK')、失敗時 (False, メッセージ)。"""
    try:
        with ftp_connection(ftp_cfg) as ftp:
            ftp.voidcmd("NOOP")
        return True, "OK"
    except Exception as e:
        host = str(ftp_cfg.get("host") or "")
        if isinstance(e, RuntimeError) and str(e):
            return False, str(e)
        return False, format_ftp_login_error(e, host=host)


@contextmanager
def ftp_connection(ftp_cfg: dict[str, Any]):
    host = (ftp_cfg.get("host") or "").strip()
    if not host:
        raise RuntimeError("FTP ホストが空です。")
    port = int(ftp_cfg.get("port") or 21)
    user = (ftp_cfg.get("username") or "").strip()
    password = resolve_ftp_password(ftp_cfg)
    auth_key_env = (ftp_cfg.get("auth_key_env") or "FTP_AUTH_KEY").strip() or "FTP_AUTH_KEY"
    auth_key = resolve_ftp_auth_key(ftp_cfg)

    if not password and not _is_anonymous_user(user):
        env_key = ftp_cfg.get("password_env") or "FTP_PASSWORD"
        raise RuntimeError(
            f"FTP パスワードがありません。パスワード欄に入力するか、環境変数 {env_key} を設定してください。"
        )

    timeout = int(ftp_cfg.get("timeout") or 60)
    use_tls = bool(ftp_cfg.get("use_tls"))
    passive = bool(ftp_cfg.get("passive", True))

    def _make_plain_ftp() -> FTP:
        try:
            return FTP(encoding="utf-8")
        except TypeError:
            return FTP()

    def _make_tls_ftp() -> FTP_TLS:
        try:
            return FTP_TLS(encoding="utf-8")
        except TypeError:
            return FTP_TLS()

    try:
        if use_tls:
            client = _make_tls_ftp()
            client.connect(host, port, timeout=timeout)
        else:
            client = _make_plain_ftp()
            client.connect(host, port, timeout=timeout)
    except (socket.gaierror, OSError) as e:
        raise RuntimeError(format_ftp_login_error(e, host=host)) from e

    try:
        if auth_key:
            client.login(user, password, auth_key)
        else:
            client.login(user, password)
    except error_perm as e:
        raw = str(e).strip()
        low = raw.lower()
        raise RuntimeError(_format_error_perm_login(raw, low, auth_key_env)) from e

    if use_tls:
        try:
            client.prot_p()
        except Exception as e:
            try:
                client.quit()
            except Exception:
                client.close()
            raise RuntimeError(
                f"FTPS の保護データチャネル（PROT P）の有効化に失敗しました。TLS の設定を確認してください。\n詳細: {e}"
            ) from e

    client.set_pasv(passive)
    try:
        yield client
    finally:
        try:
            client.quit()
        except Exception:
            try:
                client.close()
            except Exception:
                pass
