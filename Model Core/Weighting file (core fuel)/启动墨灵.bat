@echo off
setlocal
chcp 65001 >nul

set "PROJECT_ROOT=%~dp0"
set "FRONTEND_DIR=%PROJECT_ROOT%Frontend"
if not defined MODEL_BACKEND set "MODEL_BACKEND=ollama"
if not defined OLLAMA_MODEL set "OLLAMA_MODEL=qwen2.5:0.5b"
if not defined OLLAMA_URL set "OLLAMA_URL=http://127.0.0.1:11434"

echo.
echo   墨灵桌面助手 - 启动检查
echo   -------------------------

where.exe node >nul 2>&1
if errorlevel 1 (
    echo [缺少依赖] 未找到 Node.js。请先安装 Node.js 20 或更新版本。
    goto :failed
)

node.exe -e "process.exit(Number(process.versions.node.split('.')[0]) >= 20 ? 0 : 1)" >nul 2>&1
if errorlevel 1 (
    echo [版本不符] 墨灵桌面端需要 Node.js 20 或更新版本。
    goto :failed
)

where.exe npm.cmd >nul 2>&1
if errorlevel 1 (
    echo [缺少依赖] 未找到 npm。请重新安装 Node.js 并启用 npm。
    goto :failed
)

where.exe py.exe >nul 2>&1
if errorlevel 1 (
    echo [缺少依赖] 未找到 Python Launcher（py.exe）。请先安装 Python 3.10 或更新版本。
    goto :failed
)

py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [版本不符] 找不到 Python 3.10 或更新版本。
    goto :failed
)

if not exist "%FRONTEND_DIR%\package.json" (
    echo [项目文件缺失] 找不到 Frontend\package.json。
    goto :failed
)

if not exist "%FRONTEND_DIR%\node_modules\electron\dist\electron.exe" (
    echo.
    echo 首次启动需要安装桌面端依赖，需联网下载约百余 MB。
    choice /C YN /N /M "现在运行 npm ci 安装依赖吗？[Y/N] "
    if errorlevel 2 goto :cancelled
    pushd "%FRONTEND_DIR%"
    call npm.cmd ci
    set "INSTALL_EXIT_CODE=%ERRORLEVEL%"
    popd
    if not "%INSTALL_EXIT_CODE%"=="0" (
        echo [安装失败] npm ci 返回代码 %INSTALL_EXIT_CODE%。
        goto :failed
    )
)

py -3 -c "import json, os, urllib.request; data=json.load(urllib.request.urlopen(os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/') + '/api/tags', timeout=3)); raise SystemExit(0 if any(item.get('name') == os.getenv('OLLAMA_MODEL', 'qwen2.5:0.5b') for item in data.get('models', [])) else 2)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [模型未就绪] 无法确认 Ollama 服务或模型 "%OLLAMA_MODEL%" 可用。
    echo 请启动 Ollama，再下载模型：
    if defined OLLAMA_EXECUTABLE (
        echo "%OLLAMA_EXECUTABLE%" pull %OLLAMA_MODEL%
    ) else if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
        echo "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" pull %OLLAMA_MODEL%
    ) else (
        echo ollama pull %OLLAMA_MODEL%
    )
    choice /C YN /N /M "仍要打开桌面设置和聊天窗口吗？[Y/N] "
    if errorlevel 2 goto :cancelled
)

echo.
echo 正在启动墨灵桌面端……
pushd "%FRONTEND_DIR%"
call npm.cmd start
set "APP_EXIT_CODE=%ERRORLEVEL%"
popd
if not "%APP_EXIT_CODE%"=="0" (
    echo.
    echo [启动失败] Electron 返回代码 %APP_EXIT_CODE%。
    goto :failed
)
goto :done

:cancelled
echo 已取消启动。
goto :done

:failed
echo.
echo 请先修复上方提示的依赖或配置问题，再重新运行本启动器。
pause
exit /b 1

:done
endlocal
