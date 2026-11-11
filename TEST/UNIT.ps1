param(
    [string]$Python='python',
    [string[]]$Module=@(),
    [switch]$RequireComplete
)
$ErrorActionPreference='Stop'
$kb2PreviousBytecode=$env:PYTHONDONTWRITEBYTECODE
$env:PYTHONDONTWRITEBYTECODE='1'
$kb2Repository=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Push-Location $kb2Repository
try {
    & $Python TEST/HOST/prepare.py
    if ($LASTEXITCODE -ne 0) {throw 'Unit host compilation failed'}
    & $Python -m unittest discover -s TEST/HOST -p 'test_*.py'
    if ($LASTEXITCODE -ne 0) {throw 'Unit harness checks failed'}
    $kb2Arguments=@('TEST/HOST/run.py')
    if ($Module.Count) {$kb2Arguments+=@('--module');$kb2Arguments+=$Module}
    if ($RequireComplete) {$kb2Arguments+='--require-complete'}
    & $Python @kb2Arguments
    if ($LASTEXITCODE -ne 0) {throw 'Unit tests failed'}
    if (-not $Module.Count) {
        & $Python TEST/HOST/scenarios.py
        if ($LASTEXITCODE -ne 0) {throw 'Composed scenarios failed'}
    }
    exit $LASTEXITCODE
} finally {
    Pop-Location
    $env:PYTHONDONTWRITEBYTECODE=$kb2PreviousBytecode
}
