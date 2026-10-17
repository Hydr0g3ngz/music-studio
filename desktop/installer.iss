#ifndef BuildVersion
  #define BuildVersion "0.1.4"
#endif
[Setup]
AppId=MusicStudio.Local.SongAnalysis
AppName=Music Studio
AppVersion={#BuildVersion}
AppVerName=Music Studio {#BuildVersion}
AppPublisher=Music Studio Contributors
AppPublisherURL=https://github.com/Hydr0g3ngz/music-studio
DefaultDirName={localappdata}\Programs\Music Studio
DefaultGroupName=Music Studio
DisableProgramGroupPage=yes
DisableDirPage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19045
WizardStyle=modern
LicenseFile={#Repo}\LICENSE
InfoBeforeFile={#Repo}\desktop\installation-info.txt
OutputDir={#Destination}
OutputBaseFilename=Music-Studio-{#BuildVersion}-Setup-x64
Compression=lzma2/normal
LZMADictionarySize=131072
LZMAUseSeparateProcess=yes
SolidCompression=yes
LZMANumBlockThreads=2
SetupLogging=yes
UninstallDisplayIcon={app}\Music Studio.exe
AppMutex=MusicStudio.Desktop.Running
CloseApplications=no
RestartApplications=no
Uninstallable=yes
UsePreviousAppDir=yes
VersionInfoVersion={#BuildVersion}.0
VersionInfoProductName=Music Studio

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "{#ChineseLanguage}"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: checkedonce

[Files]
Source: "{#Payload}\*"; DestDir: "{app}"; Excludes: "__pycache__\*,*.pyc,*.log"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#WebViewInstaller}"; DestName: "WebView2Setup.exe"; Flags: dontcopy
Source: "{#VcInstaller}"; DestName: "VcRuntimeSetup.exe"; Flags: dontcopy

[Icons]
Name: "{group}\Music Studio"; Filename: "{app}\Music Studio.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Music Studio"; Filename: "{app}\Music Studio.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[InstallDelete]
; Remove obsolete package metadata when upgrading the CPU installer to CUDA.
Type: filesandordirs; Name: "{app}\runtime\Lib\site-packages\torch-*.dist-info"
Type: filesandordirs; Name: "{app}\runtime\Lib\site-packages\torchaudio-*.dist-info"
Type: filesandordirs; Name: "{app}\runtime\Lib\site-packages\music_studio_local-*.dist-info"

[Run]
Filename: "{app}\Music Studio.exe"; Description: "{cm:LaunchProgram,Music Studio}"; Flags: nowait postinstall skipifsilent

[Code]
function VcPresent: Boolean;
var Installed, Major, Minor: Cardinal;
begin
  Result := RegQueryDWordValue(HKLM64, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Installed', Installed) and (Installed = 1) and
    RegQueryDWordValue(HKLM64, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Major', Major) and
    RegQueryDWordValue(HKLM64, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Minor', Minor) and
    ((Major > 14) or ((Major = 14) and (Minor >= 44)));
end;

function WebViewPresent: Boolean;
var Version: String;
begin
  Result := (RegQueryStringValue(HKLM32, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
  if not Result then
    Result := (RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var ExitCode: Integer;
begin
  Result := '';
  if FileExists(AddBackslash(ExpandConstant('{app}')) + '.music-studio-server.lock') or
     FileExists(AddBackslash(ExpandConstant('{app}')) + '.studio.sqlite3') then begin
    Result := 'Choose a program folder separate from song/project data. / 请选择独立于歌曲和作品数据的程序目录。';
    exit;
  end;
  if not VcPresent then begin
    WizardForm.StatusLabel.Caption := 'Installing inference runtime / 正在安装推理运行库…';
    ExtractTemporaryFile('VcRuntimeSetup.exe');
    if not Exec(ExpandConstant('{tmp}\VcRuntimeSetup.exe'), '/install /quiet /norestart', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
      Result := 'Could not start Microsoft VC++ setup. / 无法启动微软 VC++ 安装程序。'
    else if not VcPresent then
      Result := 'Microsoft VC++ setup did not complete. Please retry. / 微软 VC++ 运行库安装未完成，请重试。';
    if ExitCode = 3010 then NeedsRestart := True;
    if Result <> '' then exit;
  end;
  if not WebViewPresent then begin
    WizardForm.StatusLabel.Caption := 'Installing desktop display component / 正在安装桌面显示组件…';
    ExtractTemporaryFile('WebView2Setup.exe');
    if not Exec(ExpandConstant('{tmp}\WebView2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
      Result := 'Could not start the display component installer. / 无法启动显示组件安装。'
    else if not WebViewPresent then
      Result := 'Display setup did not complete. Retry installation. / 显示组件安装未完成，请重试。';
  end;
end;
