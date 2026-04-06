; =====================================================
; 碁華 (Goka GO) インストーラー
; Inno Setup 6.x 用スクリプト
; =====================================================

#define AppName      "碁華 Goka GO"
#define AppVersion   "1.2.8"
#define AppPublisher "CochanHachan"
#define AppURL       "https://goka-go.com"
#define AppExeName   "goka_go.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\GokaGo
DefaultGroupName={#AppName}
AllowNoIcons=yes
; OutputDir はbuild.batから上書きするため省略可
OutputDir=..\dist\installer
OutputBaseFilename=GokaGo_Setup_{#AppVersion}
; SetupIconFile=..\goka.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "english";  MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; \
  Description: "{cm:CreateDesktopIcon}"; \
  GroupDescription: "{cm:AdditionalIcons}"; \
  Flags: unchecked

[Dirs]
; インストールフォルダに書き込み権限を付与（自動アップデートで管理者権限不要にする）
Name: "{app}"; Permissions: users-modify

[Files]
; ---- アプリ本体 (PyInstaller の出力フォルダをまるごと) ----
Source: "..\dist\goka_go\*"; \
  DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

; ---- デフォルト設定ファイル (初回起動時に %APPDATA%\GokaGo にコピーされる) ----
Source: "..\igo_config.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\stone_click.wav"; DestDir: "{app}"; Flags: ignoreversion

; ---- KataGo 本体 ----
Source: "..\katago\katago.exe";                    DestDir: "{app}\katago"; Flags: ignoreversion
Source: "..\katago\libcrypto-3-x64.dll";           DestDir: "{app}\katago"; Flags: ignoreversion
Source: "..\katago\libssl-3-x64.dll";              DestDir: "{app}\katago"; Flags: ignoreversion
Source: "..\katago\libz.dll";                      DestDir: "{app}\katago"; Flags: ignoreversion
Source: "..\katago\libzip.dll";                    DestDir: "{app}\katago"; Flags: ignoreversion
Source: "..\katago\msvcp140.dll";                  DestDir: "{app}\katago"; Flags: ignoreversion
Source: "..\katago\msvcp140_1.dll";                DestDir: "{app}\katago"; Flags: ignoreversion
Source: "..\katago\msvcp140_2.dll";                DestDir: "{app}\katago"; Flags: ignoreversion
Source: "..\katago\msvcp140_atomic_wait.dll";      DestDir: "{app}\katago"; Flags: ignoreversion
Source: "..\katago\msvcp140_codecvt_ids.dll";      DestDir: "{app}\katago"; Flags: ignoreversion
Source: "..\katago\vcruntime140.dll";              DestDir: "{app}\katago"; Flags: ignoreversion
Source: "..\katago\vcruntime140_1.dll";            DestDir: "{app}\katago"; Flags: ignoreversion
Source: "..\katago\cacert.pem";                    DestDir: "{app}\katago"; Flags: ignoreversion
Source: "..\katago\default_gtp.cfg";               DestDir: "{app}\katago"; Flags: ignoreversion

; ---- KataGo モデル ----
Source: "..\katago\model.bin"; \
  DestDir: "{app}\katago"; \
  Flags: ignoreversion

; ---- KataGo チューニングデータ ----
Source: "..\katago\KataGoData\*"; \
  DestDir: "{app}\katago\KataGoData"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}";                       Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";                 Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; \
  Description: "{cm:LaunchProgram,{#AppName}}"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
; アプリが生成する設定ファイルも削除
Type: filesandordirs; Name: "{app}"
