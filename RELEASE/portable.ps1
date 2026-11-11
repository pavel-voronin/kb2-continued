#Requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[vV][0-9]+(\.[0-9]+){0,2}(-[0-9A-Za-z]+([.-][0-9A-Za-z]+)*)?$')]
    [string]$Tag,
    [string]$OutputDirectory = (Join-Path ([IO.Path]::GetTempPath()) 'kb2-releases'),
    [string]$WorkDirectory = (Join-Path ([IO.Path]::GetTempPath()) ('kb2-build-' + [guid]::NewGuid().ToString('N')))
)
$ErrorActionPreference = 'Stop'
$repository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
# Fail before downloads, workspace creation or DOS compilation.
. (Join-Path $PSScriptRoot 'changelog.ps1')
$changes = Get-ReleaseChanges -Path (Join-Path $repository 'CHANGELOG.md') -Tag $Tag
$WorkDirectory = [IO.Path]::GetFullPath($WorkDirectory)
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $WorkDirectory) { throw 'Use a new, empty build directory.' }
New-Item -ItemType Directory -Path $WorkDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$archive = Join-Path $OutputDirectory "KB2-continued-$Tag-win64-portable.zip"
if (Test-Path -LiteralPath $archive) { throw "Archive already exists: $archive" }

function Write-DosText([string]$Path, [string]$Text) {
    [IO.File]::WriteAllText($Path, ($Text -replace '\r?\n', "`r`n"), [Text.Encoding]::ASCII)
}
function Write-Utf8([string]$Path, [string]$Text) {
    [IO.File]::WriteAllText($Path, $Text, [Text.UTF8Encoding]::new($true))
}

# Download a pinned official binary; never compile or patch the emulator.
$emulator = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'dosbox-x.json') -Raw | ConvertFrom-Json
$upstream = 'https://github.com/joncampbell123/dosbox-x'
$download = "$upstream/releases/download/$($emulator.tag)/$($emulator.asset)"
$downloaded = Join-Path $WorkDirectory 'dosbox-x.zip'
Invoke-WebRequest -Uri $download -OutFile $downloaded
if ((Get-FileHash -LiteralPath $downloaded -Algorithm SHA256).Hash -ine $emulator.sha256) {
    throw 'Official DOSBox-X archive checksum mismatch.'
}
$official = Join-Path $WorkDirectory 'official'
Expand-Archive -LiteralPath $downloaded -DestinationPath $official
$runtime = Join-Path $official $emulator.directory
$exe = Join-Path $runtime 'dosbox-x.exe'
if ((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash -ine $emulator.exeSha256) {
    throw 'Official DOSBox-X executable checksum mismatch.'
}

# Build in an isolated DOS tree, ignoring any existing SRC/DIST or compiler output.
$build = Join-Path $WorkDirectory 'build'
$source = Join-Path $build 'SRC'
New-Item -ItemType Directory -Path $source,(Join-Path $build 'PASCAL') -Force | Out-Null
Get-ChildItem -LiteralPath (Join-Path $repository 'SRC') -File |
    Where-Object { $_.Extension -in '.PAS','.INC' } |
    Copy-Item -Destination $source
foreach ($folder in 'ART','DOC') {
    Copy-Item -LiteralPath (Join-Path $repository "SRC/$folder") -Destination $source -Recurse
}
Copy-Item -LiteralPath (Join-Path $repository 'SRC/PACK.LST') -Destination $source
foreach ($name in 'TPC.EXE','TURBO.TPL') {
    Copy-Item -LiteralPath (Join-Path $repository "PASCAL/$name") -Destination (Join-Path $build 'PASCAL')
}
Copy-Item -LiteralPath (Join-Path $repository 'BUILD.BAT') -Destination $build
$buildConfig = Join-Path $WorkDirectory 'BUILD.CNF'
Write-DosText $buildConfig @"
[sdl]
output=surface
[dosbox]
machine=ega
memsize=16
[cpu]
core=normal
cycles=max
[mixer]
nosound=true
[autoexec]
mount c "$build"
c:
config -securemode
call BUILD.BAT
exit
"@
$start = [Diagnostics.ProcessStartInfo]::new()
$start.FileName = $exe
$start.ArgumentList.Add('-conf')
$start.ArgumentList.Add($buildConfig)
$start.ArgumentList.Add('-fastlaunch')
$start.ArgumentList.Add('-nogui')
$start.ArgumentList.Add('-exit')
$start.WorkingDirectory = $build
$start.UseShellExecute = $false
$start.CreateNoWindow = $true
$start.Environment['SDL_VIDEODRIVER'] = 'dummy'
$start.Environment['SDL_AUDIODRIVER'] = 'dummy'
$process = [Diagnostics.Process]::Start($start)
# Share two logical processors with the compiler child; keep local builds unobtrusive.
$mask = (Get-Process -Id $PID).ProcessorAffinity.ToInt64()
$first = $mask -band (-$mask)
$rest = $mask -band (-bnot $first)
$process.ProcessorAffinity = [IntPtr]($first -bor ($rest -band (-$rest)))
$process.PriorityClass = 'BelowNormal'
if (-not $process.WaitForExit(600000)) { $process.Kill(); throw 'DOS compilation timed out.' }
if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath (Join-Path $source 'BUILD.OK'))) {
    throw "Game build failed. Compiler logs: $source"
}
$game = Join-Path $source 'DIST'
$required = @('KB2.EXE','KB2.DOC','MAPS.TXT')
foreach ($entry in Get-Content -LiteralPath (Join-Path $source 'PACK.LST')) {
    if ($entry -match '^([TSF])\s+(\w+)\s+\d+\s*$') {
        $required += if ($Matches[1] -eq 'F') { 'KB2.FNT' } else { $Matches[2] + '.PIC' }
    }
}
foreach ($name in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $game $name))) {
        throw "Incomplete game distribution: $name"
    }
}

$package = Join-Path $WorkDirectory 'package'
New-Item -ItemType Directory -Path $package,(Join-Path $package 'DOSBOX'),(Join-Path $package 'LICENSES') | Out-Null
Copy-Item -LiteralPath $game -Destination (Join-Path $package 'GAME') -Recurse
Copy-Item -LiteralPath (Join-Path $repository 'CHANGELOG.md') -Destination (Join-Path $package 'CHANGELOG.md')
foreach ($name in 'dosbox-x.exe','inpoutx64.dll','README.txt') {
    Copy-Item -LiteralPath (Join-Path $runtime $name) -Destination (Join-Path $package 'DOSBOX')
}
Copy-Item -Path (Join-Path $PSScriptRoot 'LICENSES/*') -Destination (Join-Path $package 'LICENSES')
Copy-Item -LiteralPath (Join-Path $repository 'LICENSE') -Destination (Join-Path $package 'LICENSES/RECONSTRUCTION-MIT.txt')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'ORIGINAL.txt') -Destination (Join-Path $package 'LICENSES/ORIGINAL-GAME.txt')
Write-DosText (Join-Path $package 'START.BAT') @'
@echo off
cd /d "%~dp0"
start "" "DOSBOX\dosbox-x.exe" -conf "DOSBOX.CNF" -fastlaunch
'@
Write-DosText (Join-Path $package 'DOSBOX.CNF') @'
[sdl]
fullscreen=false
output=surface
[dosbox]
machine=ega
memsize=1
[cpu]
core=normal
cputype=286
cycles=fixed 3000
[render]
aspect=false
scaler=normal2x
[video]
vmemsize=0
vmemsizekb=256
[dos]
xms=false
ems=false
umb=false
[autoexec]
@echo off
mount c "GAME"
c:
KB2.EXE
exit
'@
$sources = "$upstream/tree/$($emulator.tag)"
$sourceDownload = "$upstream/archive/refs/tags/$($emulator.tag).zip"
Write-Utf8 (Join-Path $package 'DOSBOX-SOURCE.txt') @"
DOSBox-X $($emulator.version), official MinGW x64 / SDL2 build.
The executable and DLL have not been modified.
Official release: $upstream/releases/tag/$($emulator.tag)
Original binary archive: $download
Archive SHA256: $($emulator.sha256)
Corresponding source: $sources
Source download: $sourceDownload
Build instructions: $upstream/blob/$($emulator.tag)/BUILD.md

DOSBox-X permits GPL version 2 or any later version. This distribution
elects GPL version 3 for DOSBox-X; see LICENSES/GPL-3.0.txt.
The original GPLv2 text and upstream credits are also included.
The DOS game is a separate program with separate licensing.
"@
Write-Utf8 (Join-Path $package 'README.txt') @"
King's Bounty 2 — Continued $Tag, portable для Windows x64

Распакуйте весь архив в обычную папку и запустите START.BAT.
Установка, интернет и ручная настройка не нужны.
Управление — клавиатурой. Alt+Enter переключает полный экран.
Игра и создаваемые ею сохранения находятся в папке GAME.

Репозиторий проекта: https://github.com/pavel-voronin/kb2-continued

Автор оригинальной игры — Сергей Прокофьев.
Автор реконструкции и дополнений — Павел Воронин.
Условия использования и авторство указаны в LICENSES.
Используется официальный DOSBox-X $($emulator.version).
Его исходники: $sources
"@
[IO.Compression.ZipFile]::CreateFromDirectory($package, $archive, [IO.Compression.CompressionLevel]::SmallestSize, $false)
$notes = Join-Path $OutputDirectory "KB2-continued-$Tag-release.md"
Write-Utf8 $notes @"
$changes

---

Portable для Windows x64: распакуйте ZIP и запустите START.BAT. Установка не требуется.
"@
if ($env:GITHUB_OUTPUT) {
    Add-Content -LiteralPath $env:GITHUB_OUTPUT -Value "archive=$archive"
    Add-Content -LiteralPath $env:GITHUB_OUTPUT -Value "notes=$notes"
}
Write-Host "Portable archive: $archive"
Write-Host "Size: $((Get-Item -LiteralPath $archive).Length) bytes"
