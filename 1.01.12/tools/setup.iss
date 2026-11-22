#ifndef AppVersionText
#error Pass /DAppVersionText=major.xx.xx
#endif
#ifndef PayloadRoot
#define PayloadRoot "..\dist\NKC_Galgame_Translator"
#endif
[Setup]
#ifdef SetupFixture
AppId=Sabour1NX.NKCGalgameTranslator.SetupTest
#else
AppId=Sabour1NX.NKCGalgameTranslator
#endif
AppName=NKC_Galgame_Translator
AppVersion={#AppVersionText}
AppPublisher=Sabour1NX
AppPublisherURL=https://github.com/Sabour1NX/NKC_Galgame_Translator
DefaultDirName={localappdata}\Programs\NKC_Galgame_Translator\{#AppVersionText}
DefaultGroupName=NKC_Galgame_Translator
DisableDirPage=no
DirExistsWarning=no
DisableWelcomePage=no
DisableFinishedPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
WizardImageFile=..\assets\wizard-art.bmp
WizardSmallImageFile=..\assets\wizard-icon.bmp
SetupIconFile=..\assets\taiji.ico
UninstallDisplayIcon={app}\NKC_Galgame_Translator.exe
#ifdef SetupFixture
OutputDir=..\build\setup-fixture
#else
OutputDir=..\dist
#endif
OutputBaseFilename=NKC_Galgame_Translator-{#AppVersionText}-setup
Compression=lzma2/fast
SolidCompression=no
ShowLanguageDialog=yes

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "zh"; MessagesFile: "ChineseSimplified.isl"
Name: "ja"; MessagesFile: "compiler:Languages\Japanese.isl"

[Files]
Source: "{#PayloadRoot}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
#ifdef SetupFixture
Name: "{app}\shortcuts\{cm:ShortcutName}"; Filename: "{app}\NKC_Galgame_Translator.exe"; WorkingDir: "{app}"
#else
Name: "{userdesktop}\{cm:ShortcutName}"; Filename: "{app}\NKC_Galgame_Translator.exe"; WorkingDir: "{app}"
Name: "{userprograms}\{cm:ShortcutName}"; Filename: "{app}\NKC_Galgame_Translator.exe"; WorkingDir: "{app}"

#endif

#include "setup_messages.isl"

[Code]
const
#ifdef SetupFixture
  ProtocolKey = 'Software\Classes\nkc-translater-setup-test';
  BackupKey = 'Software\Sabour1NX\NKCSetupTest';
#else
  ProtocolKey = 'Software\Classes\nkc-translater';
  BackupKey = 'Software\Sabour1NX\NKC_Galgame_Translator\Setup';
#endif

function AppCommand: String;
begin
  Result := '"' + ExpandConstant('{app}\NKC_Galgame_Translator.exe') + '"';
end;

function HasFiles(Folder: String): Boolean;
var Entry: TFindRec;
begin
  Result := False;
  if FindFirst(AddBackslash(Folder) + '*', Entry) then try
    repeat
      if (Entry.Name <> '.') and (Entry.Name <> '..') then begin
        Result := True;
        exit;
      end;
    until not FindNext(Entry);
  finally
    FindClose(Entry);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var Folder: String;
begin
  Folder := WizardDirValue;
  if (CompareText(AddBackslash(Folder), AddBackslash(ExtractFileDrive(Folder))) = 0) or
     (DirExists(Folder) and HasFiles(Folder) and
      not (FileExists(Folder + '\NKC_Galgame_Translator.exe') and FileExists(Folder + '\SHA256SUMS.txt'))) then
    Result := CustomMessage('ChooseEmptyFolder');
end;

procedure RemoveOwnedLink(Path: String);
var Shell, Link: Variant;
begin
  if FileExists(Path) then begin
    Shell := CreateOleObject('WScript.Shell');
    Link := Shell.CreateShortcut(Path);
    if CompareText(Link.TargetPath, ExpandConstant('{app}\NKC_Galgame_Translator.exe')) = 0 then
      DeleteFile(Path);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var Previous, Config, Alternate: String;
begin
  if CurStep <> ssPostInstall then exit;
  Config := ExpandConstant('{app}\config\local.json');
  if not FileExists(Config) then
    if not SaveStringToFile(Config, '{"app_language":"' + CustomMessage('LocaleCode') +
                            '","app_language_selected":true}', False) then
      RaiseException(SysErrorMessage(DLLGetLastError));
  if ActiveLanguage = 'zh' then Alternate := 'NKC_Galgame_Translator'
  else Alternate := #$4E8C#$8272#$8776 + 'Galgame' + #$7FFB#$8BD1;
#ifndef SetupFixture
  RemoveOwnedLink(ExpandConstant('{userdesktop}\') + Alternate + '.lnk');
  RemoveOwnedLink(ExpandConstant('{userprograms}\') + Alternate + '.lnk');
#endif
  if RegQueryStringValue(HKCU, ProtocolKey + '\shell\open\command', '', Previous) and
     (CompareText(Previous, AppCommand) <> 0) then
    RegWriteStringValue(HKCU, BackupKey, 'PreviousCommand', Previous);
  RegWriteStringValue(HKCU, ProtocolKey, '', 'URL:NKC_Translater');
  RegWriteStringValue(HKCU, ProtocolKey, 'URL Protocol', '');
  RegWriteStringValue(HKCU, ProtocolKey + '\shell\open\command', '', AppCommand);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var Current, Previous: String;
begin
  if CurUninstallStep <> usPostUninstall then exit;
  if RegQueryStringValue(HKCU, ProtocolKey + '\shell\open\command', '', Current) and
     (CompareText(Current, AppCommand) = 0) then begin
    if RegQueryStringValue(HKCU, BackupKey, 'PreviousCommand', Previous) then
      RegWriteStringValue(HKCU, ProtocolKey + '\shell\open\command', '', Previous)
    else
      RegDeleteKeyIncludingSubkeys(HKCU, ProtocolKey);
  end;
  RegDeleteValue(HKCU, BackupKey, 'PreviousCommand');
  RegDeleteKeyIfEmpty(HKCU, BackupKey);
end;

procedure StartInstalled(Sender: TObject);
var Params: String;
    Code: Integer;
begin
  Params := '';
  if TNewButton(Sender).Tag = 1 then Params := '--welcome ' + CustomMessage('LocaleCode');
  if Exec(ExpandConstant('{app}\NKC_Galgame_Translator.exe'), Params,
          ExpandConstant('{app}'), SW_SHOWNORMAL, ewNoWait, Code) then
    WizardForm.NextButton.OnClick(WizardForm.NextButton)
  else MsgBox(SysErrorMessage(Code), mbError, MB_OK);
end;

procedure FinishButton(Caption: String; Row: Integer);
var Button: TNewButton;
begin
  Button := TNewButton.Create(WizardForm);
  Button.Parent := WizardForm.FinishedPage;
  Button.Left := WizardForm.FinishedLabel.Left;
  Button.Top := WizardForm.FinishedLabel.Top + ScaleY(54 + Row * 36);
  Button.Width := WizardForm.FinishedLabel.Width;
  Button.Height := ScaleY(29);
  Button.Caption := Caption;
  Button.Tag := Row;
  Button.OnClick := @StartInstalled;
end;

procedure InitializeWizard;
begin
  FinishButton(CustomMessage('OpenApp'), 0);
  FinishButton(CustomMessage('OpenTour'), 1);
end;

procedure CurPageChanged(Page: Integer);
begin
  if Page = wpFinished then WizardForm.FinishedLabel.Caption := CustomMessage('SuccessText');
end;

procedure CurInstallProgressChanged(CurProgress, MaxProgress: Integer);
var Percent: Integer;
begin
  if MaxProgress > 0 then begin
    Percent := Round((CurProgress * 100.0) / MaxProgress);
    WizardForm.StatusLabel.Caption := CustomMessage('ProgressText') + '  ' + IntToStr(Percent) + '%';
  end;
end;
