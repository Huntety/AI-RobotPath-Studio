$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$robotPython = Join-Path $PSScriptRoot '..\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $robotPython)) {
    throw 'Python/test shared environment not found. See README.md.'
}
$robotTemp = Join-Path $PSScriptRoot '.cache\tmp'
New-Item -ItemType Directory -Force -Path $robotTemp | Out-Null
$env:TEMP = $robotTemp
$env:TMP = $robotTemp
& $robotPython -m PyInstaller --noconfirm RobotStudioAI.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
Write-Host 'Run dist\RobotStudioAI\RobotStudioAI.exe. Keep its _internal directory beside it.'
