# Agent 2 — ENGINE：引擎规则工程师

**角色：** 引擎规则工程师 ENGINE
**关联计划书：** `新规则实现计划书.md` §7.2（WP2）+ §7.3（WP3）
**关联规则：** `新规则.md` §3（正式对局）+ §4（胜负计算）

---

## 更新日志

> 每次完成任务后在此追加一节。遇到阻塞立即在文档顶部标注 `🚫 BLOCKED`。

| 日期 | 状态 | 任务 | 摘要 |
|------|------|------|------|
| 2026-08-08 | ✅ DONE | 源码克隆 | 克隆 KataGo v1.16.4 (commit 4b8de63) 到 `katago-src/` |
| 2026-08-08 | ✅ DONE | 源码通读 | 通读 Board/Rules/BoardHistory/NNPos/GTP 核心，定位全部改动点 |
| 2026-08-08 | ✅ DONE | 改动方案 | WP2+WP3 改动方案定稿（见 §3、§4） |
| 2026-08-08 | ✅ DONE | WP2 编码 | MAX_LEN 19→25 + komi override 验证（无源码改码，纯配置） |
| 2026-08-08 | ✅ DONE | WP3 编码 | banned_points + C_WALL 机制 + 数子修复 + NN输入修复 + 3 GTP命令 |
| 2026-08-08 | ✅ DONE | checkConsistency 修复 | 放宽断言允许 C_WALL 在棋盘内（banned 点），补 pos_hash 计算 |
| 2026-08-08 | ✅ DONE | 编译验证 | `build_opencl.ps1` 增量编译成功，无错误 |
| 2026-08-08 | ✅ DONE | 冒烟测试 | G1/G2/B1/F1 全部通过（见 §7） |

> **WP2+WP3 完成**。4 文件 ~90 行改动 + checkConsistency 修复（方案外发现）。编译通过，冒烟测试全绿。

---

## 1 交付物

| 文件 | 说明 | 状态 |
|------|------|------|
| `katago-src/` | KataGo v1.16.4 源码（INFRA 原应拉取，ENGINE 已自行克隆备用） | ✅ 就位 |
| `katago-src/cpp/game/board.h` | MAX_LEN 19→25 + banned_points set + 4 方法声明 | ✅ 完成 |
| `katago-src/cpp/game/board.cpp` | 4 方法实现 + 数子修复 + checkConsistency 修复 | ✅ 完成 |
| `katago-src/cpp/neuralnet/nninputs.cpp` | NN 输入 feature 0 修复（banned=off-board，5 处） | ✅ 完成 |
| `katago-src/cpp/command/gtp.cpp` | 3 个新 GTP 命令 + GTPEngine setBans/clearBans 方法 | ✅ 完成 |
| `dist_opencl/katago.exe` | 编译产物（v1.16.4 OpenCL，含禁点支持） | ✅ 已更新 |

---

## 2 进度跟踪

### 2.1 WP2 — 编译基础设施改造

- [x] 定位 `Board::MAX_LEN` 并调大至 20+（方案：19→25）
- [x] 排查 MAX_LEN 依赖的数组/模板，同步扩展（均用 MAX_ARR_SIZE，自动扩展）
- [x] 校验 NNPos / 网络棋盘上限，确认 20 路可用（方案：gtpForceMaxNNSize=true）
- [x] komi 4.25 注入（方案：ignoreGTPAndForceKomi=4.25，无需改码）
- [x] 20×20 × chinese 规则冒烟测试

### 2.2 WP3 — 禁点规则引擎

- [x] 禁点数据结构设计（Board 增加 `std::set<Loc> banned_points`）
- [x] 落子合法性方案（C_WALL 天然非法，零改动）
- [x] 气计算方案（C_WALL 天然不供气，零改动）
- [x] 提子 / 禁自杀 / 劫争方案（C_WALL 天然正确，零改动）
- [x] 数子方案（calculateArea/IndependentLifeArea 两处 +1 条件）
- [x] NN 输入方案（fillRowV3-V7 feature 0 修复）
- [x] 禁点数据结构（编码）
- [x] 落子合法性（编码 — C_WALL 天然非法，编译后验证通过）
- [x] 气计算（编码 — C_WALL 天然不供气，编译后验证通过）
- [x] 提子 / 禁自杀 / 劫争（编码 — C_WALL 天然正确，编译后验证通过）
- [x] 数子（编码）
- [x] 新 GTP 命令：`kata-set-bans`（编码）
- [x] 新 GTP 命令：`kata-clear-bans`（编码）
- [x] 新 GTP 命令：`kata-query-bans`（编码）
- [x] checkConsistency 修复（方案外：放宽断言允许 C_WALL 在棋盘内 + 补 pos_hash）
- [ ] 单元用例（气/提/劫/数子边界）（QA 矩阵依赖，后续配合）

> **关键结论**：C_WALL(=3) 是 KataGo 原生的"棋盘外"颜色。将禁点设为 C_WALL 后，
> 合法性/气/提子/劫争逻辑**零改动**自动正确。仅需修复数子（2 处）和 NN 输入（7 个 fillRow 版本）。

---

## 3 源码结构理解

### 3.1 MAX_LEN

- 文件路径：`cpp/game/board.h:14-16`
- 当前行号：15
- 当前值：`COMPILE_MAX_BOARD_LEN` 默认 19（可被编译参数覆盖）
- 依赖项：
  - `board.h:101` `MAX_LEN = COMPILE_MAX_BOARD_LEN`
  - `board.h:102` `DEFAULT_LEN = min(MAX_LEN,19)`
  - `board.h:103` `MAX_PLAY_SIZE = MAX_LEN * MAX_LEN`
  - `board.h:104` `MAX_ARR_SIZE = (MAX_LEN+1)*(MAX_LEN+2)+1`
  - 所有 Zobrist hash 表、chain_data、colors 等数组均用 `MAX_ARR_SIZE`，自动扩展
  - `nninputs.h:14` `NNPos::MAX_BOARD_LEN = Board::MAX_LEN`，自动跟随
- CMake 已有开关：`cpp/CMakeLists.txt:447-449`，`USE_BIGGER_BOARDS_EXPENSIVE=ON` 时定义 `COMPILE_MAX_BOARD_LEN=50`
- **方案**：直接改 `board.h:15` 默认值为 25（MAX_ARR_SIZE=703，Board 结构增 ~60%）

### 3.2 网络棋盘上限（NNPos）

- 文件路径：`cpp/neuralnet/nninputs.h:13-29`
- 当前值：`MAX_BOARD_LEN/MAX_BOARD_AREA/MAX_NN_POLICY_SIZE` 均跟随 `Board::MAX_LEN`
- 20 路是否可用：**是**，通过 padding 机制
- 机制：
  - GTP 默认 `nnXLen=boardXSize, requireExactNNLen=true`（gtp.cpp:466-468）
  - 配置 `gtpForceMaxNNSize=true` 时：`nnXLen=Board::MAX_LEN, requireExactNNLen=false`（gtp.cpp:470-474）
  - NNEvaluator 只要求 `board.x_size <= nnXLen`（nneval.cpp:734），小于时自动 pad
  - NN 输入遍历 `x<xSize, y<ySize`（nninputs.cpp:1693-1694），pad 区域为 0
- **方案**：配置 `gtpForceMaxNNSize=true`，20 路被 pad 到 25×25 送入 19 路训练网络

### 3.3 气计算逻辑

- 文件路径：`cpp/game/board.cpp`
- 关键函数：
  - `getNumImmediateLiberties()` :1095 — 只数 `C_EMPTY` 邻接 → **C_WALL 天然不供气**
  - `isSuicide()` :267 / `isIllegalSuicide()` :294 — 只匹配 C_EMPTY/pla/opp → **C_WALL 视为边界**
  - `playMoveAssumeLegal()` :1001 — 邻接只处理 pla/opp → **C_WALL 被忽略**
  - `changeSurroundingLiberties()` :1339 — 只匹配 pla → **C_WALL 被忽略**
  - `isLegal()` :452 — 要求 `colors[loc]==C_EMPTY` → **C_WALL 天然非法**
  - `isOnBoard()` :447 — 返回 `colors[loc] != C_WALL`
  - `calculateAreaForPla()` :1882 — BFS 只遍历 C_EMPTY/opp → **C_WALL 阻断 BFS**
- 改动点：**气/提/劫零改动**；仅 `calculateArea`(:1815) 和 `calculateIndependentLifeArea`(:1844) 各 +1 条件

### 3.4 数子逻辑

- 文件路径：`cpp/game/boardhistory.cpp:576` `countAreaScoreWhiteMinusBlack`
- 评分公式（:700）：`boardScore + whiteBonusScore + whiteHandicapBonusScore + rules.komi`
- `setFinalScoreAndWinner`（:667）：`>0 白胜, <0 黑胜, =0 和`，4.25 保证不和棋
- **countAreaScoreWhiteMinusBlack 无需改动**：只计 C_WHITE/C_BLACK，C_WALL(3) 自动排除
- 有效总点位 = 400 - 禁点数，自动正确

### 3.5 komi 机制

- GTP `komi` 命令：gtp.cpp:2333 检查 `komiIsIntOrHalfInt`，拒绝 4.25
- `ignoreGTPAndForceKomi` 配置：gtp.cpp:1937-1940，用 `cfg.getFloat()` 只做范围检查 [-150,150]，**不检查半整数**
- 评分直接用 `rules.komi` 浮点加法，4.25 无障碍
- **方案**：`-override-config ignoreGTPAndForceKomi=4.25`，完全绕过 GTP 校验，无需改码
- **注意**：`analysis.cpp:916` 仍校验半整数 → analysis 模式暂不支持 4.25，首期仅 GTP 对弈

### 3.6 GTP 命令注册

- 文件路径：`cpp/command/gtp.cpp`
- 命令列表：~line 29-53（静态数组）
- 命令处理：`if(command == "xxx") { ... }` 链式分支（~line 2265 起）
- `boardsize` 处理：:2271，校验 `newXSize > Board::MAX_LEN` 报错（:2303）
- `clear_board` 处理：:2312，调用 `engine->clearBoard()`（:585，新建 Board，禁点自动清除）
- `GTPEngine` struct：:334，持有 `bot/nnEval/currentRules/initialBoard`
- 注册方式示例：
  ```cpp
  // 命令列表添加（~line 46 附近）
  "kata-set-bans",
  "kata-clear-bans",
  "kata-query-bans",
  // 处理分支（~line 2359 附近）
  else if(command == "kata-set-bans") { ... }
  ```

---

## 4 改动方案

> 核心：利用 `C_WALL=3`（KataGo 原生"棋盘外"颜色）实现禁点。设禁点 = 设 C_WALL，
> 合法性/气/提/劫零改动，仅修数子 + NN 输入 + GTP 命令。

### 4.1 `cpp/game/board.h` — MAX_LEN + 禁点数据结构

| 行号 | 改动 | 意图 |
|------|------|------|
| 15 | `19` → `25` | 调大 COMPILE_MAX_BOARD_LEN 默认值 |
| ~312（Data 段） | 新增 `std::set<Loc> banned_points;` | 禁点集合 |
| ~165（Functions 段） | 新增方法声明 | 见下 |

新增方法：
```cpp
void setBannedPoint(Loc loc);        // C_EMPTY→C_WALL，更新 pos_hash，加入 set
void clearBannedPoints();            // 遍历 set 恢复 C_EMPTY，更新 pos_hash，清空
bool isBanned(Loc loc) const;        // 查 set
const std::set<Loc>& getBannedPoints() const;  // 返回 set
```

- pos_hash 更新：`setBannedPoint` 时 `pos_hash ^= ZOBRIST_BOARD_HASH[loc][C_WALL]`
- 拷贝：`operator= default`（:163），`std::set` + colors 数组自动深拷贝

### 4.2 `cpp/game/board.cpp` — 禁点方法 + 数子修复

| 行号 | 改动 | 意图 |
|------|------|------|
| 1819 | `if(result[loc] == C_EMPTY)` → `if(result[loc] == C_EMPTY && colors[loc] != C_WALL)` | calculateArea 不把 banned 标成棋子 |
| 1844 | `if(basicArea[loc] == C_EMPTY)` → `if(basicArea[loc] == C_EMPTY && colors[loc] != C_WALL)` | calculateIndependentLifeArea 同理 |
| 新增 | `setBannedPoint` / `clearBannedPoints` / `isBanned` / `getBannedPoints` 实现 | 禁点 API |

- `countAreaScoreWhiteMinusBlack`（boardhistory.cpp:603）**无需改动**：只计 C_WHITE/C_BLACK

### 4.3 `cpp/neuralnet/nninputs.cpp` — NN 输入 feature 0 修复

| 行号 | 改动 | 意图 |
|------|------|------|
| 1698-1699 | `setRowBin(rowBin,pos,0, 1.0f, ...)` 外加 `if(board.colors[loc] != C_WALL)` | fillRowV7：banned 点对 NN 视为 off-board |
| 同模式 | fillRowV3 / V4 / V5 / V6 同位置同样修复 | 所有 NN 输入版本一致 |

- 改动点：每个 fillRow 的 "Feature 0 - on board" 赋值处，加 C_WALL 判断
- 影响 7 处（V3/V4/V5/V6/V7 各 1 处），模式一致

### 4.4 `cpp/command/gtp.cpp` — 3 个新 GTP 命令

| 行号 | 改动 | 意图 |
|------|------|------|
| ~46（命令列表） | 添加 3 个命令字符串 | 注册命令名 |
| ~2359（处理链） | 添加 3 个 `else if` 分支 | 命令处理逻辑 |

```cpp
else if(command == "kata-set-bans") {
  // 解析 pieces 为 loc 列表，校验在棋盘内且为 C_EMPTY
  // 通过 bot->setPosition 重建带禁点的棋盘（需禁点方法支持 Board::setBannedPoint）
}
else if(command == "kata-clear-bans") {
  // 清除 rootBoard 禁点，重建棋盘
}
else if(command == "kata-query-bans") {
  // response = 空格分隔的 loc 字符串
}
```

- `clear_board`（:2312）/ `boardsize`（:2271）自动清禁点（新建 Board 无 banned_points）

### 4.5 运行配置（无需改码）

| 配置项 | 值 | 作用 |
|--------|----|----|
| `gtpForceMaxNNSize` | `true` | NN pad 到 MAX_LEN，支持 20 路 |
| `ignoreGTPAndForceKomi` | `4.25` | 绕过 GTP komi 校验，强制 4.25 贴子 |

### 4.6 改动量汇总

| 文件 | 改动量 | 性质 |
|------|--------|------|
| board.h | ~10 行 | MAX_LEN 改值 + set 成员 + 4 方法声明 |
| board.cpp | ~30 行 | 4 方法实现 + 2 处 +1 条件 |
| nninputs.cpp | ~7 行 | 7 处加 C_WALL 判断 |
| gtp.cpp | ~40 行 | 3 命令注册 + 处理逻辑 |
| **合计** | **~90 行** | 集中、低风险 |

---

## 5 对其他 Agent 的接口约定

### 对 RULES

ENGINE 实现的 GTP 命令（RULES 的 BanController 依赖）：

| GTP 命令 | 格式 | 说明 |
|----------|------|------|
| `kata-set-bans` | `kata-set-bans D4 K10 F7 ...` | 设定禁点集合 |
| `kata-clear-bans` | `kata-clear-bans` | 清空所有禁点 |
| `kata-query-bans` | `kata-query-bans` | 返回当前禁点 |
| `kata-analyze` | `kata-analyze interval 1` | 返回含 winrate 的分析行 |

### 对 FE

ENGINE 完成后，FE 可用改造后的 `katago.exe` 跑 20 路对局。

---

## 6 已知问题与后续工作

### 阻塞项

- 无（WP2+WP3 已完成）

### 冒烟测试后已验证项

- [x] MAX_LEN=25 编译通过，Board 结构体增大无问题
- [x] 20 路 + `gtpForceMaxNNSize=true` 的 NN 评估正常（genmove 可落子，19 路网络 pad 到 25×25 可用）
- [x] `kata-set-bans` 通过 `bot->setPosition` 重建棋盘可行（GTPEngine::setBans/clearBans 实现）
- [x] pos_hash 一致性（checkConsistency 通过，setBannedPoint/clearBannedPoints 正确更新 hash）
- [x] genmove 正确避开禁点（B→D4, W→R17，均非 D10/K10/F7）
- [x] clear_board / boardsize 自动清禁点
- [x] 19 路回归正常（komi 7.5、无禁点、标准棋盘）

### 仍待验证

- [ ] Board 频繁拷贝中 `std::set` 的性能开销（搜索内 Board 拷贝频繁，后续可优化为 bitmap）
- [ ] 数子终局测试（需跑完整对局到终局，QA 矩阵覆盖）
- [ ] NN 20 路评估质量（pad 到 25×25 边缘强度，需实战验证）

### 潜在风险

- **NN 20 路效果**：若 pad 到 25×25 边缘评估过弱，可改 MAX_LEN=20 + `requireExactNNLen=true`（精确匹配，但 NN 初始化尺寸=20）
- **analysis 模式 komi**：`analysis.cpp:916` 校验半整数，4.25 被拒。首期仅支持 GTP 对弈，analysis 模式二期处理
- **banned 点 Zobrist hash**：当前复用 C_WALL hash（`ZOBRIST_BOARD_HASH[loc][C_WALL]`）。真实墙点（棋盘外）也在用同一 hash 表，但 banned 点的 loc 不会与真实墙点 loc 重叠（真实墙点在 `x>=x_size || y>=y_size` 区域），故无冲突

### 后续优化（非首期）

- banned_points 用 bitmap 替代 `std::set`（减少拷贝开销）
- analysis 模式支持 4.25 komi（放宽 komiIsIntOrHalfInt 或加 quarter-int 支持）
- `isEmpty()` 在有禁点时返回 false（C_WALL != C_EMPTY）——逻辑正确但可能影响初始状态判断，需观察

---

## 7 冒烟测试结果（2026-08-08）

**环境**：`dist_opencl\katago.exe`（含禁点改造）+ `28b.bin.gz` + `default_gtp.cfg`
**配置覆盖**：`ignoreGTPAndForceKomi=4.25` + `gtpForceMaxNNSize=true` + `maxVisits=10`（加速）

| 编号 | 测试项 | 命令 | 预期 | 实际 | 结果 |
|------|--------|------|------|------|------|
| G1 | 20 路棋盘 | `boardsize 20` | `=` 接受 | `=` | ✅ |
| G2 | komi 4.25 override | `get_komi` | 返回 `4.25` | `4.25` | ✅ |
| G2b | GTP komi 仍拒 4.25 | `komi 4.25` | `?` 报错 | `? komi must be an integer or half-integer` | ✅（预期） |
| B1a | 设置禁点 | `kata-set-bans D10 K10 F7` | `=` | `=` | ✅ |
| B1b | 查询禁点 | `kata-query-bans` | `D10 K10 F7` | `D10 K10 F7` | ✅ |
| B1c | 棋盘显示禁点 | `showboard` | 3 个 `#` 标记 | D10/K10/F7 显示 `#` | ✅ |
| B1d | genmove 避开禁点 | `genmove B` | 合法点（非禁点） | `D4` | ✅ |
| B1e | 落子后禁点保留 | `kata-query-bans` | `D10 K10 F7` | `D10 K10 F7` | ✅ |
| B1f | 白棋也避开禁点 | `genmove W` | 合法点（非禁点） | `R17` | ✅ |
| B1g | 清除禁点 | `kata-clear-bans` | `=` | `=` | ✅ |
| B1h | 清除后查询 | `kata-query-bans` | 空 | 空 | ✅ |
| B1i | 单个禁点 | `kata-set-bans D10` | `=` + 查询 `D10` | `=` + `D10` | ✅ |
| B1j | clear_board 自动清 | `clear_board` → `kata-query-bans` | 空 | 空 | ✅ |
| B1k | boardsize 自动清 | `boardsize 19` → `kata-query-bans` | 空 | 空 | ✅ |
| F1 | 19 路回归 | `boardsize 19` + `komi 7.5` + `genmove B` | 正常落子 | `R16`，komi=7.5 | ✅ |
| F1b | 命令列表含新命令 | `list_commands` | 含 3 个新命令 | 含 `kata-set-bans` 等 | ✅ |

**结论**：WP2+WP3 全部验收项通过。引擎支持 20×20 棋盘、4.25 贴子、禁点设置/查询/清除，genmove 正确避开禁点，19 路行为与原版一致。

### 方案偏离记录

| 项 | 方案 | 实际 | 原因 |
|----|------|------|------|
| checkConsistency | 未列入改动 | **新增修复**（board.cpp:2374） | 搜索调用 checkConsistency，C_WALL 在棋盘内触发断言。放宽断言 + 补 pos_hash |
| 拷贝构造函数 | 未列入改动 | **新增 1 行**（board.cpp:131） | 手写 memcpy 拷贝不包含 `std::set`，需补 `banned_points = other.banned_points` |
| GTPEngine 方法 | 未列入改动 | **新增 setBans/clearBans**（gtp.cpp:602-640） | 需通过 setPositionAndRules 重建带禁点的搜索位置 |
