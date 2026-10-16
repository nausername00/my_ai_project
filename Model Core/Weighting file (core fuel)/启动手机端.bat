@echo off
setlocal EnableDelayedExpansion

set "PROJECT_ROOT=%~dp0"
set "ENGINE_DIR=%PROJECT_ROOT%Source code engine"
set "TOKEN_FILE=%PROJECT_ROOT%mobile_token.txt"

echo.
echo   墨灵 - 手机端访问启动器
echo   -------------------------
echo   [说明] 以局域网监听启动后端，手机浏览器输入
echo          http://电脑IP:8000/v1/mobile/ 即可打开墨灵移动页。
echo.

rem ---- 依赖检查 ----
where.exe py.exe >nul 2>&1
if errorlevel 1 (
    echo [缺少依赖] 未找到 Python Launcher（py.exe）。
    pause
    exit /b 1
)

rem ---- Token 处理：非本机访问必须带 token ----
set "MOLING_API_TOKEN="
if exist "%TOKEN_FILE%" (
    set /p MOLING_API_TOKEN=<"%TOKEN_FILE%"
)
if not defined MOLING_API_TOKEN (
    echo   首次使用：正在生成访问 Token...
    for /f %%i in ('powershell -NoProfile -Command "$h=[guid]::NewGuid().ToString('N'); Write-Output $h"') do set "MOLING_API_TOKEN=%%i"
    > "%TOKEN_FILE%" echo %MOLING_API_TOKEN%
    echo   已生成并保存到 mobile_token.txt
) else (
    echo   复用已有 Token（见 mobile_token.txt）
)
echo   你的 Token: %MOLING_API_TOKEN%
echo   ^(在手机页右上角齿轮图标里填入后保存；仅存手机浏览器^)
echo.

rem ---- 模型后端沿用默认配置 ----
if not defined MODEL_BACKEND set "MODEL_BACKEND=ollama"
if not defined OLLAMA_MODEL set "OLLAMA_MODEL=qwen2.5:3b"
if not defined OLLAMA_URL set "OLLAMA_URL=http://127.0.0.1:11434"

echo   正在以局域网监听启动后端（0.0.0.0:8000）……
echo   手机访问地址：http://<电脑IP>:8000/v1/mobile/
echo   电脑 IP 请用 ipconfig 查看，或参考下面列出的地址：
powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | ForEach-Object { Write-Output ('   http://' + $_.IPAddress + ':8000/v1/mobile/') }"
echo.
echo   [提示] 关闭本窗口即停止服务。按 Ctrl+C 可退出。
echo.

cd /d "%ENGINE_DIR%"
set "MOLING_API_TOKEN=%MOLING_API_TOKEN%"
py -3 app.py --host 0.0.0.0 --port 8000

echo.
echo   服务已停止。
pause
endlocal
