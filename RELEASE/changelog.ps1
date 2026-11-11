function Get-ReleaseChanges {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Tag
    )
    $version = $Tag -creplace '^[vV]', ''
    $lines = [IO.File]::ReadAllLines($Path)
    $sections = @()
    $current = $null
    $fence = $null
    for ($i = 0; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]
        # Markdown headings inside fenced examples are part of the release text.
        if ($line -match '^ {0,3}(`{3,}|~{3,})') {
            $marker = $Matches[1]
            if ($null -eq $fence) {
                $fence = $marker
            } elseif ($marker[0] -eq $fence[0] -and $marker.Length -ge $fence.Length -and
                      $line.Trim() -eq $marker) {
                $fence = $null
            }
            continue
        }
        if ($null -ne $fence -or $line -notmatch '^ {0,3}##(?:\s+|$)') { continue }
        if ($null -ne $current) { $current.End = $i }
        $current = $null
        if ($line -match '^ {0,3}##\s+(\S+)\s+-\s+\d{4}-\d{2}-\d{2}\s*$' -and
            $Matches[1] -ceq $version) {
            $current = @{ Start = $i + 1; End = $lines.Count }
            $sections += $current
        }
    }
    if ($sections.Count -eq 0) {
        throw "CHANGELOG.md: missing section '## $version - YYYY-MM-DD' for tag $Tag."
    }
    if ($sections.Count -ne 1) {
        throw "CHANGELOG.md: version $version occurs more than once."
    }
    $section = $sections[0]
    $body = if ($section.End -gt $section.Start) {
        ($lines[$section.Start..($section.End - 1)] -join "`n").Trim()
    } else { '' }
    if (-not $body) { throw "CHANGELOG.md: version $version has no release notes." }
    return $body
}
