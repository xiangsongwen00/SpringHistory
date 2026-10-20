$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw '请先运行安装阅读系统.ps1。' }
& $pythonPath (Join-Path $PSScriptRoot 'launch_reader.py')
if ($LASTEXITCODE -ne 0) { throw '阅读室启动失败，请查看提示或reader-service.log。' }