[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$candidates = [System.Collections.Generic.List[string]]::new()

function Add-Candidate {
    param([string]$Path)

    $value = $Path.Trim()
    if (-not $value) {
        return
    }
    if (-not $candidates.Contains($value)) {
        $candidates.Add($value)
    }
}

if ($env:GRIT_PYTHON) {
    Add-Candidate $env:GRIT_PYTHON
}
Add-Candidate (Join-Path $repoRoot ".venv\Scripts\python.exe")

Get-Command python -All -ErrorAction SilentlyContinue |
    ForEach-Object { Add-Candidate $_.Source }
where.exe python 2>$null |
    ForEach-Object { Add-Candidate $_ }

foreach ($candidate in $candidates) {
    if ([System.IO.Path]::IsPathRooted($candidate) -and -not (Test-Path -LiteralPath $candidate)) {
        continue
    }
    try {
        $output = @(
            & $candidate -c "import fastapi, uvicorn, importlib.util, sys; assert importlib.util.find_spec('futu') is not None; print(sys.executable)" 2>$null
        )
        if ($LASTEXITCODE -ne 0 -or $output.Count -eq 0) {
            continue
        }
        $resolved = [string]$output[-1]
        if (Test-Path -LiteralPath $resolved) {
            Write-Output $resolved
            exit 0
        }
    }
    catch {
        continue
    }
}

Write-Error "[Grit] No Python runtime with fastapi, uvicorn, and futu-api was found. Install the project dependencies or set GRIT_PYTHON."
exit 1
