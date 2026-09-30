@echo off
setlocal

reg delete "HKCU\Software\Classes\SystemFileAssociations\.xml\shell\eDefterDenetimMerkezi" /f >nul 2>nul

echo XML sag tik menusu kaldirildi.
pause
