"""マルチデプロイターゲット（最大50）の一覧・編集ダイアログ。"""
from __future__ import annotations

import copy
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable

from multi_deploy import MAX_DEPLOY_TARGETS, normalize_deploy_targets


class DeployTargetsDialog(tk.Toplevel):
    def __init__(
        self,
        master: tk.Tk,
        targets: list[dict[str, Any]],
        on_save: Callable[[list[dict[str, Any]]], None],
    ) -> None:
        super().__init__(master)
        self.title("マルチデプロイ — ターゲット（指定1〜50）")
        self.geometry("900x520")
        self.transient(master)
        self._data = copy.deepcopy(normalize_deploy_targets(targets))
        self._on_save = on_save

        info = ttk.Label(
            self,
            text=(
                "各行は監視対象ファイルごとに評価されます。"
                "「別FTP」がオフならメインの FTP 接続情報を使います。"
                "書き換えは UTF-8 テキストのみ（拡張子は一覧で判定）。"
                "置換は「検索語1|検索語2<TAB>置換後」のように TAB で区切り、"
                "検索語は | で並べるとそれぞれ同じ置換後へ差し替わります。"
            ),
            wraplength=860,
        )
        info.pack(fill=tk.X, padx=8, pady=4)

        cols = ("ix", "en", "label", "ftp", "append", "cond")
        twrap = ttk.Frame(self)
        twrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self.tree = ttk.Treeview(twrap, columns=cols, show="headings", height=14)
        self.tree.heading("ix", text="#")
        self.tree.heading("en", text="有効")
        self.tree.heading("label", text="ラベル")
        self.tree.heading("ftp", text="FTP")
        self.tree.heading("append", text="remote 追加パス")
        self.tree.heading("cond", text="条件（含む／先頭）")
        self.tree.column("ix", width=36)
        self.tree.column("en", width=44)
        self.tree.column("label", width=88)
        self.tree.column("ftp", width=72)
        self.tree.column("append", width=160)
        self.tree.column("cond", width=380)
        sb = ttk.Scrollbar(twrap, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Double-1>", self._on_double)
        bf = ttk.Frame(self, padding=6)
        bf.pack(fill=tk.X)
        ttk.Button(bf, text="選択を編集…", command=self._edit_selected).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="保存して閉じる", command=self._save_close).pack(side=tk.RIGHT, padx=4)
        ttk.Button(bf, text="キャンセル", command=self.destroy).pack(side=tk.RIGHT, padx=4)

        self._refresh_tree()
        self.grab_set()

    def _summary_cond(self, t: dict[str, Any]) -> str:
        bits = []
        if (t.get("local_path_contains") or "").strip():
            bits.append(f"含む:{t['local_path_contains'][:40]}")
        if (t.get("local_path_prefix") or "").strip():
            bits.append(f"先頭:{t['local_path_prefix'][:40]}")
        if (t.get("filename_glob") or "").strip():
            bits.append(f"ファイル:{t['filename_glob'][:40]}")
        return " / ".join(bits) if bits else "（条件なし＝すべて一致）"

    def _refresh_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for i, t in enumerate(self._data[:MAX_DEPLOY_TARGETS]):
            self.tree.insert(
                "",
                tk.END,
                iid=str(i),
                values=(
                    i + 1,
                    "○" if t.get("enabled") else "",
                    (t.get("label") or "")[:32],
                    "別" if not t.get("use_main_ftp", True) else "メイン",
                    (t.get("remote_append_path") or "")[:48],
                    self._summary_cond(t)[:120],
                ),
            )

    def _selected_index(self) -> int | None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(self.title(), "行を選択してください。", parent=self)
            return None
        return int(sel[0])

    def _on_double(self, _evt: tk.Event) -> None:
        self._edit_selected()

    def _edit_selected(self) -> None:
        ix = self._selected_index()
        if ix is None:
            return
        TargetEditorDialog(self, ix, self._data[ix], self._apply_edit)

    def _apply_edit(self, index: int, new_t: dict[str, Any]) -> None:
        self._data[index] = new_t
        self._refresh_tree()

    def _save_close(self) -> None:
        self._on_save(copy.deepcopy(self._data))
        self.destroy()


class TargetEditorDialog(tk.Toplevel):
    def __init__(
        self,
        master: tk.Toplevel,
        index: int,
        target: dict[str, Any],
        apply_cb: Callable[[int, dict[str, Any]], None],
    ) -> None:
        super().__init__(master)
        self.title(f"指定 {index + 1} を編集")
        self.geometry("640x680")
        self.transient(master)
        self._index = index
        self._apply_cb = apply_cb
        self._t = copy.deepcopy(target)

        f = ttk.Frame(self, padding=8)
        f.pack(fill=tk.BOTH, expand=True)
        r = 0
        self.var_en = tk.BooleanVar(value=bool(self._t.get("enabled")))
        ttk.Checkbutton(f, text="このターゲットを有効にする", variable=self.var_en).grid(
            row=r, column=0, columnspan=2, sticky=tk.W
        )
        r += 1
        ttk.Label(f, text="ラベル").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.var_label = tk.StringVar(value=str(self._t.get("label", "")))
        ttk.Entry(f, textvariable=self.var_label, width=48).grid(row=r, column=1, sticky=tk.EW, pady=2)
        r += 1

        self.var_main = tk.BooleanVar(value=bool(self._t.get("use_main_ftp", True)))
        ttk.Checkbutton(
            f,
            text="メインの FTP（接続・同期のホスト等）をそのまま使う",
            variable=self.var_main,
            command=self._toggle_ftp,
        ).grid(row=r, column=0, columnspan=2, sticky=tk.W)
        r += 1

        ttk.Label(f, text="ホスト（別FTP時）").grid(row=r, column=0, sticky=tk.W)
        self.var_host = tk.StringVar(value=str(self._t.get("host", "")))
        self.ent_host = ttk.Entry(f, textvariable=self.var_host, width=44)
        self.ent_host.grid(row=r, column=1, sticky=tk.EW, pady=2)
        r += 1
        ttk.Label(f, text="ポート").grid(row=r, column=0, sticky=tk.W)
        self.var_port = tk.StringVar(value=str(self._t.get("port", 21)))
        self.ent_port = ttk.Entry(f, textvariable=self.var_port, width=10)
        self.ent_port.grid(row=r, column=1, sticky=tk.W, pady=2)
        r += 1
        ttk.Label(f, text="ユーザー（別FTP時）").grid(row=r, column=0, sticky=tk.W)
        self.var_user = tk.StringVar(value=str(self._t.get("username", "")))
        self.ent_user = ttk.Entry(f, textvariable=self.var_user, width=44)
        self.ent_user.grid(row=r, column=1, sticky=tk.EW, pady=2)
        r += 1
        ttk.Label(f, text="パスワード（別FTP時・未入力なら環境変数）").grid(row=r, column=0, sticky=tk.W)
        self.var_pw = tk.StringVar(value=str(self._t.get("password", "")))
        self.ent_pw = ttk.Entry(f, textvariable=self.var_pw, width=44, show="*")
        self.ent_pw.grid(row=r, column=1, sticky=tk.EW, pady=2)
        r += 1
        self.var_tls = tk.BooleanVar(value=bool(self._t.get("use_tls")))
        self.var_passive = tk.BooleanVar(value=bool(self._t.get("passive", True)))
        ff = ttk.Frame(f)
        ff.grid(row=r, column=1, sticky=tk.W)
        ttk.Checkbutton(ff, text="TLS", variable=self.var_tls).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Checkbutton(ff, text="パッシブ", variable=self.var_passive).pack(side=tk.LEFT)
        r += 1

        ttk.Label(f, text="remote 追加パス").grid(row=r, column=0, sticky=tk.NW, pady=2)
        self.var_append = tk.StringVar(value=str(self._t.get("remote_append_path", "")))
        ttk.Entry(f, textvariable=self.var_append, width=44).grid(row=r, column=1, sticky=tk.EW, pady=2)
        ttk.Label(
            f,
            text="（マッピング後のディレクトリにさらに追加するサブパス。例: mirror/site2）",
            font=("Segoe UI", 8),
        ).grid(row=r + 1, column=1, sticky=tk.W)
        r += 2

        ttk.Label(f, text="ローカル相対パスに含める文字列").grid(row=r, column=0, sticky=tk.W)
        self.var_contain = tk.StringVar(value=str(self._t.get("local_path_contains", "")))
        ttk.Entry(f, textvariable=self.var_contain, width=44).grid(row=r, column=1, sticky=tk.EW, pady=2)
        r += 1
        ttk.Label(f, text="ローカル相対パスの先頭一致").grid(row=r, column=0, sticky=tk.W)
        self.var_prefix = tk.StringVar(value=str(self._t.get("local_path_prefix", "")))
        ttk.Entry(f, textvariable=self.var_prefix, width=44).grid(row=r, column=1, sticky=tk.EW, pady=2)
        r += 1
        ttk.Label(f, text="ファイル名パターン(;区切)").grid(row=r, column=0, sticky=tk.W)
        self.var_glob = tk.StringVar(value=str(self._t.get("filename_glob", "")))
        ttk.Entry(f, textvariable=self.var_glob, width=44).grid(row=r, column=1, sticky=tk.EW, pady=2)
        r += 1

        ttk.Label(f, text="書き換え対象拡張子(,区切・空欄=既定)").grid(row=r, column=0, sticky=tk.W)
        self.var_re_ext = tk.StringVar(value=str(self._t.get("rewrite_extensions", "")))
        ttk.Entry(f, textvariable=self.var_re_ext, width=44).grid(row=r, column=1, sticky=tk.EW, pady=2)
        r += 1
        ttk.Label(
            f,
            text="置換ルール（各行: 検索語1|検索語2|…<TAB>置換後／複数行で複数ルール）",
        ).grid(row=r, column=0, sticky=tk.NW)
        self.txt_pairs = tk.Text(f, height=12, width=52, font=("Consolas", 9))
        self.txt_pairs.grid(row=r, column=1, sticky=tk.EW, pady=2)
        pairs = self._t.get("rewrite_pairs") or []
        lines = []
        for p in pairs:
            if isinstance(p, dict):
                lines.append(f"{p.get('find', '')}\t{p.get('replace', '')}")
        self.txt_pairs.insert("1.0", "\n".join(lines))
        r += 1

        bf = ttk.Frame(f)
        bf.grid(row=r, column=0, columnspan=2, pady=8)
        ttk.Button(bf, text="確定", command=self._ok).pack(side=tk.RIGHT, padx=4)
        ttk.Button(bf, text="キャンセル", command=self.destroy).pack(side=tk.RIGHT, padx=4)
        f.columnconfigure(1, weight=1)
        self._toggle_ftp()
        self.grab_set()

    def _toggle_ftp(self) -> None:
        m = self.var_main.get()
        st = tk.DISABLED if m else tk.NORMAL
        for w in (
            self.ent_host,
            self.ent_port,
            self.ent_user,
            self.ent_pw,
        ):
            w.configure(state=st)

    def _ok(self) -> None:
        pairs: list[dict[str, str]] = []
        raw = self.txt_pairs.get("1.0", tk.END)
        for line in raw.splitlines():
            line = line.rstrip("\r")
            if not line.strip():
                continue
            if "\t" in line:
                find, rep = line.split("\t", 1)
            else:
                messagebox.showerror(
                    self.title(),
                    "各行は TAB で区切り、「左: 検索語を | で並べる」「右: 置換後」の形式にしてください。",
                    parent=self,
                )
                return
            pairs.append({"find": find.strip(), "replace": rep})
        try:
            port = int(self.var_port.get().strip() or "21")
        except ValueError:
            port = 21
        self._t = {
            "enabled": bool(self.var_en.get()),
            "label": self.var_label.get().strip() or f"指定{self._index + 1}",
            "use_main_ftp": bool(self.var_main.get()),
            "host": self.var_host.get().strip(),
            "port": port,
            "username": self.var_user.get().strip(),
            "password": self.var_pw.get(),
            "use_tls": bool(self.var_tls.get()),
            "passive": bool(self.var_passive.get()),
            "remote_append_path": self.var_append.get().strip(),
            "local_path_contains": self.var_contain.get().strip(),
            "local_path_prefix": self.var_prefix.get().strip(),
            "filename_glob": self.var_glob.get().strip(),
            "rewrite_extensions": self.var_re_ext.get().strip(),
            "rewrite_pairs": pairs,
        }
        self._apply_cb(self._index, self._t)
        self.destroy()
