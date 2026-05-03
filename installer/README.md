# Windows インストーラー（Inno Setup）

1. [Inno Setup 6](https://jrsoftware.org/isdl.php) をインストールする（ビルド PC のみでよい）。
2. リポジトリルートで `.\build_installer.ps1` を実行する。  
   - まず `build.ps1` で `dist\FTPAutoSync.exe` を生成し、続けて `FTPAutoSync.iss` をコンパイルする。
3. 成果物は `release\FTPAutoSync_Setup_<version>.exe`。

バージョン文字列は `FTPAutoSync.iss` 先頭の `#define MyAppVersion` を変更する。

EXE のみ必要な場合は `.\build.ps1` だけで `dist\FTPAutoSync.exe` が得られます。
