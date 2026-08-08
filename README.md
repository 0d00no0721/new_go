# 20路Ban选围棋 — KataGo 实现

在 KataGo v1.16.4 上实现「20路Ban选围棋」变体规则的完整可玩实现。

## 项目简介

- **棋盘**：20×20 交叉点
- **两阶段**：Ban 选阶段（10 次禁点选择）→ 正式围棋对局
- **贴子**：黑贴 4.25 子（有效点位 390，基准 195）
- **AI**：基于 KataGo v1.16.4 源码改造，支持禁点规则与 20 路棋盘
- **当前状态**：核心交付完成（M1-M7 ✅），5 agent 全部完成，DoD 8 条全覆盖（整体 ~92%）

## 快速开始

### 对弈（AI vs AI）

```powershell
# 默认 20 路，自动导出 SGF（需 gtp_override.cfg 缓存 OpenCL tuner，启动 ~10s）
python cli_player.py --mode aivai --max-moves 10 --extra-config gtp_override.cfg
```

### 对弈（人 vs AI）

```powershell
python cli_player.py --mode human --color B --extra-config gtp_override.cfg
```

### SGF 复盘

```powershell
python cli_player.py --sgf-in game_YYYYMMDD_HHMMSS.sgf
```

CLI 默认使用 `dist_opencl\katago.exe`（改造后引擎），并自动注入两个 override：
`ignoreGTPAndForceKomi=4.25` + `gtpForceMaxNNSize=true`（19 路网络 pad 到 20 路）。

## 构建（KataGo 编译）

需 MSVC + vcpkg（MinGW 不支持）。`cl`/`cmake` 不在全局 PATH，由 `build_opencl.ps1` 内部经 `vcvars64.bat` 注入。

```powershell
.\build_opencl.ps1         # 增量构建
.\build_opencl.ps1 -Clean  # 清理重建
```

产物：`dist_opencl\katago.exe` + `OpenCL.dll` + `z.dll`。
benchmark：RTX 5060 OpenCL，20 线程 **429 visits/s**。
`katago-src/` 是 shallow clone 且已 `.gitignore`，**勿提交**。

## 测试

```powershell
$env:PYTHONIOENCODING='utf-8'
python -m pytest test_qa_matrix.py test_gtp_engine.py test_e2e.py test_params.py test_perf.py -v  # 常规（~105s）
python -m pytest test_perf.py -v --slow                                # 性能基准
python -m py_compile *.py                                              # 语法检查
```

PowerShell 下中文输出须先设 `$env:PYTHONIOENCODING='utf-8'`，否则 print 报 cp950 编码错。

测试结果：24 passed + 5 xfailed（GTP 接口限制诚实标注）+ 3 slow，约 105s。DoD 8 条全覆盖。

## 目录结构

```
new_go/
├── katago-src/              # KataGo 改造源码（gitignored）
├── dist_opencl/             # 编译产物 katago.exe + OpenCL.dll + z.dll（gitignored）
├── ban_controller.py        # Ban 阶段控制器（397 行）
├── test_ban.py              # 控制器测试（36 用例）
├── cli_player.py            # CLI 对弈工具（716 行，aivai/human/sgf-in 三模式）
├── sgf_io.py                # SGF 导出/导入（262 行，AE 禁点标记）
├── gtp_override.cfg         # 附加 GTP 配置（homeDataDir 缓存 OpenCL tuner）
├── build_opencl.ps1         # 编译脚本（MSVC + vcpkg）
├── test_qa_matrix.py        # QA 矩阵 A1-A8（Ban 阶段校验，8/8 通过）
├── test_gtp_engine.py       # QA 矩阵 B/C/G/F（GTP 引擎层，实测）
├── test_e2e.py              # QA 矩阵 D1-D3（端到端）
├── test_perf.py             # 性能基准（@slow）
├── test_params.py           # 参数化用例 E1-E5
├── conftest.py              # pytest 配置（--slow 标记）
├── 新规则.md                 # 完整规则文档（V1.0 修订版）
├── 新规则实现计划书.md       # KataGo 实现计划书
├── 文件索引.md               # KataGo 整合包文件分类索引
├── AGENTS.md                 # 项目专属指引（agent 协作）
├── 进度总览.md               # 全局进度（PM 维护，入手先读）
├── Agent 1 — INFRA.md       # 构建工具链反馈
├── Agent 2 — ENGINE.md      # 源码改造反馈
├── Agent 3 — RULES.md       # Ban 控制器反馈
├── Agent 4 — FE.md          # CLI 工具反馈
└── Agent 5 — QA.md          # 测试验收反馈
```

## 技术要点

### 引擎改造（C_WALL 技巧，4 文件 ~90 行）

核心思路：**禁点 = `C_WALL`**（KataGo 原生"棋盘外"色）→ 合法性 / 气 / 提子 / 劫争**零改动**，仅改数子 + NN 输入 + GTP 命令。

| 改动 | 位置 |
|------|------|
| `Board::MAX_LEN` 19→25 | `katago-src/cpp/game/board.h:15` |
| `std::set<Loc> banned_points` + 4 方法 | `board.h` / `board.cpp` |
| 数子排除 C_WALL | `board.cpp`（`calculateArea` + `calculateIndependentLifeArea` 各 +1 条件） |
| NN 输入 feature 0 | `nninputs.cpp`（5 处 fillRow 加 C_WALL 判断） |
| 新 GTP 命令 | `gtp.cpp`：`kata-set-bans` / `kata-clear-bans` / `kata-query-bans` |
| `checkConsistency` 放宽 | `board.cpp`（允许 C_WALL 在棋盘内，方案外发现） |

### 配置（无需改码）

| 配置项 | 值 | 作用 |
|--------|----|----|
| `gtpForceMaxNNSize` | `true` | 19 路网络 pad 到 20 路 |
| `ignoreGTPAndForceKomi` | `4.25` | 绕过 GTP `komi` 半整数校验 |

注意：`analysis.cpp:916` 仍校验半整数，4.25 在 analysis 模式被拒——首期仅支持 GTP 对弈。

## 外部依赖

| 项 | 路径 |
|----|------|
| 原 KataGo 整合包 | `E:\2026-01-07-win64-KataGo\` |
| 权重 | `E:\2026-01-07-win64-KataGo\weights\28b.bin.gz` |
| 引擎配置 | `E:\2026-01-07-win64-KataGo\katago_configs\default_gtp.cfg` |
| vcpkg | `E:\vcpkg`（已装 `opencl` / `zlib`） |
| 工具链 | VS 2022 BuildTools（MSVC 19.44 + CMake 3.31 + Win SDK 26100） |
| 构建中间目录 | `E:\katabuild\`（英文路径） |

## 开发角色（5 agent 并行）

| 角色 | 职责 | 状态 |
|------|------|------|
| INFRA | 构建工具链与环境 | ✅ 完成 |
| ENGINE | KataGo 源码改造（MAX_LEN / 禁点 / komi） | ✅ 完成 |
| RULES | Ban 控制器（序列 / 校验 / AI 选点） | ✅ 完成 |
| FE | CLI 对弈工具 + SGF | ✅ 完成 |
| QA | 测试与验收 | ✅ 完成 |

详见 `AGENTS.md`（协作约定）与 `进度总览.md`（全局进度）。
