[CmdletBinding()]
param(
    [string]$PythonPath = ".\.venv\Scripts\python.exe",
    [switch]$InstallBuildDeps,
    [switch]$Clean,
    [switch]$SkipArchive,
    [int]$ArchiveRetryCount = 12,
    [int]$ArchiveRetryDelaySeconds = 5
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildRoot = Join-Path $RepoRoot ".build"
$TempRoot = Join-Path $BuildRoot "tmp"
$WorkRoot = Join-Path $BuildRoot "pyinstaller-work"
$SpecRoot = Join-Path $BuildRoot "spec"
$DistRoot = Join-Path $RepoRoot "dist"
$ReleaseRoot = Join-Path $RepoRoot "release"
$AppName = "TFC Document Control"
$AppEntry = Join-Path $RepoRoot "app.py"
$IconPath = Join-Path $RepoRoot "app.ico"
$PythonExe = if ([System.IO.Path]::IsPathRooted($PythonPath)) { $PythonPath } else { Join-Path $RepoRoot $PythonPath }
$ArchiveName = "tfc-document-control-windows.zip"
$ArchivePath = Join-Path $ReleaseRoot $ArchiveName
$OutputDir = Join-Path $DistRoot $AppName

function Reset-Directory([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Path | Out-Null
}

function Ensure-Directory([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Test-FileReadable([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $false
    }
    $stream = $null
    try {
        $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
        return $true
    }
    catch {
        return $false
    }
    finally {
        if ($null -ne $stream) {
            $stream.Dispose()
        }
    }
}

function Wait-ForReadableBundle([string]$Path, [int]$TimeoutSeconds) {
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    while ($stopwatch.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        $lockedFiles = @()
        foreach ($file in Get-ChildItem -LiteralPath $Path -Recurse -File) {
            if (-not (Test-FileReadable $file.FullName)) {
                $lockedFiles += $file.FullName
            }
        }
        if ($lockedFiles.Count -eq 0) {
            return
        }
        Start-Sleep -Seconds 2
    }
    throw "Timed out waiting for bundle files to become readable. Endpoint protection may still be scanning files under: $Path"
}

function New-ArchiveWithRetry([string]$SourceDir, [string]$DestinationPath, [int]$RetryCount, [int]$RetryDelaySeconds) {
    $lastError = $null
    for ($attempt = 1; $attempt -le $RetryCount; $attempt++) {
        try {
            Wait-ForReadableBundle -Path $SourceDir -TimeoutSeconds ([Math]::Max(5, $RetryDelaySeconds * 2))
            if (Test-Path -LiteralPath $DestinationPath) {
                Remove-Item -LiteralPath $DestinationPath -Force
            }
            Compress-Archive -Path $SourceDir -DestinationPath $DestinationPath -CompressionLevel Optimal -Force
            return
        }
        catch {
            $lastError = $_
            if ($attempt -eq $RetryCount) {
                break
            }
            Write-Warning "Archive attempt $attempt of $RetryCount failed: $($_.Exception.Message)"
            Start-Sleep -Seconds $RetryDelaySeconds
        }
    }
    throw "Failed to create release archive after $RetryCount attempts. Last error: $($lastError.Exception.Message)"
}

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

if (-not (Test-Path -LiteralPath $AppEntry)) {
    throw "App entrypoint not found: $AppEntry"
}

if ($Clean) {
    foreach ($path in @($BuildRoot, $DistRoot, $ReleaseRoot)) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Recurse -Force
        }
    }
}

Ensure-Directory $BuildRoot
Reset-Directory $TempRoot
Reset-Directory $WorkRoot
Reset-Directory $SpecRoot
Ensure-Directory $DistRoot
Ensure-Directory $ReleaseRoot

$env:TMP = $TempRoot
$env:TEMP = $TempRoot
$env:PYINSTALLER_CONFIG_DIR = Join-Path $BuildRoot "pyinstaller-config"
$env:PYTHONUTF8 = "1"

if ($InstallBuildDeps) {
    & $PythonExe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upgrade pip."
    }
    & $PythonExe -m pip install -r (Join-Path $RepoRoot "requirements.txt") -r (Join-Path $RepoRoot "requirements-build.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install build dependencies."
    }
}

& $PythonExe -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not installed. Run .\build.ps1 -InstallBuildDeps or install requirements-build.txt first."
}

$pyInstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--onedir",
    "--noupx",
    "--name", $AppName,
    "--distpath", $DistRoot,
    "--workpath", $WorkRoot,
    "--specpath", $SpecRoot,
    "--contents-directory", "_internal",
    "--hidden-import", "PySide6.QtCore",
    "--hidden-import", "PySide6.QtGui",
    "--hidden-import", "PySide6.QtWidgets",
    "--collect-submodules", "document_control"
)

$iconArgs = @()
if (Test-Path -LiteralPath $IconPath -PathType Leaf) {
    $iconArgs = @("--icon", $IconPath)
}

& $PythonExe @pyInstallerArgs @iconArgs $AppEntry
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

if (-not (Test-Path -LiteralPath $OutputDir)) {
    throw "Expected build output not found: $OutputDir"
}

$ExePath = Join-Path $OutputDir "$AppName.exe"
$ExeHash = if (Test-Path -LiteralPath $ExePath) { (Get-FileHash -Algorithm SHA256 -LiteralPath $ExePath).Hash } else { "" }

$ArchiveCreated = $false
if (-not $SkipArchive) {
    New-ArchiveWithRetry -SourceDir $OutputDir -DestinationPath $ArchivePath -RetryCount $ArchiveRetryCount -RetryDelaySeconds $ArchiveRetryDelaySeconds
    $ArchiveCreated = $true
}

Write-Host ""
Write-Host "Build complete." -ForegroundColor Green
Write-Host "Executable: $ExePath"
Write-Host "Bundle:     $OutputDir"
if ($ArchiveCreated) {
    Write-Host "Archive:    $ArchivePath"
}
else {
    Write-Host "Archive:    skipped"
}
if ($ExeHash) {
    Write-Host "SHA256:     $ExeHash"
}
Write-Host ""
Write-Host "Notes:"
Write-Host "- This build uses PyInstaller onedir mode to avoid onefile temp extraction."
Write-Host "- TMP/TEMP/PyInstaller config are pinned inside the repo to reduce endpoint protection interference."
