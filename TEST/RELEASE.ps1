#Requires -Version 7.2
$ErrorActionPreference = 'Stop'
$repository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $repository 'RELEASE/changelog.ps1')
$folder = Join-Path ([IO.Path]::GetTempPath()) ('kb2-changelog-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $folder | Out-Null
$fixture = Join-Path $folder 'CHANGELOG.md'
function Check-Changes([string]$Text, [string]$Tag, [string]$Expected, [string]$ErrorFragment = '') {
    [IO.File]::WriteAllText($fixture, $Text, [Text.UTF8Encoding]::new($false))
    $actual = $null
    $failure = $null
    try { $actual = Get-ReleaseChanges -Path $fixture -Tag $Tag } catch { $failure = $_.Exception.Message }
    if ($ErrorFragment) {
        if (-not $failure -or -not $failure.Contains($ErrorFragment)) { throw "Expected '$ErrorFragment', got '$failure'." }
    } elseif ($failure -or $actual -cne $Expected) {
        throw "Unexpected extraction for ${Tag}: '$actual'; $failure"
    }
}
Check-Changes @'
# История изменений
## 2.0.0 - 2026-11-12
- Новая версия.
## 1.2.3 - 2026-11-11

- Исправлена ошибка.

### Баланс

Текст с **Markdown**.

## 1.0.0 - 2026-11-01
- Старые записи.
'@ 'v1.2.3' "- Исправлена ошибка.`n`n### Баланс`n`nТекст с **Markdown**."
Check-Changes "## 1.0.0 - 2026-11-11`r`n`r`n- Последняя секция.`r`n" 'V1.0.0' '- Последняя секция.'
Check-Changes "## 1.2.3-rc.1 - 2026-11-11`n- RC." 'v1.2.3-rc.1' '- RC.'
Check-Changes "## 1 - 2026-11-11`n- Версия." 'v1' '- Версия.'
Check-Changes "## 1.2 - 2026-11-11`n- Версия." 'v1.2' '- Версия.'
Check-Changes "## 1.0.0 - 2026-11-11`n- Старое." 'v2.0.0' '' 'missing section'
Check-Changes "## 1.0.0 - 2026-11-11`n- A.`n## 1.0.0 - 2026-11-12`n- B." 'v1.0.0' '' 'more than once'
Check-Changes "## 1.0.0 - 2026-11-11`n`n## 0.9.0 - 2026-11-01`n- Старое." 'v1.0.0' '' 'no release notes'
Check-Changes "## 1.0.0 - 11.11.2026`n- A." 'v1.0.0' '' 'missing section'
Check-Changes @'
## 1.0.0 - 2026-11-11
Пример:
```markdown
## 1.0.0 - 2026-11-11
```
### Детали
- Запись.
## 0.9.0 - 2026-11-01
- Старое.
'@ 'v1.0.0' "Пример:`n``````markdown`n## 1.0.0 - 2026-11-11`n```````n### Детали`n- Запись."

# Test the actual entry point: bad changelog must abort before any workspace exists.
$work = Join-Path $folder 'must-not-exist'
$output = Join-Path $folder 'must-not-exist-either'
$failed = $false
try {
    & (Join-Path $repository 'RELEASE/portable.ps1') -Tag 'v999999.999999.999999' -WorkDirectory $work -OutputDirectory $output
} catch {
    if (-not $_.Exception.Message.Contains('missing section')) { throw }
    $failed = $true
}
if (-not $failed -or (Test-Path -LiteralPath $work) -or (Test-Path -LiteralPath $output)) {
    throw 'Invalid changelog did not abort before build preparation.'
}
Write-Host 'PASS: 10 extraction cases; invalid release aborts before downloads and build preparation.'
