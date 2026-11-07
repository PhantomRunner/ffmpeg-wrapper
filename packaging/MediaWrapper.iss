; Compile through scripts/build_windows_installer.py after native payload checks.
#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef PayloadDir
  #error PayloadDir is required
#endif
#ifndef OutputBaseName
  #error OutputBaseName is required
#endif
#ifndef AppIcon
  #error AppIcon is required
#endif

[Setup]
AppId={{4F7D770D-E00A-4AA4-BA73-66369E11025A}
AppName=FFmpeg Wrapper
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\MediaWrapper
DefaultGroupName=FFmpeg Wrapper
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
DisableProgramGroupPage=yes
OutputBaseFilename={#OutputBaseName}
SetupIconFile={#AppIcon}
UninstallDisplayIcon={app}\MediaWrapper.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no
AppMutex=Local\MediaWrapper.FlatUI
Uninstallable=yes

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked

[Icons]
Name: "{autoprograms}\FFmpeg Wrapper"; Filename: "{app}\MediaWrapper.exe"
Name: "{autodesktop}\FFmpeg Wrapper"; Filename: "{app}\MediaWrapper.exe"; Tasks: desktopicon

; Do not add UninstallDelete: only installer-owned files may be removed.
; User preferences, history, presets, sources, partials and outputs remain intact.
