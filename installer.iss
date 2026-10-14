#define MyAppName      "SiteCapture"
#define MyAppVersion   "1.0.0"
#define MyAppPublisher "Martin Pavion"
#define MyAppURL       "https://github.com/martinpavion/sitecapture"
#define MyAppExeName   "SiteCapture.exe"
#define MyAppDir       "dist\SiteCapture"

[Setup]
AppId={{A3F2C8D1-4B7E-4F91-8C3D-2E9A5B6F7D8C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=installer_output
OutputBaseFilename=SiteCapture_Setup_v{#MyAppVersion}
SetupIconFile=icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#MyAppExeName}
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "{#MyAppDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}";                           Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}";                 Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";                     Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
