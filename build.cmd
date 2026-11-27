@echo off
setlocal DisableDelayedExpansion
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0scripts\build_windows.ps1" -LocalBuild %*
exit /b %errorlevel%
