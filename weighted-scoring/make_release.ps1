<#
.SYNOPSIS
  组装 weighted-scoring 发布 zip 包（脚手架）。

.DESCRIPTION
  将最终发布 zip 组装到 release/ 目录。
  最终 zip 应含：
    - katago.exe            （加权改造引擎）
    - OpenCL.dll、z.dll     （OpenCL 运行时依赖）
    - weight_table_final.txt（最终权重表）
    - default_gtp.cfg       （引擎配置，随包分发版本）
    - gtp_override.cfg      （方向覆盖配置，含 komi）
    - 加权点目围棋规则.md    （规则文档，取 Agent 3 交付）
    - README.md             （发布说明）
    - weights/28b.bin.gz    （不附，README 给下载链接）

  注意：
    - 权重文件 28b.bin.gz 太大，不入 zip；README 给下载链接。
    - kata-src/、dist_opencl/ 均 .gitignore，不入库（但入 zip）。
    - 本脚本对缺失/未就绪的产物会给出明确告警而非静默跳过。

.PARAMETER DistDir
  引擎产物目录，默认指向本方向 dist_opencl/。

.PARAMETER OutFile
  输出 zip 路径，默认 releases/weighted-scoring-v<version>.zip。

.EXAMPLE
  .\make_release.ps1
  .\make_release.ps1 -Version 1.0.1
#>
[CmdletBinding()]
param(
    [string]$Version = "1.0.0",
    [string]$DistDir = "E:\小工具\new_go\weighted-scoring\dist_opencl",
    [string]$OutFile = ""
)
$ErrorActionPreference = 'Stop'

$Root = "E:\小工具\new_go\weighted-scoring"
$ReleaseDir = Join-Path $Root "releases"
$BuildDir  = Join-Path $ReleaseDir "build"
if (-not $OutFile) { $OutFile = Join-Path $ReleaseDir "weighted-scoring-v$Version.zip" }

function Assert-File {
    param([string]$Path, [string]$Label, [switch]$Blocker)
    if (Test-Path -LiteralPath $Path) { Write-Host "  [ok ] $Label -> $Path" -ForegroundColor Green }
    else {
        if ($Blocker) {
            Write-Host "  [BUG] $Label 缺失: $Path （发布仍阻塞）" -ForegroundColor Red
            $script:blocked = $true
        } else {
            Write-Host "  [WARN] $Label 缺失: $Path （将用占位/跳过，见 README）" -ForegroundColor Yellow
        }
    }
}

Write-Host "== 组装发布包 v$Version ==" -ForegroundColor Cyan
$script:blocked = $false

# === 清理并准备 staging 目录 ===
if (Test-Path -LiteralPath $BuildDir) { Remove-Item -LiteralPath $BuildDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null

# === 引擎 + 运行时（发布 z 包核心）===
Assert-File (Join-Path $DistDir "katago.exe")   "katago.exe"   -Blocker
Assert-File (Join-Path $DistDir "OpenCL.dll")   "OpenCL.dll"   -Blocker
Assert-File (Join-Path $DistDir "z.dll")        "z.dll"        -Blocker
Copy-Item (Join-Path $DistDir "*.exe")  $BuildDir -Force -ErrorAction SilentlyContinue
Copy-Item (Join-Path $DistDir "*.dll")  $BuildDir -Force -ErrorAction SilentlyContinue

# === 权重表 ===
Assert-File (Join-Path $Root "weight_table_final.txt") "weight_table_final.txt"
Copy-Item (Join-Path $Root "weight_table_final.txt") $BuildDir -Force -ErrorAction SilentlyContinue

# === GTP 配置 ===
Assert-File (Join-Path $Root "gtp_override.cfg") "gtp_override.cfg"
Copy-Item (Join-Path $Root "gtp_override.cfg") $BuildDir -Force -ErrorAction SilentlyContinue
# default_gtp.cfg 由外部 KataGo 安装提供；随包给一份模板以防缺
$defaultCfg = "E:\2026-01-07-win64-KataGo\katago_configs\default_gtp.cfg"
if (Test-Path -LiteralPath $defaultCfg) { Copy-Item $defaultCfg $BuildDir -Force }
else {
    Write-Host "  [WARN] default_gtp.cfg 未找到: $defaultCfg，将从 gtp.cfg 复制占位" -ForegroundColor Yellow
    Copy-Item (Join-Path $Root "gtp.cfg") (Join-Path $BuildDir "default_gtp.cfg") -Force -ErrorAction SilentlyContinue
}

# === 规则文档 ===
$rules = Join-Path $Root "加权点目围棋规则.md"
Assert-File $rules "加权点目围棋规则.md" -Blocker
if (Test-Path -LiteralPath $rules) { Copy-Item $rules $BuildDir -Force }

# === README ===
Assert-File (Join-Path $Root "README.md") "README.md (发布说明)"
if (Test-Path -LiteralPath (Join-Path $Root "README.md")) { Copy-Item (Join-Path $Root "README.md") $BuildDir -Force }

# === 核对发布包包含项 ===
Write-Host "`n== 发布包内容清单 ==" -ForegroundColor Cyan
$needed = 'katago.exe','OpenCL.dll','z.dll','weight_table_final.txt','default_gtp.cfg','gtp_override.cfg','加权点目围棋规则.md','README.md'
foreach ($f in $needed) {
    $p = Join-Path $BuildDir $f
    if (Test-Path -LiteralPath $p) { Write-Host "  [x] $f" -ForegroundColor Green }
    else { Write-Host "  [ ] $f" -ForegroundColor Red; $script:blocked = $true }
}
Write-Host "  [i] weights/28b.bin.gz 不附（太大），README 给下载链接"

if ($script:blocked) {
    Write-Host "`n== 🚫 BLOCKED：仍有阻塞项未就绪，未生成 zip ==" -ForegroundColor Red
    exit 1
}

# === 打包 ===
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
if (Test-Path -LiteralPath $OutFile) { Remove-Item -LiteralPath $OutFile -Force }
Compress-Archive -Path (Join-Path $BuildDir "*") -DestinationPath $OutFile
Write-Host "`n== 完成: $OutFile ==" -ForegroundColor Green