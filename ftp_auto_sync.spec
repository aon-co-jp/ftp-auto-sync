# -*- mode: python ; coding: utf-8 -*-
# PyInstaller — GUI を単一 EXE にまとめる（コンソールなし）

block_cipher = None

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[("config.example.json", ".")],
    hiddenimports=[
        "watchdog.observers",
        "watchdog.events",
        "dotenv",
        "ftp_util",
        "anchor_sync",
        "paths",
        "ftp_watcher",
        "profile_store",
        "v2_git_assist",
        "v3_ftp_download",
        "multi_deploy",
        "deploy_targets_dialog",
        "ftp_mtime",
        "ui_i18n",
        "bulk_remote_select_dialog",
        "sync_scope",
        "ai_upload_rewrite",
        "cursor_launch",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Ftp-Auto-Sync",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
