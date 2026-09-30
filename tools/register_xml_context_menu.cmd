@echo off
setlocal

set "EXE_PATH=%~dp0..\dist\e-Defter Denetim Merkezi\e-Defter Denetim Merkezi.exe"
if not exist "%EXE_PATH%" (
  set "EXE_PATH=%ProgramFiles%\e-Defter Denetim Merkezi\e-Defter Denetim Merkezi.exe"
)
if not exist "%EXE_PATH%" (
  echo e-Defter Denetim Merkezi.exe bulunamadi.
  echo Beklenen konum:
  echo %~dp0..\dist\e-Defter Denetim Merkezi\e-Defter Denetim Merkezi.exe
  pause
  exit /b 1
)

reg add "HKCU\Software\Classes\SystemFileAssociations\.xml\shell\eDefterDenetimMerkezi" /ve /d "e-Defter Denetim Merkezi ile Ac" /f >nul
reg add "HKCU\Software\Classes\SystemFileAssociations\.xml\shell\eDefterDenetimMerkezi" /v "Icon" /d "\"%EXE_PATH%\"" /f >nul
reg add "HKCU\Software\Classes\SystemFileAssociations\.xml\shell\eDefterDenetimMerkezi\command" /ve /d "\"%EXE_PATH%\" \"%%1\"" /f >nul

echo XML sag tik menusu eklendi.
echo Menu metni: e-Defter Denetim Merkezi ile Ac
pause
