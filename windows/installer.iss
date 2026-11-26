; Inno Setup-script voor mini-Maple (gebouwd in GitHub Actions, zie .github/workflows/release.yml).
; Installeert per gebruiker (geen admin), maakt snelkoppelingen, koppelt .mw/.mpl en minimaple:// en
; heeft een uninstaller die alles weer weghaalt. Bron: windows/build/mini-Maple (gemaakt door build.sh).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6C1F7A52-3E0B-4C1B-9D7E-6D3A9B1E2F40}
AppName=mini-Maple
AppVersion={#AppVersion}
AppPublisher=Henri Goudezeune
AppPublisherURL=https://maple.hydrargyrum.be
AppSupportURL=https://github.com/HenriGoudezeune/minimaple
DefaultDirName={localappdata}\Programs\mini-Maple
DefaultGroupName=mini-Maple
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=mini-Maple-setup
SetupIconFile=assets\mini-Maple.ico
UninstallDisplayIcon={app}\app\mini-Maple.ico
UninstallDisplayName=mini-Maple
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "nl"; MessagesFile: "compiler:Languages\Dutch.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Snelkoppeling op het bureaublad"; GroupDescription: "Extra:"
Name: "assoc"; Description: ".mw- en .mpl-bestanden openen met mini-Maple"; GroupDescription: "Bestanden:"

[Files]
Source: "build\mini-Maple\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\mini-Maple"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\mini-Maple.vbs"""; IconFilename: "{app}\app\mini-Maple.ico"; WorkingDir: "{app}"
Name: "{group}\mini-Maple verwijderen"; Filename: "{uninstallexe}"
Name: "{userdesktop}\mini-Maple"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\mini-Maple.vbs"""; IconFilename: "{app}\app\mini-Maple.ico"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
; ProgID
Root: HKCU; Subkey: "Software\Classes\miniMaple.Werkblad"; ValueType: string; ValueName: ""; ValueData: "mini-Maple-werkblad"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\miniMaple.Werkblad\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\app\mini-Maple.ico,0"
Root: HKCU; Subkey: "Software\Classes\miniMaple.Werkblad\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{sys}\wscript.exe"" ""{app}\mini-Maple.vbs"" ""%1"""
; Openen met... (altijd), standaard alleen als de taak gekozen is
Root: HKCU; Subkey: "Software\Classes\.mw\OpenWithProgids"; ValueType: string; ValueName: "miniMaple.Werkblad"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\.mpl\OpenWithProgids"; ValueType: string; ValueName: "miniMaple.Werkblad"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\.mw"; ValueType: string; ValueName: ""; ValueData: "miniMaple.Werkblad"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\.mpl"; ValueType: string; ValueName: ""; ValueData: "miniMaple.Werkblad"; Flags: uninsdeletevalue; Tasks: assoc
; Instellingen > Standaard-apps
Root: HKCU; Subkey: "Software\miniMaple"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\miniMaple\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "mini-Maple"
Root: HKCU; Subkey: "Software\miniMaple\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Rekenomgeving met Maple-syntax"
Root: HKCU; Subkey: "Software\miniMaple\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mw"; ValueData: "miniMaple.Werkblad"
Root: HKCU; Subkey: "Software\miniMaple\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mpl"; ValueData: "miniMaple.Werkblad"
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "mini-Maple"; ValueData: "Software\miniMaple\Capabilities"; Flags: uninsdeletevalue
; minimaple:// (werkblad meenemen vanuit de webversie)
Root: HKCU; Subkey: "Software\Classes\minimaple"; ValueType: string; ValueName: ""; ValueData: "URL:mini-Maple"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\minimaple"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\minimaple\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{sys}\wscript.exe"" ""{app}\mini-Maple.vbs"" ""%1"""

[Run]
Filename: "{sys}\wscript.exe"; Parameters: """{app}\mini-Maple.vbs"""; Description: "mini-Maple nu starten"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\runtime\__pycache__"
Type: filesandordirs; Name: "{app}\app\__pycache__"
