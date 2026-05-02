@echo off
REM Google ドライブや任意ドライブ上のフォルダにプロファイルを保存する例。
REM このファイルをコピーして run_with_data_dir.bat にリネームし、下のパスだけ編集してください。

REM 例: 英語の「My Drive」
REM set FTP_AUTOSYNC_DATA_DIR=G:\My Drive\FTPAutoSyncData

REM 例: 日本語の「マイドライブ」
set "FTP_AUTOSYNC_DATA_DIR=G:\マイドライブ\FTPAutoSyncData"

cd /d "%~dp0.."
python app.py
if errorlevel 1 pause
