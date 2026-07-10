#define AppName "Save Shift"
#define AppVersion "0.1.0-alpha"
#define AppPublisher "Jacob Bourcy"
#define AppExeName "SaveShift.exe"

[Setup]
AppId={{8D439843-CB79-4B35-A4DB-4C03FBC28D8A}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}

DefaultDirName={localappdata}\Programs\Save Shift
DefaultGroupName=Save Shift

PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=SaveShiftSetup-{#AppVersion}

Compression=lzma2
SolidCompression=yes
WizardStyle=modern

UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}

VersionInfoVersion=0.1.0.0
VersionInfoCompany={#AppPublisher}
VersionInfoDescription=Save Shift Installer
VersionInfoProductName={#AppName}
VersionInfoProductVersion=0.1.0.0

SetupLogging=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\SaveShift\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Save Shift"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\Save Shift"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch Save Shift"; Flags: nowait postinstall skipifsilent