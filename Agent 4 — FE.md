# Agent 4 — FE：前端/工具工程师

**角色：** 前端/工具工程师 FE
**关联计划书：** `新规则实现计划书.md` §7.5（WP5）
**关联规则：** `新规则.md` §6（流程总览）

---

## 更新日志

> 每次完成任务后在此追加一节。遇到阻塞立即在文档顶部标注 `🚫 BLOCKED`。

| 日期 | 状态 | 任务 | 摘要 |
|------|------|------|------|
| 2026-08-08 | ✅ 完成 | 第一阶段：CLI Server 框架 | `cli_player.py`（503 行）：GtpEngine 类 + run_game（Ban 阶段+正式对局）+ argparse 入口。19 路 AI vs AI 真机跑通，human 模式 mock 验证通过。komi 4.25 / kata-set-bans / 数子公式均为占位，待 ENGINE 就绪后切换。 |
| 2026-08-08 | ✅ 完成 | SGF 导出/导入 | 新建 `sgf_io.py`（216 行）：坐标转换（GTP↔SGF，跳 I vs 不跳 I）+ SgfGame + export_sgf（AE 禁点 + B/W 落子 + RE 结果）+ import_sgf（解析 AE/手谱）+ ReplayBoard（带提子的复盘棋盘）。`cli_player.py` 增至 690 行：run_game 追踪手谱并终局自动导出、review_sgf 复盘打印、--sgf-out/--sgf-in/--no-sgf 参数。19 路真机导出+导入还原验证通过，pass/resign mock 测试通过。 |
| 2026-08-08 | ✅ 完成 | 第三阶段：切 20 路 + 移除占位 + 数子实装 | ENGINE 已就绪，所有占位代码移除。默认引擎改为 `dist_opencl\katago.exe`，硬编码 `-override-config ignoreGTPAndForceKomi=4.25` + `gtpForceMaxNNSize=true`。`--boardsize` 默认 20。移除 komi try/except（改用 get_komi 确认）、kata-set-bans stub（改真发命令注入双引擎）、落禁点占位警告。数子公式实装：final_score 结果直接可信 + 打印 20 路公式。20 路 AI vs AI 真机跑通，SGF SZ[20] 导出/导入还原一致。`cli_player.py` 690→613 行（移除占位后精简）。 |

---

## 1 交付物

| 文件 | 行数 | 说明 |
|------|------|------|
| `cli_player.py` | 613 | CLI 对弈工具：GtpEngine（subprocess GTP 通信 + override-config）+ run_game（Ban 阶段+正式对局+终局数子+SGF 自动导出）+ review_sgf（SGF 导入复盘）+ argparse 命令行入口（aivai/human/sgf-in 模式） |
| `sgf_io.py` | 216 | SGF 导出/导入模块：坐标转换（GTP↔SGF）+ SgfGame 数据结构 + export_sgf + import_sgf + ReplayBoard（带提子的复盘棋盘） |
| `gtp_override.cfg` | 2 | 附加 GTP 配置（设 `homeDataDir=E:/katago_cache` 缓存 OpenCL tuner，含 x19+x25 缓存） |

---

## 2 进度跟踪

### 2.1 WP5 — 对弈工具 + 前端

- [x] `GtpEngine` 类（subprocess + GTP 通信）
- [x] Ban 阶段整合（调用 BanController）
- [x] 正式对局流程（黑先交替 genmove）
- [x] 终局判定（双方 pass / 认输）
- [x] 数子判胜负（195 / 199.25 / 4.25）—— 引擎 `final_score`（komi 4.25 + 禁点不计地域）+ 打印 20 路公式（有效点 390 / 基准 195 / 黑>199.25 / 白>190.75）
- [x] AI vs AI 模式
- [x] 人 vs AI 模式
- [x] SGF 导出（20×20 + ban 标记）—— `sgf_io.py`：AE 禁点 + B/W 落子 + RE 结果；`cli_player.py`：终局自动导出 + `--sgf-in` 复盘导入
- [x] 命令行参数解析

---

## 3 架构设计

```
cli_player.py（613 行）
├── 常量层 ──── DEFAULT_ENGINE/MODEL/CONFIG、DEFAULT_OVERRIDE_CONFIGS、PLAYER_TO_COLOR/COLOR_TO_PLAYER
├── GtpEngine 类 ── subprocess 管道 + 守护读线程 + queue + override-config
│   ├── __init__      启动 `katago gtp -config ... -override-config ... -model ...`，stderr→文件，初始化 boardsize/clear_board
│   ├── _read_loop    守护线程：stdout.readline → queue（send 与 analyze 共用读取通道）
│   ├── send(cmd)     标准命令：写命令 → 跳过 analyze 残留 info 行 → 读 `=`/`?` 响应头 → 读至空行 → 失败抛异常
│   ├── analyze(t)    流式命令：写 `kata-analyze interval <cs>` → 读 t 秒内 info 行（秒→厘秒转换）
│   ├── boardsize/clear_board/genmove/play/final_score   高级封装（无 komi：经 override-config 生效）
│   └── close         发 quit → wait(5) → kill
├── print_board() ── ASCII 棋盘（B黑/W白/X禁/.空，列 A-H,J-U 跳过 I）
├── GameConfig ──── dataclass（mode/color/boardsize=20/引擎路径/override_configs/ban_strategy/max_moves/komi/sgf_out/no_sgf）
├── run_game(cfg) ── 对局主流程
│   ├── 启动双引擎（黑=选手B / 白=选手A），override-config 硬编码 komi4.25 + gtpForceMaxNNSize
│   ├── get_komi 确认 4.25（不发 komi 命令）
│   ├── Ban 阶段：BanController（区域 margin=3），按序列交替 human input / bc.submit_ai(random/gtp)
│   ├── 注入真实 GTP callable（kata-analyze 走 analyze，其余走 send）
│   ├── Ban 结束：kata-set-bans 真实注入双引擎
│   ├── 正式对局：黑先，双引擎交替 genmove（己方思考）+ play（同步对方落子），检测 pass/resign/连续pass
│   │   └── game_moves 列表追踪每手（pass/落子），resign 不记录
│   ├── 终局数子：final_score（komi4.25+禁点不计地域，结果可信）+ 打印 20 路公式（黑>199.25 / 白>190.75）
│   └── SGF 导出：SgfGame → export_sgf（默认 game_YYYYMMDD_HHMMSS.sgf，--no-sgf 跳过）
├── review_sgf(path) ── SGF 导入复盘：import_sgf → 打印信息/禁点/手谱 + ReplayBoard 回放终局棋盘
└── main() ──────── argparse → GameConfig → run_game（或 --sgf-in → review_sgf）

sgf_io.py（216 行）
├── 坐标转换 ──── point_to_sgf / sgf_to_point / gtp_to_sgf / sgf_to_gtp
│   └── GTP 跳 I（A-H,J-U）↔ SGF 不跳 I（a-t），经 (row,col) 中转
├── SgfGame ──── dataclass（boardsize/komi/player_b/player_a/date/bans/moves/result）
├── export_sgf() ── 写 .sgf：根节点 FF/GM/SZ/CA/KM/RU/AP/PB/PW/DT/RE + AE[禁点] + ;B[xx];W[yy] 落子
├── import_sgf() ── 读 .sgf：_parse_node_props 解析属性 → 还原 boardsize/komi/bans(AE)/moves/RE
└── ReplayBoard ── 简易围棋棋盘（落子+提子，禁点=外边界），用于复盘展示终局棋盘
```

### 3.1 关键设计决策

**GTP 通信（读线程 + queue）：** 所有 stdout 行由一个守护线程放入 `queue.Queue`，`send` 与 `analyze` 共用此 queue。
- `kata-analyze` 是流式命令（info 行无 `=` 前缀、无空行结束、靠新命令终止），与标准 GTP 响应格式不同。
- analyze 读取 N 秒后返回，残留 info 行留在 queue；下一次 `send` 写新命令后，自动跳过这些残留行直到读到新命令的 `=`/`?` 响应头 —— 实现「自动终止并消费残留」，无需额外同步。
- 进程退出检测：`get(timeout=1)` 超时后 `poll()`，避免引擎崩溃时永久阻塞。

**双引擎实例 + 手动同步：** 黑白各起一个 KataGo 实例（独立搜索树）。每手棋：己方 `genmove` → 对方 `play` 同步。代价：2× 内存与启动时间；好处：双方可独立配置（如不同模型），互不干扰。

**override-config 硬编码：** `DEFAULT_OVERRIDE_CONFIGS = ["ignoreGTPAndForceKomi=4.25", "gtpForceMaxNNSize=true"]` 随引擎启动自动注入。komi 4.25 绕过 GTP 半整数限制（不发 `komi` 命令）；`gtpForceMaxNNSize` 让 19 路网络 pad 到 20 路。启动后用 `get_komi` 确认 4.25 生效。

**OpenCL tuner 缓存：** 首次启动需 OpenCL tuning（实测 ~104s）。通过 `gtp_override.cfg` 设 `homeDataDir=E:/katago_cache` 缓存 tuner 文件（含 x19 + x25 两套），后续启动跳过 tuning（~10s）。`--extra-config` 支持多个附加 config 覆盖主 config。

**选手 ↔ 棋色映射：** 规则规定选手 B 执黑、选手 A 执白。ban 序列用选手代号 A/B，正式对局用棋色 B/W，`PLAYER_TO_COLOR`/`COLOR_TO_PLAYER` 互转。

### 3.2 命令行接口

```
# AI vs AI 20 路（自动导出 SGF）
python cli_player.py --mode aivai --extra-config gtp_override.cfg --max-moves 5

# 人 vs AI 20 路
python cli_player.py --mode human --color B --extra-config gtp_override.cfg

# 指定 SGF 导出路径
python cli_player.py --mode aivai --sgf-out mygame.sgf --extra-config gtp_override.cfg --max-moves 5

# SGF 导入复盘（不启动新对局）
python cli_player.py --sgf-in mygame.sgf

# 不导出 SGF（调试用）
python cli_player.py --mode aivai --no-sgf --max-moves 3
```
| 参数 | 说明 |
|------|------|
| `--mode` | `aivai`（AI 对 AI）/ `human`（人对 AI） |
| `--color` | human 模式人类棋色 B（黑先）/ W（白后） |
| `--boardsize` | 棋盘尺寸（默认 20） |
| `--engine`/`--model`/`--config` | 引擎/权重/配置路径（默认指向 `dist_opencl\katago.exe`） |
| `--extra-config` | 附加 GTP 配置（可多次，如 tuner 缓存） |
| `--ban-strategy` | Ban 阶段 AI 策略：`random`（保底）/ `gtp` / `auto` |
| `--max-moves` | 正式对局最大手数（0=不限，调试用小值） |
| `--komi` | 贴子（默认 4.25，经 override-config 生效） |
| `--sgf-out` | SGF 导出路径（默认自动生成 `game_YYYYMMDD_HHMMSS.sgf`） |
| `--sgf-in` | SGF 导入复盘路径（不启动新对局，直接打印棋谱+禁点+终局棋盘） |
| `--no-sgf` | 不导出 SGF 文件 |

---

## 4 对其他 Agent 的依赖

### 依赖 RULES（✅ 已就绪）

- `ban_controller.py` 已完成（397 行，36 测试全过）
- API 文档：`Agent 3 — RULES.md`
- 关键 API：
  ```python
  from ban_controller import BanController, BanConfig
  bc = BanController()
  bc.submit_label("D7")     # 人类输入
  bc.submit_ai()            # AI 自动选点
  bc.get_result()           # 取最终禁点集合
  bc.set_gtp_engine(callable)  # 注入 GTP 引擎
  ```

### 依赖 ENGINE（✅ 已就绪）

- 改造后的 `katago.exe` 已交付：`E:\小工具\new_go\dist_opencl\katago.exe`（v1.16.4，含禁点改造）
- 已验证功能（ENGINE 冒烟 + FE 联调）：
  1. ✅ `boardsize 20` → 接受
  2. ✅ `get_komi` → 4.25（经 `-override-config ignoreGTPAndForceKomi=4.25` 生效）
  3. ✅ `kata-set-bans D10 K10 F7` → 设置成功；`kata-query-bans` → D10 K10 F7
  4. ✅ `genmove B` → R17（正确避开禁点 D10/K10/F7）
  5. ✅ `kata-clear-bans` → 清空；`clear_board` / `boardsize` 自动清禁点
  6. ✅ 19 路回归正常（komi 7.5）
  7. ✅ `final_score` 返回结果含 komi 4.25 + 禁点不计地域（如 B+2.5）
- FE 侧已移除所有占位代码，使用真实 GTP 命令

---

## 5 环境信息

| 项 | 值 |
|----|-----|
| 工作目录 | `E:\小工具\new_go\` |
| 改造后引擎 | `E:\小工具\new_go\dist_opencl\katago.exe`（v1.16.4，20 路 + 禁点） |
| 权重 | `E:\2026-01-07-win64-KataGo\weights\28b.bin.gz`（19 路网络，pad 到 20 路） |
| 引擎配置 | `E:\2026-01-07-win64-KataGo\katago_configs\default_gtp.cfg` |
| override-config | `ignoreGTPAndForceKomi=4.25` + `gtpForceMaxNNSize=true`（硬编码） |
| OpenCL tuner 缓存 | `E:\katago_cache\opencltuning\`（x19 + x25）或 `dist_opencl\KataGoData\opencltuning\` |

---

## 6 已知问题与后续工作

### 6.1 占位项迁移状态（全部已实装）

| 项 | 原占位 | 现状 |
|----|--------|------|
| komi 4.25 | 原版拒绝，try/except 占位 | ✅ 已实装：`-override-config ignoreGTPAndForceKomi=4.25` 硬编码，`get_komi` 确认 4.25 |
| `kata-set-bans` | stub 占位返回 `=`，打印 placeholder | ✅ 已实装：Ban 结束后真发 `kata-set-bans` 注入双引擎 |
| 禁点正式对局生效 | 不生效，打印警告接受 | ✅ 已实装：genmove 自动避开禁点，无落禁点异常 |
| 数子公式 | 打印 20 路 TODO | ✅ 已实装：`final_score`（komi4.25+禁点不计地域）+ 打印 20 路公式 |
| 20 路棋盘 | `--boardsize 19`（原版上限） | ✅ 已实装：`--boardsize 20` 默认，x25 tuner 缓存已就位 |
| SGF SZ 值 | 导出 `SZ[19]` | ✅ 已实装：导出 `SZ[20]`，导入校验 SZ |

### 6.2 后续工作

- [x] ENGINE 就绪后切换 20 路 + 真实 `kata-set-bans` + komi 4.25 + 数子公式
- [x] SGF 导出（20×20 + ban 标记）—— AE 禁点格式已实装，20 路验证通过
- [ ] Ban 阶段 GTP 评估策略联调（`bc.set_gtp_engine` 注入真实 `kata-analyze` 解析）
- [ ] 正式对局禁点违例处理（落禁点 3 次判负，规则 §5）
- [ ] `--max-moves` 之外的真实终局（连续 pass / resign）完整对局验证
- [ ] 可选：单引擎模式（genmove 自动落子内部棋盘，省一半内存）作为 `--single-engine` 选项

---

## 7 SGF 坐标约定（与 QA 对齐）

### 7.1 坐标系对照

| 体系 | 列字母 | 跳 I？ | 格式 | 示例 |
|------|--------|--------|------|------|
| GTP | A-H, J-U（大写） | 跳 I | `letter(col)` + `row` | `D7`（col=4, row=7） |
| SGF | a-t（小写） | **不跳 I** | `chr(col-1+'a')` + `chr(row-1+'a')` | `dg`（col=4, row=7） |
| ban_controller | 数字 1-20 | N/A | `(row, col)` 元组 | `(7, 4)` |

**关键易错点：** GTP 的 `J`（col=9，跳过 I）→ SGF 的 `i`（col=9，不跳 I）。即 GTP `J16` → SGF `ip`。

### 7.2 SGF 文件格式（已与 QA 冻结）

```
(;FF[4]GM[1]SZ[20]CA[UTF-8]KM[4.25]RU[chinese]AP[new_go]PB[选手B]PW[选手A]DT[2026-08-08]AE[dg][kk]...
;B[qp]
;W[dp]
;B[]          ← pass
)
```

- **ban 点**：根节点 `AE[sgf坐标][sgf坐标]...`（SGF 标准 Add Empty 属性）
- **落子**：`;B[sgf坐标]` / `;W[sgf坐标]`，pass 为 `;B[]` / `;W[]`
- **结果**：根节点 `RE[B+R]`（黑胜认输）/ `RE[W+R]`（白胜认输）/ `RE[B+4.25]`（数子）
- **导入只读 AE**；可选叠加 `CR[]` 仅供编辑器可视化，导入不读

### 7.3 换算链

```
GTP "D7" → gtp_to_point → (row=7, col=4) → point_to_sgf → SGF "dg"
SGF "dg" → sgf_to_point → (row=7, col=4) → point_to_gtp → GTP "D7"
```

函数均在 `sgf_io.py` 中，复用 `ban_controller.gtp_to_point` / `point_to_gtp` 做 GTP↔(row,col)，再用 `point_to_sgf` / `sgf_to_point` 做 (row,col)↔SGF。

---

## 8 联调结果（20 路 AI vs AI）

**测试命令：**
```
python cli_player.py --mode aivai --boardsize 20 --max-moves 5 --sgf-out test20.sgf --extra-config gtp_override.cfg
```

**验证项：**

| 项 | 结果 |
|----|------|
| 引擎启动 | ✅ 双引擎启动无报错，启动 ~10s（x25 tuner 缓存命中） |
| komi 4.25 | ✅ `get_komi` 返回 4.25（override-config 生效） |
| Ban 阶段 | ✅ 10 次 ban 完成，`kata-set-bans` 真实注入双引擎（无 placeholder） |
| genmove 避开禁点 | ✅ 5 手棋全部避开 10 个禁点（无落禁点异常） |
| final_score | ✅ 返回 `B+2.5`（引擎用 komi 4.25 + 禁点不计地域数子） |
| 20 路公式 | ✅ 打印：有效点=390，基准=195.0，黑>199.25，白>190.75 |
| SGF 导出 | ✅ `SZ[20] KM[4.25] AE[10禁点] RE[B+2.5]` + 5 手落子 |
| SGF 导入还原 | ✅ 禁点 10 个一致、手谱 5 手一致、终局棋盘一致 |

**SGF 文件示例：**
```
(;FF[4]GM[1]SZ[20]CA[UTF-8]KM[4.25]RU[chinese]AP[new_go]PB[选手B]PW[选手A]DT[2026-08-08]RE[B+2.5]AE[...]
;B[qr]
;W[qd]
;B[cd]
;W[dr]
;B[cp]
)
```
