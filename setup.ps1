# Windows entry point: finds Python 3.8+ (offering to install it) and runs setup.py.
#   .\setup.cmd            (recommended: also works when PowerShell scripts are blocked)
#   .\setup.ps1 [setup.py options]

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Find-Python {
    foreach ($candidate in @(@("py", "-3"), @("python"), @("python3"))) {
        $exe = $candidate[0]
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $extra = @($candidate | Select-Object -Skip 1)
        # the Microsoft Store "python" stub exists on PATH but exits non-zero, so test that it really runs
        & $exe @extra -c "import sys; sys.exit(sys.version_info < (3, 8))" 2>$null
        if ($LASTEXITCODE -eq 0) { return , @($exe) + $extra }
    }
    return $null
}

$py = Find-Python
if (-not $py) {
    Write-Host "Python 3.8 or newer was not found."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        $answer = Read-Host "Install Python 3.12 now with winget? [Y/n]"
        if ($answer -eq "" -or $answer -match "^[Yy]") {
            winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
            $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
            $py = Find-Python
        }
    }
    if (-not $py) {
        Write-Host "Install Python from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run this again."
        exit 1
    }
}

$extra = @($py | Select-Object -Skip 1)
& $py[0] @extra setup.py @args
exit $LASTEXITCODE
