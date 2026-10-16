# setup_https.ps1 —— T4 系统层：安装自签名 HTTPS 证书（方案 A，可重复执行）。
#
# 流程：
#   1. py -3 gen_cert.py 生成/复用 OpenSSL 兼容证书
#      （%LOCALAPPDATA%\MOLING\certs\moling_cert.pem / moling_key.pem / moling_cert.cer）
#   2. 把证书装入当前用户受信任根（Cert:\CurrentUser\Root）：
#      首次安装即信任；若本机已存在旧版同名证书则先移除再导入最新，
#      避免指纹重复。证书指纹由 gen_cert.py 输出（GENERATED / REUSED）。
#   3. 输出指纹与 PEM 路径，供后端 TLS 挂载。
#
# 隐私边界：私钥只落在当前用户目录，不写入仓库、不输出到日志。
# 删除信任：Remove-Item Cert:\CurrentUser\Root\<Thumbprint>（本脚本不执行删除）。
#
# 用法：powershell -ExecutionPolicy Bypass -File setup_https.ps1

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$certsDir = Join-Path $env:LOCALAPPDATA "MOLING\certs"
$cerPath = Join-Path $certsDir "moling_cert.cer"
$certPath = Join-Path $certsDir "moling_cert.pem"
$keyPath = Join-Path $certsDir "moling_key.pem"
$subject = "CN=MOLING Local Service, O=MOLING"

# 1) 生成/复用证书（cryptography 保证 OpenSSL 兼容）
$output = py -3 (Join-Path $scriptDir "gen_cert.py") 2>&1 | Out-String
$statusLine = ($output -split "`r?`n" | Where-Object { $_ -match "^(GENERATED|REUSED) " } | Select-Object -Last 1)
if (-not $statusLine) {
    Write-Host "[setup_https] gen_cert.py 异常退出："
    Write-Host $output
    exit 1
}
$fingerprint = ($statusLine -split " ")[1]
$generated = $statusLine.StartsWith("GENERATED")
Write-Host "[setup_https] 证书指纹 $fingerprint ($(if ($generated) { '新建' } else { '复用' }))"

# 2) 同步受信任根：只在新生成或尚未信任时导入
$trusted = Get-ChildItem "Cert:\CurrentUser\Root" |
    Where-Object { $_.Thumbprint -eq $fingerprint } | Select-Object -First 1
if ($trusted) {
    Write-Host "[setup_https] 该指纹已在受信任根，无需重复导入。"
} else {
    # 移除同名的旧证书（若有），再导入最新证书
    Get-ChildItem "Cert:\CurrentUser\Root" |
        Where-Object { $_.Subject -eq $subject } |
        ForEach-Object {
            Write-Host "  [setup_https] 移除旧证书 $($_.Thumbprint)"
            Remove-Item "Cert:\CurrentUser\Root\$($_.Thumbprint)" -Force
        }
    Import-Certificate -FilePath $cerPath -CertStoreLocation "Cert:\CurrentUser\Root" | Out-Null
    Write-Host "[setup_https] 已导入受信任根。"
}

Write-Host "[setup_https] 完成。"
Write-Host "  thumbprint=$fingerprint"
Write-Host "  cert=$certPath"
Write-Host "  key=$keyPath"
Write-Host "  信任库：Cert:\CurrentUser\Root"
