#define MyAppName "e-Defter Denetim Merkezi"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "SkynonLabs"
#define MyAppExeName "e-Defter Denetim Merkezi.exe"
#define MyAppFolder "e-Defter Denetim Merkezi"
#define MySourceDir "C:\Users\Admin\Documents\Edefter Denetim Merkezi\dist\e-Defter Denetim Merkezi"
#define MyIconFile "C:\Users\Admin\Documents\Edefter Denetim Merkezi\assets\branding\e_defter_denetim_merkezi_logo_set\edefter-denetim-merkezi.ico"
#define MyWizardImageFile "C:\Users\Admin\Documents\Edefter Denetim Merkezi\assets\branding\e_defter_denetim_merkezi_logo_set\installer\wizard-image.bmp"
#define MyWizardSmallImageFile "C:\Users\Admin\Documents\Edefter Denetim Merkezi\assets\branding\e_defter_denetim_merkezi_logo_set\installer\wizard-small.bmp"

[Setup]
AppId={{E4F6D1B8-4A91-4E9A-88B9-4A4B943A5C55}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppPublisher}\{#MyAppFolder}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile={#MyIconFile}
WizardImageFile={#MyWizardImageFile}
WizardSmallImageFile={#MyWizardSmallImageFile}
OutputDir=C:\Users\Admin\Documents\Edefter Denetim Merkezi\dist\installer
OutputBaseFilename=e-Defter-Denetim-Merkezi-Setup
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "desktopicon"; Description: "Masaustu kisayolu olustur"; Flags: unchecked

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppExeName}"

[Registry]
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.xml\shell\eDefterDenetimMerkezi"; ValueType: string; ValueName: ""; ValueData: "e-Defter Denetim Merkezi ile Ac"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.xml\shell\eDefterDenetimMerkezi"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.xml\shell\eDefterDenetimMerkezi\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Flags: uninsdeletekey

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\SkynonLabs\e-Defter Denetim Merkezi"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "e-Defter Denetim Merkezi baslat"; Flags: nowait postinstall skipifsilent
