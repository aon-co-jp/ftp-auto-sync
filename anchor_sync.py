"""
アンカーフォルダ名でローカルとリモートの階層を揃えた同期用の準備・パス解決。
- リモートは remote_root 以下を最大 max_anchor_search_depth 階層まで探索し、同名フォルダを候補にする。
- 承認内容（候補一覧・採用パス）の署名が前回と同じなら確認を省略。
- API キーがある場合は OpenAI 互換の chat/completions で確認文を生成。
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from ftplib import FTP, error_perm
from paths import app_data_dir
from ftp_util import ftp_connection

LOG = logging.getLogger(__name__)

ApprovalFn = Callable[[str, str], bool]


def remote_index_lookup_keys_for_local_segment(
    seg: str, mapping: dict[str, Any]
) -> list[str]:
    """
    リモート索引を引くキー一覧。ローカル側フォルダ名 seg に対し、
    △対応（delta_folder_mappings）で別名のサーバーフォルダ名も列挙する。
    """
    s0 = seg.strip().lower()
    keys: list[str] = [s0]
    seen = {s0}
    for dm in mapping.get("delta_folder_mappings") or []:
        if not isinstance(dm, dict):
            continue
        loc = str(dm.get("local_segment") or "").strip().lower()
        if loc != s0:
            continue
        for name in dm.get("remote_folder_names") or []:
            t = str(name).strip().lower()
            if t and t not in seen:
                seen.add(t)
                keys.append(t)
    return keys


def _approval_path() -> Path:
    d = app_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "anchor_sync_approvals.json"


def _load_approvals() -> dict[str, Any]:
    p = _approval_path()
    if not p.is_file():
        return {"version": 1, "profiles": {}}
    try:
        with p.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"version": 1, "profiles": {}}


def _save_approvals(data: dict[str, Any]) -> None:
    p = _approval_path()
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def profile_key(
    local_root: str,
    remote_root: str,
    anchor: str,
    profile_id: int | None = None,
) -> str:
    d: dict[str, Any] = {"an": anchor.lower(), "lr": local_root, "rr": remote_root}
    if profile_id is not None:
        d["pid"] = int(profile_id)
    raw = json.dumps(d, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_mapping_approved(profile: str, situation_sig: str) -> bool:
    data = _load_approvals()
    rec = data.get("profiles", {}).get(profile)
    return bool(rec and rec.get("situation_sig") == situation_sig)


def record_mapping_approval(profile: str, situation_sig: str) -> None:
    data = _load_approvals()
    data.setdefault("profiles", {})[profile] = {"situation_sig": situation_sig}
    _save_approvals(data)


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


def enumerate_remote_directory_paths(
    ftp: FTP,
    remote_root_segments: list[str],
    max_depth: int,
) -> list[list[str]]:
    """
    remote_root 直下から最大 max_depth 階層まで辿り、見つかった各ディレクトリの
    remote_root からの相対セグメント列を列挙（各要素の末尾がそのディレクトリ名）。
    """
    saved = ftp.pwd()
    found: list[list[str]] = []

    def list_children() -> list[str]:
        try:
            raw = ftp.nlst()
        except Exception:
            return []
        names: list[str] = []
        for x in raw:
            n = Path(x).name
            if n and n not in (".", ".."):
                names.append(n)
        return sorted(set(names))

    def is_dir(name: str) -> bool:
        try:
            ftp.cwd(name)
            ftp.cwd("..")
            return True
        except Exception:
            return False

    def walk(rel_from_remote_root: list[str], depth: int) -> None:
        if depth > max_depth:
            return
        for child in list_children():
            if not is_dir(child):
                continue
            path_here = rel_from_remote_root + [child]
            found.append(path_here)
            if depth >= max_depth:
                continue
            try:
                ftp.cwd(child)
                walk(path_here, depth + 1)
            finally:
                try:
                    ftp.cwd("..")
                except Exception:
                    pass

    try:
        _cwd_create_chain(ftp, remote_root_segments)
        walk([], 0)
    finally:
        try:
            ftp.cwd(saved)
        except Exception:
            pass

    return found


def build_remote_folder_name_index(paths: list[list[str]]) -> dict[str, list[list[str]]]:
    """フォルダ名（小文字）→ その名前で終わるリモート相対パス（複数可）。"""
    from collections import defaultdict

    idx: dict[str, list[list[str]]] = defaultdict(list)
    for p in paths:
        if p:
            idx[p[-1].lower()].append(p)
    return dict(idx)


def index_signature(idx: dict[str, list[list[str]]]) -> str:
    body = {
        k: sorted("/".join(x) for x in v)
        for k, v in sorted(idx.items(), key=lambda kv: kv[0])
    }
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def discover_remote_anchor_paths(
    ftp: FTP,
    remote_root_segments: list[str],
    anchor_name: str,
    max_depth: int,
) -> list[list[str]]:
    """
    remote_root 直下から最大 max_depth 階層まで辿り、フォルダ名が anchor_name と一致するパス（remote_root からの相対セグメント列、末尾が anchor）を列挙。
    """
    anchor_l = anchor_name.strip().lower()
    saved = ftp.pwd()
    found: list[list[str]] = []

    def list_children() -> list[str]:
        try:
            raw = ftp.nlst()
        except Exception:
            return []
        names: list[str] = []
        for x in raw:
            n = Path(x).name
            if n and n not in (".", ".."):
                names.append(n)
        return sorted(set(names))

    def is_dir(name: str) -> bool:
        try:
            ftp.cwd(name)
            ftp.cwd("..")
            return True
        except Exception:
            return False

    def walk(rel_from_remote_root: list[str], depth: int) -> None:
        if depth > max_depth:
            return
        for child in list_children():
            if child.lower() == anchor_l:
                found.append(rel_from_remote_root + [child])
            if depth >= max_depth:
                continue
            if not is_dir(child):
                continue
            try:
                ftp.cwd(child)
                walk(rel_from_remote_root + [child], depth + 1)
            finally:
                try:
                    ftp.cwd("..")
                except Exception:
                    pass

    try:
        _cwd_create_chain(ftp, remote_root_segments)
        walk([], 0)
    finally:
        try:
            ftp.cwd(saved)
        except Exception:
            pass

    return found


def choose_shortest_candidate(candidates: list[list[str]]) -> list[str]:
    if not candidates:
        raise RuntimeError("候補がありません")
    return sorted(candidates, key=lambda c: (len(c), "/".join(c)))[0]


def split_local_at_anchor(
    local_file: Path,
    local_root: Path,
    anchor_name: str,
) -> tuple[list[str], str] | None:
    """ローカルで anchor より下のディレクトリ列とファイル名。見つからなければ None。"""
    anchor_l = anchor_name.strip().lower()
    try:
        rel = local_file.resolve().relative_to(local_root.resolve())
    except ValueError:
        return None
    parts = rel.parts
    if not parts:
        return None
    idx = None
    for i, p in enumerate(parts):
        if p.lower() == anchor_l:
            idx = i
            break
    if idx is None:
        return None
    fname = parts[-1]
    mid = parts[idx + 1 : -1]
    return list(mid), fname


def local_file_under_anchor(local_path: Path, local_root: Path, anchor_name: str) -> bool:
    return split_local_at_anchor(local_path, local_root, anchor_name) is not None


def build_situation_signature(
    local_root: Path,
    remote_root: str,
    anchor_name: str,
    chosen_rel_under_remote_root: list[str],
    all_candidates: list[list[str]],
) -> str:
    body = {
        "anchor": anchor_name.lower(),
        "candidates": sorted("/".join(c) for c in all_candidates),
        "chosen": "/".join(chosen_rel_under_remote_root),
        "lr": str(local_root.resolve()),
        "rr": remote_root.strip().replace("\\", "/"),
    }
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def build_mapping_summary_text(
    local_root: Path,
    remote_root: str,
    anchor_name: str,
    chosen: list[str],
    candidates: list[list[str]],
) -> str:
    lines = [
        "【同期マッピングの確認】",
        f"ローカル監視ルート: {local_root}",
        f"FTP リモート先頭: {remote_root}",
        f"アンカーフォルダ名: {anchor_name}",
        f"サーバー上で採用するパス（先頭からの相対）: {'/'.join(chosen) if chosen else '(直下)'}",
        "",
        "サーバー上の同名フォルダ候補:",
    ]
    for c in sorted(candidates, key=lambda x: (len(x), "/".join(x))):
        lines.append("  - " + "/".join(c))
    lines.append("")
    lines.append("ローカルでは、この名前のフォルダより下だけを上記リモート側に載せます。")
    lines.append("階層のずれは設定の探索深さの範囲で吸収しています。")
    lines.append("この内容で同期してよいですか？")
    return "\n".join(lines)


def build_auto_mapping_summary_text(
    local_root: Path,
    remote_root: str,
    max_depth: int,
    total_dirs: int,
    index: dict[str, list[list[str]]],
) -> str:
    sample_keys = sorted(index.keys())[:24]
    lines = [
        "【同期マッピングの確認（自動・同名フォルダ照合）】",
        f"ローカル監視ルート: {local_root}",
        f"FTP リモート先頭: {remote_root or '(ルート)'}",
        f"サーバー側の探索深さ: 先頭から最大 {max_depth} 階層",
        f"サーバー上で見つかったディレクトリ数: {total_dirs}",
        f"フォルダ名の種類（索引）: {len(index)}",
        "",
        "ローカルのパスに含まれるフォルダ名のうち、上記の範囲でサーバーにも存在する名前と突き合わせ、",
        "階層が数段ずれていても最短のリモートパスへ UPLOAD します（同名が複数ある場合は浅いパスを優先）。",
        "",
        "検出されたフォルダ名の例（先頭24件）:",
    ]
    for k in sample_keys:
        lines.append(f"  - {k}")
    if len(index) > 24:
        lines.append(f"  … 他 {len(index) - 24} 件")
    lines.append("")
    lines.append("この内容で同期してよいですか？")
    return "\n".join(lines)


def _template_question(summary: str) -> str:
    return summary


def ai_paraphrase_question(summary: str, ai_cfg: dict[str, Any]) -> str:
    key = (ai_cfg.get("openai_api_key") or "").strip()
    if not key:
        return _template_question(summary)
    base = (ai_cfg.get("openai_base_url") or "https://api.openai.com/v1").rstrip("/")
    model = (ai_cfg.get("openai_model") or "gpt-4o-mini").strip()
    url = base + "/chat/completions"
    system = (
        "あなたはファイル同期の案内役です。ユーザーに丁寧語で、"
        "ローカルとサーバーのフォルダ対応が想定と少しずれている可能性があることを短く説明し、"
        "続行してよいか一言で確認してください。200文字以内。技術用語は必要最小限に。"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": summary},
        ],
        "max_tokens": 300,
        "temperature": 0.3,
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
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
            or _template_question(summary)
        )
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:500]
        LOG.warning("AI API HTTP error: %s %s", e.code, err)
        return _template_question(summary) + "\n\n(AI 呼び出しに失敗したため上記をそのまま表示します)"
    except Exception as e:
        LOG.warning("AI API error: %s", e)
        return _template_question(summary) + "\n\n(AI 呼び出しに失敗したため上記をそのまま表示します)"


def prepare_anchor_sync_or_legacy(
    config: dict[str, Any],
    ask_yes_no: ApprovalFn,
    *,
    app_title: str = "FTP 自動同期",
    profile_id: int | None = None,
) -> dict[str, Any] | None:
    """
    戻り値:
      - {"type": "legacy", "remote_root": str} 従来の相対パス同期
      - {"type": "anchor_auto", "remote_root_segments", "remote_folder_index", ...} 同名フォルダ自動照合
      - {"type": "anchor", "anchor_name": str, "remote_root_segments": list[str],
         "anchor_rel_under_remote_root": list[str]}  # remote_root 直下から見たアンカーまでの相対
    None = ユーザーがキャンセル
    """
    sync = config.get("sync") or {}
    ftp_cfg = config.get("ftp") or {}
    remote_root = (sync.get("remote_root") or "").strip().replace("\\", "/").strip("/")
    remote_segs = [s for s in remote_root.split("/") if s] if remote_root else []
    local_root = Path(sync["local_root"]).expanduser().resolve()
    use_anchor = bool(sync.get("use_anchor_sync", False))
    if not use_anchor:
        return {"type": "legacy", "remote_root": remote_root}

    max_depth = int(sync.get("max_anchor_search_depth", 3))
    max_depth = max(0, min(max_depth, 128))
    anchor_auto_match = bool(sync.get("anchor_auto_match", True))
    anchor = (sync.get("anchor_folder_name") or "").strip()
    ai_anchor = bool(sync.get("ai_anchor_sync", False))
    if ai_anchor:
        anchor_auto_match = True

    if anchor_auto_match:
        with ftp_connection(ftp_cfg) as ftp:
            all_paths = enumerate_remote_directory_paths(ftp, remote_segs, max_depth)
        index = build_remote_folder_name_index(all_paths)
        if not index:
            raise RuntimeError(
                f"サーバー上の「{remote_root or '(ルート)'}」から {max_depth} 階層以内に "
                "ディレクトリが見つかりませんでした。リモート先頭パス・接続・探索深さを確認してください。"
            )
        sig = index_signature(index)
        prof = profile_key(str(local_root), remote_root, "__auto__", profile_id)
        if is_mapping_approved(prof, sig):
            LOG.info("自動同名フォルダ照合は前回承認済みのため確認を省略します。")
            return {
                "type": "anchor_auto",
                "remote_root_segments": remote_segs,
                "remote_folder_index": index,
                "max_anchor_search_depth": max_depth,
                "ai_anchor_sync": ai_anchor,
                "delta_folder_mappings": copy.deepcopy(sync.get("delta_folder_mappings") or []),
            }
        summary = build_auto_mapping_summary_text(
            local_root, remote_root, max_depth, len(all_paths), index
        )
        ai_cfg = config.get("ai") or {}
        question = ai_paraphrase_question(summary, ai_cfg)
        if not ask_yes_no(app_title, question):
            return None
        record_mapping_approval(prof, sig)
        return {
            "type": "anchor_auto",
            "remote_root_segments": remote_segs,
            "remote_folder_index": index,
            "max_anchor_search_depth": max_depth,
            "ai_anchor_sync": ai_anchor,
            "delta_folder_mappings": copy.deepcopy(sync.get("delta_folder_mappings") or []),
        }

    if not anchor:
        return {"type": "legacy", "remote_root": remote_root}

    with ftp_connection(ftp_cfg) as ftp:
        candidates = discover_remote_anchor_paths(ftp, remote_segs, anchor, max_depth)

    if not candidates:
        raise RuntimeError(
            f"サーバー上の「{remote_root or '(ルート)'}」から {max_depth} 階層以内に "
            f"フォルダ「{anchor}」が見つかりませんでした。"
        )

    chosen = choose_shortest_candidate(candidates)
    sig = build_situation_signature(
        local_root, remote_root, anchor, chosen, candidates
    )
    prof = profile_key(str(local_root), remote_root, anchor, profile_id)

    if is_mapping_approved(prof, sig):
        LOG.info("同期マッピングは前回承認済みのため確認を省略します。")
        return {
            "type": "anchor",
            "anchor_name": anchor,
            "remote_root_segments": remote_segs,
            "anchor_rel_under_remote_root": chosen,
        }

    summary = build_mapping_summary_text(
        local_root, remote_root, anchor, chosen, candidates
    )
    ai_cfg = config.get("ai") or {}
    question = ai_paraphrase_question(summary, ai_cfg)
    if not ask_yes_no(app_title, question):
        return None

    record_mapping_approval(prof, sig)
    return {
        "type": "anchor",
        "anchor_name": anchor,
        "remote_root_segments": remote_segs,
        "anchor_rel_under_remote_root": chosen,
    }


def pick_anchor_auto(
    local_file: Path,
    local_root: Path,
    mapping: dict[str, Any],
) -> tuple[list[str], str, list[str]] | None:
    """
    同名フォルダ自動照合: ローカルパスのディレクトリセグメントを末尾側から見て、
    リモート索引に存在する最初の名前で同期点を決める（最深優先）。
    戻り値: (FTP で cwd するディレクトリ列, ファイル名, 同期点より下のローカル subdir 列)
    """
    idx = mapping.get("remote_folder_index") or {}
    try:
        rel = local_file.resolve().relative_to(local_root.resolve())
    except ValueError:
        return None
    parts = rel.parts
    if len(parts) < 2:
        return None
    fname = parts[-1]
    dir_parts = list(parts[:-1])
    rr_segs = list(mapping.get("remote_root_segments") or [])
    ai_anchor = bool(mapping.get("ai_anchor_sync"))
    for j in range(len(dir_parts) - 1, -1, -1):
        seg = dir_parts[j]
        if ai_anchor and "." in seg:
            continue
        tail = dir_parts[j + 1 :]
        candidates: list[list[str]] = []
        for rk in remote_index_lookup_keys_for_local_segment(seg, mapping):
            for c in idx.get(rk, []) or []:
                candidates.append(list(c))
        if not candidates:
            continue
        chosen = choose_shortest_candidate(candidates)
        full_dir = rr_segs + chosen + tail
        return full_dir, fname, tail
    return None


def upload_path_parts_for_file(
    local_file: Path,
    local_root: Path,
    mapping: dict[str, Any],
) -> tuple[list[str], str] | None:
    """
    STOR 用: (cwd 用ディレクトリセグメント列（ホームからフルパス）、ファイル名)
    legacy: remote_root + rel(local)
    anchor_auto: サーバー側のフォルダ名索引で同名を照合
    anchor: remote_root + chosen_rel + tail_under_anchor
    """
    if mapping.get("type") == "legacy":
        rr = (mapping.get("remote_root") or "").strip().replace("\\", "/").strip("/")
        rel = local_file.resolve().relative_to(local_root.resolve())
        parts = [s for s in rr.split("/") if s] + list(rel.parts)
        if not parts:
            return [], local_file.name
        return parts[:-1], parts[-1]

    if mapping.get("type") == "anchor_auto":
        picked = pick_anchor_auto(local_file, local_root, mapping)
        if picked is None:
            return None
        dir_parts, fn, _tail = picked
        return dir_parts, fn

    if mapping.get("type") != "anchor":
        return None

    anchor_name = mapping["anchor_name"]
    split = split_local_at_anchor(local_file, local_root, anchor_name)
    if split is None:
        return None
    tail_dirs, fname = split
    rr_segs = list(mapping.get("remote_root_segments") or [])
    ar_segs = list(mapping.get("anchor_rel_under_remote_root") or [])
    dir_parts = rr_segs + ar_segs + tail_dirs
    return dir_parts, fname
