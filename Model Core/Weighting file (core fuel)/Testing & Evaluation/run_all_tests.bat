@echo off
setlocal
REM ============================================================
REM 墨灵统一测试入口（阶段 0 · P0-7）
REM 用法: 双击运行 或 cmd 里执行 run_all_tests.bat
REM 覆盖: Python 全量 / 前端语法 / Node 单测；先停 8000 后端（E11 坑）
REM ============================================================

set "ROOT=%~dp0.."
set "ENG=%ROOT%\Model Core\Weighting file (core fuel)\Source code engine"
set "TESTS=%ROOT%\Model Core\Weighting file (core fuel)\Testing & Evaluation\tests"
set "FRONT=%ROOT%\Model Core\Weighting file (core fuel)\Frontend"

echo [1/4] 停止可能运行中的后端(8000)...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
  taskkill /PID %%p /F >nul 2>&1
)

echo [2/4] Python 全量测试...
pushd "%ROOT%"
set "PYTHONPATH=%ENG%;%TESTS%"
py -3 -m unittest discover -s "%TESTS%"
set "PY_EXIT=%ERRORLEVEL%"

echo [3/4] 前端语法检查...
pushd "%FRONT%"
call npm run check >nul 2>&1
set "CHECK_EXIT=%ERRORLEVEL%"

echo [4/4] 前端 Node 单测...
call npm test >nul 2>&1
set "NODE_EXIT=%ERRORLEVEL%"
popd

echo.
echo ============================================
echo  汇总: Python=%PY_EXIT% 语法=%CHECK_EXIT% Node=%NODE_EXIT%  (0=通过)
echo ============================================
if not "%PY_EXIT%"=="0" exit /b %PY_EXIT%
if not "%CHECK_EXIT%"=="0" exit /b %CHECK_EXIT%
if not "%NODE_EXIT%"=="0" exit /b %NODE_EXIT%
echo 全部通过
exit /b 0
