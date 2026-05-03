; Inno Setup 6 — https://jrsoftware.org/isinfo.php
; 事前に .\build.ps1 で dist\Ftp-Auto-Sync.exe を生成してください。

#define MyAppNameEn "Ftp-Auto-Sync"
#define MyAppNameJp "Ftp-Auto-Sync"
#define MyAppVersion "4.1.0"
#define MyAppPublisher "ftp-auto-sync contributors"
#define MyAppExeName "Ftp-Auto-Sync.exe"
#define MyAppURL "https://github.com/aon-co-jp/ftp-auto-sync"

[Setup]
AppId={{8F4E2B1C-9D0A-4E5F-8B7C-6A5D4E3F2A1B}
AppName={#MyAppNameJp}
AppVersion={#MyAppVersion}
AppVerName={#MyAppNameJp} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={commonpf}\FTPAutoSync
DefaultGroupName={#MyAppNameJp}
AllowNoIcons=yes
LicenseFile=..\LICENSE
OutputDir=..\release
OutputBaseFilename=Ftp-Auto-Sync_Setup_{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
DisableProgramGroupPage=no
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config.example.json"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppNameJp}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppNameJp}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppNameJp}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "アプリケーションを起動"; Flags: nowait postinstall skipifsilent
