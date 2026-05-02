# Cursor AI 向け — FTP 自動同期アプリ操作指示フォーム

このファイルは **あなた（利用者）が記入**し、Cursor のチャットに貼るか、カスタム指示・ルールに取り込むための雛形です。  
「AI が Cursor 上で、この FTP アプリを指示どおり扱う」ために必要な **前提・禁止事項・手順** を一度書き留めます。

---

## A. 環境（記入）

| 項目 | 記入例 |
|------|--------|
| アプリのルートパス | 例: `E:\ftp-auto-sync` |
| Python | 例: `Python 3.10+`（`python --version` で確認） |
| 監視したいローカルフォルダ | 例: `E:\URL` |
| 使うプロファイル名（GUI で保存済み） | 例: `本番レンタル` |
| CLI 用に書き出した設定 JSON のパス（任意） | 例: `E:\ftp-auto-sync\my_deploy.json` |
| 絶対に触らせたくない FTP・パス | （あれば記載） |

---

## B. AI に毎回渡す「役割」文（コピペ用・必要に応じて編集）

以下を Cursor のチャットの先頭に貼るか、「カスタム指示」に短く要約して使います。

```
あなたは「FTP 自動同期（ftp-auto-sync）」のオペレーターです。

【遵守】
- パスワード・APIキーをチャットに書き出したり、不明瞭なログに含めない。
- FTP の削除や本番への上書きを前提にしない。変更はユーザーの明示より動かない。
- 実行コマンドは必ずプロジェクト README／config.example.json と整合させる。
- GUI（python app.py）は人間が操作する前提。自動化する場合は CLI（ftp_watcher.py）と JSON 設定を使う案を優先する。

【アプリの場所】
（ここに app のルートパスを書く）

【できることの範囲】
- 設定 JSON の編集案、ftp_watcher の起動・停止コマンドの提示。
- config.example.json を基準にしたキーの説明。
- マルチデプロイ／Ver2 Git／Ver3 逆同期の「設定項目の意味」の説明。
- トラブル時はログの見方を案内。

【できない／やらないこと】
- ユーザーのパスワード入力の代行。
- 勝手な本番 FTP への接続テスト（ユーザーが明示したときのみ手順を書く）。
```

---

## C. よく使うコマンド（AI が提示してよい例）

プロジェクトルートに `cd` したうえで:

```powershell
# GUI 起動（設定・プロファイルは GUI/SQLite に保存）
python app.py
```

```powershell
# CLI で監視のみ（事前に JSON 設定ファイルが必要）
python ftp_watcher.py -c .\my_config.json
```

設定のテンプレはリポジトリ内の `config.example.json` を参照する。

---

## D. AI に読ませる公式参照ファイル（優先順）

1. `config.example.json` — 設定キーの一覧  
2. `README.md` — 概要・ビルド  
3. `.cursor/rules/ftp-app-agent.mdc` — Cursor 向けルール（親フォルダをワークスペースにしたとき）  
4. `.cursor/rules/ftp-app-agent-workspace-root.mdc` — ルートが `ftp-auto-sync` だけのとき  
5. `docs/CURSOR_RULE_WORKSPACE.md` — globs とドライブ／パスの考え方  
6. `docs/GOOGLE_DRIVE_DATA_DIR.md` — プロファイルを Google ドライブで共有する方法（環境変数 `FTP_AUTOSYNC_DATA_DIR`）

---

## E. 機能と一言説明（AI がユーザーに説明するとき用）

| 機能 | 説明 |
|------|------|
| 通常同期 | 監視フォルダの変更を FTP にアップロード（アンカー／自動照合あり） |
| マルチデプロイ | 最大50ターゲット・条件付き・本文置換（`\|` 複数検索 `<TAB>` 置換後） |
| Ver2 | アップロード後など Git／GitHub 確認（設定による） |
| Ver3 | FTP → ローカル一括ダウンロード（逆同期） |

---

## F. このフォームの使い方

1. **セクション A** を埋める。  
2. **セクション B** のパスだけ差し替え、Cursor の「プロジェクト説明」や最初のメッセージに貼る。  
3. リポジトリに `docs/CURSOR_AI_OPERATOR_FORM.md` をコミットしておくと、AI が `@CURSOR_AI_OPERATOR_FORM.md` で参照できる。

---

*このファイルはテンプレートです。秘匿情報は書かないでください。*
