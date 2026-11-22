#ifndef AppVersionText
#error Pass /DAppVersionText=major.xx.xx
#endif
[Setup]
AppId=Sabour1NX.NKCGalgameTranslator
AppName=NKC_Galgame_Translator
AppVersion={#AppVersionText}
AppPublisher=Sabour1NX
AppPublisherURL=https://github.com/Sabour1NX/NKC_Galgame_Translator
DefaultDirName={localappdata}\Programs\NKC_Galgame_Translator-WinGet
DefaultGroupName=NKC_Galgame_Translator
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=NKC_Galgame_Translator-{#AppVersionText}-winget-x64
Compression=lzma2/fast
SolidCompression=no
UninstallDisplayIcon={app}\NKC_Galgame_Translator.exe
SetupIconFile=..\assets\taiji.ico
DisableProgramGroupPage=yes

[Files]
Source: "..\dist\NKC_Galgame_Translator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\NKC_Galgame_Translator"; Filename: "{app}\NKC_Galgame_Translator.exe"
