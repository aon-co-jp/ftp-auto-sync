"""Ftp-Auto-Sync GUI 文言（Ver 4.0）。キーは英語スラッグ。"""
from __future__ import annotations

APP_PRODUCT = "Ftp-Auto-Sync"
APP_VERSION = "4.0.0"

LANG_CODES = (
    "ja",
    "ko",
    "zh_cn",
    "zh_tw",
    "en",
    "it",
    "fr",
    "de",
    "ru",
    "uk",
    "ar",
    "fa",
)

# ラジオ表示名（その言語で）
LANG_RADIO_LABELS: dict[str, str] = {
    "ja": "日本語",
    "ko": "한국어",
    "zh_cn": "简体中文",
    "zh_tw": "繁體（台灣）",
    "en": "English",
    "it": "Italiano",
    "fr": "Français",
    "de": "Deutsch",
    "ru": "Русский",
    "uk": "Українська",
    "ar": "العربية",
    "fa": "فارسی",
}

_EN: dict[str, str] = {
    "app_title": f"{APP_PRODUCT} {APP_VERSION}",
    "lang_select": "Language",
    "status_idle": "Idle",
    "status_syncing": "Syncing…",
    "lbl_ftp_auth_key": "Auth key (ACCT / second password, optional)",
    "btn_ftp_test": "Test FTP login",
    "ftp_test_ok": "FTP login succeeded.",
    "btn_rename_profile": "Rename profile",
    "profile_renamed_ok": "Profile display name was updated.",
    "profile_rename_need_select": "Select a profile in the list first.",
    "profile_rename_prompt": "New display name",
    "profile_lf": "Profiles (FTP / server)",
    "lbl_display_name": "Display name",
    "lbl_search": "Search",
    "btn_search_list": "Search",
    "btn_refresh": "Refresh list",
    "btn_new": "New",
    "btn_save": "Save to profile",
    "btn_delete": "Delete",
    "btn_duplicate": "Duplicate",
    "btn_export": "Export JSON…",
    "btn_import": "Import JSON…",
    "btn_data_folder": "Open data folder",
    "btn_clone_all": "Copy all app data…",
    "conn_lf": "Connection & sync",
    "lbl_host": "FTP host",
    "lbl_port": "Port",
    "chk_tls": "FTPS (TLS)",
    "chk_passive": "Passive mode",
    "lbl_user": "Username",
    "lbl_pass": "Password",
    "lbl_watch": "Watch folder",
    "btn_browse_local": "Browse…",
    "lbl_remote_root": "Remote root path",
    "lbl_max_sync_depth": "Max sync directory depth",
    "lbl_max_hint": "(-1 = unlimited)",
    "lbl_debounce": "Debounce (sec)",
    "chk_recursive": "Watch subfolders",
    "chk_backup": "Archive remote file before overwrite",
    "anchor_lf": "Anchor sync",
    "chk_use_anchor": "Use anchor sync (auto same-name folder match)",
    "chk_anchor_auto": "Auto match by folder name (no anchor name required)",
    "lbl_anchor_name": "Anchor name (manual only)",
    "lbl_anchor_depth": "Server search depth (levels)",
    "anchor_skew_intro": (
        "By default, path offset up to the depth below is corrected automatically for sync. "
        "How many levels of offset to correct?"
    ),
    "lbl_skew_levels": "Levels to correct",
    "lbl_skew_hint": "(default 3; applies to server search depth above)",
    "lbl_openai_key": "OpenAI API key (optional)",
    "lbl_openai_base": "API base URL",
    "lbl_openai_model": "Model name",
    "ver2_lf": "Ver2 — Git / GitHub",
    "chk_v2": "Prompt after upload/rename (8 languages)",
    "chk_v2_push": "After YES, also git push to origin",
    "lbl_v2_cd": "Min prompt interval (sec)",
    "btn_v2_demo": "Try prompt (no watch)",
    "v3_lf": "Ver3 — Reverse sync (FTP → local)",
    "lbl_v3_dest": "Local destination",
    "btn_v3_browse": "Browse…",
    "lbl_v3_remote": "Server root (empty = same as remote root)",
    "btn_v3_run": "V3 bulk download (after confirm)",
    "multi_lf": "Multi-deploy (up to 50)",
    "lbl_multi_mode": "Mode",
    "multi_hint": "Double-click a row to edit.",
    "btn_multi_edit": "Edit targets (1–50)…",
    "only_newer_chk": "Upload only if local file is newer than on server (default)",
    "sync_scope_lf": "Sync scope (★ no sync / 〻 sync)",
    "sync_scope_intro": (
        "Default: paths that are not under this app's data directory, and paths under the watch folder "
        "that never pass through a folder whose name contains a dot (e.g. example.com), are not auto-synced. "
        "★ list: relative paths (one per line) — that folder/file and everything under it are never auto-synced. "
        "〻 list: relative paths — that folder/file and below are auto-synced even when the default domain-style rule is on."
    ),
    "chk_sync_domain_scope": 'Use default rule: only paths under a "domain-style" folder name (contains .)',
    "chk_sync_skip_appdata": "Never auto-sync files under the app data directory",
    "lbl_sync_star_list": "★ Never auto-sync (relative paths, one per line):",
    "lbl_sync_mark_list": "〻 Auto-sync including subfolders (relative paths, one per line):",
    "delta_ai_lf": "△ Folder alias ↔ server name + AI rewrite (saved in profile)",
    "delta_triangle_intro": (
        "When the server uses a short folder name (e.g. aon) but locally you use a domain-style folder "
        "(e.g. aon.tokyo), or the opposite, list one row per local folder name (last segment) in the box below. "
        "The app matches those local names against the extra server folder names when resolving the upload path. "
        "Separate server-side names with |. This is saved in the profile."
    ),
    "delta_format_hint": "One line per pair: local_folder_name<TAB>server_name1|server_name2 (TAB between columns).",
    "ai_cursor_intro": (
        "If you install Cursor on this PC first, when AI auto-sync runs (options below), "
        "this app can start Cursor on the file being uploaded so you can edit or rewrite with Cursor’s AI features. "
        "Please use Cursor’s free trial or a paid plan such as PRO, according to Cursor’s own terms. "
        "After saving in Cursor, sync again as usual. "
        "Optional: with an API key, OpenAI-compatible auto-rewrite can also run before upload."
    ),
    "chk_ai_rewrite_upload": "AI auto-sync on upload (OpenAI-compatible rewrite if API key is set)",
    "chk_ai_rewrite_launch_cursor": (
        "Also launch Cursor on the file (Cursor must be installed; use free trial or PRO per Cursor)"
    ),
    "lbl_ai_rewrite_instruction": "AI rewrite policy (saved in profile; domains, logos, wording rules, etc.):",
    "lbl_ai_rewrite_extensions": "Extensions for AI rewrite (empty = default set; e.g. .html,.css,.php,.js):",
    "ai_anchor_chk": "AI-style anchor: sync non-domain folder names (manual anchor optional)",
    "bulk_pick_chk": "Pick bulk deploy folders on server…",
    "chk_bulk_on_start": "Ask bulk deploy paths when starting watch",
    "log_lf": "Log",
    "btn_start": "Start watch",
    "btn_stop": "Stop watch",
    "multi_m_off": "Off (single FTP path)",
    "multi_m_add": "Default FTP + multi targets",
    "multi_m_only": "Multi targets only",
}

_JA: dict[str, str] = {
    "app_title": f"{APP_PRODUCT} {APP_VERSION}",
    "lang_select": "表示言語",
    "status_idle": "待機中",
    "status_syncing": "同期中です。",
    "lbl_ftp_auth_key": "認証キー（ACCT／第二パスワード・任意）",
    "btn_ftp_test": "FTP 接続テスト",
    "ftp_test_ok": "FTP ログインに成功しました。",
    "btn_rename_profile": "プロファイル名変更",
    "profile_renamed_ok": "プロファイル表示名を更新しました。",
    "profile_rename_need_select": "リストで名前を変更するプロファイルを選択してください。",
    "profile_rename_prompt": "新しいプロファイル表示名",
    "profile_lf": "プロファイル（FTP／サーバー）",
    "lbl_display_name": "表示名",
    "lbl_search": "検索",
    "btn_search_list": "検索",
    "btn_refresh": "一覧更新",
    "btn_new": "新規",
    "btn_save": "プロファイルに保存",
    "btn_delete": "削除",
    "btn_duplicate": "複製",
    "btn_export": "JSONへ書き出し…",
    "btn_import": "JSONから取り込み…",
    "btn_data_folder": "データフォルダを開く",
    "btn_clone_all": "データ一式をコピー…",
    "conn_lf": "接続・同期",
    "lbl_host": "FTP ホスト",
    "lbl_port": "ポート",
    "chk_tls": "FTPS (TLS)",
    "chk_passive": "パッシブモード",
    "lbl_user": "ユーザー名",
    "lbl_pass": "パスワード",
    "lbl_watch": "監視フォルダ",
    "btn_browse_local": "参照…",
    "lbl_remote_root": "リモート先頭パス",
    "lbl_max_sync_depth": "同期する最大ディレクトリ深さ",
    "lbl_max_hint": "(-1=制限なし)",
    "lbl_debounce": "デバウンス(秒)",
    "chk_recursive": "サブフォルダも監視",
    "chk_backup": "上書き前にリモートの同名ファイルを日時付きで退避",
    "anchor_lf": "アンカー階層同期",
    "chk_use_anchor": "アンカー同期を使う（同名フォルダの自動照合）",
    "chk_anchor_auto": "同名フォルダで自動照合（アンカー名は不要）",
    "lbl_anchor_name": "アンカー名（手動モード時のみ）",
    "lbl_anchor_depth": "サーバー探索の深さ(階層)",
    "anchor_skew_intro": (
        "現在、デフォルトで3階層までのずれは、自動で誤差の修正を行なって同期をとります。"
        "何階層までのずれを修正しますか？（下の数値。既定3・変更可）"
    ),
    "lbl_skew_levels": "ずれ修正する階層数",
    "lbl_skew_hint": "（この数値がサーバー側フォルダ探索の最大深さになります）",
    "lbl_openai_key": "OpenAI API キー（任意）",
    "lbl_openai_base": "API ベースURL",
    "lbl_openai_model": "モデル名",
    "ver2_lf": "Ver2 — Git / GitHub",
    "chk_v2": "アップロード後など 8 言語で Git 確認",
    "chk_v2_push": "YES 後に git push（origin）",
    "lbl_v2_cd": "確認の最短間隔（秒）",
    "btn_v2_demo": "確認ダイアログを試す",
    "v3_lf": "Ver3 — 逆同期（FTP→ローカル）",
    "lbl_v3_dest": "ローカル保存先",
    "btn_v3_browse": "参照…",
    "lbl_v3_remote": "サーバー起点（空欄＝リモート先頭と同じ）",
    "btn_v3_run": "V3 一斉ダウンロード",
    "multi_lf": "マルチデプロイ（最大50）",
    "lbl_multi_mode": "モード",
    "multi_hint": "ダブルクリックで編集。",
    "btn_multi_edit": "ターゲット一覧を編集…",
    "only_newer_chk": "サーバー上のファイルより新しいときだけ自動アップロード（既定・推奨）",
    "sync_scope_lf": "同期の範囲（★同期しない／〻同期する）",
    "sync_scope_intro": (
        "【既定】このアプリのデータ保存フォルダ（環境変数で指定した場合はその配下）にあるファイルは、"
        "自動ではサーバーと同期しません。また監視フォルダ内で、名前にピリオド「.」を含むフォルダ"
        "（例: example.com）の下に来ないパスは、既定では自動同期しません。"
        "★（五芒星・星で示す除外）: 下の欄に書いた相対パスのフォルダ／ファイルとその下は、チェックを付けた扱いで自動同期しません。"
        "〻（レ点で示す対象）: 下の欄に書いた相対パスのフォルダ／ファイルとその下は、既定のドメイン階層がオンでも自動同期の対象に含めます。"
        "いずれも監視フォルダからの相対パスを1行に1つ（例: coupon-site/public）。"
    ),
    "chk_sync_domain_scope": "既定ルールを使う（名前に「.」を含むフォルダ階層の下だけ既定で同期）",
    "chk_sync_skip_appdata": "アプリのデータ保存フォルダ配下は自動同期しない",
    "lbl_sync_star_list": "★ 自動同期しない（相対パス・1行1つ・配下も含む）:",
    "lbl_sync_mark_list": "〻 自動同期する（相対パス・1行1つ・その下も同期対象）:",
    "delta_ai_lf": "△ 略称／正式名フォルダ対応 ＋ AI 書き換え（プロファイルに保存）",
    "delta_triangle_intro": (
        "サーバー上位が「aon」など略称・ペンネーム、ローカルが「aon.tokyo」のように正式な場合や、その逆も、"
        "下の一覧で「ローカル側のフォルダ名（パスの最後の1段）」と「サーバー側で実際にある別名」を対応付けます（複数 | 区切り）。"
        "アンカー自動照合でリモート索引を引くときに併用されます。"
        "アップロードするファイル内のドメイン名・ロゴ文言などを、プロファイルに書いた方針に沿って OpenAI 互換 API で書き換える場合は、"
        "下のチェックと「書き換え方針」に記載し、API キー（上段のアンカー用と同じ設定）を入れてください。"
        "マルチデプロイの各ターゲットでも同じ方針が適用されます。"
    ),
    "delta_format_hint": "1行1組: ローカルフォルダ名<TAB>サーバー名1|サーバー名2（列の間は TAB）",
    "ai_cursor_intro": (
        "PC に Cursor を事前にインストールしておいていただければ、AI 自動同期（下のオプション有効時）に "
        "Cursor を自動起動し、Cursor 上の AI 機能で編集・書き換えが行えます。"
        "Cursor をご利用の方は、無料トライアルもしくは PRO 版など、Cursor が提供する形態に従ってご利用くださいませ。"
        "エディタで保存したあと、必要に応じて再度同期してください。"
        "（API キーをお持ちの場合は、併せて OpenAI 互換の自動書き換えもアップロード前に実行できます。）"
    ),
    "chk_ai_rewrite_upload": "AI 自動同期（アップロード時・下記方針。API キーがあれば OpenAI 互換で自動書き換え）",
    "chk_ai_rewrite_launch_cursor": "同期時に Cursor を自動起動（要インストール・ご利用は無料トライアルまたは PRO 等 Cursor に従ってください）",
    "lbl_ai_rewrite_instruction": "AI への書き換え方針（プロファイルに保存・ドメイン／ロゴ／禁止事項など）:",
    "lbl_ai_rewrite_extensions": "AI 書き換え対象拡張子（空欄＝既定の .html 等）例: .html,.css,.php,.js",
    "ai_anchor_chk": "AIアンカー同期（ドメイン名でないローカルフォルダ名をサーバーと照合）",
    "bulk_pick_chk": "サーバー上の一斉配信先フォルダを選ぶ…",
    "chk_bulk_on_start": "監視開始時に一斉配信先を確認",
    "log_lf": "ログ",
    "btn_start": "監視開始",
    "btn_stop": "監視停止",
    "multi_m_off": "オフ（1系統のみ）",
    "multi_m_add": "既定FTP＋マルチ",
    "multi_m_only": "マルチのみ",
}

_KO: dict[str, str] = {
    **_EN,
    "app_title": f"{APP_PRODUCT} {APP_VERSION}",
    "lang_select": "언어",
    "profile_lf": "프로필 (FTP/서버)",
    "conn_lf": "연결·동기화",
    "btn_start": "감시 시작",
    "btn_stop": "감시 중지",
    "only_newer_chk": "로컬 파일이 서버보다 최신일 때만 업로드",
}

_ZH_CN: dict[str, str] = {**_EN, "lang_select": "语言", "conn_lf": "连接与同步", "btn_start": "开始监视", "btn_stop": "停止监视", "only_newer_chk": "仅当本地文件比服务器新时才上传"}

_ZH_TW: dict[str, str] = {**_EN, "lang_select": "語言", "conn_lf": "連線與同步", "btn_start": "開始監看", "btn_stop": "停止監看", "only_newer_chk": "僅於本機檔案較新時上傳"}

_IT: dict[str, str] = {**_EN, "conn_lf": "Connessione e sincronizzazione", "btn_start": "Avvia monitoraggio", "btn_stop": "Interrompi"}

_FR: dict[str, str] = {**_EN, "conn_lf": "Connexion et synchronisation", "btn_start": "Démarrer la surveillance", "btn_stop": "Arrêter"}

_DE: dict[str, str] = {**_EN, "conn_lf": "Verbindung & Sync", "btn_start": "Überwachung starten", "btn_stop": "Stoppen"}

_RU: dict[str, str] = {**_EN, "conn_lf": "Подключение и синхронизация", "btn_start": "Начать наблюдение", "btn_stop": "Остановить"}

_UK: dict[str, str] = {**_RU, "conn_lf": "Підключення та синхронізація", "btn_start": "Почати спостереження", "btn_stop": "Зупинити"}

_AR: dict[str, str] = {**_EN, "lang_select": "اللغة", "btn_start": "بدء المراقبة", "btn_stop": "إيقاف"}

_FA: dict[str, str] = {**_EN, "lang_select": "زبان", "btn_start": "شروع پایش", "btn_stop": "توقف"}

TABLES: dict[str, dict[str, str]] = {
    "ja": {**_EN, **_JA},
    "ko": _KO,
    "zh_cn": _ZH_CN,
    "zh_tw": _ZH_TW,
    "en": _EN,
    "it": _IT,
    "fr": _FR,
    "de": _DE,
    "ru": _RU,
    "uk": _UK,
    "ar": _AR,
    "fa": _FA,
}


def t(lang: str, key: str) -> str:
    lang = (lang or "ja").strip().lower().replace("-", "_")
    if lang not in TABLES:
        lang = "en"
    tab = TABLES[lang]
    return tab.get(key) or _EN.get(key) or key
