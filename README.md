# ftp-auto-sync

**EN:** Watch a local folder and sync changes to FTP on Windows — optional anchor mapping, AI confirmation, and many profiles.  
**JA:** Windows 向けにローカルフォルダを監視し、変更を FTP に同期するツールです。アンカー階層の揃え方、AI による確認、多数プロファイルに対応します。

### Short descriptions for Git hosts (GitHub「About」など)

Copy from these one-line files:

- **English:** [`DESCRIPTION.en.txt`](DESCRIPTION.en.txt)
- **日本語:** [`DESCRIPTION.ja.txt`](DESCRIPTION.ja.txt)

---

## English

### Overview

`ftp-auto-sync` is a small Python application with:

- **GUI** (`app.py`) and **CLI** (`ftp_watcher.py`)
- **Debounced** uploads after file changes
- Optional **remote backup** before overwrite: `filename-YYYY-MM-DD-HHmm.ext`
- Optional **anchor sync**: match a folder name (e.g. `auto`) between local tree and FTP, with a configurable search depth on the server
- **Approval cache** for mapping; optional **OpenAI-compatible** Chat Completions to phrase the confirm dialog
- **`max_sync_directory_depth`**: limit how many directory levels are synced (`-1` = no limit)
- Up to **100,000 profiles** in SQLite under `%LOCALAPPDATA%\FTPAutoSync\profiles.db`
- **Ver2** (`v2_git_assist.py`): optional Git assist — after upload or path rename, the app can ask (via AI when configured, or fixed templates) whether to use Git for local file/folder name history and optional GitHub sync. The confirmation text is provided in **English, Japanese, Simplified Chinese, Korean, Russian, German, Arabic, and Persian**. If Git is missing, install instructions use the same eight languages.

### Requirements

- Python 3.10+
- Dependencies: see `requirements.txt`

### Install

```bash
cd ftp-auto-sync
pip install -r requirements.txt
```

### Run

GUI:

```bash
python app.py
```

CLI (expects a JSON config path; for profiles, export or mirror settings into a file if you use CLI only):

```bash
python ftp_watcher.py -c path/to/config.json
```

### Build Windows EXE (optional)

```powershell
.\build.ps1
```

Output: `dist\FTPAutoSync.exe` (PyInstaller is installed by the script if missing).

### Windows installer (Inno Setup)

1. Install [Inno Setup 6](https://jrsoftware.org/isdl.php) on the build machine.
2. From the repo root run:

```powershell
.\build_installer.ps1
```

This builds the EXE then compiles `installer\FTPAutoSync.iss`. Output: `release\FTPAutoSync_Setup_<version>.exe`. See [`installer/README.md`](installer/README.md). Bump `#define MyAppVersion` in `installer/FTPAutoSync.iss` when releasing.

### Configuration

- Use the GUI to create and save **profiles** (FTP host, credentials, local root, sync options).
- `config.example.json` is a **template**; runtime data is stored under `%LOCALAPPDATA%\FTPAutoSync\`.

### Security

Do **not** commit real passwords or API keys. Secrets stay in the local profile database on your PC.

### License

[MIT](LICENSE)

### Contributing

Issues and pull requests are welcome.

---

## 日本語 (Japanese)

### 概要

`ftp-auto-sync` は次の機能を備えた小さな Python アプリです。

- **GUI**（`app.py`）と **CLI**（`ftp_watcher.py`）
- ファイル変更を **デバウンス** してから FTP アップロード
- 上書き前にリモート既存ファイルを **日時付きファイル名へ退避**（任意）
- **アンカー同期**（任意）: ローカルとサーバーで同じフォルダ名（例: `auto`）を基準にパスを揃え、サーバー側の探索深さを設定可能
- マッピングの **承認をキャッシュ**；任意で **OpenAI 互換 API** により確認文を言い換え
- **`max_sync_directory_depth`**: 同期するディレクトリの深さ上限（`-1` で無制限）
- SQLite に **最大 10 万件**のプロファイル（`%LOCALAPPDATA%\FTPAutoSync\profiles.db`）
- **Ver2**（`v2_git_assist.py`）: アップロード後やパス変更時に、Git でファイル／フォルダ名を記録し、必要なら GitHub 連携の準備としてよいかを確認。**英語・日本語・简体中文・韓国語・ロシア語・ドイツ語・アラビア語・ペルシャ語（فارسی）**の 8 言語ブロックで表示（AI 利用時は API が生成、オフライン時は固定文）。Git 未インストール時も同 8 言語でインストール案内。

### Git ホスト用の一行説明（GitHub「About」など）

次のファイルをそのままコピーして使えます。

- **English:** [`DESCRIPTION.en.txt`](DESCRIPTION.en.txt)
- **日本語:** [`DESCRIPTION.ja.txt`](DESCRIPTION.ja.txt)

### 動作環境

- Python 3.10 以上
- 依存パッケージ: `requirements.txt` を参照

### インストール

```bash
cd ftp-auto-sync
pip install -r requirements.txt
```

### 起動方法

GUI:

```bash
python app.py
```

CLI（JSON 設定ファイルのパスを指定。プロファイル機能は GUI 主体のため、CLI のみ利用する場合は設定を JSON に書き出して指定してください）:

```bash
python ftp_watcher.py -c path/to/config.json
```

### Windows EXE のビルド（任意）

```powershell
.\build.ps1
```

成果物: `dist\FTPAutoSync.exe`（ビルドスクリプト内で PyInstaller を導入します）。

### Windows インストーラー（Inno Setup）

1. ビルド用 PC に [Inno Setup 6](https://jrsoftware.org/isdl.php) を入れる。
2. リポジトリルートで:

```powershell
.\build_installer.ps1
```

`release\FTPAutoSync_Setup_<バージョン>.exe` が生成されます。詳細は [`installer/README.md`](installer/README.md)。バージョンは `installer\FTPAutoSync.iss` の `#define MyAppVersion` を変更。

### 設定について

- GUI で **プロファイル**（FTP 接続情報・監視フォルダ・同期オプション）を作成し、「プロファイルに保存」します。
- `config.example.json` は **サンプル** です。実行時のデータは `%LOCALAPPDATA%\FTPAutoSync\` 配下に保存されます。

### セキュリティ

**パスワードや API キーをリポジトリに含めないでください。** 秘密情報はご利用の PC 上のプロファイル用データベースにのみ保存されます。

### ライセンス

[MIT](LICENSE)

### コントリビューション

Issue・Pull Request を歓迎します。

## API 方針: REST 全廃・gRPC / Connect へ (2026-11-04)

### 日本語
- **REST は全廃する。新しい API は REST で作らない。** ブラウザや `curl` から呼ぶ API は **Connect の単純呼び出し**(`POST /<パッケージ>.<Service>/<Method>`、`content-type: application/json`、本文は JSON)、サービス間は **gRPC / gRPC-web**(RPoem の管理API `open_runo.admin.v1.Admin` と同じ流儀)。ストリーミングは、必要になってから。
- **既存の REST は、触るときに順に移す。** 移したら旧 REST の経路は消す。移行が終わるまで残るが、**新規には追加しない**。
- **JSON は RS-JSON に統一**する(読み込みは `from_str_secure` / `parse_secure` でサイズ・深さ・重複キーの上限つき、書き出しは `rust_json::fast`)。ブラウザの WASM に `prost` は入れない(サイズが増えるため)。
- **例外(自分たちの API ではなく、相手の規格が決めているもの)**: ACME、OAuth/OIDC のコールバック、第三者(GitHub など)からの Webhook、ヘルスチェック、静的ファイル配信、OTLP など。これらは規格どおりの HTTP を受ける。
- 参考実装: `RPoem`(`open_runo.admin.v1.Admin`)、`open-easy-web`(`server/src/connect.rs`、`proto/open_easy_web/admin/v1/admin.proto`)。
- ※ このリポジトリのコードが既に方針どおりかどうかは、各リポジトリの現状による。この節は方針の記録であり、コードの変更を意味しない。

### English
- **REST is being abolished. New APIs are not built as REST.** APIs called from browsers or `curl` use **Connect unary calls** (`POST /<package>.<Service>/<Method>`, `content-type: application/json`, JSON body); service-to-service calls use **gRPC / gRPC-web** (the same style as RPoem's admin API `open_runo.admin.v1.Admin`). Streaming only when it is actually needed.
- **Existing REST endpoints are migrated one by one, when they are touched.** The old REST route is removed once migrated. Until migration is finished they remain, but **no new ones are added**.
- **JSON is unified on RS-JSON**: reading with `from_str_secure` / `parse_secure` (size, depth and duplicate-key limits), writing with `rust_json::fast`. `prost` is not put into browser WASM (it would grow the binary).
- **Exceptions (shapes dictated by someone else's standard, not our own API)**: ACME, OAuth/OIDC callbacks, webhooks from third parties (e.g. GitHub), health checks, static file serving, OTLP, and so on. These accept plain HTTP as the standard requires.
- Reference implementations: `RPoem` (`open_runo.admin.v1.Admin`) and `open-easy-web` (`server/src/connect.rs`, `proto/open_easy_web/admin/v1/admin.proto`).
- Note: whether the code in a given repository already follows this policy depends on that repository. This section records the policy; it does not mean the code has been changed.

### Deutsch (KI-Übersetzung, noch nicht von Muttersprachlern geprüft)
- **REST wird abgeschafft. Neue APIs werden nicht als REST gebaut.** APIs, die aus dem Browser oder mit `curl` aufgerufen werden, nutzen **Connect-Unary-Aufrufe** (`POST /<Paket>.<Service>/<Methode>`, `content-type: application/json`, JSON-Body); zwischen Diensten gilt **gRPC / gRPC-web** (wie bei der Admin-API von RPoem, `open_runo.admin.v1.Admin`). Streaming erst, wenn es wirklich nötig ist.
- **Bestehende REST-Endpunkte werden einzeln migriert, sobald man sie anfasst.** Nach der Migration wird die alte REST-Route entfernt. Bis dahin bleiben sie bestehen, es werden aber **keine neuen hinzugefügt**.
- **JSON wird auf RS-JSON vereinheitlicht**: Lesen mit `from_str_secure` / `parse_secure` (Grenzen für Größe, Tiefe und doppelte Schlüssel), Schreiben mit `rust_json::fast`. `prost` kommt nicht in Browser-WASM (die Datei würde größer).
- **Ausnahmen (Formate, die ein fremder Standard vorgibt, nicht unsere eigene API)**: ACME, OAuth/OIDC-Callbacks, Webhooks von Dritten (z. B. GitHub), Health-Checks, statische Dateien, OTLP usw. Diese nehmen schlichtes HTTP entgegen, wie es der Standard verlangt.
- Referenzimplementierungen: `RPoem` (`open_runo.admin.v1.Admin`) und `open-easy-web` (`server/src/connect.rs`, `proto/open_easy_web/admin/v1/admin.proto`).
- Hinweis: Ob der Code eines Repositorys diese Richtlinie schon befolgt, hängt vom jeweiligen Repository ab. Dieser Abschnitt hält die Richtlinie fest; er bedeutet nicht, dass der Code bereits geändert wurde.

### Русский (машинный перевод, носителями языка ещё не проверен)
- **REST полностью отменяется. Новые API не создаются как REST.** API, вызываемые из браузера или через `curl`, используют **унарные вызовы Connect** (`POST /<пакет>.<Service>/<Method>`, `content-type: application/json`, тело — JSON); между сервисами — **gRPC / gRPC-web** (так же, как административный API RPoem, `open_runo.admin.v1.Admin`). Потоковая передача — только когда она действительно нужна.
- **Существующие REST-эндпоинты переносятся по одному, когда до них доходят руки.** После переноса старый REST-маршрут удаляется. До завершения переноса они остаются, но **новые не добавляются**.
- **JSON унифицируется на RS-JSON**: чтение через `from_str_secure` / `parse_secure` (ограничения на размер, глубину и повторяющиеся ключи), запись через `rust_json::fast`. `prost` не добавляется в браузерный WASM (размер вырос бы).
- **Исключения (форматы, заданные чужим стандартом, а не наш собственный API)**: ACME, обратные вызовы OAuth/OIDC, вебхуки сторонних сервисов (например, GitHub), проверки работоспособности, раздача статических файлов, OTLP и т. п. Они принимают обычный HTTP, как требует стандарт.
- Эталонные реализации: `RPoem` (`open_runo.admin.v1.Admin`) и `open-easy-web` (`server/src/connect.rs`, `proto/open_easy_web/admin/v1/admin.proto`).
- Примечание: соответствует ли код конкретного репозитория этой политике, зависит от самого репозитория. Этот раздел фиксирует политику и не означает, что код уже изменён.
