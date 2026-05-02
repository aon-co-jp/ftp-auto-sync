"""
Ver2: アップロード後・パス変更検知時に AI が Git/GitHub 連携の確認を多言語で提案。
Git 未導入時も主要言語でインストール案内。
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

LOG = logging.getLogger(__name__)

# --- Git 未インストール時（8言語）共通 URL ---
_GIT_WIN_URL = "https://git-scm.com/download/win"


def multilingual_git_install_help() -> str:
    """Git が無いときに messagebox 等へ。そのまま貼れるブロック形式。"""
    return "\n\n".join(
        [
            _block_en_install(),
            _block_ja_install(),
            _block_zh_install(),
            _block_ko_install(),
            _block_ru_install(),
            _block_de_install(),
            _block_ar_install(),
            _block_fa_install(),
        ]
    )


def _block_en_install() -> str:
    return f"""=== English ===
Git is not installed or not on your PATH.

Install Git for Windows:
  {_GIT_WIN_URL}

After installation:
  1. Restart this application and your terminal.
  2. Run: git --version

Git runs only on your PC to record file/folder name history."""


def _block_ja_install() -> str:
    return f"""=== 日本語 ===
Git がインストールされていないか、PATH から見つかりません。

Git for Windows をインストールしてください:
  {_GIT_WIN_URL}

インストール後:
  1. このアプリとターミナルを再起動してください。
  2. 「git --version」で確認してください。

Git はお使いの PC 上だけでファイル名・フォルダ名の履歴を残すために使います。"""


def _block_zh_install() -> str:
    return f"""=== 简体中文 ===
未检测到 Git，或未加入 PATH。

请安装 Git for Windows：
  {_GIT_WIN_URL}

安装后：
  1. 重启本程序与终端。
  2. 运行：git --version

Git 仅在本地用于记录文件与文件夹名称的历史。"""


def _block_ko_install() -> str:
    return f"""=== 한국어 ===
Git이 설치되어 있지 않거나 PATH에 없습니다.

Git for Windows 설치:
  {_GIT_WIN_URL}

설치 후:
  1. 이 앱과 터미널을 다시 시작하세요.
  2. git --version 으로 확인하세요.

Git은 로컬 PC에서만 파일/폴더 이름 이력을 남기는 데 사용됩니다."""


def _block_ru_install() -> str:
    return f"""=== Русский ===
Git не установлен или недоступен в PATH.

Установите Git for Windows:
  {_GIT_WIN_URL}

После установки:
  1. Перезапустите приложение и терминал.
  2. Выполните: git --version

Git используется только локально для истории имён файлов и папок."""


def _block_de_install() -> str:
    return f"""=== Deutsch ===
Git ist nicht installiert oder nicht im PATH.

Git für Windows installieren:
  {_GIT_WIN_URL}

Danach:
  1. Diese App und das Terminal neu starten.
  2. Prüfen mit: git --version

Git dient nur lokal zur Versionshistorie von Datei- und Ordnernamen."""


def _block_ar_install() -> str:
    return f"""=== العربية ===
لم يُعثر على Git أو لا يظهر في PATH.

ثبّت Git لنظام Windows:
  {_GIT_WIN_URL}

بعد التثبيت:
  1. أعد تشغيل هذا البرنامج والطرفية.
  2. نفّذ: git --version

Git يعمل محليًا فقط لتسجيل أسماء الملفات والمجلدات."""


def _block_fa_install() -> str:
    return f"""=== فارسی ===
Git نصب نشده یا در PATH نیست.

Git برای Windows را نصب کنید:
  {_GIT_WIN_URL}

پس از نصب:
  1. این برنامه و ترمینال را مجدداً راه‌اندازی کنید.
  2. با git --version بررسی کنید.

Git فقط روی رایانهٔ شما برای تاریخچهٔ نام فایل و پوشه استفاده می‌شود."""


def bilingual_git_missing_message() -> str:
    """後方互換: 旧コード向け。実体は多言語。"""
    return multilingual_git_install_help()


def is_git_on_path() -> bool:
    return shutil.which("git") is not None


def _run_git(args: list[str], cwd: Path, timeout: int = 120) -> tuple[int, str, str]:
    try:
        creationflags = 0
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW
        p = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=creationflags,
        )
        return p.returncode, p.stdout or "", p.stderr or ""
    except FileNotFoundError:
        return 127, "", "git not found"
    except subprocess.TimeoutExpired:
        return 124, "", "git timeout"


def ensure_git_repository(repo_root: Path) -> tuple[bool, str]:
    repo_root = repo_root.resolve()
    git_dir = repo_root / ".git"
    if git_dir.is_dir():
        return True, "existing repo"
    code, out, err = _run_git(["init"], cwd=repo_root)
    if code != 0:
        return False, (err or out or f"exit {code}")[:500]
    ignore = repo_root / ".gitignore"
    if not ignore.is_file():
        try:
            ignore.write_text(
                "# Added by ftp-auto-sync Ver2 (Git assist)\n"
                ".ftp-auto-sync-local/\n",
                encoding="utf-8",
            )
            _run_git(["add", ".gitignore"], cwd=repo_root)
            _run_git(
                ["commit", "-m", "ftp-auto-sync: add .gitignore", "--allow-empty"],
                cwd=repo_root,
            )
        except OSError:
            pass
    return True, "initialized"


def git_add_all_and_commit(repo_root: Path, message: str) -> tuple[bool, str]:
    code, out, err = _run_git(["add", "-A"], cwd=repo_root)
    if code != 0:
        return False, f"git add: {err or out}"[:500]
    code2, out2, err2 = _run_git(
        ["commit", "-m", message, "--allow-empty"],
        cwd=repo_root,
    )
    if code2 != 0:
        if "nothing to commit" in (err2 + out2).lower():
            return True, "nothing to commit"
        return False, f"git commit: {err2 or out2}"[:500]
    return True, "committed"


def git_try_push(repo_root: Path) -> tuple[bool, str]:
    """origin 等が無い・認証できない場合は失敗してメッセージを返す。"""
    code, out, err = _run_git(["push"], cwd=repo_root, timeout=180)
    if code != 0:
        return False, (err or out or f"exit {code}")[:500]
    return True, (out or err or "push ok").strip()[:500] or "push ok"


def build_v2_summary_upload(local_path: Path, local_root: Path) -> str:
    try:
        rel = local_path.resolve().relative_to(local_root.resolve())
    except ValueError:
        rel = local_path
    return (
        "Context: FTP upload just finished.\n"
        f"Relative path under watch root: {rel.as_posix()}\n\n"
        "Generate ONE confirmation block for the user asking whether they want to use Git "
        "to track file/folder names (for version history and optional publication/sync via GitHub).\n"
        "You MUST output exactly these 8 sections in this order, each starting with the label line:\n"
        "English:\n"
        "日本語:\n"
        "简体中文:\n"
        "한국어:\n"
        "Русский:\n"
        "Deutsch:\n"
        "العربية:\n"
        "فارسی:\n"
        "Each section: one or two short polite sentences. No markdown code fences."
    )


def build_v2_summary_rename(src: Path, dest: Path, local_root: Path, is_dir: bool) -> str:
    kind = "directory" if is_dir else "file"
    try:
        rs = src.resolve().relative_to(local_root.resolve())
    except ValueError:
        rs = src
    try:
        rd = dest.resolve().relative_to(local_root.resolve())
    except ValueError:
        rd = dest
    return (
        f"Context: local {kind} path changed (move/rename).\n"
        f"Before: {rs.as_posix()}\n"
        f"After: {rd.as_posix()}\n\n"
        "Generate ONE confirmation block asking whether to manage names with Git "
        "(history of file/folder names; optional GitHub).\n"
        "You MUST output exactly these 8 sections in this order, each starting with the label line:\n"
        "English:\n"
        "日本語:\n"
        "简体中文:\n"
        "한국어:\n"
        "Русский:\n"
        "Deutsch:\n"
        "العربية:\n"
        "فارسی:\n"
        "Each section: one or two short polite sentences. No markdown code fences."
    )


def static_multilingual_git_question_upload(rel_display: str) -> str:
    """API キーなし時の固定 8 言語テンプレート。"""
    return _static_question_blocks(
        f"(path: {rel_display})\n",
        upload=True,
    )


def static_multilingual_git_question_rename(rs: str, rd: str) -> str:
    return _static_question_blocks(
        f"(before: {rs} → after: {rd})\n",
        upload=False,
    )


def _static_question_blocks(context: str, *, upload: bool) -> str:
    if upload:
        mid_en = "FTP upload has finished."
        mid_ja = "FTP のアップロードが完了しました。"
    else:
        mid_en = "A file or folder path was renamed or moved locally."
        mid_ja = "ローカルでファイルまたはフォルダの名前／場所が変更されました。"
    en_body = (
        f"{mid_en} Do you want to track these changes with Git (file/folder name history), "
        "for optional sync or publication on GitHub?"
    )
    ja_body = (
        f"{mid_ja} "
        "ファイル名・フォルダ名の履歴として Git で管理し、必要なら GitHub への公開や同期のための準備としてよいですか？"
    )
    zh_mid = "上传已完成。" if upload else "本地的文件或文件夹路径已更改。"
    zh_body = f"{zh_mid}是否使用 Git 记录名称变更（可选地与 GitHub 同步或发布）？"
    ko_mid = "업로드가 완료되었습니다." if upload else "로컬에서 파일 또는 폴더 경로가 변경되었습니다."
    ko_body = f"{ko_mid} Git으로 이름 변경 이력을 관리하고, 필요 시 GitHub 동기화·공개를 준비할까요?"
    ru_mid = "Загрузка завершена." if upload else "Локальный путь файла или папки изменён."
    ru_body = f"{ru_mid} Хотите ли вы вести учёт имён через Git (для возможной синхронизации с GitHub)?"
    de_mid = "Der Upload ist abgeschlossen." if upload else "Ein Datei- oder Ordnerpfad wurde lokal geändert."
    de_body = f"{de_mid} Sollen die Namensänderungen mit Git protokolliert werden (optional für GitHub)?"
    ar_mid = "اكتمل الرفع." if upload else "تم تغيير مسار ملف أو مجلد محليًا."
    ar_body = f"{ar_mid} هل تريد تتبع الأسماء باستخدام Git (للمزامنة أو النشر على GitHub اختياريًا)؟"
    fa_mid = "آپلود تمام شد." if upload else "مسیر فایل یا پوشه به‌صورت محلی تغییر کرد."
    fa_body = f"{fa_mid} آیا می‌خواهید با Git تاریخچهٔ نام‌ها را ثبت کنید (برای همگام‌سازی یا انتشار در GitHub در صورت نیاز)؟"
    parts = [
        context.rstrip() + "\n",
        "English:\n" + en_body + "\n\n",
        "日本語:\n" + ja_body + "\n\n",
        "简体中文:\n" + zh_body + "\n\n",
        "한국어:\n" + ko_body + "\n\n",
        "Русский:\n" + ru_body + "\n\n",
        "Deutsch:\n" + de_body + "\n\n",
        "العربية:\n" + ar_body + "\n\n",
        "فارسی:\n" + fa_body,
    ]
    return "".join(parts)


def ai_git_management_question(
    summary: str,
    ai_cfg: dict[str, Any],
    *,
    static_fallback_builder: Callable[[], str] | None = None,
) -> str:
    """
    OpenAI 互換 API で 8 言語ブロックを生成。キーが無いときは static_fallback_builder() を呼ぶ。
    """
    key = (ai_cfg.get("openai_api_key") or "").strip()
    if not key:
        if callable(static_fallback_builder):
            return static_fallback_builder()
        return summary

    base = (ai_cfg.get("openai_base_url") or "https://api.openai.com/v1").rstrip("/")
    model = (ai_cfg.get("openai_model") or "gpt-4o-mini").strip()
    url = base + "/chat/completions"
    system = (
        "You write bilingual/multilingual user-facing confirmation text for a desktop sync app. "
        "Always output exactly 8 labeled sections in this fixed order: "
        "English, 日本語, 简体中文, 한국어, Русский, Deutsch, العربية, فارسی. "
        "Each section starts with its label on its own line, then one or two polite sentences. "
        "Topic: suggest using Git locally to record file/folder name history, "
        "and optionally prepare for GitHub sync or publication — ask for user consent. "
        "Do not use markdown code blocks. Keep Arabic and Persian natural RTL-friendly wording."
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": summary},
        ],
        "max_tokens": 2200,
        "temperature": 0.35,
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
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        return text or (static_fallback_builder() if callable(static_fallback_builder) else summary)
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:400]
        LOG.warning("V2 AI HTTP error: %s %s", e.code, err)
    except Exception as e:
        LOG.warning("V2 AI error: %s", e)
    return static_fallback_builder() if callable(static_fallback_builder) else summary + "\n\n[Git / GitHub confirmation fallback]"
