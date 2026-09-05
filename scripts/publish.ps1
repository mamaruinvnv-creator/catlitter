# publish.ps1 — 一键把 litter-scoop 发布到 GitHub（Windows PowerShell）
# 用法:
#   .\scripts\publish.ps1 -RepoName litter-scoop -Visibility public
# 首次使用若提示未登录, 脚本会引导你执行: gh auth login
param(
    [string]$RepoName = "litter-scoop",
    [ValidateSet("public", "private")]
    [string]$Visibility = "public",
    [string]$Description = "猫砂模型冗余代码清理器: auto-detect project, scoop redundant code into a restorable garbage bag"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Assert-Command($name) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        Write-Error "未找到 $name，请先安装后重试。"
        exit 1
    }
}

Assert-Command "git"
Assert-Command "gh"

# 1. GitHub 登录状态
$auth = gh auth status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "尚未登录 GitHub，正在启动登录流程（浏览器授权，按提示操作）..." -ForegroundColor Yellow
    gh auth login
    if ($LASTEXITCODE -ne 0) { Write-Error "GitHub 登录失败，已中止。"; exit 1 }
}

# 2. 初始化本地仓库
if (-not (Test-Path .git)) {
    git init -b main
}
git add -A
$status = git status --porcelain
if ($status) {
    git commit -m "feat: initial release of litter-scoop (cat-litter redundant-code cleaner)"
} else {
    Write-Host "工作区无未提交改动。"
}

# 3. 创建远端仓库并推送（已存在则只推送）
$exists = gh repo view $RepoName 2>$null
if ($LASTEXITCODE -ne 0) {
    gh repo create $RepoName --$Visibility --source=. --remote=origin --push --description $Description
} else {
    git push -u origin main
}

Write-Host "完成: $((gh repo view $RepoName --json url -q .url))" -ForegroundColor Green
