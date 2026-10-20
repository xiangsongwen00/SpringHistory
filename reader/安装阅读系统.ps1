$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw '创建Python环境失败' }
    }
    & '.venv\Scripts\python.exe' -m pip install -r requirements-reader.txt
    if ($LASTEXITCODE -ne 0) { throw '安装本机连接器失败' }
    npm.cmd ci --ignore-scripts --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw '安装阅读器依赖失败' }
    npm.cmd run build:reader
    if ($LASTEXITCODE -ne 0) { throw '构建阅读页面失败' }
    Write-Host '安装完成。运行“启动阅读系统.ps1”即可。'
} finally { Pop-Location }
