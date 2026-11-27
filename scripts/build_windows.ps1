<#
.SYNOPSIS
Build a Windows x64 portable ZIP and per-user installer using Python 3.11.
.DESCRIPTION
Requires Git, FFmpeg and FFprobe on PATH. Each build gets its own output folder
unless -OutputDir is supplied. Use build.cmd for everyday builds.
.PARAMETER LocalBuild
Verify the portable application and ZIP without installing or uninstalling the app.
#>
[CmdletBinding()]
param(
    [string]$OutputDir = "",
    [string]$Python = "",
    [switch]$ReuseBundle,
    [switch]$OfflineTools,
    [switch]$SkipTests,
    [switch]$LocalBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "Run this command on native Windows x64."
}
$repository = Split-Path -Parent $PSScriptRoot
function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $Executable $Arguments" }
}

foreach ($tool in @("git", "ffmpeg", "ffprobe")) {
    $command = Get-Command $tool -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $command) {
        throw "$tool is required. Install it, add it to PATH, then reopen the terminal."
    }
    $versionOption = if ($tool -eq "git") { "--version" } else { "-version" }
    Invoke-Checked $command.Source @($versionOption) | Out-Null
}

if (-not $OutputDir) {
    if ($ReuseBundle) {
        $OutputDir = "dist/windows-x86_64"
    } else {
        $timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmss'Z'", [Globalization.CultureInfo]::InvariantCulture)
        $suffix = [guid]::NewGuid().ToString("N").Substring(0, 8)
        $OutputDir = "dist/builds/windows-x86_64/$timestamp-$suffix"
    }
}
if (-not [IO.Path]::IsPathRooted($OutputDir)) { $OutputDir = Join-Path $repository $OutputDir }
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
$bundle = Join-Path $OutputDir "MediaWrapper"
if ((Test-Path -LiteralPath $bundle) -and -not $ReuseBundle) {
    throw "$bundle already exists. Choose another -OutputDir or explicitly use -ReuseBundle."
}
if ($ReuseBundle -and -not (Test-Path -LiteralPath $bundle -PathType Container)) {
    throw "-ReuseBundle requires an existing MediaWrapper directory."
}
$reports = Join-Path $OutputDir "reports"
[IO.Directory]::CreateDirectory($reports) | Out-Null
$transcript = Join-Path $reports ("bootstrap-" + [guid]::NewGuid().ToString("N") + ".log")
Start-Transcript -LiteralPath $transcript | Out-Null
$previousPythonPath = $env:PYTHONPATH
$previousQtPlatform = $env:QT_QPA_PLATFORM
$previousHashSeed = $env:PYTHONHASHSEED
$previousPythonUtf8 = $env:PYTHONUTF8
$previousPythonIoEncoding = $env:PYTHONIOENCODING
Push-Location -LiteralPath $repository
try {
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    $pythonArguments = @()
    if ($Python) {
        if (Test-Path -LiteralPath $Python -PathType Leaf) {
            $pythonCommand = (Get-Item -LiteralPath $Python).FullName
        } else {
            $pythonCommand = (Get-Command $Python -CommandType Application -ErrorAction Stop |
                Select-Object -First 1).Source
        }
    } else {
        $launcher = Get-Command py -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $launcher) {
            throw "Python 3.11 x64 with the Windows Python launcher (py) is required. Install it or pass -Python with the full path to python.exe."
        }
        $pythonCommand = $launcher.Source
        $pythonArguments = @("-3.11")
    }
    $versionCheck = "import platform, sys; assert sys.version_info[:2] == (3, 11) and sys.maxsize > 2**32 and platform.machine().lower() in ('amd64', 'x86_64'), 'Python 3.11 x64 is required'"
    Invoke-Checked $pythonCommand ($pythonArguments + @("-c", $versionCheck))
    $environmentDir = Join-Path $repository "build/windows-venv"
    if (-not (Test-Path -LiteralPath (Join-Path $environmentDir "Scripts/python.exe") -PathType Leaf)) {
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
    if ($LocalBuild) { $arguments += "--skip-installer-verification" }
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
