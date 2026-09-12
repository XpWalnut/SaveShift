#define AppName "Save Shift"
#ifndef AppVersion
  #define AppVersion "0.1.0-alpha.2"
#endif
#ifndef AppVersionInfo
  #define AppVersionInfo "0.1.0.2"
#endif
#define AppPublisher "Jacob Bourcy"
#define AppExeName "SaveShift.exe"
#define AppIcon "..\assets\icons\SaveShift-Vaporwave.ico"

[Setup]
AppId={{8D439843-CB79-4B35-A4DB-4C03FBC28D8A}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
SetupIconFile={#AppIcon}
LicenseFile=..\LICENSE

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

VersionInfoVersion={#AppVersionInfo}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription=Save Shift Installer
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersionInfo}

SetupLogging=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\SaveShift\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#AppIcon}"; DestDir: "{app}"; DestName: "SaveShift-Vaporwave.ico"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\TRADEMARKS.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Save Shift"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\SaveShift-Vaporwave.ico"
Name: "{autodesktop}\Save Shift"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\SaveShift-Vaporwave.ico"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Classes\.sspkg"; ValueType: string; ValueName: ""; ValueData: "SaveShift.Package"; Flags: uninsdeletevalue

Root: HKCU; Subkey: "Software\Classes\SaveShift.Package"; ValueType: string; ValueName: ""; ValueData: "Save Shift Package"; Flags: uninsdeletekey

Root: HKCU; Subkey: "Software\Classes\SaveShift.Package\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\SaveShift-Vaporwave.ico"""

Root: HKCU; Subkey: "Software\Classes\SaveShift.Package\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch Save Shift"; Flags: nowait postinstall skipifsilent
