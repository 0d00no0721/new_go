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

echo.
echo ============ BUILD SUCCESS ============
echo Output: dist\BanGo.exe
echo.
echo Note: exe references external files at runtime:
echo   - dist_opencl\katago.exe (engine)
echo   - weights\28b.bin.gz (model)
echo   - gtp_override.cfg (tuner cache config)
echo =======================================
pause
exit /b 0

:err
echo.
echo ============ BUILD FAILED ============
pause
exit /b 1