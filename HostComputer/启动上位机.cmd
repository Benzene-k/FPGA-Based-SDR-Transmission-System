@echo off
setlocal
cd /d "%~dp0"
set "PY=python"
if exist "%~dp0runtime\python\python.exe" set "PY=%~dp0runtime\python\python.exe"
"%PY%" -B "%~dp0tools\portable_bootstrap.py"
if errorlevel 1 (
  echo.
  echo 启动失败，请检查上方错误信息。
  pause
)
