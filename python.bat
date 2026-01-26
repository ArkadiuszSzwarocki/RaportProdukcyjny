@echo off
REM Wrapper to use project's virtualenv python when running 'python' inside repo
setlocal
set VENV=%~dp0.venv\Scripts\python.exe
if exist "%VENV%" (
  "%VENV%" %*
) else (
  REM fallback to system python if virtualenv missing
  python %*
)
endlocal
