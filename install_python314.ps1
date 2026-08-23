$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw '未找到 Python Launcher。请先安装 64 位 Python 3.14，并确认 py -3.14 可用。'
}

$version = (& py -3.14 --version 2>&1).ToString()
if ($version -notmatch 'Python 3\.14\.') {
    throw "需要 Python 3.14，当前 py -3.14 输出为: $version"
}

if (Test-Path '.venv') {
    Write-Host '已有 .venv，保留现有环境；如需全新验证请先删除 .venv。'
} else {
    & py -3.14 -m venv .venv
}

$Python = Join-Path $Root '.venv\Scripts\python.exe'
& $Python -m pip install --upgrade pip setuptools
& $Python -m pip install -e .
& $Python -m pip check
& $Python verify_migration.py
Write-Host '运行环境安装完成。需要离线回归时再执行：'
Write-Host '.\.venv\Scripts\python.exe -m pip install -e ".[test]"'
Write-Host '.\.venv\Scripts\python.exe -m pytest -q'
