#define AppName "Save Shift"
#define AppVersion "0.1.0-alpha.2"
#define AppPublisher "Jacob Bourcy"
#define AppExeName "SaveShift.exe"
#define AppIcon "..\assets\icons\SaveShift.ico"

[Setup]
AppId={{8D439843-CB79-4B35-A4DB-4C03FBC28D8A}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
SetupIconFile={#AppIcon}

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

VersionInfoVersion=0.1.0.2
VersionInfoCompany={#AppPublisher}
VersionInfoDescription=Save Shift Installer
VersionInfoProductName={#AppName}
VersionInfoProductVersion=0.1.0.2

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
Name: "{group}\Save Shift"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#AppExeName}"
Name: "{autodesktop}\Save Shift"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Classes\.sspkg"; ValueType: string; ValueName: ""; ValueData: "SaveShift.Package"; Flags: uninsdeletevalue

Root: HKCU; Subkey: "Software\Classes\SaveShift.Package"; ValueType: string; ValueName: ""; ValueData: "Save Shift Package"; Flags: uninsdeletekey

Root: HKCU; Subkey: "Software\Classes\SaveShift.Package\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"",0"

Root: HKCU; Subkey: "Software\Classes\SaveShift.Package\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch Save Shift"; Flags: nowait postinstall skipifsilent