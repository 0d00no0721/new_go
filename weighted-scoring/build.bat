@echo off
chcp 65001 >nul
cd /d %~dp0
title WeightedGo Build

echo ============================================
echo  WeightedGo - Build to EXE
echo ============================================
echo.

echo [1/3] Checking dependencies...
pip install pyinstaller >nul 2>&1

echo [2/3] Building executable...
python -m PyInstaller --noconfirm --onefile --windowed --name WeightedGo gui.py
if errorlevel 1 goto :err

echo [3/3] Copying runtime dependencies...
if not exist dist\gtp_override.cfg copy /y gtp_override.cfg dist\ >nul
if not exist dist\weight_table_final.txt copy /y weight_table_final.txt dist\ >nul
if not exist dist\katago.exe copy /y dist_opencl\katago.exe dist\ >nul
if not exist dist\OpenCL.dll copy /y dist_opencl\OpenCL.dll dist\ >nul
if not exist dist\z.dll copy /y dist_opencl\z.dll dist\ >nul
if not exist dist\default_gtp.cfg (
  if exist "E:\2026-01-07-win64-KataGo\katago_configs\default_gtp.cfg" (
    copy /y "E:\2026-01-07-win64-KataGo\katago_configs\default_gtp.cfg" dist\ >nul
  ) else (
    echo WARNING: default_gtp.cfg NOT copied - configure engine in GUI settings
  )
)

echo.
echo ============ BUILD SUCCESS ============
echo Output: dist\WeightedGo.exe
echo.
echo Note: exe references external files at runtime (in dist\):
echo   - katago.exe (engine)
echo   - OpenCL.dll + z.dll
echo   - default_gtp.cfg (engine config)
echo   - gtp_override.cfg (komi 7.5 + search limits)
echo   - weight_table_final.txt (weight table)
echo   - 28b.bin.gz (model weights, NOT included - see README download link)
echo =======================================
pause
exit /b 0

:err
echo.
echo ============ BUILD FAILED ============
pause
exit /b 1