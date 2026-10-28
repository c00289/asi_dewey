# Regenerate the Excel workbook from the database.
# Both paths come from dewey.toml (or ASI_DEWEY_DB / ASI_DEWEY_WORKBOOK). Pass --out <file>
# to write somewhere else, for example:  .\export-excel.ps1 --out "C:\temp\dewey.xlsx"
# If the workbook is open in Excel, the export writes a timestamped sibling and says so.
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$exe = Join-Path $PSScriptRoot ".venv\Scripts\asi-dewey.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    Write-Error "Virtual environment not found. Run 'uv sync' in $PSScriptRoot first."
}

$json = & $exe export excel @args
if ($LASTEXITCODE -ne 0) {
    $json
    exit $LASTEXITCODE
}

$result = $json | ConvertFrom-Json
Write-Host "Workbook written to: $($result.data.path)"
foreach ($w in $result.warnings) { Write-Warning $w }
exit 0
