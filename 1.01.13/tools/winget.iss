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
Name: "{userprograms}\{code:ShortcutLabel}"; Filename: "{app}\NKC_Galgame_Translator.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\{code:ShortcutLabel}"; Filename: "{app}\NKC_Galgame_Translator.exe"; WorkingDir: "{app}"

[Code]
var
  LanguagePage: TInputOptionWizardPage;

function ChineseLabel: String;
begin
  Result := #$4E8C#$8272#$8776 + 'Galgame' + #$7FFB#$8BD1;
end;

procedure InitializeWizard;
var
  Locale: String;
begin
  LanguagePage := CreateInputOptionPage(wpWelcome, 'Shortcut language',
    'Choose the language for your desktop and Start menu shortcuts.', '', True, False);
  LanguagePage.Add('English');
  LanguagePage.Add(#$4E2D#$6587);
  LanguagePage.Add(#$65E5#$672C#$8A9E);
  Locale := Lowercase(ExpandConstant('{param:NKCLang|}'));
  if (Pos('zh', Locale) = 1) or ((Locale = '') and ((GetUILanguage and $3FF) = 4)) then
    LanguagePage.SelectedValueIndex := 1
  else if (Pos('ja', Locale) = 1) or ((Locale = '') and ((GetUILanguage and $3FF) = 17)) then
    LanguagePage.SelectedValueIndex := 2
  else
    LanguagePage.SelectedValueIndex := 0;
end;

function ShortcutLabel(Param: String): String;
begin
  if LanguagePage.SelectedValueIndex = 1 then Result := ChineseLabel
  else Result := 'NKC_Galgame_Translator';
end;

procedure RemoveOwnedShortcut(Path: String);
var
  Shell, Link: Variant;
begin
  if FileExists(Path) then begin
    Shell := CreateOleObject('WScript.Shell');
    Link := Shell.CreateShortcut(Path);
    if CompareText(Link.TargetPath, ExpandConstant('{app}\NKC_Galgame_Translator.exe')) = 0 then
      DeleteFile(Path);
  end;
end;

procedure CurStepChanged(Step: TSetupStep);
var
  OldName: String;
begin
  if Step = ssPostInstall then begin
    if LanguagePage.SelectedValueIndex = 1 then OldName := 'NKC_Galgame_Translator'
    else OldName := ChineseLabel;
    RemoveOwnedShortcut(ExpandConstant('{userdesktop}\') + OldName + '.lnk');
    RemoveOwnedShortcut(ExpandConstant('{userprograms}\') + OldName + '.lnk');
    RemoveOwnedShortcut(ExpandConstant('{group}\NKC_Galgame_Translator.lnk'));
  end;
end;
