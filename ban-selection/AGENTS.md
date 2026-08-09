# AGENTS.md — new_go（20路Ban选围棋）

> 本文件为 `E:\小工具\new_go\ban-selection\` 项目专属指引。工作区其他项目见 `E:\小工具\AGENTS.md`。

## 这是什么

在 KataGo v1.16.4 源码上实现「20路Ban选围棋」变体：Ban 选阶段（10 禁点）+ 正式对局（黑贴 4.25 子）。Git 仓库：`github.com/0d00no0721/new_go`。

## 多 Agent 协作（入手必读）

5 个 agent 并行开发，各维护反馈文档：

1. **先读 `进度总览.md`**（PM 维护的全局进度，单页可览）
2. **再读相关 `Agent N — *.md`**（各 agent 的细节日志，`N` = 1..5）
3. 遇 `🚫 BLOCKED` 标记需优先处理

| Agent | 文档 | 职责 |
|-------|------|------|
| INFRA | `Agent 1 — INFRA.md` | 构建工具链与环境 |
| ENGINE | `Agent 2 — ENGINE.md` | KataGo 源码改造 |
| RULES | `Agent 3 — RULES.md` | Ban 阶段控制器 |
| FE | `Agent 4 — FE.md` | CLI 对弈工具 |
| QA | `Agent 5 — QA.md` | 测试与验收 |

规则文档：`新规则.md`；实现计划书：`新规则实现计划书.md`；KataGo 整合包索引：`文件索引.md`。

## 构建（KataGo 编译）

```powershell
.\build_opencl.ps1         # 增量构建
.\build_opencl.ps1 -Clean  # 清理重建
```

- **必须 MSVC + vcpkg**（MinGW 不支持 KataGo Windows 编译）；vcpkg 在 `E:\vcpkg`（需装 `opencl:x64-windows` `zlib:x64-windows`）
- `cl` / `cmake` **不在全局 PATH**——`build_opencl.ps1` 内部经 `vcvars64.bat` 注入环境；在普通终端 `cl`/`cmake` 会 "not recognized"，属正常
- 产物：`dist_opencl\katago.exe` + `OpenCL.dll` + `z.dll`
- `katago-src/` 是 shallow clone 且已 `.gitignore`，**勿提交**
- INFRA 已完成并 benchmark 验证：RTX 5060 OpenCL，20 线程 **429 visits/s**（MSVC 19.44 / CMake 3.31 / Win SDK 26100）
- 建议 `numSearchThreads` 调到 **20**（默认 6 偏低），在 config 或 `--extra-config` 中设
- 首次启动 OpenCL autotuning ~2 分钟，缓存于 `dist_opencl\KataGoData\opencltuning\`；FE 的 `gtp_override.cfg` 设 `homeDataDir=E:/katago_cache` 也可缓存 tuner，后续启动 <10s
- 构建中间目录 `E:\katabuild\`（英文路径，规避中文路径致 vcpkg 子进程失败）

## KataGo 改造要点（详见 `Agent 2 — ENGINE.md`）

核心思路：禁点 = `C_WALL`（KataGo 原生"棋盘外"色）→ 合法性 / 气 / 提子 / 劫争**零改动**，仅改数子 + NN 输入 + GTP 命令（合计 ~90 行）。

| 改动 | 位置 / 方式 |
|------|------------|
| `Board::MAX_LEN` 19→25 | `katago-src/cpp/game/board.h:15` |
| 禁点数据结构 + 数子修复 | `board.h` / `board.cpp`（`calculateArea` + `calculateIndependentLifeArea` 各 +1 条件） |
| NN 输入 feature 0 | `nninputs.cpp`（7 处 fillRow 加 `C_WALL` 判断） |
| 新 GTP 命令 | `gtp.cpp`：`kata-set-bans` / `kata-clear-bans` / `kata-query-bans` |
| komi 4.25 | `-override-config ignoreGTPAndForceKomi=4.25`（无需改码） |
| 20 路网络 | `gtpForceMaxNNSize=true`（19 路网络自动 pad 到 MAX_LEN，无需改码） |

> 注意：`analysis.cpp:916` 仍校验半整数，4.25 在 analysis 模式被拒——首期仅支持 GTP 对弈，analysis 模式二期处理。

> ENGINE 现已解阻塞（INFRA 交付工具链），可开始 WP2/WP3 编码并用 `build_opencl.ps1` 编译验证。

## 测试

```powershell
$env:PYTHONIOENCODING='utf-8'; python -m pytest test_ban.py -q
```

- 无 lint / typecheck 配置；语法验证用 `python -m py_compile *.py`
- PowerShell 下中文输出须先设 `$env:PYTHONIOENCODING='utf-8'`，否则 print 报 cp950 编码错
- 测试矩阵（29 用例覆盖 DoD 8 条）在 `Agent 5 — QA.md`，依赖产物就绪后执行

## 外部依赖

| 项 | 路径 |
|----|------|
| 原 KataGo 整合包 | `E:\2026-01-07-win64-KataGo\` |
| 权重 | `E:\2026-01-07-win64-KataGo\weights\28b.bin.gz` |
| 引擎配置 | `E:\2026-01-07-win64-KataGo\katago_configs\default_gtp.cfg` |
| vcpkg | `E:\vcpkg`（已装 `opencl` / `zlib`） |
| 工具链 | VS 2022 BuildTools（MSVC 19.44 + CMake 3.31 + Win SDK 26100） |
| 构建中间目录 | `E:\katabuild\`（英文路径） |
| OpenCL tuner 缓存 | `dist_opencl\KataGoData\opencltuning\` 或 `E:\katago_cache\`（经 `gtp_override.cfg`） |

## 目录速查

| 路径 | 说明 |
|------|------|
| `katago-src/` | KataGo 源码（gitignored） |
| `dist_opencl/` | 编译产物（gitignored） |
| `ban_controller.py` | Ban 阶段控制器（RULES 交付，397 行，36 测试全过） |
| `test_ban.py` | 控制器测试（36 用例） |
| `cli_player.py` | CLI 对弈工具（FE 第一阶段完成，591 行；19 路框架已跑通，komi4.25/bans/数子为占位待 ENGINE） |
| `gtp_override.cfg` | FE 附加 GTP 配置（`homeDataDir` 缓存 OpenCL tuner） |
| `build_opencl.ps1` | 编译脚本（INFRA 完成，benchmark 验证通过） |
| `进度总览.md` | 全局进度（PM 维护，入手先读） |
| `Agent N — *.md` | 各 agent 反馈文档 |
