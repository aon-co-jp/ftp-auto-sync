"""
FTP 自動同期 — Windows 向け GUI（tkinter）。
プロファイルは SQLite（最大 100,000 件）に保存: %LOCALAPPDATA%\\FTPAutoSync\\profiles.db
Ver2: アップロード後などに Git／GitHub 確認。Ver3: FTP→ローカル一括ダウンロード（逆同期）。
"""
from __future__ import annotations

import copy
import json
import logging
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from anchor_sync import prepare_anchor_sync_or_legacy
from deploy_targets_dialog import DeployTargetsDialog
from ftp_watcher import WatcherService, load_config
from multi_deploy import MAX_DEPLOY_TARGETS, normalize_deploy_targets
from v3_ftp_download import run_reverse_sync
from paths import bundled_example_config, data_dir_env_var_name, profiles_db_path
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

APP_TITLE = "FTP 自動同期"


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
        self.title(APP_TITLE)
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

        self._build_profile_panel()
        self._build_form()
        self._build_log()
        self._build_buttons()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._setup_logging()
        self._bootstrap_load()
        self.after(150, self._drain_log_queue)
        self.after(260, self._poll_v2_queue)

    def _build_profile_panel(self) -> None:
        pf = ttk.LabelFrame(
            self,
            text=f"プロファイル（最大 {MAX_PROFILES:,} 件・FTPアカウント／サーバー）",
            padding=6,
        )
        pf.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(pf, text="表示名").grid(row=0, column=0, sticky=tk.W)
        self.var_profile_name = tk.StringVar(value="新規プロファイル")
        ttk.Entry(pf, textvariable=self.var_profile_name, width=36).grid(
            row=0, column=1, sticky=tk.W, padx=4
        )
        ttk.Label(pf, text="検索").grid(row=0, column=2, sticky=tk.E, padx=(12, 4))
        self.var_profile_search = tk.StringVar()
        ttk.Entry(pf, textvariable=self.var_profile_search, width=24).grid(
            row=0, column=3, sticky=tk.EW
        )
        ttk.Button(pf, text="検索", command=self._refresh_profile_list).grid(
            row=0, column=4, padx=4
        )
        self.lb_profiles = tk.Listbox(pf, height=5, exportselection=False, font=("Segoe UI", 9))
        self.lb_profiles.grid(row=1, column=0, columnspan=4, sticky=tk.NSEW, pady=4)
        sb = ttk.Scrollbar(pf, command=self.lb_profiles.yview)
        sb.grid(row=1, column=4, sticky=tk.NS)
        self.lb_profiles.configure(yscrollcommand=sb.set)
        bf = ttk.Frame(pf)
        bf.grid(row=2, column=0, columnspan=5, sticky=tk.W)
        ttk.Button(bf, text="一覧更新", command=self._refresh_profile_list).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="新規", command=self._new_profile).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="プロファイルに保存", command=self._save_profile_to_db).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(bf, text="削除", command=self._delete_profile).pack(side=tk.LEFT, padx=2)
        self.lbl_profile_status = ttk.Label(pf, text="", foreground="gray")
        self.lbl_profile_status.grid(row=3, column=0, columnspan=5, sticky=tk.W)
        pf.columnconfigure(3, weight=1)
        self.lb_profiles.bind("<<ListboxSelect>>", self._on_profile_list_select)
        self.lb_profiles.bind("<Double-Button-1>", self._on_profile_list_select)

    def _build_form(self) -> None:
        frm = ttk.LabelFrame(self, text="接続・同期", padding=8)
        frm.pack(fill=tk.X, padx=8, pady=6)

        r = 0
        ttk.Label(frm, text="FTP ホスト").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.var_host = tk.StringVar()
        ttk.Entry(frm, textvariable=self.var_host, width=40).grid(
            row=r, column=1, columnspan=3, sticky=tk.EW, pady=2
        )
        r += 1

        ttk.Label(frm, text="ポート").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.var_port = tk.StringVar(value="21")
        ttk.Entry(frm, textvariable=self.var_port, width=8).grid(row=r, column=1, sticky=tk.W, pady=2)
        self.var_tls = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm, text="FTPS (TLS)", variable=self.var_tls).grid(
            row=r, column=2, sticky=tk.W, padx=8
        )
        self.var_passive = tk.BooleanVar(value=True)
        ttk.Checkbutton(frm, text="パッシブモード", variable=self.var_passive).grid(
            row=r, column=3, sticky=tk.W
        )
        r += 1

        ttk.Label(frm, text="ユーザー名").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.var_user = tk.StringVar()
        ttk.Entry(frm, textvariable=self.var_user, width=28).grid(row=r, column=1, sticky=tk.W, pady=2)
        ttk.Label(frm, text="パスワード").grid(row=r, column=2, sticky=tk.W, padx=(12, 0), pady=2)
        self.var_password = tk.StringVar()
        ttk.Entry(frm, textvariable=self.var_password, width=20, show="*").grid(
            row=r, column=3, sticky=tk.W, pady=2
        )
        r += 1

        ttk.Label(frm, text="監視フォルダ").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.var_local = tk.StringVar()
        ttk.Entry(frm, textvariable=self.var_local, width=50).grid(
            row=r, column=1, columnspan=2, sticky=tk.EW, pady=2
        )
        ttk.Button(frm, text="参照…", command=self._browse_local).grid(row=r, column=3, sticky=tk.E, pady=2)
        r += 1

        ttk.Label(frm, text="リモート先頭パス").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.var_remote = tk.StringVar(value="public_html")
        ttk.Entry(frm, textvariable=self.var_remote, width=50).grid(
            row=r, column=1, columnspan=3, sticky=tk.EW, pady=2
        )
        r += 1

        ttk.Label(frm, text="同期する最大ディレクトリ深さ").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.var_max_sync_depth = tk.StringVar(value="-1")
        ttk.Entry(frm, textvariable=self.var_max_sync_depth, width=8).grid(
            row=r, column=1, sticky=tk.W, pady=2
        )
        ttk.Label(
            frm,
            text="(-1=制限なし。アンカー同期時はアンカー直下のフォルダ段数のみ数える／通常は監視ルートからの段数)",
            font=("Segoe UI", 8),
        ).grid(row=r, column=2, columnspan=2, sticky=tk.W)
        r += 1

        ttk.Label(frm, text="デバウンス(秒)").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.var_debounce = tk.StringVar(value="1.5")
        ttk.Entry(frm, textvariable=self.var_debounce, width=8).grid(row=r, column=1, sticky=tk.W, pady=2)
        self.var_recursive = tk.BooleanVar(value=True)
        ttk.Checkbutton(frm, text="サブフォルダも監視", variable=self.var_recursive).grid(
            row=r, column=2, columnspan=2, sticky=tk.W
        )
        r += 1
        self.var_backup_remote = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frm,
            text="上書き前にリモートの同名ファイルを「名前-YYYY-MM-DD-HHmm.拡張子」へ退避",
            variable=self.var_backup_remote,
        ).grid(row=r, column=0, columnspan=4, sticky=tk.W)
        r += 1
        af = ttk.LabelFrame(self, text="アンカー階層同期（任意）", padding=8)
        af.pack(fill=tk.X, padx=8, pady=4)
        ar = 0
        self.var_use_anchor = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            af,
            text="アンカー同期を使う（同名フォルダの自動照合で階層のずれを吸収。オフにすると従来どおり監視ルートからの相対パスのみ）",
            variable=self.var_use_anchor,
        ).grid(row=ar, column=0, columnspan=4, sticky=tk.W)
        ar += 1
        self.var_anchor_auto = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            af,
            text="同名フォルダで自動照合（既定・サーバー側を探索してフォルダ名で対応。アンカー名の入力は不要）",
            variable=self.var_anchor_auto,
        ).grid(row=ar, column=0, columnspan=4, sticky=tk.W)
        ar += 1
        ttk.Label(af, text="アンカー名（手動モード時のみ）").grid(row=ar, column=0, sticky=tk.W, pady=2)
        self.var_anchor = tk.StringVar(value="")
        ttk.Entry(af, textvariable=self.var_anchor, width=16).grid(row=ar, column=1, sticky=tk.W, pady=2)
        ttk.Label(af, text="サーバー探索の深さ(階層)").grid(row=ar, column=2, sticky=tk.E, padx=(12, 4), pady=2)
        self.var_anchor_depth = tk.StringVar(value="3")
        ttk.Entry(af, textvariable=self.var_anchor_depth, width=4).grid(row=ar, column=3, sticky=tk.W, pady=2)
        ar += 1
        ttk.Label(af, text="OpenAI API キー（任意）").grid(row=ar, column=0, sticky=tk.W, pady=2)
        self.var_openai_key = tk.StringVar()
        ttk.Entry(af, textvariable=self.var_openai_key, width=36, show="*").grid(
            row=ar, column=1, columnspan=3, sticky=tk.EW, pady=2
        )
        ar += 1
        ttk.Label(af, text="API ベースURL").grid(row=ar, column=0, sticky=tk.W, pady=2)
        self.var_openai_base = tk.StringVar(value="https://api.openai.com/v1")
        ttk.Entry(af, textvariable=self.var_openai_base, width=50).grid(
            row=ar, column=1, columnspan=3, sticky=tk.EW, pady=2
        )
        ar += 1
        ttk.Label(af, text="モデル名").grid(row=ar, column=0, sticky=tk.W, pady=2)
        self.var_openai_model = tk.StringVar(value="gpt-4o-mini")
        ttk.Entry(af, textvariable=self.var_openai_model, width=24).grid(row=ar, column=1, sticky=tk.W, pady=2)
        af.columnconfigure(1, weight=1)
        frm.columnconfigure(1, weight=1)

        vf = ttk.LabelFrame(
            self,
            text="Ver2 — Git / GitHub（チェック→プロファイル保存→監視開始）",
            padding=8,
        )
        vf.pack(fill=tk.X, padx=8, pady=4)
        self.var_v2_git = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            vf,
            text="アップロード後・ファイル／フォルダの名前変更後に、8言語で Git／GitHub の確認を出す（API キーなしでも定型文）",
            variable=self.var_v2_git,
        ).grid(row=0, column=0, columnspan=4, sticky=tk.W)
        self.var_v2_push = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            vf,
            text="上で YES と確定したあと Git に記録したうえで、GitHub（origin）へ git push も試みる",
            variable=self.var_v2_push,
        ).grid(row=1, column=0, columnspan=4, sticky=tk.W)
        ttk.Label(vf, text="確認の最短間隔（秒）").grid(row=2, column=0, sticky=tk.W, pady=4)
        self.var_v2_cooldown = tk.StringVar(value="90")
        ttk.Entry(vf, textvariable=self.var_v2_cooldown, width=8).grid(row=2, column=1, sticky=tk.W)
        ttk.Button(
            vf,
            text="確認ダイアログを試す（クリック・監視なし）",
            command=self._demo_v2_dialog,
        ).grid(row=2, column=2, sticky=tk.W, padx=12)
        vf.columnconfigure(3, weight=1)

        v3f = ttk.LabelFrame(
            self,
            text="Ver3 — 逆同期（FTP→ローカル一括ダウンロード）",
            padding=8,
        )
        v3f.pack(fill=tk.X, padx=8, pady=4)
        vr = 0
        ttk.Label(v3f, text="ローカル保存先（ドライブ／フォルダ）").grid(
            row=vr, column=0, sticky=tk.W, pady=2
        )
        self.var_v3_local = tk.StringVar()
        ttk.Entry(v3f, textvariable=self.var_v3_local, width=56).grid(
            row=vr, column=1, columnspan=2, sticky=tk.EW, pady=2
        )
        ttk.Button(v3f, text="参照…", command=self._browse_v3_dest).grid(
            row=vr, column=3, sticky=tk.E, pady=2
        )
        vr += 1
        ttk.Label(
            v3f,
            text="サーバー起点パス（空欄＝「リモート先頭パス」と同じ）",
        ).grid(row=vr, column=0, sticky=tk.W, pady=2)
        self.var_v3_remote = tk.StringVar()
        ttk.Entry(v3f, textvariable=self.var_v3_remote, width=56).grid(
            row=vr, column=1, columnspan=3, sticky=tk.EW, pady=2
        )
        vr += 1
        self.btn_v3 = ttk.Button(
            v3f,
            text="V3 一斉ダウンロード（確認のあと実行）",
            command=self._run_v3_reverse_sync,
        )
        self.btn_v3.grid(row=vr, column=0, columnspan=2, sticky=tk.W, pady=4)
        v3f.columnconfigure(1, weight=1)

        mdf = ttk.LabelFrame(
            self,
            text="マルチデプロイ（指定1〜50・ドメイン置換／複数FTP）",
            padding=8,
        )
        mdf.pack(fill=tk.X, padx=8, pady=4)
        self.var_multi_deploy_mode = tk.StringVar(value="off")
        mr = 0
        ttk.Label(mdf, text="モード").grid(row=mr, column=0, sticky=tk.W)
        mf = ttk.Frame(mdf)
        mf.grid(row=mr, column=1, sticky=tk.W)
        for key, lab in (
            ("off", "オフ（これまでどおり1系統のアップロード）"),
            ("additional", "既定FTPにも送る → さらにマルチターゲットへ"),
            ("targets_only", "マルチターゲットのみ（条件一致時）"),
        ):
            ttk.Radiobutton(mf, text=lab, variable=self.var_multi_deploy_mode, value=key).pack(
                anchor=tk.W
            )
        mr += 1
        ttk.Label(
            mdf,
            text=f"ターゲットは最大 {MAX_DEPLOY_TARGETS} 件。各行ダブルクリックで編集。",
            font=("Segoe UI", 8),
        ).grid(row=mr, column=1, sticky=tk.W)
        mr += 1
        ttk.Button(mdf, text="ターゲット一覧（指定1〜50）を編集…", command=self._edit_deploy_targets).grid(
            row=mr, column=1, sticky=tk.W, pady=4
        )
        mdf.columnconfigure(1, weight=1)

    def _build_log(self) -> None:
        lf = ttk.LabelFrame(self, text="ログ", padding=4)
        lf.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self.txt_log = tk.Text(lf, height=12, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9))
        scroll = ttk.Scrollbar(lf, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=scroll.set)
        self.txt_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_buttons(self) -> None:
        bf = ttk.Frame(self, padding=6)
        bf.pack(fill=tk.X)
        self.btn_start = ttk.Button(bf, text="監視開始", command=self._start_watcher)
        self.btn_start.pack(side=tk.LEFT, padx=4)
        self.btn_stop = ttk.Button(bf, text="監視停止", command=self._stop_watcher, state=tk.DISABLED)
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
                APP_TITLE + " — Git",
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
        if ask_yes_no_scroll(self, APP_TITLE + " — Ver2 / Git", msg):
            self._v2_run_git_commit(lr)

    def _v2_run_git_commit(self, repo_root: Path) -> None:
        ok, info = ensure_git_repository(repo_root)
        if not ok:
            messagebox.showerror(APP_TITLE, info)
            return
        ok2, info2 = git_add_all_and_commit(repo_root, "ftp-auto-sync Ver2 snapshot")
        if not ok2:
            messagebox.showerror(APP_TITLE, info2)
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
        messagebox.showinfo(APP_TITLE, "Git に記録しました。\n" + info2 + push_note)

    def _demo_v2_dialog(self) -> None:
        if not self.var_v2_git.get():
            messagebox.showinfo(
                APP_TITLE,
                "先に「Ver2」のチェックをオンにしてください。\n"
                "オンにしてプロファイル保存後、「監視開始」でも同じ確認が自動で出ます。",
            )
            return
        data = self._config_from_ui()
        err = self._validate_config_dict(data)
        if err:
            messagebox.showerror(APP_TITLE, err)
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
            ask_ok_scroll(self, APP_TITLE + " — Git をインストール", multilingual_git_install_help())
            return
        if ask_yes_no_scroll(self, APP_TITLE + " — Ver2（試す）", msg):
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
            messagebox.showinfo(APP_TITLE, "Ver3 の処理が実行中です。")
            return
        data = self._config_from_ui()
        err = self._validate_config_dict(data)
        if err:
            messagebox.showerror(APP_TITLE, err)
            return
        sync = data.get("sync") or {}
        dest_s = (sync.get("v3_reverse_local") or "").strip()
        if not dest_s:
            messagebox.showerror(APP_TITLE, "Ver3 の「ローカル保存先」を入力してください。")
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
            APP_TITLE + " — Ver3 / 逆同期",
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
            messagebox.showerror(APP_TITLE, "Ver3 逆同期が完了しませんでした。\n\n" + err)
            return
        messagebox.showinfo(
            APP_TITLE,
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

    def _edit_deploy_targets(self) -> None:
        def on_save(data: list[dict[str, Any]]) -> None:
            self._deploy_targets = normalize_deploy_targets(data)
            logging.info("マルチデプロイターゲットを更新しました（プロファイル保存で記録されます）。")

        DeployTargetsDialog(self, self._deploy_targets, on_save)

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
        ):
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
            messagebox.showerror(APP_TITLE, err)
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
            messagebox.showinfo(APP_TITLE, "プロファイルに保存しました。")
        except RuntimeError as e:
            messagebox.showerror(APP_TITLE, str(e))
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))

    def _delete_profile(self) -> None:
        if self._current_profile_id is None:
            messagebox.showinfo(APP_TITLE, "リストで削除するプロファイルを選択してください。")
            return
        if not messagebox.askyesno(APP_TITLE, f"id={self._current_profile_id} を削除しますか？"):
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
            messagebox.showerror(APP_TITLE, "先に「プロファイルに保存」して id を付与してください。")
            return
        cfg = self._config_from_ui()
        err = self._validate_config_dict(cfg)
        if err:
            messagebox.showerror(APP_TITLE, err)
            return
        with self._watcher_lock:
            if self._watcher is not None:
                messagebox.showinfo(APP_TITLE, "すでに監視中です。")
                return
            try:
                mapping = prepare_anchor_sync_or_legacy(
                    cfg,
                    messagebox.askyesno,
                    app_title=APP_TITLE,
                    profile_id=self._current_profile_id,
                )
            except Exception as e:
                messagebox.showerror(APP_TITLE, str(e))
                return
            if mapping is None:
                return
            try:
                self._runtime_cfg = dict(cfg)
                self._watcher = WatcherService(dict(cfg), mapping, self._v2_queue)
                self._watcher.start()
            except Exception as e:
                self._watcher = None
                self._runtime_cfg = None
                messagebox.showerror(APP_TITLE, str(e))
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
        logging.info("%s を起動しました。", APP_TITLE)
        super().mainloop(n)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    app = FtpAutoSyncApp()
    app.mainloop()


if __name__ == "__main__":
    main()
