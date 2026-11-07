<# Build a Windows x64 portable ZIP and per-user installer using Python 3.11. #>
[CmdletBinding()]
param(
    [string]$OutputDir = "dist/windows-x86_64",
    [string]$Python = "",
    [switch]$ReuseBundle,
    [switch]$OfflineTools,
    [switch]$SkipTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "Run this command on native Windows x64."
}
$repository = Split-Path -Parent $PSScriptRoot
if (-not [IO.Path]::IsPathRooted($OutputDir)) { $OutputDir = Join-Path $repository $OutputDir }
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
$bundle = Join-Path $OutputDir "MediaWrapper"
if ((Test-Path $bundle) -and -not $ReuseBundle) {
    throw "$bundle already exists. Choose another -OutputDir or explicitly use -ReuseBundle."
}
if ($ReuseBundle -and -not (Test-Path -PathType Container $bundle)) {
    throw "-ReuseBundle requires an existing MediaWrapper directory."
}
$reports = Join-Path $OutputDir "reports"
New-Item -ItemType Directory -Force -Path $reports | Out-Null
$transcript = Join-Path $reports ("bootstrap-" + [guid]::NewGuid().ToString("N") + ".log")

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $Executable $Arguments" }
}

Start-Transcript -Path $transcript | Out-Null
$previousPythonPath = $env:PYTHONPATH
$previousQtPlatform = $env:QT_QPA_PLATFORM
$previousHashSeed = $env:PYTHONHASHSEED
$previousPythonUtf8 = $env:PYTHONUTF8
$previousPythonIoEncoding = $env:PYTHONIOENCODING
Push-Location $repository
try {
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    $pythonArguments = @()
    if ($Python) {
        $pythonCommand = (Get-Command $Python -ErrorAction Stop).Source
    } else {
        $pythonCommand = (Get-Command py -ErrorAction Stop).Source
        $pythonArguments = @("-3.11")
    }
    $versionCheck = "import platform, sys; assert sys.version_info[:2] == (3, 11) and sys.maxsize > 2**32 and platform.machine().lower() in ('amd64', 'x86_64'), 'Python 3.11 x64 is required'"
    Invoke-Checked $pythonCommand ($pythonArguments + @("-c", $versionCheck))
    $environmentDir = Join-Path $repository "build/windows-venv"
    if (-not (Test-Path (Join-Path $environmentDir "Scripts/python.exe"))) {
        Invoke-Checked $pythonCommand ($pythonArguments + @("-m", "venv", $environmentDir))
    }
    $buildPython = Join-Path $environmentDir "Scripts/python.exe"
    Invoke-Checked $buildPython @("-c", $versionCheck)
    Invoke-Checked $buildPython @("-m", "pip", "install", "--disable-pip-version-check", "-r", "packaging/requirements.txt", "-r", "packaging/test-requirements.txt")
    # Tests and the native verifier must resolve this checkout, not an older installed app.
    $env:PYTHONPATH = Join-Path $repository "src"
    $env:QT_QPA_PLATFORM = "offscreen"
    $env:PYTHONHASHSEED = "0"
    $arguments = @("scripts/build_release.py", "--output-dir", $OutputDir)
    if ($ReuseBundle) { $arguments += "--reuse-bundle" }
    if ($OfflineTools) { $arguments += "--offline-tools" }
    if ($SkipTests) { $arguments += "--skip-tests" }
    Invoke-Checked $buildPython $arguments
} finally {
    $env:PYTHONPATH = $previousPythonPath
    $env:QT_QPA_PLATFORM = $previousQtPlatform
    $env:PYTHONHASHSEED = $previousHashSeed
    $env:PYTHONUTF8 = $previousPythonUtf8
    $env:PYTHONIOENCODING = $previousPythonIoEncoding
    Pop-Location
    Stop-Transcript | Out-Null
}
