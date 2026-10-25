#ifndef AppVersion
  #error AppVersion must be supplied by the build script
#endif
#ifndef ProjectRoot
  #define ProjectRoot ".."
#endif

[Setup]
AppId={{48EFC847-1129-4E95-A52E-71BD9C2D0065}
AppName=TreeSize Explorer
AppVersion={#AppVersion}
AppPublisher=CodeHive
AppPublisherURL=https://github.com/mycodehive/TreeSize
AppSupportURL=https://github.com/mycodehive/TreeSize/issues
AppUpdatesURL=https://github.com/mycodehive/TreeSize/releases
DefaultDirName={localappdata}\Programs\TreeSizeExplorer
DefaultGroupName=TreeSize Explorer
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#ProjectRoot}\dist\release
OutputBaseFilename=TreeSizeExplorer-Setup-{#AppVersion}
SetupIconFile={#ProjectRoot}\build\app.ico
UninstallDisplayIcon={app}\TreeSizeExplorer.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
AppMutex=TreeSizeExplorerMutex
SetupMutex=TreeSizeExplorerSetupMutex
VersionInfoVersion={#AppVersion}.0
VersionInfoDescription=TreeSize Explorer Setup
VersionInfoCompany=CodeHive

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#ProjectRoot}\dist\TreeSizeExplorer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\TreeSize Explorer"; Filename: "{app}\TreeSizeExplorer.exe"
Name: "{autodesktop}\TreeSize Explorer"; Filename: "{app}\TreeSizeExplorer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\TreeSizeExplorer.exe"; Description: "{cm:LaunchProgram,TreeSize Explorer}"; Flags: nowait postinstall skipifsilent
