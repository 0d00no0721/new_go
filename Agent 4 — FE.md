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

---

## 1 交付物

| 文件 | 行数 | 说明 |
|------|------|------|
| `cli_player.py` | 503 | CLI 对弈工具：GtpEngine（subprocess GTP 通信）+ run_game（Ban 阶段+正式对局+终局数子占位）+ argparse 命令行入口（aivai/human 模式） |
| `gtp_override.cfg` | 2 | 附加 GTP 配置（设 `homeDataDir=E:/katago_cache` 缓存 OpenCL tuner，避免每次启动重新调优） |

---

## 2 进度跟踪

### 2.1 WP5 — 对弈工具 + 前端

- [x] `GtpEngine` 类（subprocess + GTP 通信）
- [x] Ban 阶段整合（调用 BanController）
- [x] 正式对局流程（黑先交替 genmove）
- [x] 终局判定（双方 pass / 认输）
- [x] 数子判胜负（195 / 199.25 / 4.25）—— **占位完成**：调用引擎 `final_score` + 打印 20 路公式 TODO，待 ENGINE 就绪（komi 4.25 + 禁点数子）后实现完整公式
- [x] AI vs AI 模式
- [x] 人 vs AI 模式
- [ ] SGF 导出（20×20 + ban 标记）—— 后续阶段
- [x] 命令行参数解析

---

## 3 架构设计

```
cli_player.py（503 行）
├── 常量层 ──── DEFAULT_ENGINE/MODEL/CONFIG、PLAYER_TO_COLOR/COLOR_TO_PLAYER
├── GtpEngine 类 ── subprocess 管道 + 守护读线程 + queue
│   ├── __init__      启动 `katago gtp -config ... -model ...`，stderr→文件，初始化 boardsize/clear_board
│   ├── _read_loop    守护线程：stdout.readline → queue（send 与 analyze 共用读取通道）
│   ├── send(cmd)     标准命令：写命令 → 跳过 analyze 残留 info 行 → 读 `=`/`?` 响应头 → 读至空行 → 失败抛异常
│   ├── analyze(t)    流式命令：写 `kata-analyze interval <cs>` → 读 t 秒内 info 行（秒→厘秒转换）
│   ├── boardsize/clear_board/komi/genmove/play/final_score   高级封装
│   └── close         发 quit → wait(5) → kill
├── print_board() ── ASCII 棋盘（B黑/W白/X禁/.空，列 A-T/A-U 跳过 I）
├── GameConfig ──── dataclass（mode/color/boardsize/引擎路径/ban_strategy/max_moves/komi）
├── run_game(cfg) ── 对局主流程
│   ├── 启动双引擎（黑=选手B / 白=选手A），set komi（占位 try/except）
│   ├── Ban 阶段：BanController（区域 margin=3），按序列交替 human input / bc.submit_ai(random)
│   ├── 注入 GTP stub（kata-set-bans/clear-bans 占位返回 `=`；kata-analyze 走 analyze）
│   ├── Ban 结束：打印禁点 + placeholder would set bans
│   ├── 正式对局：黑先，双引擎交替 genmove（己方思考）+ play（同步对方落子），检测 pass/resign/连续pass
│   └── 终局数子：final_score（占位）+ 打印 20 路公式 TODO（黑>199.25 / 白>190.75）
└── main() ──────── argparse → GameConfig → run_game
```

### 3.1 关键设计决策

**GTP 通信（读线程 + queue）：** 所有 stdout 行由一个守护线程放入 `queue.Queue`，`send` 与 `analyze` 共用此 queue。
- `kata-analyze` 是流式命令（info 行无 `=` 前缀、无空行结束、靠新命令终止），与标准 GTP 响应格式不同。
- analyze 读取 N 秒后返回，残留 info 行留在 queue；下一次 `send` 写新命令后，自动跳过这些残留行直到读到新命令的 `=`/`?` 响应头 —— 实现「自动终止并消费残留」，无需额外同步。
- 进程退出检测：`get(timeout=1)` 超时后 `poll()`，避免引擎崩溃时永久阻塞。

**双引擎实例 + 手动同步：** 黑白各起一个 KataGo 实例（独立搜索树）。每手棋：己方 `genmove` → 对方 `play` 同步。代价：2× 内存与启动时间；好处：双方可独立配置（如不同模型），互不干扰。

**OpenCL tuner 缓存：** 首次启动需 OpenCL tuning（实测 ~104s）。通过 `gtp_override.cfg` 设 `homeDataDir=E:/katago_cache` 缓存 tuner 文件，后续启动跳过 tuning（<10s）。`--extra-config` 支持多个附加 config 覆盖主 config。

**选手 ↔ 棋色映射：** 规则规定选手 B 执黑、选手 A 执白。ban 序列用选手代号 A/B，正式对局用棋色 B/W，`PLAYER_TO_COLOR`/`COLOR_TO_PLAYER` 互转。

### 3.2 命令行接口

```
python cli_player.py --mode aivai --boardsize 19 --extra-config gtp_override.cfg --max-moves 3
python cli_player.py --mode human --color B --boardsize 19 --extra-config gtp_override.cfg
```
| 参数 | 说明 |
|------|------|
| `--mode` | `aivai`（AI 对 AI）/ `human`（人对 AI） |
| `--color` | human 模式人类棋色 B（黑先）/ W（白后） |
| `--boardsize` | 棋盘尺寸（默认 19，ENGINE 就绪后切 20） |
| `--engine`/`--model`/`--config` | 引擎/权重/配置路径（默认指向原版整合包） |
| `--extra-config` | 附加 GTP 配置（可多次，覆盖主 config，如 tuner 缓存） |
| `--ban-strategy` | Ban 阶段 AI 策略：`random`（保底）/ `gtp` / `auto` |
| `--max-moves` | 正式对局最大手数（0=不限，调试用小值） |
| `--komi` | 贴子（默认 4.25，传给引擎 final_score） |

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

### 依赖 ENGINE（❌ 未就绪）

- 需要改造后的 `katago.exe`（支持 20 路 + `kata-set-bans`）
- 临时方案：用原版 19 路 `katago.exe` 开发框架，`kata-set-bans` 用占位实现
- **已验证的 ENGINE 待办（FE 联调发现）：**
  1. `komi 4.25` 原版被拒（"komi must be an integer or half-integer"）→ 需 ENGINE 用 `-override-config ignoreGTPAndForceKomi=4.25`，FE 侧已 try/except 占位
  2. `kata-set-bans` 原版返回 `? unknown command` → FE 侧已 stub 占位返回 `=`
  3. 正式对局禁点不生效（原版引擎不知禁点，可能落在禁点上）→ FE 侧打印警告并接受，待 ENGINE 实装后真正生效
  4. 数子公式（195/199.25/4.25）依赖「禁点不计入地域」+ komi 4.25，需 ENGINE 数子改造完成后实装

---

## 5 环境信息

| 项 | 值 |
|----|-----|
| 工作目录 | `E:\小工具\new_go\` |
| 现有引擎 | `E:\2026-01-07-win64-KataGo\katago_opencl\katago.exe` |
| 现有权重 | `E:\2026-01-07-win64-KataGo\weights\28b.bin.gz` |
| 现有配置 | `E:\2026-01-07-win64-KataGo\katago_configs\default_gtp.cfg` |

---

## 6 已知问题与后续工作

### 6.1 第一阶段已知限制（均为占位，待 ENGINE 就绪）

| 项 | 现状 | 待办 |
|----|------|------|
| komi 4.25 | 原版拒绝（仅接受整数/半整数），`run_game` try/except 占位 | ENGINE 用 `ignoreGTPAndForceKomi=4.25`，FE 移除 try/except |
| `kata-set-bans` | stub 占位返回 `=`，打印 `placeholder would set bans` | ENGINE 实装后，FE 改为真发命令 |
| 禁点正式对局生效 | 不生效（原版引擎不知禁点，可能落禁点上，打印警告接受） | ENGINE 实装后自动生效 |
| 数子公式 | 调用 `final_score` + 打印 20 路 TODO（黑>199.25 / 白>190.75） | ENGINE 数子改造后，FE 按公式判定 |
| 20 路棋盘 | 当前 `--boardsize 19`（原版上限） | ENGINE 改 `MAX_LEN` 后切 `--boardsize 20`（会触发新一轮 OpenCL tuning） |

### 6.2 后续工作

- [ ] ENGINE 就绪后切换 20 路 + 真实 `kata-set-bans` + komi 4.25 + 数子公式
- [ ] SGF 导出（20×20 + ban 标记）
- [ ] Ban 阶段 GTP 评估策略联调（`bc.set_gtp_engine` 注入真实 `kata-analyze` 解析）
- [ ] 正式对局禁点违例处理（落禁点 3 次判负，规则 §5）
- [ ] `--max-moves` 之外的真实终局（连续 pass / resign）完整对局验证
- [ ] 可选：单引擎模式（genmove 自动落子内部棋盘，省一半内存）作为 `--single-engine` 选项
