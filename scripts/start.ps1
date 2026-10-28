param([int]$Port = 8080)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path .venv/Scripts/python.exe)) {
    throw 'Install first: py -3 -m venv .venv; .venv/Scripts/python.exe -m pip install -e ".[dev]"'
}
& .venv/Scripts/python.exe -m depgraph serve --port $Port
