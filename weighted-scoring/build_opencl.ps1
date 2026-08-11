<#
.SYNOPSIS
  编译 KataGo OpenCL 后端 (MSVC + vcpkg) — weighted-scoring 方向

.DESCRIPTION
  依赖（须事先就绪）:
    - VS 2022 BuildTools: MSVC 19.x + CMake + Windows SDK
    - vcpkg @ E:\vcpkg, 已安装 opencl:x64-windows 与 zlib:x64-windows
  产出: dist_opencl\katago.exe (+ OpenCL.dll, z.dll)

.PARAMETER Clean
  重新清理 build 目录后再配置（默认增量构建）。

.EXAMPLE
  .\build_opencl.ps1
  .\build_opencl.ps1 -Clean
#>
[CmdletBinding()]
param(
    [switch]$Clean
)
$ErrorActionPreference = 'Stop'

# === 路径配置 ===
$VcVars    = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
$VcpkgRoot = "E:\vcpkg"
$SrcDir    = "E:\小工具\new_go\weighted-scoring\katago-src\cpp"
$BuildDir  = "E:\katabuild_ws"
$DistDir   = "E:\小工具\new_go\weighted-scoring\dist_opencl"
$Proxy     = "http://127.0.0.1:15715"

# vcpkg/git 子进程联网需要代理（编译本身不联网，但 configure 会调 git 取 revision）
$env:HTTP_PROXY  = $Proxy
$env:HTTPS_PROXY = $Proxy

function Invoke-CmdChecked {
    param([scriptblock]$Block, [string]$Stage)
    & $Block
    if ($LASTEXITCODE -ne 0) { throw "$Stage 失败 (exit $LASTEXITCODE)" }
}

# === [1/4] 注入 MSVC 环境 ===
Write-Host "== [1/4] 注入 MSVC 环境 ==" -ForegroundColor Cyan
if (-not (Test-Path $VcVars)) { throw "vcvars64.bat 未找到: $VcVars" }
cmd /c "`"$VcVars`" >nul 2>&1 && set" 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
    }
}
if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) { throw "cl.exe 不可用，vcvars 注入失败" }
if (-not (Get-Command cmake.exe -ErrorAction SilentlyContinue)) { throw "cmake 不可用，vcvars 注入失败" }
Write-Host ("  cl   : " + ((cl 2>&1 | Select-String 'Microsoft \(R\) C/C\+\+').Line.Trim()))
Write-Host ("  cmake: " + (cmake --version | Select-Object -First 1).Trim())

# === [2/4] CMake Configure ===
Write-Host "== [2/4] CMake Configure ==" -ForegroundColor Cyan
if (-not (Test-Path $SrcDir)) { throw "KataGo 源码目录未找到: $SrcDir" }
if (-not (Test-Path "$VcpkgRoot/scripts/buildsystems/vcpkg.cmake")) { throw "vcpkg toolchain 未找到" }
if ($Clean -and (Test-Path $BuildDir)) { Remove-Item -LiteralPath $BuildDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null

Push-Location $BuildDir
try {
    Invoke-CmdChecked {
        cmake -G "Visual Studio 17 2022" -A x64 `
            -DCMAKE_TOOLCHAIN_FILE="$VcpkgRoot/scripts/buildsystems/vcpkg.cmake" `
            -DVCPKG_TARGET_TRIPLET=x64-windows `
            -DUSE_BACKEND=OPENCL `
            -DBUILD_DISTRIBUTED=0 `
            "$SrcDir"
    } "CMake configure"

    # === [3/4] CMake Build ===
    Write-Host "== [3/4] CMake Build (Release) ==" -ForegroundColor Cyan
    Invoke-CmdChecked {
        cmake --build . --config Release -- /m
    } "CMake build"
}
finally { Pop-Location }

# === [4/4] 收集产物 ===
Write-Host "== [4/4] 收集产物 ==" -ForegroundColor Cyan
$exe = "$BuildDir\Release\katago.exe"
if (-not (Test-Path $exe)) { throw "编译产物未找到: $exe" }
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
Copy-Item $exe $DistDir -Force
Copy-Item "$VcpkgRoot\installed\x64-windows\bin\OpenCL.dll" $DistDir -Force
Copy-Item "$VcpkgRoot\installed\x64-windows\bin\z.dll" $DistDir -Force

Write-Host "完成: $DistDir\katago.exe" -ForegroundColor Green
& "$DistDir\katago.exe" version
