# Cursor ルールの globs とワークスペース（ドライブは任意）

ドライブ文字（`E:` `G:` など）は固定ではありません。**パス全体が見えればよい**だけです。

## 同梱されている2種類のルール

| ファイル | globs | 使うとき |
|----------|-------|----------|
| `.cursor/rules/ftp-app-agent.mdc` | `ftp-auto-sync/**/*` | ワークスペースに **親フォルダ**（例: ドライブ直下・`repos`）を開き、その下に **`ftp-auto-sync` フォルダ**があるとき |
| `.cursor/rules/ftp-app-agent-workspace-root.mdc` | `**/*` | ワークスペースのルートが **`ftp-auto-sync` フォルダそのもの**のとき |

## 差分（設定のコピペ用）

**親フォルダを開いている場合（推奨 globs）** — `ftp-app-agent.mdc` の先頭:

```yaml
globs: ftp-auto-sync/**/*
```

**リポジトリだけをルートで開いている場合** — `ftp-app-agent-workspace-root.mdc` を有効にするか、手元の `.mdc` で:

```yaml
globs: "**/*"
```

## モノレポの例

```
D:\work\monorepo\
  ftp-auto-sync\     ← このリポジトリ
  other-project\
```

ワークスペースを `D:\work\monorepo` にすると、`ftp-auto-sync/**/*` でマッチする。

## 注意

- globs は **Cursor が解釈するワークスペース相対パス**です。ドライブレターは含めません。
- ルールを編集したあと、必要なら Cursor を再読み込みするか、ルール一覧でオフ→オンし直してください。
