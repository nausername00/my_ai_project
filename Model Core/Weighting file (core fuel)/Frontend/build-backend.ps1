$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$engineDir = Join-Path $projectRoot "Source code engine"
$outputDir = Join-Path $PSScriptRoot "release-backend"
$workDir = Join-Path $PSScriptRoot ".pyinstaller-work"
$specDir = Join-Path $workDir "spec"
$voiceModel = Join-Path $projectRoot "Character\assets\voices\zh_CN-huayan-medium.onnx"
$voiceConfig = "$voiceModel.json"

if (-not (Test-Path $voiceModel -PathType Leaf) -or -not (Test-Path $voiceConfig -PathType Leaf)) {
    throw "The default Piper voice model and matching JSON config must exist in Character\assets\voices."
}

$null = New-Item -ItemType Directory -Path $specDir -Force

$pyinstallerArgs = @(
    "-3"
    "-m"
    "PyInstaller"
    "--noconfirm"
    "--clean"
    "--onedir"
    "--name"
    "MolingBackend"
    "--distpath"
    $outputDir
    "--workpath"
    $workDir
    "--specpath"
    $specDir
    "--paths"
    $engineDir
    "--collect-all"
    "faster_whisper"
    "--collect-all"
    "ctranslate2"
    "--collect-all"
    "av"
    "--collect-all"
    "piper"
    "--collect-all"
    "onnxruntime"
    (Join-Path $engineDir "app.py")
)

& py @pyinstallerArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}
