#Requires -Version 7.2
<#
.SYNOPSIS
Run every project test against the files staged for commit.
.DESCRIPTION
Stage the intended changes before running this script. Enable the project Git
hooks in this worktree with: git config --worktree core.hooksPath .githooks
#>
param()
$ErrorActionPreference = 'Stop'

function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program $($Arguments -join ' ') failed (exit $LASTEXITCODE)." }
}

function Get-GitValue([string[]]$Arguments) {
    $value = git @Arguments
    if ($LASTEXITCODE -ne 0) { throw "git $($Arguments -join ' ') failed." }
    return $value
}

function Get-TestKey([string[]]$Paths, [string[]]$Environment) {
    $inputs = Get-GitValue (@('-C', $root, 'ls-tree', '--full-tree', $tree, '--') + $Paths)
    $key = (@($inputs) + $Environment) -join "`n"
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($key)))
}

function Write-TestResult([string]$Path, [string]$Value) {
    $temporary = "$Path.$([guid]::NewGuid().ToString('N')).tmp"
    [IO.File]::WriteAllText($temporary, $Value)
    [IO.File]::Move($temporary, $Path, $true)
}

$root = Split-Path $PSScriptRoot
Push-Location $root
try {
    $gitDir = Get-GitValue @('rev-parse', '--absolute-git-dir')
    $commonDir = Get-GitValue @('rev-parse', '--path-format=absolute', '--git-common-dir')
    $tree = Get-GitValue @('write-tree')
    $workspace = (New-Item -ItemType Directory -Path (Join-Path $gitDir ('kb2-check-' + [guid]::NewGuid().ToString('N')))).FullName
    $checkout = (New-Item -ItemType Directory -Path (Join-Path $workspace 'tree')).FullName
    $links = @()
    try {
        $prefix = $checkout.Replace('\', '/') + '/'
        Invoke-Checked git @('checkout-index', '--all', "--prefix=$prefix")
        if ((Get-GitValue @('write-tree')) -ne $tree) { throw 'The Git index changed while copying files.' }

        $python = Join-Path $commonDir 'kb2-unit-host/Scripts/python.exe'
        if ($env:PYTHON) { $python = (Get-Command $env:PYTHON).Source }
        elseif (!(Test-Path -LiteralPath $python)) { $python = (Get-Command python).Source }
        $pwsh = (Get-Process -Id $PID).Path
        $node = (Get-Command node -CommandType Application | Select-Object -First 1).Source
        $env:PYTHON = $python
        if (!$env:KB2_TEST_WORK) { $env:KB2_TEST_WORK = Join-Path $gitDir 'kb2-test' }
        $env:KB2_TEST_WORK = [IO.Path]::GetFullPath($env:KB2_TEST_WORK)
        if ($env:KB2_DOSBOX) { $env:KB2_DOSBOX = [IO.Path]::GetFullPath($env:KB2_DOSBOX) }
        else {
            $dosbox = Get-Command dosbox-x -ErrorAction SilentlyContinue
            if ($dosbox) { $env:KB2_DOSBOX = $dosbox.Source }
            else {
                $runtime = Get-Content (Join-Path $checkout 'RELEASE/dosbox-x.json') -Raw | ConvertFrom-Json
                $installed = Join-Path $root "WEB/.build/dev/dosbox/$($runtime.directory)/dosbox-x.exe"
                if ((Test-Path -LiteralPath $installed) -and
                    ((Get-FileHash -LiteralPath $installed).Hash -ieq $runtime.exeSha256)) {
                    $env:KB2_DOSBOX = $installed
                }
            }
        }

        $jsDependencies = foreach ($package in 'WEB', 'TOOLS') {
            $installed = Join-Path $root "$package/node_modules"
            $link = Join-Path $checkout "$package/node_modules"
            $lockfile = "$package/package-lock.json"
            $lock = Get-Content (Join-Path $checkout $lockfile) -Raw | ConvertFrom-Json -AsHashtable
            $fflate = Join-Path $installed 'fflate/package.json'
            if ((Test-Path -LiteralPath $fflate) -and
                (Get-FileHash -LiteralPath (Join-Path $root $lockfile)).Hash -eq (Get-FileHash -LiteralPath (Join-Path $checkout $lockfile)).Hash -and
                (Get-Content -LiteralPath $fflate -Raw | ConvertFrom-Json).version -eq $lock.packages.'node_modules/fflate'.version) {
                $null = New-Item -ItemType Junction -Path $link -Target $installed
                $links += $link
            } else {
                Invoke-Checked npm @('--prefix', (Join-Path $checkout $package), 'ci', '--ignore-scripts', '--no-audit', '--no-fund') | Out-Host
            }
            Get-ChildItem -LiteralPath (Join-Path $link 'fflate') -Recurse -File | Sort-Object FullName | ForEach-Object {
                "$($_.Name):$((Get-FileHash -LiteralPath $_.FullName).Hash)"
            }
        }

        Push-Location $checkout
        try {
            Invoke-Checked $pwsh @('-NoProfile', '-File', 'TEST/RELEASE.ps1')
            foreach ($suite in 'DISCORD', 'WEB', 'SCENARIOS') { Invoke-Checked $node @("TEST/$suite.cjs") }
            $built = $false
            if (!$env:KB2_DOSBOX) {
                Invoke-Checked $pwsh @('-NoProfile', '-File', 'WEB/dev-game.ps1')
                $env:KB2_DOSBOX = Join-Path $checkout "WEB/.build/dev/dosbox/$($runtime.directory)/dosbox-x.exe"
                $built = $true
            }

            $pythonRuntime = & $python -B -c @'
from hashlib import sha256
from pathlib import Path
import sys
import capstone
import unicorn

print(sys.version)
binary = Path(sys._base_executable)
for file in [binary, *binary.parent.glob('python*.dll')]:
    print(file, sha256(file.read_bytes()).hexdigest())
for module in (capstone, unicorn):
    root = Path(module.__file__).parent
    for file in sorted(root.rglob('*')):
        if file.suffix in {'.py', '.dll', '.pyd', '.so', '.dylib'}:
            print(module.__name__, file.relative_to(root), sha256(file.read_bytes()).hexdigest())
'@
            if ($LASTEXITCODE -ne 0) { throw 'Unable to identify the Pascal test runtime.' }
            $runtimeKey = @($pythonRuntime) + @(
                $env:PATH, $env:PYTHONPATH, $env:PYTHONHOME, $PSVersionTable.GitCommitId,
                (Get-FileHash -LiteralPath $python).Hash, (Get-FileHash -LiteralPath $env:KB2_DOSBOX).Hash,
                (Get-FileHash -LiteralPath $PSCommandPath).Hash
            )
            $cache = (New-Item -ItemType Directory -Path (Join-Path $env:KB2_TEST_WORK 'ALL-CACHE') -Force).FullName
            # Fingerprint the complete test inputs before accepting a prior pass.
            $unitInputs = @('SRC', 'PASCAL', 'TEST/HOST', 'TEST/UNIT.ps1', 'TEST/EXPECT', 'TEST/SCENARIOS', 'TEST/UNREACHABLE.json')
            $unitResult = Join-Path $cache ((Get-TestKey $unitInputs $runtimeKey) + '.unit')
            # WORLD generates and verifies a campaign with a fixed seed.
            $campaign = Join-Path $env:KB2_TEST_WORK 'UNIT/SCENES/WORLD/DATA/L0.DAT'
            if ((Test-Path -LiteralPath $unitResult -PathType Leaf) -and (Test-Path -LiteralPath $campaign -PathType Leaf) -and
                (Get-Content -LiteralPath $unitResult -Raw) -ceq (Get-FileHash -LiteralPath $campaign).Hash) {
                Write-Host 'PASS Pascal unit tests and WORLD/COMBAT (cached)'
            } else {
                Invoke-Checked $pwsh @('-NoProfile', '-File', 'TEST/UNIT.ps1', '-Python', $python)
                Write-TestResult $unitResult (Get-FileHash -LiteralPath $campaign).Hash
            }

            $nativeInputs = @('BUILD.BAT', 'SRC', 'PASCAL', 'TEST/HOST/state.py', 'TEST/HOST/dos.ps1', 'TEST/SEMANTIC.cjs',
                'RELEASE/dosbox-x.json', 'TOOLS', 'WEB/dev-game.ps1', 'WEB/game-bundle.cjs', 'WEB/assets/classic.jsdos',
                'WEB/package.json', 'WEB/package-lock.json', 'WEB/runtime/vendor')
            $nativeRuntime = $runtimeKey + @((Get-FileHash -LiteralPath $node).Hash, $env:NODE_OPTIONS, $env:NODE_PATH,
                (Get-FileHash -LiteralPath $campaign).Hash) + $jsDependencies
            $nativeResult = Join-Path $cache ((Get-TestKey $nativeInputs $nativeRuntime) + '.native')
            if ((Test-Path -LiteralPath $nativeResult -PathType Leaf) -and (Get-Content -LiteralPath $nativeResult -Raw) -ceq 'PASS') {
                Write-Host 'PASS native snapshot scenarios (cached)'
            } else {
                if (!$built) { Invoke-Checked $pwsh @('-NoProfile', '-File', 'WEB/dev-game.ps1') }
                Invoke-Checked $node @('TEST/SEMANTIC.cjs', '--native', '--base', $campaign)
                Write-TestResult $nativeResult 'PASS'
            }
        } finally { Pop-Location }

        if ((Get-GitValue @('write-tree')) -ne $tree) { throw 'The Git index changed during testing. Run the checks again.' }
        Write-Host 'ALL GREEN'
    } finally {
        foreach ($link in $links) { [IO.Directory]::Delete($link) }
        if ((Split-Path (Resolve-Path -LiteralPath $workspace).Path) -ne (Resolve-Path -LiteralPath $gitDir).Path) {
            throw "Unexpected test directory: $workspace"
        }
        Remove-Item -LiteralPath $workspace -Recurse -Force
    }
} finally { Pop-Location }
