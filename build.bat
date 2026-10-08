@echo off
cd /d %~dp0

rem ====== 构建（N3 修复：无空续行；与实际构建方式一致）======
.venv\Scripts\pyinstaller.exe --noconfirm --clean --onefile --windowed ^
  --name IntranetCleaner ^
  --paths app ^
  --collect-all customtkinter ^
  --add-data "tools;tools" ^
  app\main.py
if errorlevel 1 goto :fail

rem ====== 清理分发目录运行痕迹（N14）======
if exist dist\config.json.bak del dist\config.json.bak
if exist dist\config.json.corrupt del dist\config.json.corrupt
if exist dist\*.log del dist\*.log

echo.
echo ====== 发布前校验（N4：GitHub 侧零词表）======
.venv\Scripts\python.exe tools\release_check.py
if errorlevel 1 goto :fail

echo.
echo 构建完成：dist\IntranetCleaner.exe
pause
exit /b 0

:fail
echo.
echo 构建或校验失败，请查看上方输出。
pause
exit /b 1
