@echo off
chcp 65001 >nul
cd /d %~dp0
title BanGo Build

echo ============================================
echo  BanGo - Build to EXE
echo ============================================
echo.

echo [1/2] Checking dependencies...
pip install pyinstaller >nul 2>&1

echo [2/2] Building executable...
python -m PyInstaller --noconfirm --onefile --windowed --name BanGo gui.py
if errorlevel 1 goto :err

if not exist dist\gtp_override.cfg copy /y gtp_override.cfg dist\ >nul

echo [3/3] Copying runtime dependencies...
if not exist dist\katago.exe copy /y dist_opencl\katago.exe dist\ >nul
if not exist dist\OpenCL.dll copy /y dist_opencl\OpenCL.dll dist\ >nul
if not exist dist\z.dll copy /y dist_opencl\z.dll dist\ >nul
if not exist dist\default_gtp.cfg (
  if exist "E:\2026-01-07-win64-KataGo\katago_configs\default_gtp.cfg" (
    copy /y "E:\2026-01-07-win64-KataGo\katago_configs\default_gtp.cfg" dist\ >nul
  )
)

echo.
echo ============ BUILD SUCCESS ============
echo Output: dist\BanGo.exe
echo.
echo Note: exe references external files at runtime:
echo   - katago.exe (engine, copied to dist\)
echo   - OpenCL.dll + z.dll (copied to dist\)
echo   - default_gtp.cfg (NOT included — user must provide)
echo   - *.bin.gz (model weights, NOT included — user must download)
echo   - gtp_override.cfg (copied to dist\)
echo =======================================
pause
exit /b 0

:err
echo.
echo ============ BUILD FAILED ============
pause
exit /b 1