; Per-user installer for a verified UFM Studio folder candidate.
; The installer never bundles or removes the separate user data directory.
#define AppName "UFM Studio"
#define AppVersion GetEnv("UFM_APP_VERSION")
#define BundleDir GetEnv("UFM_BUNDLE_DIR")
#define InstallerOutput GetEnv("UFM_INSTALLER_OUTPUT")

#if AppVersion == ""
  #error Set UFM_APP_VERSION before compiling this installer.
#endif
#if BundleDir == ""
  #error Set UFM_BUNDLE_DIR before compiling this installer.
#endif
#if InstallerOutput == ""
  #error Set UFM_INSTALLER_OUTPUT before compiling this installer.
#endif

[Setup]
AppId={{B99318F9-88B1-49BE-948E-7A3EC8369147}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\UFM Studio
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
UsePreviousAppDir=no
WizardStyle=modern
SetupIconFile={#BundleDir}\ufm.ico
UninstallDisplayIcon={app}\UFM Studio.exe
Uninstallable=yes
OutputDir={#InstallerOutput}
OutputBaseFilename=UFM-Studio-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes

[Tasks]
Name: "desktopicon"; Description: "Створити ярлик на робочому столі"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\UFM Studio"; Filename: "{app}\UFM Studio.exe"; WorkingDir: "{app}"; IconFilename: "{app}\ufm.ico"
Name: "{autodesktop}\UFM Studio"; Filename: "{app}\UFM Studio.exe"; WorkingDir: "{app}"; IconFilename: "{app}\ufm.ico"; Tasks: desktopicon

; No [UninstallDelete]: AppPaths stores personal data outside {app}.
