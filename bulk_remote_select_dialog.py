"""サーバー上の同名フォルダ候補を一覧し、一斉配信用の remote 追加パスとして選ぶ。"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable

from anchor_sync import enumerate_remote_directory_paths
from ftp_util import ftp_connection


def local_non_domain_folder_names(local_root: Path) -> set[str]:
    """監視ルート直下で、ドメイン風（名前に . を含む）でないフォルダ名。"""
    out: set[str] = set()
    root = local_root.expanduser().resolve()
    if not root.is_dir():
        return out
    try:
        for p in root.iterdir():
            if not p.is_dir():
                continue
            n = p.name
            if n.startswith("."):
                continue
            if "." in n:
                continue
            out.add(n.lower())
    except OSError:
        pass
    return out


def show_bulk_remote_folder_dialog(
    master: tk.Tk,
    ftp_cfg: dict[str, Any],
    sync: dict[str, Any],
    local_root: Path,
    on_ok: Callable[[list[str]], None],
) -> None:
    """リモート側の相対パス（/区切り）を選び on_ok に渡す。"""
    remote_root = (sync.get("remote_root") or "").strip().replace("\\", "/").strip("/")
    remote_segs = [s for s in remote_root.split("/") if s] if remote_root else []
    try:
        max_depth = int(sync.get("max_anchor_search_depth", 6))
    except (TypeError, ValueError):
        max_depth = 3
    max_depth = max(0, min(max_depth, 128))

    locals_l = local_non_domain_folder_names(local_root)
    if not locals_l:
        messagebox.showinfo(
            master.title(),
            "監視ルート直下に、ドメイン名でないフォルダがありません。",
            parent=master,
        )
        return

    try:
        with ftp_connection(ftp_cfg) as ftp:
            all_paths = enumerate_remote_directory_paths(ftp, remote_segs, max_depth)
    except Exception as e:
        messagebox.showerror(master.title(), str(e), parent=master)
        return

    candidates: list[str] = []
    for segs in all_paths:
        if not segs:
            continue
        last = segs[-1].lower()
        if last in locals_l:
            candidates.append("/".join(segs))

    candidates = sorted(set(candidates))
    if not candidates:
        messagebox.showinfo(
            master.title(),
            "サーバー上に、該当する同名フォルダが見つかりませんでした。",
            parent=master,
        )
        return

    win = tk.Toplevel(master)
    win.title("一斉配信先（サーバー上のフォルダ）")
    win.geometry("640x480")
    win.transient(master)

    ttk.Label(
        win,
        text="監視ルート直下の「ドメイン名でないフォルダ名」と一致するサーバー側パスです。\n"
        "マルチデプロイの remote 追加パスとして登録するフォルダにチェックを付けて OK。",
        wraplength=600,
    ).pack(anchor=tk.W, padx=8, pady=6)

    canvas = tk.Canvas(win, highlightthickness=0)
    sb = ttk.Scrollbar(win, command=canvas.yview)
    inner = ttk.Frame(canvas)
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor=tk.NW)
    canvas.configure(yscrollcommand=sb.set)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=4)
    sb.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 8), pady=4)

    checks: dict[str, tk.BooleanVar] = {}
    for c in candidates:
        v = tk.BooleanVar(value=False)
        checks[c] = v
        ttk.Checkbutton(inner, text=c, variable=v).pack(anchor=tk.W, padx=4)

    def ok() -> None:
        sel = [p for p, var in checks.items() if var.get()]
        if not sel:
            messagebox.showinfo(win.title(), "1つ以上選んでください。", parent=win)
            return
        on_ok(sel)
        win.destroy()

    bf = ttk.Frame(win, padding=6)
    bf.pack(fill=tk.X)
    ttk.Button(bf, text="OK", command=ok).pack(side=tk.RIGHT, padx=4)
    ttk.Button(bf, text="キャンセル", command=win.destroy).pack(side=tk.RIGHT, padx=4)
    win.grab_set()
