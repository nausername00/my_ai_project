# install_autostart.ps1 —— T4 系统层：墨灵开机自启（用户级注册表 Run 键）。
#
# 用途（显式安装，默认不启用）：
#   powershell -File install_autostart.ps1 -Install    # 启用开机自启（当前用户）
#   powershell -File install_autostart.ps1 -Remove     # 取消开机自启
#   powershell -File install_autostart.ps1 -Status     # 查看自启状态（默认）
#
# 实现：HKCU\Software\Microsoft\Windows\CurrentVersion\Run 的 MOLING 值，
#       登录时隐藏窗口启动 Electron（前端自动拉起 Python 后端）。
#       用户级、无需管理员；墨灵遵守"默认关"原则——不安装即不自启。
#
# 隐私边界：只写入当前用户启动项，不采集/不发送任何数据。

param(
    [switch]$Install,
    [switch]$Remove,
    [switch]$Status
)

$ErrorActionPreference = "Stop"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$valueName = "MOLING Companion"
$frontendDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$launcher = Join-Path $frontendDir "start_hidden.ps1"
$launcherText = @"
# 静默启动墨灵（开机自启用）：切换到前端目录并启动 Electron。
`$ErrorActionPreference = "Stop"
Set-Location -LiteralPath "$frontendDir"
& "cmd.exe" /c "npm start"
"@
$launcherText | Set-Content -LiteralPath $launcher -Encoding UTF8
$command = "powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$launcher`""

if ($Status -or (-not $Install -and -not $Remove)) {
    $existing = Get-ItemProperty -Path $runKey -Name $valueName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "[autostart] 已启用：登录时自动启动墨灵"
        Write-Host "  值：$($existing."$valueName")"
    } else {
        Write-Host "[autostart] 未启用（墨灵默认不自启）。启用：-Install；取消：-Remove"
    }
    exit 0
}

if ($Install) {
    Set-ItemProperty -Path $runKey -Name $valueName -Value $command
    Write-Host "[autostart] 已启用开机自启（当前用户）。取消：-Remove"
    exit 0
}

if ($Remove) {
    Remove-ItemProperty -Path $runKey -Name $valueName -ErrorAction SilentlyContinue
    Write-Host "[autostart] 已取消开机自启。"
    exit 0
}
