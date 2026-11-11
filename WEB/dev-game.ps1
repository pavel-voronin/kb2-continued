#Requires -Version 7.2
$ErrorActionPreference='Stop'
$repository=Split-Path $PSScriptRoot
$cache=Join-Path $PSScriptRoot '.build/dev'
$build=Join-Path $cache 'build'
$source=Join-Path $build 'SRC'
New-Item -ItemType Directory -Force $source,(Join-Path $build 'PASCAL') | Out-Null

$dosbox=$env:KB2_DOSBOX
if (-not $dosbox) {
    $command=Get-Command dosbox-x -ErrorAction SilentlyContinue
    if ($command) { $dosbox=$command.Source }
}
if (-not $dosbox) {
    $runtime=Get-Content (Join-Path $repository 'RELEASE/dosbox-x.json') -Raw | ConvertFrom-Json
    $tools=Join-Path $cache 'dosbox'
    $dosbox=Join-Path $tools "$($runtime.directory)/dosbox-x.exe"
    if (-not (Test-Path -LiteralPath $dosbox)) {
        Write-Host 'Downloading the pinned DOSBox-X compiler host (once)...'
        $archive=Join-Path $cache 'dosbox.zip'
        Invoke-WebRequest "https://github.com/joncampbell123/dosbox-x/releases/download/$($runtime.tag)/$($runtime.asset)" -OutFile $archive
        if ((Get-FileHash $archive -Algorithm SHA256).Hash -ine $runtime.sha256) { throw 'DOSBox-X archive checksum mismatch' }
        Expand-Archive -LiteralPath $archive -DestinationPath $tools -Force
    }
    if ((Get-FileHash $dosbox -Algorithm SHA256).Hash -ine $runtime.exeSha256) { throw 'DOSBox-X executable checksum mismatch' }
}

# Copy bytes unchanged: the DOS sources stay in CP866. Compile away from SRC/.
Get-ChildItem -LiteralPath $source -File | Remove-Item
Get-ChildItem (Join-Path $repository 'SRC') -File |
    Where-Object { $_.Extension -in '.PAS','.INC' } | Copy-Item -Destination $source
foreach ($folder in 'ART','DOC','DIST') {
    $target=Join-Path $source $folder
    if (Test-Path $target) {
        $resolved=[IO.Path]::GetFullPath($target)
        if (-not $resolved.StartsWith([IO.Path]::GetFullPath($source)+[IO.Path]::DirectorySeparatorChar)) { throw 'Unexpected build directory' }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
    if ($folder -ne 'DIST') { Copy-Item (Join-Path $repository "SRC/$folder") $source -Recurse }
}
Copy-Item (Join-Path $repository 'SRC/PACK.LST') $source
foreach ($name in 'TPC.EXE','TURBO.TPL') { Copy-Item (Join-Path $repository "PASCAL/$name") (Join-Path $build 'PASCAL') }
Copy-Item (Join-Path $repository 'BUILD.BAT') $build
& (Join-Path $repository 'TEST/HOST/dos.ps1') -Commands 'call BUILD.BAT' -Work $build -DosBox $dosbox -Core normal -TimeoutSeconds 120
if (-not (Test-Path (Join-Path $source 'BUILD.OK'))) {
    foreach ($log in 'GAME.LOG','RSPACK.LOG','PACK.LOG') {
        $file=Join-Path $source $log
        if (Test-Path $file) { Write-Host ([Text.Encoding]::GetEncoding(866).GetString([IO.File]::ReadAllBytes($file))) }
    }
    throw 'Game compilation failed; see compiler output above.'
}
Write-Host 'Game compiled from current SRC/.'
