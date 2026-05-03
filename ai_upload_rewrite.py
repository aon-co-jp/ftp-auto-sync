"""アップロード直前のテキスト書き換え（OpenAI 互換 API）と Cursor 起動。"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from cursor_launch import try_launch_cursor_for_file

LOG = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"```(?:[a-zA-Z0-9]*)\s*\n(.*?)```", re.DOTALL)


def _allowed_by_extension(filename: str, sync_cfg: dict[str, Any]) -> bool:
    raw = (sync_cfg.get("ai_rewrite_extensions") or "").strip()
    suf = Path(filename).suffix.lower()
    if not raw:
        return suf in {
            ".html",
            ".htm",
            ".php",
            ".css",
            ".js",
            ".mjs",
            ".json",
            ".xml",
            ".txt",
            ".md",
            ".vue",
            ".ts",
            ".tsx",
        }
    allowed = set()
    for x in raw.split(","):
        x = x.strip().lower()
        if not x:
            continue
        allowed.add(x if x.startswith(".") else f".{x}")
    return suf in allowed


def _openai_rewrite_bytes(
    data: bytes,
    filename: str,
    rel_posix: str,
    sync_cfg: dict[str, Any],
    ai_cfg: dict[str, Any],
    *,
    deploy_context: str | None,
    instr: str,
) -> bytes:
    key = (ai_cfg.get("openai_api_key") or "").strip()
    if not key:
        return data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    max_in = int(sync_cfg.get("ai_rewrite_max_input_chars") or 120_000)
    if len(text) > max_in:
        text = text[:max_in] + "\n\n…(truncated for AI rewrite)…\n"

    base = (ai_cfg.get("openai_base_url") or "https://api.openai.com/v1").rstrip("/")
    model = (ai_cfg.get("openai_model") or "gpt-4o-mini").strip()
    url = base + "/chat/completions"
    ctx = deploy_context or "(main / single upload)"
    system = (
        "You rewrite file contents for multi-site / multi-folder FTP deploys. "
        "Follow the user's policy exactly. Preserve structure unless policy says otherwise. "
        "Output ONLY the rewritten file body: no markdown fences, no preamble or commentary."
    )
    user = (
        f"【プロファイルに保存された書き換え方針・ルール】\n{instr}\n\n"
        f"【現在の相対パス】\n{rel_posix}\n"
        f"【デプロイ文脈】\n{ctx}\n\n"
        f"【ファイル名】\n{filename}\n\n"
        f"【元のファイル本文】\n{text}"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": int(sync_cfg.get("ai_rewrite_max_output_tokens") or 16_000),
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            out = json.loads(resp.read().decode("utf-8"))
        body = (
            out.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        if not body:
            return data
        m = _FENCE_RE.search(body)
        if m:
            body = m.group(1).strip()
        return body.encode("utf-8")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:400]
        LOG.warning("AI 書き換え HTTP エラー: %s %s", e.code, err)
        return data
    except Exception as e:
        LOG.warning("AI 書き換え失敗（元ファイルのまま）: %s", e)
        return data


def maybe_ai_rewrite_bytes(
    data: bytes,
    filename: str,
    rel_posix: str,
    sync_cfg: dict[str, Any],
    ai_cfg: dict[str, Any],
    *,
    deploy_context: str | None = None,
    source_path: Path | None = None,
) -> bytes:
    """
    ai_rewrite_on_upload が真かつ方針文があるとき:
    - API キーがあれば OpenAI 互換で本文を書き換え
    - ai_rewrite_launch_cursor が真なら対象ファイルで Cursor を起動（無料枠のエディタ AI を利用可能）
    """
    if not bool(sync_cfg.get("ai_rewrite_on_upload")):
        return data
    instr = (sync_cfg.get("ai_rewrite_instruction") or "").strip()
    if not instr:
        return data

    use_cursor = bool(sync_cfg.get("ai_rewrite_launch_cursor", False))
    key = (ai_cfg.get("openai_api_key") or "").strip()
    ext_ok = _allowed_by_extension(filename, sync_cfg)

    if not key and not use_cursor:
        LOG.debug(
            "AI 書き換え: API キーも Cursor 起動も無効のためスキップ (%s)",
            rel_posix,
        )
        return data

    out = data
    if key and ext_ok:
        out = _openai_rewrite_bytes(
            data,
            filename,
            rel_posix,
            sync_cfg,
            ai_cfg,
            deploy_context=deploy_context,
            instr=instr,
        )
    elif use_cursor and ext_ok and not key:
        LOG.info(
            "OpenAI API キーなし: サーバー送信バイトは未変換。Cursor 起動のみ行います (%s)",
            rel_posix,
        )

    if use_cursor and source_path is not None and ext_ok:
        try_launch_cursor_for_file(source_path)

    return out
