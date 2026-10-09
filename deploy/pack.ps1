<#
.SYNOPSIS
  在本机（Windows）打包部署产物：后端源码 + deploy/ + 前端 dist，可选 scp 上传。

.DESCRIPTION
  服务器上不需要装 Node —— 前端在本机构建好，直接把 dist 打包带过去。
  打包前会清掉 __pycache__ / *.pyc / 日志 / 本机 sqlite，避免把开发垃圾带上线。

.EXAMPLE
  .\deploy\pack.ps1                        # 只打包，产物在仓库根目录
  .\deploy\pack.ps1 -Upload root@1.2.3.4   # 打包后 scp 到服务器 /opt
  .\deploy\pack.ps1 -NoBuild               # 跳过前端构建，沿用现有 dist
#>
param(
    [string]$Upload = '',
    [switch]$NoBuild,
    [string]$RemoteDir = '/opt'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Green }

# ---------------------------------------------------------------- 1. 前端构建
if ($NoBuild) {
    Write-Step '跳过前端构建（-NoBuild）'
} else {
    Write-Step '构建前端（npm run build）'
    Push-Location (Join-Path $root 'frontend')
    try { npm run build } finally { Pop-Location }
}

$distIndex = Join-Path $root 'frontend\dist\index.html'
if (-not (Test-Path $distIndex)) {
    throw "缺少 $distIndex —— 前端构建失败，先修好再打包"
}
if (-not (Test-Path (Join-Path $root 'frontend\dist\assets'))) {
    throw 'frontend\dist\assets 不存在，构建不完整（可能上次 build 被中断）'
}

# ---------------------------------------------------------------- 2. 清理本地垃圾
Write-Step '清理 __pycache__ / pyc / 日志 / 本机 sqlite'
Get-ChildItem -Path $root -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $root -Recurse -File -Include '*.pyc', '*.log', '*.log.*' -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $root 'backend\db.sqlite3') -Force -ErrorAction SilentlyContinue

# 日志目录整个不打包：服务器上由 compose 的 logs 卷挂载，带上去还会因文件被占用而打包失败
$logsDir = Join-Path $root 'backend\logs'
Get-ChildItem -Path $logsDir -File -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue

# ---------------------------------------------------------------- 3. 打包
$outName = 'family-ledger-deploy.tar.gz'
$out = Join-Path $root $outName
Write-Step "打包 backend + deploy + frontend/dist -> $outName"
if (Test-Path $out) { Remove-Item $out -Force }

Push-Location $root
try {
    # 排除 backend/.env：那是本机的开发配置（含本机数据库密码），绝不能带到生产服务器上
    tar --exclude='backend/logs' --exclude='*/logs/*' --exclude='backend/media' `
        --exclude='backend/.env' -czf $outName backend deploy frontend/dist
    if ($LASTEXITCODE -ne 0) {
        throw 'tar 打包失败：多半是 backend/logs 里还有文件被运行中的 Django 占着，停掉本地服务再试；或加 -NoBuild 重试'
    }
} finally { Pop-Location }

$size = [math]::Round((Get-Item $out).Length / 1MB, 2)
Write-Host "[ok] 打包完成：$out ($size MB)" -ForegroundColor Green

# ---------------------------------------------------------------- 4. 上传
if ($Upload) {
    Write-Step "上传到 ${Upload}:${RemoteDir}"
    scp $out "${Upload}:${RemoteDir}/"
    if ($LASTEXITCODE -ne 0) { throw 'scp 上传失败' }
    Write-Host "`n接下来在服务器上执行：" -ForegroundColor Green
    Write-Host "  ssh $Upload" -ForegroundColor Cyan
    Write-Host "  mkdir -p /opt/family-ledger" -ForegroundColor Cyan
    Write-Host "  tar -xzf $RemoteDir/$outName -C /opt/family-ledger" -ForegroundColor Cyan
    Write-Host "  bash /opt/family-ledger/deploy/install.sh" -ForegroundColor Cyan
} else {
    Write-Host "`n手动上传到服务器后执行：" -ForegroundColor Green
    Write-Host "  mkdir -p /opt/family-ledger" -ForegroundColor Cyan
    Write-Host "  tar -xzf $outName -C /opt/family-ledger" -ForegroundColor Cyan
    Write-Host "  bash /opt/family-ledger/deploy/install.sh" -ForegroundColor Cyan
}
