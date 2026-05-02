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

### 設定について

- GUI で **プロファイル**（FTP 接続情報・監視フォルダ・同期オプション）を作成し、「プロファイルに保存」します。
- `config.example.json` は **サンプル** です。実行時のデータは `%LOCALAPPDATA%\FTPAutoSync\` 配下に保存されます。

### セキュリティ

**パスワードや API キーをリポジトリに含めないでください。** 秘密情報はご利用の PC 上のプロファイル用データベースにのみ保存されます。

### ライセンス

[MIT](LICENSE)

### コントリビューション

Issue・Pull Request を歓迎します。
