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
| 2026-08-08 | ✅ 完成 | 第五阶段：GUI + 打包 | 新建 `gui.py`（762 行）：tkinter GUI（20×20 Canvas 棋盘 + Ban 阶段图形化 + 正式对局 + AI 思考实时显示 + SGF 导出）。BanGoApp 类复用 GtpEngine/BanController/sgf_io，线程模型用 ai_queue + analyze_queue + root.after 轮询（Python 3.14 跨线程 after 需经队列中转）。新建 `build.bat`（PyInstaller --onefile --windowed，CRLF 换行），打包成功 `dist\BanGo.exe`（11 MB）。GUI 冒烟测试通过（mock 引擎：Canvas 127 项、Ban 阶段正确推进）。 |
| 2026-08-08 | 🐛→✅ 修复 | Bug 修复：cmd 窗口 + 禁点坐标偏移 | Bug 1：GtpEngine subprocess.Popen 加 `creationflags=CREATE_NO_WINDOW`（cli_player.py:123，`sys.platform=="win32"` 守护跨平台安全）→ 双击 BanGo.exe 不再弹 cmd 黑窗。Bug 2：gui.py draw_board 禁点遍历改为 1-based→Canvas 转换（`r=size-row1, c=col1-1`），红 X 位置与棋子/点击对齐。真实引擎端到端验证通过（komi 4.25、AI 禁 H10 坐标 roundtrip、人类点击 K10 成功禁点渲染）。重新打包 `dist\BanGo.exe` 11 MB。 |
| 2026-08-08 | ✅ 完成 | 第六阶段：设置面板 + AI 参数可配置 | 新建 `settings.py`（58 行）：settings.json 持久化 + 3 预设（新手/业余/高级）+ build_override_configs。gui.py 加 SettingsDialog 类（Toplevel，AI 水平/思考时间/深度/线程/pondering/权重文件选择）+ 菜单栏（文件→设置/新对局/退出）+ 首次启动弹设置 + `_restart_engine()` 重启引擎 + AI 思考状态显示 maxTime。真实引擎端到端验证：新手模式 maxVisits=50/maxTime=2/pondering=false 全部经 override-config 生效，AI 响应 2.8 秒不卡顿。修复 genmove 空响应崩溃。重新打包 `dist\BanGo.exe` 11 MB。 |
| 2026-08-09 | ✅ 完成 | 第七阶段：止卡顿 + 非正方形 + AIvsAI | **止卡顿**：gui.py `_ai_move_async` 去掉并发 analyze 线程（根因：analyze 与 genmove 共用 stdin 无锁冲突导致死锁），仅发 genmove。**BanController 改造**：`ban_controller.py` 加 `board_cols`（支持非正方形）+ region 默认全棋盘（去 margin=3 限制）+ `check_connectivity` 签名改为 `(board_rows, board_cols, ...)`。`test_ban.py` 更新 41 用例全过（+5 非正方形测试）。**CLI 非正方形**：`cli_player.py` GtpEngine/boardsize_n 支持 int 或 tuple，`--boardsize 15:20` 格式。**GUI 棋盘可配**：settings 加 `board_rows`/`board_cols`/`game_mode`，SettingsDialog 加行列 Spinbox(9-25) + 模式 Combobox，gui.py 全部改用 `self.rows`/`self.cols` + 非正方形 Canvas。**AIvsAI 模式**：单引擎交替 genmove black/white + Ban 阶段双 AI 自动选点 + 暂停/继续按钮 + 0.5s 延迟便于观察。真实引擎端到端：新手模式 AI 响应 0.1s 不卡顿。重新打包 11 MB。 |
| 2026-08-09 | 🐛→✅ 修复 | 第八阶段：提子不消失 bug | **根因**：GUI `self.stones` 与 CLI `stones` 影子棋盘只增不减，GTP `genmove`/`play` 返回值不含提子信息，被提棋子残留显示。**修复（方案 B 复用 ReplayBoard）**：`sgf_io.py` `ReplayBoard.__init__` 改为 `(rows, cols, bans)` 支持非正方形（边界检查 `self.rows`/`self.cols`，保留 `self.size=rows` 只读兼容）。`cli_player.py` run_game 的 `stones` 字典换为 `ReplayBoard(board_rows, board_cols, set(bc.banned))`，落子调 `board.play()`，`print_board(board.stones, ...)`；review_sgf 防御性处理 `game.boardsize` int/tuple。`gui.py` `self.stones` 换为 `self.board = ReplayBoard(self.rows, self.cols, ...)`，draw_board 遍历 1-based `board.stones` 转 Canvas（`r=rows-row1, c=col1-1`），`_on_ban_finished` 重建带 bans 的 board（提子时禁点不计气）。验证：py_compile 全过、pytest 41 passed 无回归、内联提子脚本 3 例全过（单子提子/ban不计气/非正方形边界）、CLI print_board 提子渲染正确。 |
| 2026-08-09 | ✅ 完成 | 第九阶段：新增「人vs人」本地双人对弈 | GUI 新增第三种对局模式「人vs人」（两真人本地轮流点击，引擎仅 final_score 数子，不用 genmove）。settings 注释扩到三模式；SettingsDialog Combobox 加「人vs人」选项；新增 `_is_human_vs_human()` 辅助方法。9 处守卫/显示改动：`_on_ban_click`/`_on_play_click` 接受所有点击、`_on_play_click` 末尾不调 AI、`update_status` Ban/对局显示「选手A(白)/选手B(黑)」「黑方/白方」、`_update_buttons` human_turn 含人vs人。**3 处任务未列但必要的修复**：①`_on_play_click` 的 `_do_move(self.human_color,...)` 改 `_do_move(turn,...)`（否则白方点击被记成黑子）；②`human_pass`/`human_resign` 用 `turn` 而非 `human_color`（Pass/认输对白方可用）；③`_maybe_ai_ban` 的 `is_ai_turn` 加 `not _is_human_vs_human()` 守卫——任务称其"天然正确"实则有 bug：`ai_player="A"`，Ban 序列中 player A 的回合会误触发 AI ban。验证：py_compile 全过、pytest 41 passed 无回归、9 项逻辑测试全过（模式检测/ban守卫/maybe_ai_ban修复/play守卫/按钮/状态栏角色×2/人vsAI回归/AIvsAI回归）。重新打包 11.06 MB。 |
| 2026-08-09 | ✅ 完成 | UI 调整：禁点改用消去连线表示 | 用户反馈红色叉叉不美观。gui.py draw_board 改禁点表示：从"红叉叉"改为"消去该点与相邻点之间的连线段，禁点呈孤立空白"。①网格线由贯穿画法改为**逐段画法**：先建 `banned_cv` 集合（1-based→Canvas 转换），横向段 `(r,c)→(r,c+1)`、纵向段 `(r,c)→(r+1,c)`，任一端点在 banned_cv 则跳过；②星位画法两分支（正方形 STAR_POINTS_20 / 非正方形天元）均加 `(r,c) not in banned_cv` 判断；③删除 draw_board 中遍历 `self.bc.banned` 调 `_draw_ban` 的整段；④`_draw_ban` 方法体清空（保留定义防外部调用）；⑤删除未使用常量 `BAN_COLOR`。边界点被禁时该处边界线段消失、角点被禁时两条连线都消失、禁点为星位时星位小圆点不出现——均符合预期。验证：py_compile 全过、pytest 41 passed 无回归、6 项线段逻辑测试全过（空盘12段/角点删2段/中心删4段/边点删3段/相邻禁点并集/星位跳过）。重新打包 11.05 MB。 |
| 2026-08-09 | ✅ 完成 | 第十阶段：人vs人 手动标记死子 + UI 层数子 | 人vs人 双 pass 后不再依赖引擎 final_score，改为手动标记死子 + UI 层数子，与网页端对齐。**新建 `scoring.py`（231 行）**：1:1 移植 `ban-engine.js scoreGame` 到 Python，中国规则 area scoring + 贴目公式（有效点/基准/黑>199.25/白>190.75），`dead_stones` 参数先移除死子再 BFS 独占空判定，禁点=棋盘外不参与 BFS。自带 5 组 28 项自测全过（无死子独占空/死子移除后变黑空/贴目4.25产.75/.25/双活中性/禁点不计地域）。**gui.py 改动（1213→1283, +70）**：①新增 `MARK_DEAD` 状态常量 + `self.dead_stones` 实例属性（init/new_game/_restart_engine 三处清空）；②`human_pass` 双 pass 分支：人vs人→`MARK_DEAD` 状态（不调引擎），人vsAI/AIvsAI→保持 `_end_game`（引擎 final_score）；③`on_click` 加 `MARK_DEAD` 分发→`_on_dead_click`（点击棋子切换死子标记，空点忽略）；④新增 `_canvas_to_1based` 坐标辅助；⑤`draw_board` 在 MARK_DEAD 下对死子叠红色 X 标记；⑥新增 `_confirm_dead`（调 `score_game` 数子）+ `_end_game_ui_scoring`（弹框显示黑区/白区/中性空/死子/贴目明细，不调引擎）；⑦`update_status` 加 MARK_DEAD 提示分支（已标记数）；⑧`_build_ui` 加「确认数子」按钮 + `_update_buttons` 管理（MARK_DEAD 时 NORMAL，其他 DISABLED；Pass/认输/暂停在 MARK_DEAD 自动 DISABLED）。验证：py_compile 全过、scoring.py 28 项自测全过、pytest 41 passed 无回归、8 组 34 项逻辑测试全过（人vs人MARK_DEAD/人vsAI引擎回归/AIvsAI引擎回归/死子标记切换/按钮状态/其他状态禁用/_confirm_dead集成/on_click分发）。重新打包 11.06 MB。 |

---

## 1 交付物

| 文件 | 行数 | 说明 |
|------|------|------|
| `cli_player.py` | 748 | CLI 对弈工具：GtpEngine（subprocess GTP 通信 + override-config + CREATE_NO_WINDOW + 非正方形 boardsize tuple）+ run_game（Ban 阶段+正式对局+终局数子+SGF 自动导出，ReplayBoard 影子棋盘带提子）+ review_sgf + argparse（`--boardsize 15:20` 非正方形） |
| `gui.py` | 1283 | GUI 对弈工具（tkinter）：BanGoApp（行列可配 Canvas + Ban 阶段 + 正式对局 + SGF + 设置面板 + 引擎重启 + AIvsAI + 暂停继续 + 人vs人双人 + ReplayBoard 影子棋盘带提子 + 禁点消去连线表示 + 人vs人标记死子+UI层数子）+ SettingsDialog，复用 GtpEngine/BanController/sgf_io/settings/scoring |
| `settings.py` | 78 | 设置持久化：settings.json + 3 预设 + build_override_configs + board_rows/board_cols/game_mode |
| `ban_controller.py` | 414 | Ban 控制器（RULES 资产，FE 代改）：支持非正方形 board_cols + region 默认全棋盘 + check_connectivity(rows, cols) |
| `sgf_io.py` | 265 | SGF 导出/导入模块：坐标转换 + SgfGame + export_sgf + import_sgf + ReplayBoard（支持非正方形 rows/cols + 提子，禁点不计气） |
| `scoring.py` | 231 | 数子模块：1:1 移植 ban-engine.js scoreGame，中国规则 area scoring + 贴目公式 + dead_stones 参数 + 禁点=棋盘外不参与 BFS，自带 5 组 28 项自测 |
| `test_ban.py` | 390 | BanController 测试（41 用例：坐标/区域/连通性/序列/违例/AI选点/非正方形） |
| `build.bat` | 36 | PyInstaller 打包脚本（--onefile --windowed，CRLF），输出 `dist\BanGo.exe` |
| `gtp_override.cfg` | 2 | 附加 GTP 配置（`homeDataDir=E:/katago_cache`，含 x19+x25 tuner 缓存） |

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

gui.py（937 行）
├── 常量层 ──── BOARD_SIZE=20、状态机 BAN_PHASE/PLAYING/AI_THINKING/GAME_OVER、颜色常量、星位
├── SettingsDialog(Toplevel) ── AI 设置对话框
│   ├── 预设选择        OptionMenu（新手/业余/高级/自定义）→ 自动填 visits/time/threads
│   ├── 参数输入        maxTime/maxVisits/numSearchThreads Entry + pondering Checkbutton + 权重文件浏览
│   └── 确定/取消       确定→返回 settings dict，取消→None
├── BanGoApp 类 ── tkinter GUI 主应用
│   ├── __init__        加载 settings（首次弹 SettingsDialog），初始化状态/队列/引擎/BanController
│   ├── _build_menu     菜单栏：文件→设置/新对局/退出
│   ├── _build_ui       顶部状态栏 + 左 Canvas 棋盘 + 右侧栏（AI 思考/禁点列表/按钮）+ 底部日志
│   ├── draw_board      Canvas 绘制：网格 + 星位 + 坐标标签 + 禁点(红X,1-based→Canvas) + 棋子 + 最后一手红点
│   ├── on_click        按状态分发：BAN_PHASE→_on_ban_click / PLAYING→_on_play_click
│   ├── Ban 阶段        _on_ban_click(人类) / _ban_ai_worker(AI后台) / _on_ban_finished(注入引擎)
│   ├── 正式对局        _on_play_click(人类落子+eng.play) / _ai_move_async(AI后台genmove+analyze,超时=maxTime+30)
│   ├── _analyze_worker 后台循环 eng.analyze(0.5s) → analyze_queue → _poll_analyze → 侧栏刷新
│   ├── 终局            _end_game → final_score + 20 路公式 + 自动 SGF 导出
│   ├── _open_settings  弹 SettingsDialog → save_settings → 首次直接启动/非首次提示新对局
│   ├── _restart_engine 关闭引擎→重置状态→用当前 settings 重新启动（新对局生效）
│   ├── _start_engine   后台启动 GtpEngine，override_configs = DEFAULT_OVERRIDE_CONFIGS + 搜索限制
│   ├── 线程模型        ai_queue + analyze_queue + root.after(100/200) 轮询（Python 3.14 跨线程 after 需经队列中转）
│   └── 引擎管理        单引擎（人vsAI），后台启动，关闭时 eng.close()
└── main() ──────── tk.Tk() + BanGoApp(root) + root.mainloop()

settings.py（58 行）
├── DEFAULT_SETTINGS ── 默认设置（业余 + pondering=false）
├── PRESETS ────────── 3 预设：新手(50/2s) / 业余(800/10s) / 高级(3000/30s)
├── load/save_settings settings.json 读写（exe 模式用 sys.executable 目录）
└── build_override_configs → [maxVisits=, maxTime=, numSearchThreads=, ponderingEnabled=]
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

**GUI 线程模型（Python 3.14 兼容）：** 后台线程不直接调 `root.after()`（3.14 会抛 "main thread is not in main loop"），改为将消息放入 `ai_queue` / `analyze_queue`，主线程 `root.after(100, _poll_ai)` / `root.after(200, _poll_analyze)` 轮询消费。所有 UI 更新在主线程 after 回调里完成。引擎启动也经队列通知主线程（`("engine_ready", komi)`）。

**GUI 单引擎模式：** 人 vs AI 只需 1 个引擎实例（CLI 用双引擎）。人类落子 `eng.play` 同步到引擎棋盘，AI `eng.genmove` 生成应手。AI 思考时并行 `eng.analyze` 流式刷新侧栏（winrate/visits/PV），genmove 完成后停止 analyze 线程。

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

- 改造后的 `katago.exe` 已交付：`E:\小工具\new_go\ban-selection\dist_opencl\katago.exe`（v1.16.4，含禁点改造）
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
| 工作目录 | `E:\小工具\new_go\ban-selection\` |
| 改造后引擎 | `E:\小工具\new_go\ban-selection\dist_opencl\katago.exe`（v1.16.4，20 路 + 禁点） |
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
- [x] GUI 图形界面（tkinter）+ PyInstaller 打包 —— `gui.py` + `build.bat` → `dist\BanGo.exe`（11 MB）
- [x] GUI 设置面板（AI 参数可配置）—— `settings.py` + SettingsDialog + 3 预设 + settings.json 持久化 + 引擎重启
- [x] GUI 止卡顿修复 —— 去掉并发 analyze 线程（stdin 无锁冲突死锁），AI 响应 0.1s
- [x] BanController 非正方形支持 + 去 ban 区域限制 —— `board_cols` + region 默认全棋盘 + `check_connectivity(rows, cols)`
- [x] CLI/GUI 棋盘行列可配（9-25，非正方形）—— `--boardsize 15:20` + SettingsDialog Spinbox + 非正方形 Canvas
- [x] GUI AIvsAI 模式 + 暂停/继续 —— 单引擎交替 genmove + 自动 Ban + 暂停继续按钮
- [ ] Ban 阶段 GTP 评估策略联调（`bc.set_gtp_engine` 注入真实 `kata-analyze` 解析）
- [ ] 正式对局禁点违例处理（落禁点 3 次判负，规则 §5）
- [ ] `--max-moves` 之外的真实终局（连续 pass / resign）完整对局验证
- [ ] GUI 功能增强：复盘导入（--sgf-in 等价）、棋色选择
- [ ] 可选：CLI 单引擎模式（genmove 自动落子内部棋盘，省一半内存）作为 `--single-engine` 选项

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

---

## 9 GUI 验证结果

**GUI 冒烟测试（mock 引擎）：**

| 项 | 结果 |
|----|------|
| 窗口启动 | ✅ tkinter 窗口弹出，标题"20路Ban选围棋" |
| Canvas 棋盘 | ✅ 127 项（20×20 网格线 + 5 星位 + 坐标标签 + 1 禁点 X） |
| 引擎就绪通知 | ✅ 经 ai_queue 中转（Python 3.14 跨线程 after 兼容） |
| Ban 阶段推进 | ✅ AI 先禁 1 点（序列首位 A=AI），轮到人类(B) 时 state=BAN_PHASE |
| 按钮状态 | ✅ Pass/认输/导出SGF/新对局 按状态启用/禁用 |
| AI 思考侧栏 | ✅ winrate/visits/PV 标签可更新 |

**PyInstaller 打包：**

| 项 | 结果 |
|----|------|
| build.bat 执行 | ✅ PyInstaller 6.20.0 + Python 3.14.3 |
| dist\BanGo.exe | ✅ 11 MB（--onefile --windowed，轻量） |
| dist\gtp_override.cfg | ✅ 已复制 |
| 运行时依赖 | exe 引用外部 `dist_opencl\katago.exe` + 权重 + `gtp_override.cfg`（不打包进 exe） |
| 双击无 cmd 黑窗 | ✅ 修复后验证：katago 子进程无窗口（`CREATE_NO_WINDOW` 生效） |

**实测 bug 修复（GUI 打包后）：**

| Bug | 根因 | 修复 | 验证 |
|-----|------|------|------|
| 双击 BanGo.exe 弹 cmd 黑窗 | `subprocess.Popen` 启动 katago.exe 未设 `CREATE_NO_WINDOW`，Windows 为子进程分配新控制台 | `cli_player.py:123` Popen 加 `creationflags=subprocess.CREATE_NO_WINDOW`（`sys.platform=="win32"` 守护） | ✅ 双击 exe 仅 tkinter 窗口，katago 子进程无窗口 |
| 禁点红 X 位置偏移 | `gui.py` draw_board 直接用 `bc.banned` 的 1-based (row,col) 当 Canvas 坐标，Y 翻转/偏移 | `gui.py:263` 改为 `r=size-row1, c=col1-1`（1-based→Canvas 转换，与 `_gtp_to_pos` 一致） | ✅ 真实引擎端到端：AI 禁 H10 坐标 roundtrip 正确，人类点击 K10 红X与交叉点对齐 |

**真实引擎端到端验证：**

| 项 | 结果 |
|----|------|
| 引擎启动 | ✅ ~10s（x25 tuner 缓存命中） |
| komi | ✅ get_komi 返回 4.25 |
| AI ban 坐标 | ✅ H10 (row=10,col=8) → Canvas (10,7) roundtrip 正确 |
| 人类点击 K10 | ✅ 点击 → bc.submit_label → 禁点渲染对齐 → step 推进 |

**GUI 使用方式：**
```
# 开发运行
python gui.py

# 打包
.\build.bat
# → dist\BanGo.exe（双击启动，需 dist_opencl\katago.exe 在原路径）
```

**设置面板验证（第六阶段）：**

| 项 | 结果 |
|----|------|
| settings.json 持久化 | ✅ 保存/加载/默认值/预设切换全部通过 |
| 首次启动弹设置 | ✅ settings.json 不存在时弹 SettingsDialog，确认后启动引擎 |
| 菜单栏"设置" | ✅ 文件→设置/新对局/退出，改设置后提示"新对局"重启引擎 |
| override-config 生效 | ✅ 新手模式 kata-get-param 确认 maxVisits=50/maxTime=2.0/ponderingEnabled=false |
| 默认不卡顿 | ✅ 业余默认 maxVisits=800/maxTime=10/pondering=false，AI 响应 ~2.8 秒 |
| 预设切换 | ✅ 新手(50/2s) → AI 每手 ~2 秒；业余(800/10s) → ~10 秒 |
| 权重文件选择 | ✅ 文件浏览 + 路径校验，重启引擎用新权重 |
| 引擎重启 | ✅ _restart_engine 关闭→重置→重新启动，Ban 阶段正确重开 |
| AI 思考进度 | ✅ 状态栏显示"AI 思考中... (最多 N 秒)" + 侧栏 winrate/visits/PV 实时刷新 |
| 重新打包 | ✅ dist\BanGo.exe 11 MB（含 settings.py） |

**settings.json 默认值 + 预设映射表：**

| 参数 | 默认（业余） | 新手 | 业余 | 高级 |
|------|-------------|------|------|------|
| maxVisits | 800 | 50 | 800 | 3000 |
| maxTime | 10.0 秒 | 2.0 秒 | 10.0 秒 | 30.0 秒 |
| numSearchThreads | 6 | 6 | 6 | 6 |
| ponderingEnabled | false | false | false | false |
| model_path | `28b.bin.gz` | 同左 | 同左 | 同左 |

> ponderingEnabled 默认关闭（避免后台偷算占满 GPU 卡顿）；高级用户可在设置中手动开启。

**第七阶段验证（止卡顿 + 非正方形 + AIvsAI）：**

| 项 | 结果 |
|----|------|
| **止卡顿** | ✅ 真实引擎新手模式 AI 响应 0.1s（去掉并发 analyze 线程，根因：stdin 无锁冲突死锁） |
| BanController 非正方形 | ✅ `BanConfig(board_size=15, board_cols=20)` + region 默认全棋盘 + `check_connectivity(rows, cols)` |
| test_ban.py | ✅ 41 用例全过（原 36 + 5 非正方形：默认正方形/非正方形维度/边角合法/非正方形连通性/越界） |
| CLI 非正方形 | ✅ `--boardsize 15:20` → GTP `boardsize 15:20` + BanConfig + print_board 全部支持 |
| GUI 棋盘可配 | ✅ SettingsDialog 行列 Spinbox(9-25) + 模式 Combobox → 非正方形 Canvas(604x464) |
| GUI AIvsAI | ✅ 自动 Ban 10 步 + 自动交替 genmove + 暂停/继续按钮 + 0.5s 延迟 |
| 暂停/继续 | ✅ `_toggle_pause` + `_paused` 标志 + `root.after` 调度恢复 |
| 重新打包 | ✅ `dist\BanGo.exe` 11 MB |

**止卡顿根因与修复：**
- 根因：`_ai_move_async` 并发启动 `_analyze_worker` 线程和 `genmove`，两者共用同一 GtpEngine 的 stdin/queue，无锁并发导致 GTP 命令交错冲突 → genmove 永远等不到 "=" 响应 → 死锁
- 修复：去掉 analyze 线程，仅发 genmove（`_analyze_worker` 方法保留但不再调用）

**BanController 改造（FE 代改 RULES 资产）：**
- `board_cols: Optional[int] = None`（None 时等于 board_size，正方形向后兼容）
- `region_*` 默认全棋盘（`region_row_max=0` → validate 填 board_rows）
- `check_connectivity(board_rows, board_cols, ...)` 签名（原 `board_size` 单值）
- `col_to_letter` 扩展到 1-25 列（Z）
- `board_rows` 只读属性（= board_size），`board_cols` 字段（validate 后为 int）

**第八阶段验证（提子不消失 bug 修复）：**

| 项 | 结果 |
|----|------|
| **根因** | GUI `self.stones` / CLI `stones` 影子棋盘只增不减；GTP `genmove`/`play` 返回值不含提子信息，被提棋子残留显示 |
| **修复方案** | 方案 B：复用 `sgf_io.ReplayBoard`（已正确实现落子+提子 BFS 数气 + 禁点视为棋盘外不计气）替换 `stones` 字典 |
| ReplayBoard 非正方形 | ✅ `__init__(rows, cols, bans)` + 边界检查 `self.rows`/`self.cols`（保留 `self.size=rows` 只读兼容） |
| CLI run_game | ✅ `stones` 字典 → `ReplayBoard(board_rows, board_cols, set(bc.banned))`，落子 `board.play()`，`print_board(board.stones, ...)` |
| CLI review_sgf | ✅ 防御性处理 `game.boardsize` int/tuple → `ReplayBoard(sgf_rows, sgf_cols, ban_set)` |
| GUI draw_board | ✅ 遍历 1-based `self.board.stones` 转 Canvas（`r=rows-row1, c=col1-1`）绘制 |
| GUI 落子 | ✅ `_do_move`/`_on_ai_move` 调 `self.board.play(color, row_1, col_1)`（gtp_to_point 转 1-based） |
| GUI Ban 结束 | ✅ `_on_ban_finished` 重建 `ReplayBoard(rows, cols, set(banned))`，提子时禁点不计气 |
| py_compile | ✅ gui.py / cli_player.py / sgf_io.py 全过 |
| pytest 回归 | ✅ test_ban.py 41 passed（无回归） |
| 提子场景测试 | ✅ 内联脚本 3 例全过：单子围杀提子 / ban 不计气提角子 / 非正方形 15×20 边界 |
| CLI print_board 提子 | ✅ 围杀后白子消失显示 `.`、4 黑子保留、禁点显示 `X` |
| 行数变化 | sgf_io 262→265(+3) / cli_player 744→748(+4) / gui 1187→1194(+7) |

**第九阶段验证（人vs人 本地双人对弈）：**

| 项 | 结果 |
|----|------|
| **模式检测** | ✅ `_is_human_vs_human()` 返回 True（人vs人），`_is_ai_vs_ai()` 返回 False |
| SettingsDialog Combobox | ✅ 加「人vs人」选项（values=["人vsAI", "AIvsAI", "人vs人"]） |
| Ban 阶段守卫 | ✅ `_on_ban_click` 人vs人接受 player A 和 B 的点击（`not _is_human_vs_human() and ...` 守卫跳过） |
| **`_maybe_ai_ban` 修复** | ✅ 加 `not _is_human_vs_human()` 守卫——任务称"天然正确"实则有 bug：`ai_player="A"`，Ban 序列中 player A 回合（steps 1,4,5,8,9）会误触发 AI ban，现已修复 |
| 对局守卫 | ✅ `_on_play_click` 人vs人接受 B 和 W 的点击 |
| **`_do_move` 颜色修复** | ✅ `_do_move(turn, gtp)` 用实际轮次（任务未列但必要，否则白方点击被记成黑子） |
| **`human_pass`/`human_resign` 修复** | ✅ 用 `turn` 而非 `human_color`（任务未列但必要，否则白方无法 Pass/认输记录错误） |
| AI 应手 | ✅ 人vs人 不调 `_ai_move_async()`（`_on_play_click`/`human_pass`/`_on_ban_finished` 均守卫） |
| 状态栏 Ban 阶段 | ✅ 人vs人显示「选手A(白)/选手B(黑)」（非 AI/您） |
| 状态栏对局 | ✅ 人vs人显示「黑方/白方」（非 AI/您） |
| Pass/认输按钮 | ✅ 人vs人两方均可点击（`human_turn` 含 `_is_human_vs_human()`） |
| 暂停/继续按钮 | ✅ 人vs人自动 DISABLED（`ai_vs_ai=False`） |
| 人vsAI 回归 | ✅ 守卫逻辑不变：player A 仍触发 AI ban、W 轮仍阻止人类点击、A 仍被 block |
| AIvsAI 回归 | ✅ `is_ai_turn` 仍 True、双 AI 自动对弈不变 |
| py_compile | ✅ gui.py / settings.py 全过 |
| pytest 回归 | ✅ test_ban.py 41 passed（无回归） |
| 逻辑测试 | ✅ 9 项全过（模式检测/ban守卫/maybe_ai_ban修复/play守卫/按钮/状态栏角色×2/人vsAI回归/AIvsAI回归） |
| 重新打包 | ✅ `dist\BanGo.exe` 11.06 MB（时间戳 10:16:11） |
| 行数变化 | gui 1194→1212(+18) / settings 78(仅注释) |

**UI 调整验证（禁点改用消去连线表示）：**

| 项 | 结果 |
|----|------|
| **网格线逐段画法** | ✅ 贯穿画法 → 逐段画法：横向 `(r,c)→(r,c+1)`、纵向 `(r,c)→(r+1,c)`，任一端点在 `banned_cv` 则跳过 |
| banned_cv 集合 | ✅ 1-based `(row,col)` → Canvas `(rows-row1, col1-1)` 转换 |
| 星位跳过禁点 | ✅ 正方形 STAR_POINTS_20 + 非正方形天元两分支均加 `(r,c) not in banned_cv` |
| 删除红叉叉绘制 | ✅ draw_board 遍历 `_draw_ban` 整段删除；`_draw_ban` 方法体清空（保留定义防外部调用） |
| 删除 BAN_COLOR | ✅ 未使用常量已删（仅 `_draw_ban` 曾引用） |
| 角点禁点 | ✅ 两条连线都消失（测试：3×3 角 (0,0) 删 H(0,0)+V(0,0) 共 2 段） |
| 边界禁点 | ✅ 该处边界线段消失（测试：边 (0,1) 删 3 段） |
| 中心禁点 | ✅ 4 条连线消失（测试：中心 (1,1) 删 4 段） |
| 相邻禁点 | ✅ 消去线段为并集（测试：(0,0)+(0,1) 删 4 段） |
| 禁点为星位 | ✅ 星位小圆点不出现（星位判断 `not in banned_cv`） |
| 棋子/坐标标签/最后一手/hover | ✅ 不受影响（禁点不可落子无冲突；逐段画法不影响标签；hover 画圈不涉及网格线） |
| py_compile | ✅ gui.py 全过 |
| pytest 回归 | ✅ test_ban.py 41 passed（无回归） |
| 线段逻辑测试 | ✅ 6 项全过（空盘12段/角点删2段/中心删4段/边点删3段/相邻禁点并集/星位跳过） |
| 重新打包 | ✅ `dist\BanGo.exe` 11.05 MB（时间戳 10:28:11） |
| 行数变化 | gui 1212→1213(+1) |

**第十阶段验证（人vs人 标记死子 + UI 层数子）：**

| 项 | 结果 |
|----|------|
| **scoring.py 移植** | ✅ 1:1 移植 ban-engine.js scoreGame：BFS 空连通块独占判定 + 贴目公式（有效点/基准/黑>199.25/白>190.75） |
| dead_stones 参数 | ✅ 死子先从 stones 副本移除（不计任何一方），其位置变空点参与 BFS → 被围方独占空 |
| 禁点=棋盘外 | ✅ BFS 跳过 banned 点（不产气不占地），valid_points = rows*cols − len(banned) |
| result/winner | ✅ black_area > 199.25 → "B+0.75"；white_area > 190.75 → "W+0.25"；否则 "Draw" |
| detail 明细 | ✅ black_stones/white_stones/black_territory/white_territory/dead 五项 |
| scoring.py 自测 | ✅ 5 组 28 项全过（无死子独占空/死子移除变黑空/贴目.75+.25/双活中性/禁点不计地域） |
| **MARK_DEAD 状态常量** | ✅ `MARK_DEAD = "mark_dead"` 加入状态机 |
| dead_stones 实例属性 | ✅ init/new_game/_restart_engine 三处 `self.dead_stones = set()` |
| human_pass 双 pass 分支 | ✅ 人vs人 → MARK_DEAD 状态（不调引擎）；人vsAI/AIvsAI → _end_game（引擎 final_score） |
| on_click MARK_DEAD 分发 | ✅ `elif self.state == MARK_DEAD: self._on_dead_click(r, c)` |
| _canvas_to_1based 辅助 | ✅ `(self.rows - r, c + 1)` Canvas→1-based |
| _on_dead_click | ✅ 点击棋子→切换 dead_stones 集合（增/删）；点击空点→忽略；每次重绘+更新状态 |
| draw_board 死子标记 | ✅ MARK_DEAD 下对 dead_stones 中棋子叠红色 X（`cell*0.3` 半径，MARK_RED） |
| _confirm_dead | ✅ 调 `score_game(dict(self.board.stones), set(self.bc.banned), rows, cols, 4.25, set(self.dead_stones))` → _end_game_ui_scoring |
| _end_game_ui_scoring | ✅ 弹框显示结果+黑区(活子+独占空)+白区+中性空+死子+有效点+基准+胜负阈值，自动导出 SGF，不调引擎 |
| update_status MARK_DEAD | ✅ 显示「标记死子模式 — 点击死子标记/取消，确认后数子（已标记 N 个）」 |
| 确认数子按钮 | ✅ _build_ui 加按钮（command=_confirm_dead）；MARK_DEAD→NORMAL，其他→DISABLED |
| Pass/认输/暂停 MARK_DEAD | ✅ 自动 DISABLED（playing=False → human_turn=False → Pass DISABLED；认输条件不含 MARK_DEAD；暂停 ai_vs_ai=False） |
| 人vsAI 回归 | ✅ 双 pass 仍走 _end_game（引擎 final_score），不进 MARK_DEAD |
| AIvsAI 回归 | ✅ 双 pass 仍走 _end_game（引擎 final_score），不进 MARK_DEAD |
| py_compile | ✅ gui.py / scoring.py 全过 |
| pytest 回归 | ✅ test_ban.py 41 passed（无回归） |
| 逻辑测试 | ✅ 8 组 34 项全过（人vs人MARK_DEAD/人vsAI引擎回归/AIvsAI引擎回归/死子标记切换×3/按钮状态×5/其他状态禁用×2/_confirm_dead集成×6/on_click分发） |
| 重新打包 | ✅ `dist\BanGo.exe` 11.06 MB（时间戳 15:27:24） |
| 行数变化 | gui 1213→1283(+70) / scoring 新建 231 |
