# Agent 1 — INFRA：构建环境工程师

**角色：** 构建环境工程师 INFRA
**关联计划书：** `新规则实现计划书.md` §7.1（WP1）
**关联规则：** `新规则.md`

---

## 更新日志

> 每次完成任务后在此追加一节。遇到阻塞立即在文档顶部标注 `🚫 BLOCKED`。

| 日期 | 状态 | 任务 | 摘要 |
|------|------|------|------|
| 2026-08-08 | ⚠️ 进行中 | WP1 | 已拉取 KataGo 源码，工具链安装待完成 |
| 2026-08-08 | ✅ 完成 | WP1 | 全部 5 项任务完成，已编译出 OpenCL 后端 `katago.exe` 并通过 benchmark 验证 |

---

## 1 交付物

| 文件 | 说明 |
|------|------|
| `katago-src/` | KataGo 源码（shallow clone，v1.16.4 tag） |
| `build_opencl.ps1` | OpenCL 后端编译脚本（UTF-8 BOM，PS 5.x/7 兼容） |
| `dist_opencl/katago.exe` | 编译产物（OpenCL 后端，4.46 MB） |
| `dist_opencl/OpenCL.dll` | 运行时依赖（Khronos ICD Loader） |
| `dist_opencl/z.dll` | 运行时依赖（zlib） |
| `dist_opencl/KataGoData/opencltuning/` | 首次 OpenCL autotuning 缓存（下次启动免重调） |

工具链（一次性，位于工作目录外）：

| 路径 | 说明 |
|------|------|
| `C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools` | VS 2022 BuildTools（MSVC + CMake + Win SDK） |
| `E:\vcpkg\` | vcpkg + 已装 `opencl:x64-windows` / `zlib:x64-windows` |
| `E:\katabuild\` | CMake 构建中间目录（英文路径） |

---

## 2 进度跟踪

### 2.1 任务清单（WP1）

- [x] 确认源码版本为 v1.16.4
- [x] 安装 VS Build Tools（MSVC x64 + Windows SDK）
- [x] 安装 CMake
- [x] 配置 OpenCL 头文件/库
- [x] 建立编译脚本 `build_opencl.ps1`
- [x] 编译产出 `katago.exe`（OpenCL 后端）
- [x] benchmark 验证（用现有权重）

### 2.2 验收标准

- [x] `cl /?` 可用 → MSVC 19.44.35228
- [x] `cmake --version` 可用 → 3.31.6-msvc6
- [x] `katago.exe benchmark` 正常运行 → 18b 权重，RTX 5060 OpenCL，20 线程 429 visits/s

### 2.3 benchmark 结果（2026-08-08）

- 模型：`E:\2026-01-07-win64-KataGo\weights\18b.bin.gz`（b18c384nbt, mv14）
- 配置：`katago_configs\default_gtp.cfg`，800 visits，19x19
- OpenCL 设备：自动选中 `NVIDIA GeForce RTX 5060 Laptop GPU`（score 11000300，胜过 Intel 集显）
- FP16：Storage true / TensorCores true / TensorCoresFor1x1 false（见 §5）
- 各线程数 visits/s：5→270 / 10→365 / 12→387 / 16→404 / **20→429（推荐）** / 24→430
- 建议：把 `numSearchThreads` 从默认 6 调到 20

---

## 3 环境信息

| 项 | 值 |
|----|-----|
| OS | Windows 11 (10.0.26200) |
| GPU | NVIDIA RTX 5060 Laptop (Blackwell, 4GB) + Intel RaptorLake-S 集显 |
| MSVC | 19.44.35228（VS 2022 BuildTools, `vcvars64.bat`） |
| CMake | 3.31.6-msvc6（随 BuildTools 安装） |
| Windows SDK | 10.0.26100.0 |
| vcpkg | 2026-07-27 @ `E:\vcpkg\`（装了 opencl@2024.10.24 + zlib@1.3.2） |
| OpenCL 运行时 | `C:\Windows\System32\OpenCL.dll`（NVIDIA 驱动 13.3.80 自带） |
| 代理 | `http://127.0.0.1:15715`（github/vcpkg 下载需要；编译本身不联网） |
| 现有 KataGo 包 | `E:\2026-01-07-win64-KataGo\` |
| 现有权重 | `18b.bin.gz` / `28b.bin.gz` / `humansl.bin.gz` / `model.bin` |
| 现有配置 | `E:\2026-01-07-win64-KataGo\katago_configs\default_gtp.cfg` |
| 工作目录 | `E:\小工具\new_go\ban-selection\` |
| 源码目录 | `E:\小工具\new_go\ban-selection\katago-src\` |
| 构建目录 | `E:\katabuild\`（英文路径，规避中文路径坑） |
| 产物目录 | `E:\小工具\new_go\ban-selection\dist_opencl\` |

---

## 4 对其他 Agent 的接口约定

### 对 ENGINE

INFRA 完成后，ENGINE 可在 `katago-src/` 上进行源码改造并使用 `build_opencl.ps1` 编译验证。

**重建命令（在 PowerShell 中）：**
```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File "E:\小工具\new_go\ban-selection\build_opencl.ps1"
# 干净重建：
pwsh -NoProfile -ExecutionPolicy Bypass -File "E:\小工具\new_go\ban-selection\build_opencl.ps1" -Clean
```
- 脚本会自动：注入 vcvars64 → CMake configure（vcpkg toolchain）→ MSBuild Release → 收集产物到 `dist_opencl\`
- 改源码后直接重跑脚本即可，增量构建很快
- 产物 `dist_opencl\katago.exe` + `OpenCL.dll` + `z.dll` 须放在同一目录运行

**依赖精简说明（供 ENGINE 参考改 CMakeLists 时用）：**
- ZLIB 必需（CMakeLists.txt:455，缺失则 SEND_ERROR）
- libzip 缺失自动 `NO_LIBZIP`（:473），不影响 GTP/对局/分析，仅 selfplay 写训练数据需要
- OpenSSL 仅 `BUILD_DISTRIBUTED=1` 时必需（:489-492）；当前 `BUILD_DISTRIBUTED=0`，未启用
- 当前编译选项：`USE_BACKEND=OPENCL` + `BUILD_DISTRIBUTED=0`，其余默认（保留 git revision）

---

## 5 已知问题与后续工作

### 5.1 已踩坑（已解决，记录备查）

1. **vcpkg 必须放英文路径**：`E:\小工具`（中文）下 vcpkg 获取 ninja 时子进程报 "no such file or directory"（非 ASCII 路径在 cmake 子进程代码页解析失败）。迁至 `E:\vcpkg\` 后 59 秒装好 opencl+zlib。
2. **CMake build 目录用英文路径** `E:\katabuild\` 规避同样问题。源码路径含中文但 MSVC 能正确处理，未阻碍编译。
3. **脚本编码**：无 BOM 的 UTF-8 脚本在 Windows PowerShell 5.x 下中文乱码致解析失败（"Unexpected token"）。`build_opencl.ps1` 已加 UTF-8 BOM，5.x/7 均可运行。
4. **git 代理**：`git config --global http.proxy = http://127.0.0.1:15715`，github 被墙直连超时；clone 与 vcpkg 下载都依赖此代理端口在线。

### 5.2 已知非致命问题

- **1x1 conv 的 FP16 tensor core tuning 报 "Could not find any configuration"**：Blackwell 新架构 OpenCL WMMA 适配的已知现象，KataGo 已自动 fallback 为 `FP16TensorCoresFor1x1=false`，整体仍启用 FP16 张量核心（`FP16Storage=true, FP16TensorCores=true`），不影响功能与整体性能。
- **OpenCL vs CUDA**：benchmark 输出提示「如果有强 FP16 GPU（如 RTX2080），用 CUDA 版可能更快」。当前 OpenCL 后端已够用；若后续要榨性能可考虑装 CUDA Toolkit 切 CUDA 后端（需另配 vcpkg CUDA / CUDNN）。

### 5.3 后续建议

- 实际对弈建议把配置 `numSearchThreads` 从默认 6 调到 **20**（benchmark 推荐值）。可拷一份 `default_gtp.cfg` 到 `dist_opencl\` 独立修改，避免动原 Lizzieyzy 包。
- 首次 OpenCL autotuning 约 2 分钟，结果已缓存到 `dist_opencl\KataGoData\opencltuning\`，后续启动直接复用。
- 如需 selfplay 训练（写训练数据），需补装 libzip 并去掉默认的 `NO_LIBZIP`。
- 如需分布式训练贡献，需 `-DBUILD_DISTRIBUTED=1` + OpenSSL + libzip，并在 git clone 内编译。
