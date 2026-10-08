@echo off
rem ============================================================
rem  Win7 兼容版构建脚本（与主版完全隔离）
rem  依赖：.py38\（Python 3.8.10 32位，含 customtkinter/send2trash/pyinstaller 5.13.2）
rem  产物：dist_win7\IntranetCleaner_win7.exe（32位，Win7 SP1+ 可运行）
rem  注意：主版（.venv + dist）不受本脚本影响
rem ============================================================
cd /d %~dp0

if not exist .py38\python.exe (
  echo [错误] 未找到 .py38\Python 3.8 环境，请先按 README 安装
  pause
  exit /b 1
)

.py38\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name IntranetCleaner_win7 ^
  --paths app ^
  --collect-all customtkinter ^
  --add-data "%~dp0tools;tools" ^
  --distpath dist_win7 ^
  --workpath build_win7 ^
  --specpath build_win7 ^
  app\main.py
if errorlevel 1 goto :fail

rem ====== 清理分发目录运行痕迹 ======
if exist dist_win7\config.json.bak del dist_win7\config.json.bak
if exist dist_win7\config.json.corrupt del dist_win7\config.json.corrupt
if exist dist_win7\*.log del dist_win7\*.log

rem ====== 词表随包（内网分发口径，与主版一致）======
copy /y config.json dist_win7\config.json >nul
copy /y 使用说明.md dist_win7\使用说明.md >nul

echo.
echo 构建完成：dist_win7\IntranetCleaner_win7.exe（32位）
echo 分发清单：exe + config.json（52词）+ 使用说明.md
echo          + vc_redist.x86.exe（目标机缺 UCRT 时先装它）
echo 注意：32位系统无法安装 AnyTXT x64，内容检索在这些机器上不可用
pause
exit /b 0

:fail
echo.
echo 构建失败，请查看上方输出。
pause
exit /b 1
