"""
Ftp-Auto-Sync — Windows 向け GUI（tkinter）。Ver 3.5
プロファイルは SQLite（最大 100,000 件）に保存: %LOCALAPPDATA%\\FTPAutoSync\\profiles.db
Ver2: アップロード後などに Git／GitHub 確認。Ver3: FTP→ローカル一括ダウンロード（逆同期）。
"""
from __future__ import annotations

import copy
import json
import logging
import os
import queue
import shutil
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

import ui_i18n
from anchor_sync import prepare_anchor_sync_or_legacy
from bulk_remote_select_dialog import show_bulk_remote_folder_dialog
from deploy_targets_dialog import DeployTargetsDialog
from ftp_watcher import WatcherService, load_config
from multi_deploy import MAX_DEPLOY_TARGETS, normalize_deploy_targets
from v3_ftp_download import run_reverse_sync
from paths import app_data_dir, bundled_example_config, data_dir_env_var_name, profiles_db_path
from profile_store import MAX_PROFILES, ProfileStore
from v2_git_assist import (
    ai_git_management_question,
    build_v2_summary_rename,
    build_v2_summary_upload,
    ensure_git_repository,
    git_add_all_and_commit,
    git_try_push,
    is_git_on_path,
    multilingual_git_install_help,
    static_multilingual_git_question_rename,
    static_multilingual_git_question_upload,
)


def ask_ok_scroll(master: tk.Tk, title: str, body: str) -> None:
    """長文の OK のみ（Git 未インストール案内など）。"""
    win = tk.Toplevel(master)
    win.title(title)
    win.geometry("760x560")
    win.transient(master)
    txt = tk.Text(win, wrap=tk.WORD, font=("Segoe UI", 10))
    sb = ttk.Scrollbar(win, command=txt.yview)
    txt.configure(yscrollcommand=sb.set)
    txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    sb.pack(side=tk.RIGHT, fill=tk.Y)
    txt.insert("1.0", body)
    txt.configure(state=tk.DISABLED)
    bf = ttk.Frame(win, padding=8)
    bf.pack(fill=tk.X)

    def close() -> None:
        win.destroy()

    ttk.Button(bf, text="OK", command=close).pack(side=tk.RIGHT)
    win.grab_set()
    win.wait_window()


def ask_yes_no_scroll(
    master: tk.Tk,
    title: str,
    body: str,
    *,
    radio_frame_label: str = "Git／GitHub に公開するか",
) -> bool:
    """長文の説明のあと、YES／NO ラジオと OK で確定。"""
    result: list[bool] = [False]
    win = tk.Toplevel(master)
    win.title(title)
    win.geometry("760x560")
    win.transient(master)
    txt = tk.Text(win, wrap=tk.WORD, font=("Segoe UI", 10))
    sb = ttk.Scrollbar(win, command=txt.yview)
    txt.configure(yscrollcommand=sb.set)
    txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    sb.pack(side=tk.RIGHT, fill=tk.Y)
    txt.insert("1.0", body)
    txt.configure(state=tk.DISABLED)
    bf = ttk.Frame(win, padding=8)
    bf.pack(fill=tk.X)

    choice = tk.StringVar(value="no")

    rf = ttk.LabelFrame(bf, text=radio_frame_label, padding=(8, 6))
    rf.pack(fill=tk.X, pady=(0, 8))
    rrow = ttk.Frame(rf)
    rrow.pack(fill=tk.X)
    ttk.Radiobutton(rrow, text="YES", variable=choice, value="yes").pack(side=tk.LEFT, padx=(0, 28))
    ttk.Radiobutton(rrow, text="NO", variable=choice, value="no").pack(side=tk.LEFT)

    def confirm() -> None:
        result[0] = choice.get() == "yes"
        win.destroy()

    def on_close() -> None:
        result[0] = False
        win.destroy()

    btn_row = ttk.Frame(bf)
    btn_row.pack(fill=tk.X)
    ttk.Button(btn_row, text="OK", command=confirm).pack(side=tk.RIGHT)
    win.protocol("WM_DELETE_WINDOW", on_close)
    win.grab_set()
    win.wait_window()
    return result[0]


class GuiLogHandler(logging.Handler):
    def __init__(self, q: queue.Queue[str]) -> None:
        super().__init__()
        self._q = q

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._q.put(self.format(record))
        except Exception:
            pass


class FtpAutoSyncApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.var_ui_lang = tk.StringVar(value="ja")
        self._i18n_refs: list[tuple[tk.Misc, str, str]] = []
        self.title(ui_i18n.t(self.var_ui_lang.get(), "app_title"))
        self.geometry("960x720")
        self.minsize(720, 520)

        self._store = ProfileStore()
        self._log_q: queue.Queue[str] = queue.Queue()
        self._v2_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._v2_last_prompt = 0.0
        self._runtime_cfg: dict[str, Any] | None = None
        self._watcher: WatcherService | None = None
        self._watcher_lock = threading.Lock()
        self._current_profile_id: int | None = None
        self._profile_list_ids: list[int] = []
        self._v3_busy = False
        self._deploy_targets: list[dict[str, Any]] = normalize_deploy_targets([])

        self._build_language_bar()
        self._build_profile_panel()
        self._build_form()
        self._build_log()
        self._build_buttons()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._setup_logging()
        self._bootstrap_load()
        self._apply_ui_language()
        self.after(150, self._drain_log_queue)
        self.after(260, self._poll_v2_queue)

    def _app_title(self) -> str:
        return ui_i18n.t(self.var_ui_lang.get(), "app_title")

    def _reg_i18n(self, widget: tk.Misc, attr: str, key: str) -> None:
        self._i18n_refs.append((widget, attr, key))

    def _apply_ui_language(self) -> None:
        lang = self.var_ui_lang.get()
        self.title(ui_i18n.t(lang, "app_title"))
        for w, attr, key in self._i18n_refs:
            try:
                w.configure(**{attr: ui_i18n.t(lang, key)})
            except tk.TclError:
                pass
        try:
            self._lf_profiles.configure(
                text=ui_i18n.t(lang, "profile_lf") + f"（最大 {MAX_PROFILES:,}）"
            )
        except tk.TclError:
            pass
        try:
            self._lbl_lang_select.configure(text=ui_i18n.t(lang, "lang_select"))
        except tk.TclError:
            pass
        for key, rb in getattr(self, "_multi_mode_rbs", []):
            try:
                rb.configure(text=ui_i18n.t(lang, key))
            except tk.TclError:
                pass
        try:
            self.lbl_multi_hint.configure(
                text=ui_i18n.t(lang, "multi_hint") + f" ({MAX_DEPLOY_TARGETS})"
            )
        except tk.TclError:
            pass

    def _build_language_bar(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill=tk.X, padx=8, pady=(4, 0))
        self._lbl_lang_select = ttk.Label(
            bar, text=ui_i18n.t(self.var_ui_lang.get(), "lang_select")
        )
        self._lbl_lang_select.pack(side=tk.LEFT)
        rf = ttk.Frame(bar)
        rf.pack(side=tk.LEFT, padx=(8, 0))
        for code in ui_i18n.LANG_CODES:
            ttk.Radiobutton(
                rf,
                text=ui_i18n.LANG_RADIO_LABELS[code],
                variable=self.var_ui_lang,
                value=code,
                command=self._apply_ui_language,
            ).pack(side=tk.LEFT, padx=2)

    def _build_profile_panel(self) -> None:
        pf = ttk.LabelFrame(
            self,
            text=ui_i18n.t(
                self.var_ui_lang.get(),
                "profile_lf",
            )
            + f"（最大 {MAX_PROFILES:,}）",
            padding=6,
        )
        pf.pack(fill=tk.X, padx=8, pady=4)
        self._lf_profiles = pf
        ln = ttk.Label(pf, text=ui_i18n.t(self.var_ui_lang.get(), "lbl_display_name"))
        self._reg_i18n(ln, "text", "lbl_display_name")
        ln.grid(row=0, column=0, sticky=tk.W)
        self.var_profile_name = tk.StringVar(value="新規プロファイル")
        ttk.Entry(pf, textvariable=self.var_profile_name, width=36).grid(
            row=0, column=1, sticky=tk.W, padx=4
        )
        ls = ttk.Label(pf, text=ui_i18n.t(self.var_ui_lang.get(), "lbl_search"))
        self._reg_i18n(ls, "text", "lbl_search")
        ls.grid(row=0, column=2, sticky=tk.E, padx=(12, 4))
        self.var_profile_search = tk.StringVar()
        ttk.Entry(pf, textvariable=self.var_profile_search, width=24).grid(
            row=0, column=3, sticky=tk.EW
        )
        self.btn_pf_search = ttk.Button(
            pf, text=ui_i18n.t(self.var_ui_lang.get(), "btn_search_list"), command=self._refresh_profile_list
        )
        self._reg_i18n(self.btn_pf_search, "text", "btn_search_list")
        self.btn_pf_search.grid(row=0, column=4, padx=4)
        self.lb_profiles = tk.Listbox(pf, height=5, exportselection=False, font=("Segoe UI", 9))
        self.lb_profiles.grid(row=1, column=0, columnspan=4, sticky=tk.NSEW, pady=4)
        sb = ttk.Scrollbar(pf, command=self.lb_profiles.yview)
        sb.grid(row=1, column=4, sticky=tk.NS)
        self.lb_profiles.configure(yscrollcommand=sb.set)
        bf = ttk.Frame(pf)
        bf.grid(row=2, column=0, columnspan=5, sticky=tk.W)
        self.btn_pf_refresh = ttk.Button(
            bf, text=ui_i18n.t(self.var_ui_lang.get(), "btn_refresh"), command=self._refresh_profile_list
        )
        self._reg_i18n(self.btn_pf_refresh, "text", "btn_refresh")
        self.btn_pf_refresh.pack(side=tk.LEFT, padx=2)
        self.btn_pf_new = ttk.Button(
            bf, text=ui_i18n.t(self.var_ui_lang.get(), "btn_new"), command=self._new_profile
        )
        self._reg_i18n(self.btn_pf_new, "text", "btn_new")
        self.btn_pf_new.pack(side=tk.LEFT, padx=2)
        self.btn_pf_save = ttk.Button(
            bf,
            text=ui_i18n.t(self.var_ui_lang.get(), "btn_save"),
            command=self._save_profile_to_db,
        )
        self._reg_i18n(self.btn_pf_save, "text", "btn_save")
        self.btn_pf_save.pack(side=tk.LEFT, padx=2)
        self.btn_pf_delete = ttk.Button(
            bf, text=ui_i18n.t(self.var_ui_lang.get(), "btn_delete"), command=self._delete_profile
        )
        self._reg_i18n(self.btn_pf_delete, "text", "btn_delete")
        self.btn_pf_delete.pack(side=tk.LEFT, padx=2)
        self.btn_pf_dup = ttk.Button(
            bf, text=ui_i18n.t(self.var_ui_lang.get(), "btn_duplicate"), command=self._duplicate_profile
        )
        self._reg_i18n(self.btn_pf_dup, "text", "btn_duplicate")
        self.btn_pf_dup.pack(side=tk.LEFT, padx=2)
        self.btn_pf_export = ttk.Button(
            bf, text=ui_i18n.t(self.var_ui_lang.get(), "btn_export"), command=self._export_profile_json
        )
        self._reg_i18n(self.btn_pf_export, "text", "btn_export")
        self.btn_pf_export.pack(side=tk.LEFT, padx=2)
        self.btn_pf_import = ttk.Button(
            bf, text=ui_i18n.t(self.var_ui_lang.get(), "btn_import"), command=self._import_profile_json
        )
        self._reg_i18n(self.btn_pf_import, "text", "btn_import")
        self.btn_pf_import.pack(side=tk.LEFT, padx=2)
        self.btn_pf_datadir = ttk.Button(
            bf,
            text=ui_i18n.t(self.var_ui_lang.get(), "btn_data_folder"),
            command=self._open_app_data_folder,
        )
        self._reg_i18n(self.btn_pf_datadir, "text", "btn_data_folder")
        self.btn_pf_datadir.pack(side=tk.LEFT, padx=2)
        self.btn_pf_clone = ttk.Button(
            bf,
            text=ui_i18n.t(self.var_ui_lang.get(), "btn_clone_all"),
            command=self._clone_data_folder_dialog,
        )
        self._reg_i18n(self.btn_pf_clone, "text", "btn_clone_all")
        self.btn_pf_clone.pack(side=tk.LEFT, padx=2)
        self.lbl_profile_status = ttk.Label(pf, text="", foreground="gray")
        self.lbl_profile_status.grid(row=3, column=0, columnspan=5, sticky=tk.W)
        pf.columnconfigure(3, weight=1)
        self.lb_profiles.bind("<<ListboxSelect>>", self._on_profile_list_select)
        self.lb_profiles.bind("<Double-Button-1>", self._on_profile_list_select)

    def _build_form(self) -> None:
        frm = ttk.LabelFrame(
            self, text=ui_i18n.t(self.var_ui_lang.get(), "conn_lf"), padding=8
        )
        self._lf_conn = frm
        self._reg_i18n(frm, "text", "conn_lf")
        frm.pack(fill=tk.X, padx=8, pady=6)

        r = 0
        lh = ttk.Label(frm, text=ui_i18n.t(self.var_ui_lang.get(), "lbl_host"))
        self._reg_i18n(lh, "text", "lbl_host")
        lh.grid(row=r, column=0, sticky=tk.W, pady=2)
        self.var_host = tk.StringVar()
        ttk.Entry(frm, textvariable=self.var_host, width=40).grid(
            row=r, column=1, columnspan=3, sticky=tk.EW, pady=2
        )
        r += 1

        lp = ttk.Label(frm, text=ui_i18n.t(self.var_ui_lang.get(), "lbl_port"))
        self._reg_i18n(lp, "text", "lbl_port")
        lp.grid(row=r, column=0, sticky=tk.W, pady=2)
        self.var_port = tk.StringVar(value="21")
        ttk.Entry(frm, textvariable=self.var_port, width=8).grid(row=r, column=1, sticky=tk.W, pady=2)
        self.var_tls = tk.BooleanVar(value=False)
        self.chk_tls = ttk.Checkbutton(
            frm, text=ui_i18n.t(self.var_ui_lang.get(), "chk_tls"), variable=self.var_tls
        )
        self._reg_i18n(self.chk_tls, "text", "chk_tls")
        self.chk_tls.grid(row=r, column=2, sticky=tk.W, padx=8)
        self.var_passive = tk.BooleanVar(value=True)
        self.chk_passive = ttk.Checkbutton(
            frm, text=ui_i18n.t(self.var_ui_lang.get(), "chk_passive"), variable=self.var_passive
        )
        self._reg_i18n(self.chk_passive, "text", "chk_passive")
        self.chk_passive.grid(row=r, column=3, sticky=tk.W)
        r += 1

        lu = ttk.Label(frm, text=ui_i18n.t(self.var_ui_lang.get(), "lbl_user"))
        self._reg_i18n(lu, "text", "lbl_user")
        lu.grid(row=r, column=0, sticky=tk.W, pady=2)
        self.var_user = tk.StringVar()
        ttk.Entry(frm, textvariable=self.var_user, width=28).grid(row=r, column=1, sticky=tk.W, pady=2)
        lpw = ttk.Label(frm, text=ui_i18n.t(self.var_ui_lang.get(), "lbl_pass"))
        self._reg_i18n(lpw, "text", "lbl_pass")
        lpw.grid(row=r, column=2, sticky=tk.W, padx=(12, 0), pady=2)
        self.var_password = tk.StringVar()
        ttk.Entry(frm, textvariable=self.var_password, width=20, show="*").grid(
            row=r, column=3, sticky=tk.W, pady=2
        )
        r += 1

        ll = ttk.Label(frm, text=ui_i18n.t(self.var_ui_lang.get(), "lbl_watch"))
        self._reg_i18n(ll, "text", "lbl_watch")
        ll.grid(row=r, column=0, sticky=tk.W, pady=2)
        self.var_local = tk.StringVar()
        ttk.Entry(frm, textvariable=self.var_local, width=50).grid(
            row=r, column=1, columnspan=2, sticky=tk.EW, pady=2
        )
        self.btn_browse_local = ttk.Button(
            frm, text=ui_i18n.t(self.var_ui_lang.get(), "btn_browse_local"), command=self._browse_local
        )
        self._reg_i18n(self.btn_browse_local, "text", "btn_browse_local")
        self.btn_browse_local.grid(row=r, column=3, sticky=tk.E, pady=2)
        r += 1

        lr = ttk.Label(frm, text=ui_i18n.t(self.var_ui_lang.get(), "lbl_remote_root"))
        self._reg_i18n(lr, "text", "lbl_remote_root")
        lr.grid(row=r, column=0, sticky=tk.W, pady=2)
        self.var_remote = tk.StringVar(value="public_html")
        ttk.Entry(frm, textvariable=self.var_remote, width=50).grid(
            row=r, column=1, columnspan=3, sticky=tk.EW, pady=2
        )
        r += 1

        lms = ttk.Label(frm, text=ui_i18n.t(self.var_ui_lang.get(), "lbl_max_sync_depth"))
        self._reg_i18n(lms, "text", "lbl_max_sync_depth")
        lms.grid(row=r, column=0, sticky=tk.W, pady=2)
        self.var_max_sync_depth = tk.StringVar(value="-1")
        ttk.Entry(frm, textvariable=self.var_max_sync_depth, width=8).grid(
            row=r, column=1, sticky=tk.W, pady=2
        )
        self.lbl_max_hint = ttk.Label(
            frm,
            text=ui_i18n.t(self.var_ui_lang.get(), "lbl_max_hint"),
            font=("Segoe UI", 8),
        )
        self._reg_i18n(self.lbl_max_hint, "text", "lbl_max_hint")
        self.lbl_max_hint.grid(row=r, column=2, columnspan=2, sticky=tk.W)
        r += 1

        ld = ttk.Label(frm, text=ui_i18n.t(self.var_ui_lang.get(), "lbl_debounce"))
        self._reg_i18n(ld, "text", "lbl_debounce")
        ld.grid(row=r, column=0, sticky=tk.W, pady=2)
        self.var_debounce = tk.StringVar(value="1.5")
        ttk.Entry(frm, textvariable=self.var_debounce, width=8).grid(row=r, column=1, sticky=tk.W, pady=2)
        self.var_recursive = tk.BooleanVar(value=True)
        self.chk_recursive = ttk.Checkbutton(
            frm,
            text=ui_i18n.t(self.var_ui_lang.get(), "chk_recursive"),
            variable=self.var_recursive,
        )
        self._reg_i18n(self.chk_recursive, "text", "chk_recursive")
        self.chk_recursive.grid(row=r, column=2, columnspan=2, sticky=tk.W)
        r += 1
        self.var_backup_remote = tk.BooleanVar(value=True)
        self.chk_backup = ttk.Checkbutton(
            frm,
            text=ui_i18n.t(self.var_ui_lang.get(), "chk_backup"),
            variable=self.var_backup_remote,
        )
        self._reg_i18n(self.chk_backup, "text", "chk_backup")
        self.chk_backup.grid(row=r, column=0, columnspan=4, sticky=tk.W)
        r += 1
        self.var_only_newer = tk.BooleanVar(value=True)
        self.chk_only_newer = ttk.Checkbutton(
            frm,
            text=ui_i18n.t(self.var_ui_lang.get(), "only_newer_chk"),
            variable=self.var_only_newer,
        )
        self._reg_i18n(self.chk_only_newer, "text", "only_newer_chk")
        self.chk_only_newer.grid(row=r, column=0, columnspan=4, sticky=tk.W)
        r += 1
        self._build_sync_scope_panel()
        af = ttk.LabelFrame(
            self, text=ui_i18n.t(self.var_ui_lang.get(), "anchor_lf"), padding=8
        )
        self._lf_anchor = af
        self._reg_i18n(af, "text", "anchor_lf")
        af.pack(fill=tk.X, padx=8, pady=4)
        ar = 0
        self.var_use_anchor = tk.BooleanVar(value=True)
        self.chk_use_anchor = ttk.Checkbutton(
            af,
            text=ui_i18n.t(self.var_ui_lang.get(), "chk_use_anchor"),
            variable=self.var_use_anchor,
        )
        self._reg_i18n(self.chk_use_anchor, "text", "chk_use_anchor")
        self.chk_use_anchor.grid(row=ar, column=0, columnspan=4, sticky=tk.W)
        ar += 1
        self.var_anchor_auto = tk.BooleanVar(value=True)
        self.chk_anchor_auto = ttk.Checkbutton(
            af,
            text=ui_i18n.t(self.var_ui_lang.get(), "chk_anchor_auto"),
            variable=self.var_anchor_auto,
        )
        self._reg_i18n(self.chk_anchor_auto, "text", "chk_anchor_auto")
        self.chk_anchor_auto.grid(row=ar, column=0, columnspan=4, sticky=tk.W)
        ar += 1
        self.var_ai_anchor = tk.BooleanVar(value=False)
        self.chk_ai_anchor = ttk.Checkbutton(
            af,
            text=ui_i18n.t(self.var_ui_lang.get(), "ai_anchor_chk"),
            variable=self.var_ai_anchor,
        )
        self._reg_i18n(self.chk_ai_anchor, "text", "ai_anchor_chk")
        self.chk_ai_anchor.grid(row=ar, column=0, columnspan=4, sticky=tk.W)
        ar += 1
        self.lbl_anchor_skew_intro = ttk.Label(
            af,
            text=ui_i18n.t(self.var_ui_lang.get(), "anchor_skew_intro"),
            wraplength=880,
            justify=tk.LEFT,
        )
        self._reg_i18n(self.lbl_anchor_skew_intro, "text", "anchor_skew_intro")
        self.lbl_anchor_skew_intro.grid(row=ar, column=0, columnspan=4, sticky=tk.W, pady=(4, 2))
        ar += 1
        lan = ttk.Label(af, text=ui_i18n.t(self.var_ui_lang.get(), "lbl_anchor_name"))
        self._reg_i18n(lan, "text", "lbl_anchor_name")
        lan.grid(row=ar, column=0, sticky=tk.W, pady=2)
        self.var_anchor = tk.StringVar(value="")
        ttk.Entry(af, textvariable=self.var_anchor, width=16).grid(row=ar, column=1, sticky=tk.W, pady=2)
        lad = ttk.Label(af, text=ui_i18n.t(self.var_ui_lang.get(), "lbl_skew_levels"))
        self._reg_i18n(lad, "text", "lbl_skew_levels")
        lad.grid(row=ar, column=2, sticky=tk.E, padx=(12, 4), pady=2)
        self.var_anchor_depth = tk.StringVar(value="3")
        ttk.Entry(af, textvariable=self.var_anchor_depth, width=4).grid(row=ar, column=3, sticky=tk.W, pady=2)
        ar += 1
        self.lbl_skew_hint = ttk.Label(
            af,
            text=ui_i18n.t(self.var_ui_lang.get(), "lbl_skew_hint"),
            font=("Segoe UI", 8),
        )
        self._reg_i18n(self.lbl_skew_hint, "text", "lbl_skew_hint")
        self.lbl_skew_hint.grid(row=ar, column=1, columnspan=3, sticky=tk.W)
        ar += 1
        lo = ttk.Label(af, text=ui_i18n.t(self.var_ui_lang.get(), "lbl_openai_key"))
        self._reg_i18n(lo, "text", "lbl_openai_key")
        lo.grid(row=ar, column=0, sticky=tk.W, pady=2)
        self.var_openai_key = tk.StringVar()
        ttk.Entry(af, textvariable=self.var_openai_key, width=36, show="*").grid(
            row=ar, column=1, columnspan=3, sticky=tk.EW, pady=2
        )
        ar += 1
        lob = ttk.Label(af, text=ui_i18n.t(self.var_ui_lang.get(), "lbl_openai_base"))
        self._reg_i18n(lob, "text", "lbl_openai_base")
        lob.grid(row=ar, column=0, sticky=tk.W, pady=2)
        self.var_openai_base = tk.StringVar(value="https://api.openai.com/v1")
        ttk.Entry(af, textvariable=self.var_openai_base, width=50).grid(
            row=ar, column=1, columnspan=3, sticky=tk.EW, pady=2
        )
        ar += 1
        lom = ttk.Label(af, text=ui_i18n.t(self.var_ui_lang.get(), "lbl_openai_model"))
        self._reg_i18n(lom, "text", "lbl_openai_model")
        lom.grid(row=ar, column=0, sticky=tk.W, pady=2)
        self.var_openai_model = tk.StringVar(value="gpt-4o-mini")
        ttk.Entry(af, textvariable=self.var_openai_model, width=24).grid(row=ar, column=1, sticky=tk.W, pady=2)
        af.columnconfigure(1, weight=1)
        frm.columnconfigure(1, weight=1)

        self._build_delta_ai_panel()

        vf = ttk.LabelFrame(
            self,
            text=ui_i18n.t(self.var_ui_lang.get(), "ver2_lf"),
            padding=8,
        )
        self._lf_ver2 = vf
        self._reg_i18n(vf, "text", "ver2_lf")
        vf.pack(fill=tk.X, padx=8, pady=4)
        self.var_v2_git = tk.BooleanVar(value=False)
        self.chk_v2 = ttk.Checkbutton(
            vf,
            text=ui_i18n.t(self.var_ui_lang.get(), "chk_v2"),
            variable=self.var_v2_git,
        )
        self._reg_i18n(self.chk_v2, "text", "chk_v2")
        self.chk_v2.grid(row=0, column=0, columnspan=4, sticky=tk.W)
        self.var_v2_push = tk.BooleanVar(value=False)
        self.chk_v2_push = ttk.Checkbutton(
            vf,
            text=ui_i18n.t(self.var_ui_lang.get(), "chk_v2_push"),
            variable=self.var_v2_push,
        )
        self._reg_i18n(self.chk_v2_push, "text", "chk_v2_push")
        self.chk_v2_push.grid(row=1, column=0, columnspan=4, sticky=tk.W)
        lv2 = ttk.Label(vf, text=ui_i18n.t(self.var_ui_lang.get(), "lbl_v2_cd"))
        self._reg_i18n(lv2, "text", "lbl_v2_cd")
        lv2.grid(row=2, column=0, sticky=tk.W, pady=4)
        self.var_v2_cooldown = tk.StringVar(value="90")
        ttk.Entry(vf, textvariable=self.var_v2_cooldown, width=8).grid(row=2, column=1, sticky=tk.W)
        self.btn_v2_demo = ttk.Button(
            vf,
            text=ui_i18n.t(self.var_ui_lang.get(), "btn_v2_demo"),
            command=self._demo_v2_dialog,
        )
        self._reg_i18n(self.btn_v2_demo, "text", "btn_v2_demo")
        self.btn_v2_demo.grid(row=2, column=2, sticky=tk.W, padx=12)
        vf.columnconfigure(3, weight=1)

        v3f = ttk.LabelFrame(
            self,
            text=ui_i18n.t(self.var_ui_lang.get(), "v3_lf"),
            padding=8,
        )
        self._lf_v3 = v3f
        self._reg_i18n(v3f, "text", "v3_lf")
        v3f.pack(fill=tk.X, padx=8, pady=4)
        vr = 0
        lv3d = ttk.Label(v3f, text=ui_i18n.t(self.var_ui_lang.get(), "lbl_v3_dest"))
        self._reg_i18n(lv3d, "text", "lbl_v3_dest")
        lv3d.grid(row=vr, column=0, sticky=tk.W, pady=2)
        self.var_v3_local = tk.StringVar()
        ttk.Entry(v3f, textvariable=self.var_v3_local, width=56).grid(
            row=vr, column=1, columnspan=2, sticky=tk.EW, pady=2
        )
        self.btn_v3_browse = ttk.Button(
            v3f, text=ui_i18n.t(self.var_ui_lang.get(), "btn_v3_browse"), command=self._browse_v3_dest
        )
        self._reg_i18n(self.btn_v3_browse, "text", "btn_v3_browse")
        self.btn_v3_browse.grid(row=vr, column=3, sticky=tk.E, pady=2)
        vr += 1
        lv3r = ttk.Label(v3f, text=ui_i18n.t(self.var_ui_lang.get(), "lbl_v3_remote"))
        self._reg_i18n(lv3r, "text", "lbl_v3_remote")
        lv3r.grid(row=vr, column=0, sticky=tk.W, pady=2)
        self.var_v3_remote = tk.StringVar()
        ttk.Entry(v3f, textvariable=self.var_v3_remote, width=56).grid(
            row=vr, column=1, columnspan=3, sticky=tk.EW, pady=2
        )
        vr += 1
        self.btn_v3 = ttk.Button(
            v3f,
            text=ui_i18n.t(self.var_ui_lang.get(), "btn_v3_run"),
            command=self._run_v3_reverse_sync,
        )
        self._reg_i18n(self.btn_v3, "text", "btn_v3_run")
        self.btn_v3.grid(row=vr, column=0, columnspan=2, sticky=tk.W, pady=4)
        v3f.columnconfigure(1, weight=1)

        mdf = ttk.LabelFrame(
            self,
            text=ui_i18n.t(self.var_ui_lang.get(), "multi_lf"),
            padding=8,
        )
        self._lf_multi = mdf
        self._reg_i18n(mdf, "text", "multi_lf")
        mdf.pack(fill=tk.X, padx=8, pady=4)
        self.var_multi_deploy_mode = tk.StringVar(value="off")
        mr = 0
        lmm = ttk.Label(mdf, text=ui_i18n.t(self.var_ui_lang.get(), "lbl_multi_mode"))
        self._reg_i18n(lmm, "text", "lbl_multi_mode")
        lmm.grid(row=mr, column=0, sticky=tk.W)
        mf = ttk.Frame(mdf)
        mf.grid(row=mr, column=1, sticky=tk.W)
        self._multi_mode_rbs: list[tuple[str, ttk.Radiobutton]] = []
        for key, lab_key in (
            ("off", "multi_m_off"),
            ("additional", "multi_m_add"),
            ("targets_only", "multi_m_only"),
        ):
            rb = ttk.Radiobutton(
                mf,
                text=ui_i18n.t(self.var_ui_lang.get(), lab_key),
                variable=self.var_multi_deploy_mode,
                value=key,
            )
            self._multi_mode_rbs.append((lab_key, rb))
            rb.pack(anchor=tk.W)
        mr += 1
        self.lbl_multi_hint = ttk.Label(
            mdf,
            text=ui_i18n.t(self.var_ui_lang.get(), "multi_hint")
            + f" ({MAX_DEPLOY_TARGETS})",
            font=("Segoe UI", 8),
        )
        self.lbl_multi_hint.grid(row=mr, column=1, sticky=tk.W)
        mr += 1
        self.btn_multi_edit = ttk.Button(
            mdf,
            text=ui_i18n.t(self.var_ui_lang.get(), "btn_multi_edit"),
            command=self._edit_deploy_targets,
        )
        self._reg_i18n(self.btn_multi_edit, "text", "btn_multi_edit")
        self.btn_multi_edit.grid(row=mr, column=1, sticky=tk.W, pady=4)
        mr += 1
        self.var_bulk_on_start = tk.BooleanVar(value=False)
        self.chk_bulk_on_start = ttk.Checkbutton(
            mdf,
            text=ui_i18n.t(self.var_ui_lang.get(), "chk_bulk_on_start"),
            variable=self.var_bulk_on_start,
        )
        self._reg_i18n(self.chk_bulk_on_start, "text", "chk_bulk_on_start")
        self.chk_bulk_on_start.grid(row=mr, column=1, sticky=tk.W)
        mr += 1
        self.btn_bulk_pick = ttk.Button(
            mdf,
            text=ui_i18n.t(self.var_ui_lang.get(), "bulk_pick_chk"),
            command=self._on_bulk_pick_folders,
        )
        self._reg_i18n(self.btn_bulk_pick, "text", "bulk_pick_chk")
        self.btn_bulk_pick.grid(row=mr, column=1, sticky=tk.W, pady=2)
        mdf.columnconfigure(1, weight=1)

    def _rel_lines_from_textwidget(self, w: tk.Text) -> list[str]:
        raw = w.get("1.0", tk.END)
        out: list[str] = []
        for line in raw.replace("\r\n", "\n").split("\n"):
            s = line.strip().replace("\\", "/").strip("/")
            if s:
                out.append(s)
        return out

    def _build_sync_scope_panel(self) -> None:
        scf = ttk.LabelFrame(
            self,
            text=ui_i18n.t(self.var_ui_lang.get(), "sync_scope_lf"),
            padding=8,
        )
        self._lf_sync_scope = scf
        self._reg_i18n(scf, "text", "sync_scope_lf")
        scf.pack(fill=tk.X, padx=8, pady=4)
        si = ttk.Label(
            scf,
            text=ui_i18n.t(self.var_ui_lang.get(), "sync_scope_intro"),
            wraplength=920,
            justify=tk.LEFT,
        )
        self._reg_i18n(si, "text", "sync_scope_intro")
        si.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 6))
        self.var_sync_domain_scope = tk.BooleanVar(value=True)
        self.chk_sync_domain_scope = ttk.Checkbutton(
            scf,
            text=ui_i18n.t(self.var_ui_lang.get(), "chk_sync_domain_scope"),
            variable=self.var_sync_domain_scope,
        )
        self._reg_i18n(self.chk_sync_domain_scope, "text", "chk_sync_domain_scope")
        self.chk_sync_domain_scope.grid(row=1, column=0, columnspan=2, sticky=tk.W)
        self.var_sync_skip_appdata = tk.BooleanVar(value=True)
        self.chk_sync_skip_appdata = ttk.Checkbutton(
            scf,
            text=ui_i18n.t(self.var_ui_lang.get(), "chk_sync_skip_appdata"),
            variable=self.var_sync_skip_appdata,
        )
        self._reg_i18n(self.chk_sync_skip_appdata, "text", "chk_sync_skip_appdata")
        self.chk_sync_skip_appdata.grid(row=2, column=0, columnspan=2, sticky=tk.W)
        lbls = ttk.Label(scf, text=ui_i18n.t(self.var_ui_lang.get(), "lbl_sync_star_list"))
        self._reg_i18n(lbls, "text", "lbl_sync_star_list")
        lbls.grid(row=3, column=0, sticky=tk.W, pady=(8, 2))
        star_frame = ttk.Frame(scf)
        star_frame.grid(row=4, column=0, columnspan=2, sticky=tk.NSEW)
        self.txt_sync_star = tk.Text(star_frame, height=4, width=88, font=("Consolas", 9))
        sb1 = ttk.Scrollbar(star_frame, command=self.txt_sync_star.yview)
        self.txt_sync_star.configure(yscrollcommand=sb1.set)
        self.txt_sync_star.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb1.pack(side=tk.RIGHT, fill=tk.Y)
        lblm = ttk.Label(scf, text=ui_i18n.t(self.var_ui_lang.get(), "lbl_sync_mark_list"))
        self._reg_i18n(lblm, "text", "lbl_sync_mark_list")
        lblm.grid(row=5, column=0, sticky=tk.W, pady=(8, 2))
        mark_frame = ttk.Frame(scf)
        mark_frame.grid(row=6, column=0, columnspan=2, sticky=tk.NSEW)
        self.txt_sync_mark = tk.Text(mark_frame, height=4, width=88, font=("Consolas", 9))
        sb2 = ttk.Scrollbar(mark_frame, command=self.txt_sync_mark.yview)
        self.txt_sync_mark.configure(yscrollcommand=sb2.set)
        self.txt_sync_mark.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb2.pack(side=tk.RIGHT, fill=tk.Y)
        scf.columnconfigure(0, weight=1)

    def _parse_delta_folder_mappings_from_text(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        raw = self.txt_delta_mappings.get("1.0", tk.END)
        for line in raw.replace("\r\n", "\n").split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "\t" in line:
                a, b = line.split("\t", 1)
            else:
                continue
            loc = a.strip().replace("\\", "/").strip("/")
            names = [x.strip() for x in b.replace("\\", "/").split("|") if x.strip()]
            seg = loc.split("/")[-1] if loc else ""
            if seg and names:
                out.append({"local_segment": seg, "remote_folder_names": names})
        return out

    def _build_delta_ai_panel(self) -> None:
        df = ttk.LabelFrame(
            self,
            text=ui_i18n.t(self.var_ui_lang.get(), "delta_ai_lf"),
            padding=8,
        )
        self._lf_delta_ai = df
        self._reg_i18n(df, "text", "delta_ai_lf")
        df.pack(fill=tk.X, padx=8, pady=4)
        di = ttk.Label(
            df,
            text=ui_i18n.t(self.var_ui_lang.get(), "delta_triangle_intro"),
            wraplength=920,
            justify=tk.LEFT,
        )
        self._reg_i18n(di, "text", "delta_triangle_intro")
        di.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 4))
        dfmt = ttk.Label(
            df,
            text=ui_i18n.t(self.var_ui_lang.get(), "delta_format_hint"),
            font=("Segoe UI", 8),
        )
        self._reg_i18n(dfmt, "text", "delta_format_hint")
        dfmt.grid(row=1, column=0, columnspan=2, sticky=tk.W)
        dbox = ttk.Frame(df)
        dbox.grid(row=2, column=0, columnspan=2, sticky=tk.NSEW, pady=4)
        self.txt_delta_mappings = tk.Text(dbox, height=4, width=88, font=("Consolas", 9))
        sbd = ttk.Scrollbar(dbox, command=self.txt_delta_mappings.yview)
        self.txt_delta_mappings.configure(yscrollcommand=sbd.set)
        self.txt_delta_mappings.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sbd.pack(side=tk.RIGHT, fill=tk.Y)
        lcursor = ttk.Label(
            df,
            text=ui_i18n.t(self.var_ui_lang.get(), "ai_cursor_intro"),
            wraplength=920,
            justify=tk.LEFT,
        )
        self._reg_i18n(lcursor, "text", "ai_cursor_intro")
        lcursor.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(8, 4))
        self.var_ai_rewrite_upload = tk.BooleanVar(value=False)
        self.chk_ai_rewrite = ttk.Checkbutton(
            df,
            text=ui_i18n.t(self.var_ui_lang.get(), "chk_ai_rewrite_upload"),
            variable=self.var_ai_rewrite_upload,
        )
        self._reg_i18n(self.chk_ai_rewrite, "text", "chk_ai_rewrite_upload")
        self.chk_ai_rewrite.grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=(2, 2))
        self.var_ai_rewrite_launch_cursor = tk.BooleanVar(value=False)
        self.chk_ai_rewrite_cursor = ttk.Checkbutton(
            df,
            text=ui_i18n.t(self.var_ui_lang.get(), "chk_ai_rewrite_launch_cursor"),
            variable=self.var_ai_rewrite_launch_cursor,
        )
        self._reg_i18n(self.chk_ai_rewrite_cursor, "text", "chk_ai_rewrite_launch_cursor")
        self.chk_ai_rewrite_cursor.grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=(0, 4))
        lai = ttk.Label(df, text=ui_i18n.t(self.var_ui_lang.get(), "lbl_ai_rewrite_instruction"))
        self._reg_i18n(lai, "text", "lbl_ai_rewrite_instruction")
        lai.grid(row=6, column=0, sticky=tk.W, pady=(4, 2))
        ibox = ttk.Frame(df)
        ibox.grid(row=7, column=0, columnspan=2, sticky=tk.NSEW)
        self.txt_ai_rewrite_instruction = tk.Text(ibox, height=8, width=88, font=("Consolas", 9))
        sbi = ttk.Scrollbar(ibox, command=self.txt_ai_rewrite_instruction.yview)
        self.txt_ai_rewrite_instruction.configure(yscrollcommand=sbi.set)
        self.txt_ai_rewrite_instruction.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sbi.pack(side=tk.RIGHT, fill=tk.Y)
        lex = ttk.Label(df, text=ui_i18n.t(self.var_ui_lang.get(), "lbl_ai_rewrite_extensions"))
        self._reg_i18n(lex, "text", "lbl_ai_rewrite_extensions")
        lex.grid(row=8, column=0, sticky=tk.W, pady=(6, 2))
        self.var_ai_rewrite_extensions = tk.StringVar(value="")
        ttk.Entry(df, textvariable=self.var_ai_rewrite_extensions, width=72).grid(
            row=9, column=0, columnspan=2, sticky=tk.W
        )
        df.columnconfigure(0, weight=1)

    def _build_log(self) -> None:
        lf = ttk.LabelFrame(
            self, text=ui_i18n.t(self.var_ui_lang.get(), "log_lf"), padding=4
        )
        self._lf_log = lf
        self._reg_i18n(lf, "text", "log_lf")
        lf.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self.txt_log = tk.Text(lf, height=12, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9))
        scroll = ttk.Scrollbar(lf, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=scroll.set)
        self.txt_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_buttons(self) -> None:
        bf = ttk.Frame(self, padding=6)
        bf.pack(fill=tk.X)
        self.btn_start = ttk.Button(
            bf, text=ui_i18n.t(self.var_ui_lang.get(), "btn_start"), command=self._start_watcher
        )
        self._reg_i18n(self.btn_start, "text", "btn_start")
        self.btn_start.pack(side=tk.LEFT, padx=4)
        self.btn_stop = ttk.Button(
            bf,
            text=ui_i18n.t(self.var_ui_lang.get(), "btn_stop"),
            command=self._stop_watcher,
            state=tk.DISABLED,
        )
        self._reg_i18n(self.btn_stop, "text", "btn_stop")
        self.btn_stop.pack(side=tk.LEFT, padx=4)
        ttk.Label(
            bf,
            text=(
                f"DB: {profiles_db_path()}  （環境変数 {data_dir_env_var_name()} で保存先を変更可・"
                "docs/GOOGLE_DRIVE_DATA_DIR.md）"
            ),
            foreground="gray",
            wraplength=520,
        ).pack(side=tk.RIGHT, padx=8)

    def _setup_logging(self) -> None:
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        h = GuiLogHandler(self._log_q)
        h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
        root.addHandler(h)

    def _drain_log_queue(self) -> None:
        try:
            while True:
                line = self._log_q.get_nowait()
                self.txt_log.configure(state=tk.NORMAL)
                self.txt_log.insert(tk.END, line + "\n")
                self.txt_log.see(tk.END)
                self.txt_log.configure(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.after(150, self._drain_log_queue)

    def _poll_v2_queue(self) -> None:
        try:
            while True:
                ev = self._v2_queue.get_nowait()
                self._handle_v2_event(ev)
        except queue.Empty:
            pass
        self.after(260, self._poll_v2_queue)

    def _handle_v2_event(self, ev: dict[str, Any]) -> None:
        cfg = self._runtime_cfg
        if not cfg or not cfg.get("sync", {}).get("v2_git_ai_prompt"):
            return
        sync = cfg.get("sync") or {}
        try:
            cd = float(sync.get("v2_prompt_cooldown_seconds") or 90)
        except (TypeError, ValueError):
            cd = 90
        now = time.time()
        if now - self._v2_last_prompt < cd:
            logging.info("Ver2 確認はクールダウン中のためスキップしました。")
            return
        lr = Path(sync["local_root"]).expanduser().resolve()
        ai_cfg = cfg.get("ai") or {}

        if not is_git_on_path():
            ask_ok_scroll(
                self,
                self._app_title() + " — Git",
                multilingual_git_install_help(),
            )
            return

        kind = ev.get("kind")
        msg = ""
        if kind == "upload":
            p = Path(ev["path"])
            summary = build_v2_summary_upload(p, lr)
            try:
                rel = p.resolve().relative_to(lr).as_posix()
            except ValueError:
                rel = p.name
            msg = ai_git_management_question(
                summary,
                ai_cfg,
                static_fallback_builder=lambda r=rel: static_multilingual_git_question_upload(r),
            )
        elif kind == "rename":
            src = Path(ev["src"])
            dest = Path(ev["dest"])
            is_dir = bool(ev.get("is_dir"))
            summary = build_v2_summary_rename(src, dest, lr, is_dir)
            try:
                rs = src.resolve().relative_to(lr).as_posix()
            except ValueError:
                rs = src.name
            try:
                rd = dest.resolve().relative_to(lr).as_posix()
            except ValueError:
                rd = dest.name
            msg = ai_git_management_question(
                summary,
                ai_cfg,
                static_fallback_builder=lambda a=rs, b=rd: static_multilingual_git_question_rename(
                    a, b
                ),
            )
        else:
            return

        self._v2_last_prompt = now
        if ask_yes_no_scroll(self, self._app_title() + " — Ver2 / Git", msg):
            self._v2_run_git_commit(lr)

    def _v2_run_git_commit(self, repo_root: Path) -> None:
        ok, info = ensure_git_repository(repo_root)
        if not ok:
            messagebox.showerror(self._app_title(), info)
            return
        ok2, info2 = git_add_all_and_commit(repo_root, "ftp-auto-sync Ver2 snapshot")
        if not ok2:
            messagebox.showerror(self._app_title(), info2)
            return
        logging.info("Ver2 Git: %s", info2)
        push_note = ""
        cfg = self._runtime_cfg if self._runtime_cfg is not None else self._config_from_ui()
        if cfg.get("sync", {}).get("v2_git_github_push"):
            ok3, info3 = git_try_push(repo_root)
            if ok3:
                logging.info("Ver2 GitHub: %s", info3)
                push_note = "\n\nGitHub push:\n" + info3
            else:
                logging.warning("Ver2 GitHub push 失敗: %s", info3)
                push_note = "\n\nGitHub push は失敗しました:\n" + info3
        messagebox.showinfo(self._app_title(), "Git に記録しました。\n" + info2 + push_note)

    def _demo_v2_dialog(self) -> None:
        if not self.var_v2_git.get():
            messagebox.showinfo(
                self._app_title(),
                "先に「Ver2」のチェックをオンにしてください。\n"
                "オンにしてプロファイル保存後、「監視開始」でも同じ確認が自動で出ます。",
            )
            return
        data = self._config_from_ui()
        err = self._validate_config_dict(data)
        if err:
            messagebox.showerror(self._app_title(), err)
            return
        sync = data.get("sync") or {}
        lr = Path(sync["local_root"]).expanduser().resolve()
        demo_file = lr / ".ftp-auto-sync-v2-demo.txt"
        summary = build_v2_summary_upload(demo_file, lr)
        ai_cfg = data.get("ai") or {}
        try:
            rel = demo_file.relative_to(lr).as_posix()
        except ValueError:
            rel = ".ftp-auto-sync-v2-demo.txt"
        msg = ai_git_management_question(
            summary,
            ai_cfg,
            static_fallback_builder=lambda r=rel: static_multilingual_git_question_upload(r),
        )
        if not is_git_on_path():
            ask_ok_scroll(self, self._app_title() + " — Git をインストール", multilingual_git_install_help())
            return
        if ask_yes_no_scroll(self, self._app_title() + " — Ver2（試す）", msg):
            self._v2_run_git_commit(lr)

    def _browse_local(self) -> None:
        d = filedialog.askdirectory(title="監視するフォルダを選択")
        if d:
            self.var_local.set(d)

    def _browse_v3_dest(self) -> None:
        d = filedialog.askdirectory(title="Ver3 のローカル保存先")
        if d:
            self.var_v3_local.set(d)

    def _run_v3_reverse_sync(self) -> None:
        if self._v3_busy:
            messagebox.showinfo(self._app_title(), "Ver3 の処理が実行中です。")
            return
        data = self._config_from_ui()
        err = self._validate_config_dict(data)
        if err:
            messagebox.showerror(self._app_title(), err)
            return
        sync = data.get("sync") or {}
        dest_s = (sync.get("v3_reverse_local") or "").strip()
        if not dest_s:
            messagebox.showerror(self._app_title(), "Ver3 の「ローカル保存先」を入力してください。")
            return
        dest = Path(dest_s).expanduser()
        rr_ui = (sync.get("v3_reverse_remote_override") or "").strip()
        rr_default = (sync.get("remote_root") or "").strip()
        remote_use = rr_ui if rr_ui else rr_default
        host = (data.get("ftp") or {}).get("host") or ""
        body = (
            "以下の内容で、レンタルサーバーからローカルへ一括ダウンロードします。\n\n"
            f"■ FTP ホスト\n{host}\n\n"
            "■ サーバー側の起点パス（FTP）\n"
            f"{remote_use or '(ログイン直後のディレクトリ)'}\n\n"
            "■ ローカル保存先\n"
            f"{dest}\n\n"
            "・サーバー上に存在するファイル・フォルダのみを取得します。\n"
            "・サーバーに無いローカル側のファイル・フォルダは削除しません。\n"
            "・同名のファイルは上書きします。\n"
            "・完了まで時間がかかることがあります。\n"
        )
        if not ask_yes_no_scroll(
            self,
            self._app_title() + " — Ver3 / 逆同期",
            body,
            radio_frame_label="V3 逆同期（FTP→ローカル一括取得）を実行するか",
        ):
            return
        self._v3_busy = True
        self.btn_v3.configure(state=tk.DISABLED)
        cfg_copy = dict(data)
        threading.Thread(
            target=self._v3_worker,
            args=(cfg_copy, remote_use, dest.resolve()),
            daemon=True,
        ).start()

    def _v3_worker(self, cfg: dict[str, Any], remote_path: str, dest: Path) -> None:
        try:
            ftp_cfg = cfg.get("ftp") or {}
            fc, dc, err = run_reverse_sync(ftp_cfg, remote_path, dest)
            self.after(
                0,
                lambda fc=fc, dc=dc, err=err: self._v3_finished(fc, dc, err),
            )
        except Exception as e:
            self.after(0, lambda msg=str(e): self._v3_finished(0, 0, msg))
        finally:
            self.after(0, self._v3_ui_done)

    def _v3_ui_done(self) -> None:
        self._v3_busy = False
        try:
            self.btn_v3.configure(state=tk.NORMAL)
        except tk.TclError:
            pass

    def _v3_finished(self, files: int, dirs: int, err: str | None) -> None:
        if err:
            messagebox.showerror(self._app_title(), "Ver3 逆同期が完了しませんでした。\n\n" + err)
            return
        messagebox.showinfo(
            self._app_title(),
            "Ver3 逆同期が完了しました。\n\n"
            f"取得ファイル数: {files}\n"
            f"通過したディレクトリ数: {dirs}",
        )

    def _config_from_ui(self) -> dict:
        try:
            port = int(self.var_port.get().strip() or "21")
        except ValueError:
            port = 21
        try:
            deb = float(self.var_debounce.get().strip() or "1.5")
        except ValueError:
            deb = 1.5
        try:
            ad = int(self.var_anchor_depth.get().strip() or "3")
        except ValueError:
            ad = 3
        try:
            msd = int(self.var_max_sync_depth.get().strip() or "-1")
        except ValueError:
            msd = -1
        try:
            v2cd = int(self.var_v2_cooldown.get().strip() or "90")
        except ValueError:
            v2cd = 90
        return {
            "ftp": {
                "host": self.var_host.get().strip(),
                "port": port,
                "username": self.var_user.get().strip(),
                "password": self.var_password.get(),
                "password_env": "FTP_PASSWORD",
                "use_tls": bool(self.var_tls.get()),
                "passive": bool(self.var_passive.get()),
                "timeout": 60,
            },
            "sync": {
                "local_root": self.var_local.get().strip(),
                "remote_root": self.var_remote.get().strip(),
                "debounce_seconds": deb,
                "max_sync_directory_depth": msd,
                "backup_remote_previous": bool(self.var_backup_remote.get()),
                "recursive": bool(self.var_recursive.get()),
                "use_anchor_sync": bool(self.var_use_anchor.get()),
                "anchor_auto_match": bool(self.var_anchor_auto.get()),
                "anchor_folder_name": self.var_anchor.get().strip(),
                "max_anchor_search_depth": max(0, min(ad, 128)),
                "exclude_names": [".git", "__pycache__", ".venv", "node_modules", ".idea"],
                "exclude_extensions": [".tmp", ".swp", ".lock"],
                "v2_git_ai_prompt": bool(self.var_v2_git.get()),
                "v2_git_github_push": bool(self.var_v2_push.get()),
                "v2_prompt_cooldown_seconds": max(5, min(v2cd, 86400)),
                "v3_reverse_local": self.var_v3_local.get().strip(),
                "v3_reverse_remote_override": self.var_v3_remote.get().strip(),
                "multi_deploy_mode": self.var_multi_deploy_mode.get().strip(),
                "deploy_targets": copy.deepcopy(self._deploy_targets),
                "only_upload_if_local_newer": bool(self.var_only_newer.get()),
                "upload_time_skew_seconds": 2.0,
                "ai_anchor_sync": bool(self.var_ai_anchor.get()),
                "bulk_deploy_confirm_on_start": bool(self.var_bulk_on_start.get()),
                "ui_language": self.var_ui_lang.get(),
                "sync_default_domain_scope": bool(self.var_sync_domain_scope.get()),
                "sync_skip_under_app_datadir": bool(self.var_sync_skip_appdata.get()),
                "sync_star_exclude_rel_roots": self._rel_lines_from_textwidget(
                    self.txt_sync_star
                ),
                "sync_mark_include_rel_roots": self._rel_lines_from_textwidget(
                    self.txt_sync_mark
                ),
                "delta_folder_mappings": self._parse_delta_folder_mappings_from_text(),
                "ai_rewrite_on_upload": bool(self.var_ai_rewrite_upload.get()),
                "ai_rewrite_launch_cursor": bool(self.var_ai_rewrite_launch_cursor.get()),
                "ai_rewrite_instruction": self.txt_ai_rewrite_instruction.get(
                    "1.0", tk.END
                ).strip(),
                "ai_rewrite_extensions": self.var_ai_rewrite_extensions.get().strip(),
            },
            "ai": {
                "openai_api_key": self.var_openai_key.get().strip(),
                "openai_base_url": self.var_openai_base.get().strip(),
                "openai_model": self.var_openai_model.get().strip(),
            },
        }

    def _apply_config_to_ui(self, data: dict) -> None:
        ftp = data.get("ftp") or {}
        sync = data.get("sync") or {}
        ai = data.get("ai") or {}
        self.var_host.set(str(ftp.get("host", "")))
        self.var_port.set(str(ftp.get("port", 21)))
        self.var_user.set(str(ftp.get("username", "")))
        pw = ftp.get("password")
        self.var_password.set(str(pw) if pw is not None else "")
        self.var_tls.set(bool(ftp.get("use_tls")))
        self.var_passive.set(bool(ftp.get("passive", True)))
        self.var_local.set(str(sync.get("local_root", "")))
        self.var_remote.set(str(sync.get("remote_root", "public_html")))
        self.var_max_sync_depth.set(str(sync.get("max_sync_directory_depth", -1)))
        self.var_debounce.set(str(sync.get("debounce_seconds", 1.5)))
        self.var_backup_remote.set(bool(sync.get("backup_remote_previous", True)))
        self.var_recursive.set(bool(sync.get("recursive", True)))
        self.var_use_anchor.set(bool(sync.get("use_anchor_sync", True)))
        self.var_anchor_auto.set(bool(sync.get("anchor_auto_match", True)))
        self.var_anchor.set(str(sync.get("anchor_folder_name", "")))
        self.var_anchor_depth.set(str(sync.get("max_anchor_search_depth", 3)))
        self.var_openai_key.set(str(ai.get("openai_api_key", "")))
        self.var_openai_base.set(str(ai.get("openai_base_url", "https://api.openai.com/v1")))
        self.var_openai_model.set(str(ai.get("openai_model", "gpt-4o-mini")))
        self.var_v2_git.set(bool(sync.get("v2_git_ai_prompt", False)))
        self.var_v2_push.set(bool(sync.get("v2_git_github_push", False)))
        self.var_v2_cooldown.set(str(sync.get("v2_prompt_cooldown_seconds", 90)))
        self.var_v3_local.set(str(sync.get("v3_reverse_local", "")))
        self.var_v3_remote.set(str(sync.get("v3_reverse_remote_override", "")))
        self.var_multi_deploy_mode.set(sync.get("multi_deploy_mode", "off"))
        self._deploy_targets = normalize_deploy_targets(sync.get("deploy_targets"))
        self.var_only_newer.set(bool(sync.get("only_upload_if_local_newer", True)))
        self.var_ai_anchor.set(bool(sync.get("ai_anchor_sync", False)))
        self.var_bulk_on_start.set(bool(sync.get("bulk_deploy_confirm_on_start", False)))
        self.var_sync_domain_scope.set(bool(sync.get("sync_default_domain_scope", True)))
        self.var_sync_skip_appdata.set(bool(sync.get("sync_skip_under_app_datadir", True)))
        self.txt_sync_star.delete("1.0", tk.END)
        self.txt_sync_star.insert(
            "1.0",
            "\n".join(str(x) for x in (sync.get("sync_star_exclude_rel_roots") or [])),
        )
        self.txt_sync_mark.delete("1.0", tk.END)
        self.txt_sync_mark.insert(
            "1.0",
            "\n".join(str(x) for x in (sync.get("sync_mark_include_rel_roots") or [])),
        )
        self.txt_delta_mappings.delete("1.0", tk.END)
        dm_lines: list[str] = []
        for d in sync.get("delta_folder_mappings") or []:
            if not isinstance(d, dict):
                continue
            loc = str(d.get("local_segment") or "").strip()
            rem = d.get("remote_folder_names") or []
            if loc and rem:
                dm_lines.append(f"{loc}\t{'|'.join(str(x) for x in rem)}")
        self.txt_delta_mappings.insert("1.0", "\n".join(dm_lines))
        self.var_ai_rewrite_upload.set(bool(sync.get("ai_rewrite_on_upload", False)))
        self.var_ai_rewrite_launch_cursor.set(
            bool(sync.get("ai_rewrite_launch_cursor", False))
        )
        self.txt_ai_rewrite_instruction.delete("1.0", tk.END)
        self.txt_ai_rewrite_instruction.insert(
            "1.0", str(sync.get("ai_rewrite_instruction", "")).strip()
        )
        self.var_ai_rewrite_extensions.set(str(sync.get("ai_rewrite_extensions", "")))
        ul = str(sync.get("ui_language", "ja")).strip().lower().replace("-", "_")
        if ul in ui_i18n.LANG_CODES:
            self.var_ui_lang.set(ul)
        self._apply_ui_language()

    def _edit_deploy_targets(self) -> None:
        def on_save(data: list[dict[str, Any]]) -> None:
            self._deploy_targets = normalize_deploy_targets(data)
            logging.info("マルチデプロイターゲットを更新しました（プロファイル保存で記録されます）。")

        DeployTargetsDialog(self, self._deploy_targets, on_save)

    def _merge_bulk_paths_to_targets(self, paths: list[str]) -> None:
        dt = normalize_deploy_targets(self._deploy_targets)
        pi = 0
        for raw in paths:
            app = raw.strip().replace("\\", "/").strip("/")
            if not app:
                continue
            while pi < len(dt) and dt[pi].get("enabled"):
                pi += 1
            if pi >= len(dt):
                messagebox.showwarning(
                    self._app_title(),
                    f"空きターゲットがありません（最大 {MAX_DEPLOY_TARGETS} 件）。",
                )
                break
            dt[pi]["enabled"] = True
            dt[pi]["remote_append_path"] = app
            dt[pi]["label"] = app[:48] if len(app) > 48 else app
            pi += 1
        self._deploy_targets = dt
        logging.info("一斉配信先をマルチデプロイに反映しました（プロファイル保存で記録）。")

    def _on_bulk_pick_folders(self) -> None:
        data = self._config_from_ui()
        err = self._validate_config_dict(data)
        if err:
            messagebox.showerror(self._app_title(), err)
            return
        sync = data.get("sync") or {}
        lr = Path(sync["local_root"]).expanduser().resolve()
        ftp = data.get("ftp") or {}

        def on_ok(sel: list[str]) -> None:
            self._merge_bulk_paths_to_targets(sel)

        show_bulk_remote_folder_dialog(self, ftp, sync, lr, on_ok)

    def _duplicate_profile(self) -> None:
        if self._current_profile_id is None:
            messagebox.showinfo(
                self._app_title(),
                "リストで複製元のプロファイルを選択してください。",
            )
            return
        base = self.var_profile_name.get().strip() or "profile"
        name = simpledialog.askstring(
            self._app_title(),
            "新しい表示名",
            initialvalue=base + " COPY",
            parent=self,
        )
        if not name or not name.strip():
            return
        try:
            pid = self._store.duplicate(self._current_profile_id, name.strip())
            self._current_profile_id = pid
            self.var_profile_name.set(name.strip())
            self._store.set_last_profile_id(pid)
            self._refresh_profile_list()
            self._select_listbox_by_id(pid)
            messagebox.showinfo(self._app_title(), f"複製しました (id={pid})。")
        except Exception as e:
            messagebox.showerror(self._app_title(), str(e))

    def _export_profile_json(self) -> None:
        if self._current_profile_id is None:
            messagebox.showinfo(self._app_title(), "エクスポートするプロファイルを選択してください。")
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="JSON へ書き出し",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("すべて", "*.*")],
        )
        if not path:
            return
        try:
            self._store.export_config_json(self._current_profile_id, Path(path))
            messagebox.showinfo(self._app_title(), "書き出しました。")
        except Exception as e:
            messagebox.showerror(self._app_title(), str(e))

    def _import_profile_json(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="JSON から取り込み",
            filetypes=[("JSON", "*.json"), ("すべて", "*.*")],
        )
        if not path:
            return
        name = simpledialog.askstring(
            self._app_title(),
            "プロファイル表示名",
            initialvalue="import",
            parent=self,
        )
        if not name or not name.strip():
            return
        try:
            pid = self._store.import_json_file(Path(path), name.strip())
            self._current_profile_id = pid
            self.var_profile_name.set(name.strip())
            row = self._store.get(pid)
            if row:
                _n, conf = row
                self._apply_config_to_ui(conf)
            self._store.set_last_profile_id(pid)
            self._refresh_profile_list()
            self._select_listbox_by_id(pid)
            messagebox.showinfo(self._app_title(), f"取り込みました (id={pid})。")
        except Exception as e:
            messagebox.showerror(self._app_title(), str(e))

    def _open_app_data_folder(self) -> None:
        d = app_data_dir()
        d.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(d))  # type: ignore[attr-defined]
        except Exception as e:
            messagebox.showerror(self._app_title(), str(e))

    def _clone_data_folder_dialog(self) -> None:
        dest = filedialog.askdirectory(parent=self, title="データ一式のコピー先（例: Google ドライブ上のフォルダ）")
        if not dest:
            return
        src = app_data_dir()
        dst = Path(dest).expanduser().resolve() / f"FTPAutoSync_clone_{int(time.time())}"
        try:
            shutil.copytree(src, dst, dirs_exist_ok=True)
            messagebox.showinfo(self._app_title(), f"コピーしました:\n{dst}")
        except Exception as e:
            messagebox.showerror(self._app_title(), str(e))

    def _maybe_bulk_deploy_on_start(self, cfg: dict[str, Any]) -> None:
        sync = cfg.get("sync") or {}
        if not sync.get("bulk_deploy_confirm_on_start"):
            return
        mode = (sync.get("multi_deploy_mode") or "off").strip().lower()
        if mode == "off":
            return
        lr = Path(sync["local_root"]).expanduser().resolve()
        ftp = cfg.get("ftp") or {}

        def on_ok(sel: list[str]) -> None:
            self._merge_bulk_paths_to_targets(sel)
            try:
                if self._current_profile_id is not None:
                    self._store.update(
                        self._current_profile_id,
                        self.var_profile_name.get().strip() or "無題",
                        self._config_from_ui(),
                    )
            except Exception:
                pass

        show_bulk_remote_folder_dialog(self, ftp, sync, lr, on_ok)

    def _bootstrap_load(self) -> None:
        self._refresh_profile_list()
        last = self._store.get_last_profile_id()
        if last is not None:
            row = self._store.get(last)
            if row:
                self._current_profile_id = last
                name, cfg = row
                self.var_profile_name.set(name)
                self._apply_config_to_ui(cfg)
                logging.info("前回のプロファイルを読み込みました (id=%s)", last)
                self._select_listbox_by_id(last)
                return
        if self._store.count() > 0:
            self._refresh_profile_list()
            if self._profile_list_ids:
                self.lb_profiles.selection_set(0)
                self._on_profile_list_select()
            return
        ex = bundled_example_config()
        if ex and ex.is_file():
            try:
                self._apply_config_to_ui(load_config(ex))
                logging.info("テンプレートを表示しました。プロファイルに保存してください。")
            except Exception:
                pass

    def _refresh_profile_list(self) -> None:
        self.lb_profiles.delete(0, tk.END)
        q = self.var_profile_search.get()
        rows = self._store.search(q, limit=500)
        self._profile_list_ids = [pid for pid, _ in rows]
        for pid, name in rows:
            self.lb_profiles.insert(tk.END, f"{pid} — {name}")
        n = self._store.count()
        self.lbl_profile_status.configure(
            text=f"登録 {n:,} / 最大 {MAX_PROFILES:,} 件（検索結果は最大500件表示） ・ {profiles_db_path()}"
        )

    def _select_listbox_by_id(self, profile_id: int) -> None:
        try:
            idx = self._profile_list_ids.index(profile_id)
        except ValueError:
            self._refresh_profile_list()
            try:
                idx = self._profile_list_ids.index(profile_id)
            except ValueError:
                return
        self.lb_profiles.selection_clear(0, tk.END)
        self.lb_profiles.selection_set(idx)
        self.lb_profiles.see(idx)

    def _on_profile_list_select(self, *_args: object) -> None:
        sel = self.lb_profiles.curselection()
        if not sel:
            return
        i = int(sel[0])
        if i < 0 or i >= len(self._profile_list_ids):
            return
        pid = self._profile_list_ids[i]
        row = self._store.get(pid)
        if not row:
            return
        name, cfg = row
        self._current_profile_id = pid
        self.var_profile_name.set(name)
        self._apply_config_to_ui(cfg)
        self._store.set_last_profile_id(pid)
        logging.info("プロファイル id=%s を読み込みました。", pid)

    def _new_profile(self) -> None:
        self._current_profile_id = None
        self.var_profile_name.set("新規プロファイル")
        ex = bundled_example_config()
        if ex and ex.is_file():
            try:
                self._apply_config_to_ui(load_config(ex))
            except Exception:
                pass
        logging.info("新規プロファイル用にフォームを初期化しました。")

    def _validate_config_dict(self, data: dict) -> str | None:
        if not data["ftp"]["host"]:
            return "FTP ホストを入力してください。"
        if not data["sync"]["local_root"]:
            return "監視フォルダを指定してください。"
        path = Path(data["sync"]["local_root"])
        if not path.is_dir():
            return f"監視フォルダが存在しません:\n{path}"
        if data["sync"].get("use_anchor_sync") and not data["sync"].get(
            "anchor_auto_match", True
        ) and not data["sync"].get("ai_anchor_sync"):
            if not (data["sync"].get("anchor_folder_name") or "").strip():
                return (
                    "手動アンカー（自動照合オフ）では「アンカー名」が必要です。"
                    "または「同名フォルダで自動照合」にチェックを入れてください。"
                )
        return None

    def _save_profile_to_db(self) -> None:
        data = self._config_from_ui()
        err = self._validate_config_dict(data)
        if err:
            messagebox.showerror(self._app_title(), err)
            return
        name = self.var_profile_name.get().strip() or "無題"
        try:
            if self._current_profile_id is None:
                pid = self._store.create(name, data)
                self._current_profile_id = pid
                logging.info("プロファイルを新規作成 id=%s", pid)
            else:
                self._store.update(self._current_profile_id, name, data)
                logging.info("プロファイルを更新 id=%s", self._current_profile_id)
            self._store.set_last_profile_id(self._current_profile_id)
            self._refresh_profile_list()
            if self._current_profile_id is not None:
                self._select_listbox_by_id(self._current_profile_id)
            messagebox.showinfo(self._app_title(), "プロファイルに保存しました。")
        except RuntimeError as e:
            messagebox.showerror(self._app_title(), str(e))
        except Exception as e:
            messagebox.showerror(self._app_title(), str(e))

    def _delete_profile(self) -> None:
        if self._current_profile_id is None:
            messagebox.showinfo(self._app_title(), "リストで削除するプロファイルを選択してください。")
            return
        if not messagebox.askyesno(self._app_title(), f"id={self._current_profile_id} を削除しますか？"):
            return
        pid = self._current_profile_id
        self._store.delete(pid)
        if self._store.get_last_profile_id() == pid:
            self._store.set_last_profile_id(None)
        self._current_profile_id = None
        self._new_profile()
        self._refresh_profile_list()
        logging.info("プロファイル id=%s を削除しました。", pid)

    def _start_watcher(self) -> None:
        self._save_config_silent()
        if self._current_profile_id is None:
            messagebox.showerror(self._app_title(), "先に「プロファイルに保存」して id を付与してください。")
            return
        cfg = self._config_from_ui()
        err = self._validate_config_dict(cfg)
        if err:
            messagebox.showerror(self._app_title(), err)
            return
        with self._watcher_lock:
            if self._watcher is not None:
                messagebox.showinfo(self._app_title(), "すでに監視中です。")
                return
            try:
                mapping = prepare_anchor_sync_or_legacy(
                    cfg,
                    messagebox.askyesno,
                    app_title=self._app_title(),
                    profile_id=self._current_profile_id,
                )
            except Exception as e:
                messagebox.showerror(self._app_title(), str(e))
                return
            if mapping is None:
                return
            self._maybe_bulk_deploy_on_start(cfg)
            cfg = self._config_from_ui()
            try:
                self._runtime_cfg = dict(cfg)
                self._watcher = WatcherService(dict(cfg), mapping, self._v2_queue)
                self._watcher.start()
            except Exception as e:
                self._watcher = None
                self._runtime_cfg = None
                messagebox.showerror(self._app_title(), str(e))
                return
        self.btn_start.configure(state=tk.DISABLED)
        self.btn_stop.configure(state=tk.NORMAL)
        logging.info("監視を開始しました。")

    def _save_config_silent(self) -> None:
        if self._current_profile_id is None:
            return
        data = self._config_from_ui()
        if self._validate_config_dict(data):
            return
        try:
            self._store.update(
                self._current_profile_id,
                self.var_profile_name.get().strip() or "無題",
                data,
            )
        except Exception:
            pass

    def _stop_watcher(self) -> None:
        with self._watcher_lock:
            if self._watcher is None:
                return
            try:
                self._watcher.stop()
            finally:
                self._watcher = None
                self._runtime_cfg = None
        self.btn_start.configure(state=tk.NORMAL)
        self.btn_stop.configure(state=tk.DISABLED)
        logging.info("監視を停止しました。")

    def _on_close(self) -> None:
        self._stop_watcher()
        self.destroy()

    def mainloop(self, n: int = 0) -> None:
        logging.info("%s を起動しました。", self._app_title())
        super().mainloop(n)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    app = FtpAutoSyncApp()
    app.mainloop()


if __name__ == "__main__":
    main()
