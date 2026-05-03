; =====================================================
; 碁華 Goka GO — テスト用クライアント（beta ビルド向け）
; 本番 GokaGo_Setup.iss とは別 AppId・別インストール先。
; アイコン: テスト版専用 goka_go_test.ico（インストーラ・ショートカット用）。
; goka_go_test.ico が無い場合は goka_go.ico をフォールバックで使用。
; =====================================================

#define AppName      "碁華 Goka GO（テスト）"
#define AppVersion   "2.0.0"
#define AppPublisher "CochanHachan"
#define AppURL       "https://goka-igo.com"
#define AppExeName   "goka_go.exe"

[Setup]
AppId={{B2C3D4E5-F6A7-8901-BCDE-F12345678901}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\GokaGoTest
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputDir=..\dist\installer
OutputBaseFilename=GokaGoTest_Setup_{#AppVersion}
SetupIconFile=..\goka_go_test.ico
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
Name: "{app}"; Permissions: users-modify
Name: "{app}\katago"; Permissions: users-modify

[Files]
Source: "..\dist\goka_go\*"; \
  DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\igo_config.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\stone_click.wav"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\goka_go_test.ico"; DestDir: "{app}"; Flags: ignoreversion
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
Source: "..\katago\analysis_example.cfg";          DestDir: "{app}\katago"; Flags: ignoreversion
Source: "..\katago\model.bin"; \
  DestDir: "{app}\katago"; \
  Flags: ignoreversion
Source: "..\katago\human_model.bin"; \
  DestDir: "{app}\katago"; \
  Flags: ignoreversion
Source: "..\katago\KataGoData\*"; \
  DestDir: "{app}\katago\KataGoData"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}";                       Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\goka_go_test.ico"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";                 Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\goka_go_test.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; \
  Description: "{cm:LaunchProgram,{#AppName}}"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
