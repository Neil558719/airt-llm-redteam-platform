$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Airt = Join-Path $Root '.venv\Scripts\airt.exe'

if (-not (Test-Path $Python)) {
    throw '未找到 .venv，请先运行 install_python314.ps1。'
}

# 只清理当前进程的测试凭据，避免继承用户环境污染离线测试。
$env:DIFY_API_KEY = $null
$env:DIFY_AGENT_API_KEY = $null
$env:JUDGE_API_KEY = $null

& $Python --version
& $Python -m pip check
& $Python verify_migration.py
& $Airt --help
& $Airt list --cases cases
& $Airt list --cases cases/dify-agent.yaml

Write-Host '正在运行完整离线回归；如测试依赖尚未安装，先执行 pip install -e ".[test]"。'
& $Python -m pytest -q
Write-Host 'Python 3.14 离线验收通过。实网 Dify 测试需按 DIFY_MIGRATION_CHECKLIST.md 单独授权和配置凭据。'
