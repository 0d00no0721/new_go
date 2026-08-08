# Agent 3 — RULES：Ban 阶段控制器实现报告

**角色：** 规则流程工程师 RULES
**日期：** 2026-08-08
**关联计划书：** `新规则实现计划书.md` §7.4（WP4）
**关联规则：** `新规则.md` §2（Ban选阶段规则）

---

## 1 交付物

| 文件 | 行数 | 说明 |
|------|------|------|
| `ban_controller.py` | 397 | Ban 阶段控制器全部逻辑 |
| `test_ban.py` | 342 | 配套测试（36 个用例，全部通过） |

---

## 2 架构概览

```
ban_controller.py
├── 坐标工具层 ── col_to_letter / letter_to_col / point_to_gtp / gtp_to_point
├── 数据层 ──── BanConfig / BanState / BanResult / BanPhaseResult
├── 校验器层 ── check_region / check_no_duplicate / check_connectivity
└── 控制器层 ── BanController（序列推进 + 双通道选点）
```

Ban 控制器独立于 KataGo C++ 编译，通过 GTP 协议的 `kata-set-bans` / `kata-clear-bans` / `kata-analyze` 命令与引擎交互。职责清晰：规则流程（控制器）与博弈引擎（KataGo）解耦，便于并行开发和独立测试。

---

## 3 坐标系统

20 路棋盘，1-based 行列，列用字母 A–U（跳过 I）：

| col | 1 | ... | 8 | 9 | 10 | ... | 19 | 20 |
|-----|---|-----|---|---|----|-----|----|----|
| 字母 | A | ... | H | J | K | ... | T | U |

**核心函数：**

```python
col_to_letter(1)   # → "A"
col_to_letter(20)  # → "U"
letter_to_col("J") # → 9
point_to_gtp(7, 4) # → "D7"
gtp_to_point("D7") # → (7, 4)
```

与 GTP 协议保持一致（大写字母+数字，如 `A1`、`U20`）。

---

## 4 可配置参数 `BanConfig`

```python
@dataclass
class BanConfig:
    board_size: int = 20            # 棋盘尺寸（1~MAX_LEN）
    ban_count: int = 10             # Ban 操作总次数
    sequence: str = "ABBAABBABA"    # 序列（每个字符代表谁执行该次 ban）
    region_row_min: int = 4         # 可 ban 区域：行下界
    region_row_max: int = 17        # 可 ban 区域：行上界
    region_col_min: int = 4         # 可 ban 区域：列下界
    region_col_max: int = 17        # 可 ban 区域：列上界
    max_violations: int = 3         # 违例上限（达到即判负）
    ai_candidate_sample: int = 20   # AI 评估时候选池抽样大小
```

`validate()` 方法在构造时自动校验参数合法性。

---

## 5 合法性校验器（三个独立校验器）

### 5a 区域校验 `check_region`

```python
def check_region(row: int, col: int, config: BanConfig) -> BanResult
```

- ban 点必须落在中间 14×14 区域（默认行 4–17，列 4–17）
- 外围边角（行 1–3、18–20；列 1–3、18–20）被拒绝
- 区域边界可配置

### 5b 不重复校验 `check_no_duplicate`

```python
def check_no_duplicate(row: int, col: int, banned: set) -> BanResult
```

- 禁止选择已标记为禁点的位置
- 简单集合成员检查，O(1)

### 5c 全局连通性校验 `check_connectivity`

```python
def check_connectivity(board_size: int, banned: set, new_ban: tuple) -> BanResult
```

**算法：BFS（广度优先搜索）**

1. 构建 `all_banned = banned | {new_ban}`
2. 收集所有可落子点（棋盘 1..board_size 范围内去掉所有禁点）
3. 从任意一个可落子点出发 BFS，沿四向（上下左右）遍历所有可到达的可落子点
4. 比较 `|visited|` 与 `|all_playable|`
   - 相等 → 连通性保持，合法
   - 不相等 → 棋盘被分割成多块互不可达区域，非法

**设计要点：**
- 边界（行列 <1 或 >board_size）视为自然障碍
- 允许制造局部小型空洞
- 复杂度：O(N²) 其中 N=board_size（每次 ban 都要检查，20×20=400 点，很快）
- 注意：连通性检查范围是整个棋盘的全部可落子点（含边角），不限于 ban 区域

---

## 6 Ban 控制器 `BanController`

### 6.1 状态管理

| 属性 | 类型 | 说明 |
|------|------|------|
| `banned` | `set[(row,col)]` | 当前已标记的禁点集合 |
| `history` | `list[BanState]` | Ban 事件历史记录 |
| `step` | `int` | 当前已完成的 ban 次数（0-based） |
| `violations` | `dict[str,int]` | 每位选手的违例计数 |
| `concluded` | `bool` | Ban 阶段是否已结束 |
| `conclusion_reason` | `str` | 结束原因：`"complete"` / `"violation_a"` / `"violation_b"` |

### 6.2 只读属性

| 属性 | 说明 |
|------|------|
| `current_player` | 当前轮到谁：从 `config.sequence[step]` 取 |
| `remaining` | 剩余 ban 次数 |
| `is_finished` | `concluded` 的别名 |

### 6.3 核心方法：`submit(row, col, source)`

提交一个 ban 点，流程：

1. 若 `concluded` → 直接拒绝
2. 依次运行三个校验器（区域 → 重复 → 连通性）
3. 任一校验失败 → 当前选手违例 +1，违例达上限则判负
4. 全部通过 → 禁点加入 `banned`，`step += 1`
5. 若 `step >= ban_count` → Ban 阶段正常结束

### 6.4 人类输入通道 `submit_label(label)`

```python
bc.submit_label("D7")  # → BanResult
```

接受 GTP 坐标字符串，解析为 `(row, col)` 后调用 `submit()`。自动校验坐标在棋盘范围内。

### 6.5 AI 自动选点

#### 策略一（保底）：`ai_pick_random()`

```python
def ai_pick_random(self) -> tuple[int, int]
```

- 调用 `_legal_candidates()` 收集所有合法候选（区域内 + 不重复 + 连通性通过）
- 从候选集中随机选一个
- 无条件可用，无外部依赖

#### 策略二（GTP 评估）：`ai_pick_gtp()`

```python
def ai_pick_gtp(self, top_n=1, prefer="own") -> Optional[tuple[int, int]]
```

- 从合法候选集中随机抽样 `ai_candidate_sample` 个（默认 20）
- 对每个候选：`kata-set-bans` 设定试禁点 → `kata-analyze` 分析 → 解析 `winrate`
- 根据当前选手视角（B 取 black winrate，A 取 white winrate），选胜率最高者
- `prefer="opponent"` 时翻转：选对敌方胜率最低（即最难应对）的点
- 需先 `set_gtp_engine(callable)` 注入 GTP 引擎接口

#### 统一入口：`ai_pick(strategy)`

```python
bc.ai_pick("random")  # 纯随机保底
bc.ai_pick("gtp")     # GTP 评估
bc.ai_pick("auto")    # 有 GTP 引擎则用 gtp，否则 fallback
```

#### 批量提交：`submit_ai(strategy)`

```python
bc.submit_ai()  # → BanResult，自动选点并提交一步
```

### 6.6 GTP 引擎注入接口

```python
bc.set_gtp_engine(my_engine_callable)
```

`my_engine_callable` 应为接受 GTP 命令字符串、返回 GTP 响应字符串的可调用对象。

---

## 7 违例处理

- 违例计数器分选手独立计数：`violations["A"]` 和 `violations["B"]`
- 每次非法 ban 后当前选手违例 +1
- 任一选手累计达到 `max_violations`（默认 3）→ 立即判负，Ban 阶段结束
- 违例时序列不推进（当前选手重新选点）
- `reset()` 清空所有计数

---

## 8 结果获取

```python
result = bc.get_result()  # → BanPhaseResult

print(result.banned_points)  # frozenset of (row, col)
print(result.history)        # list of BanState
print(result.concluded_by)   # "complete" | "violation_a" | "violation_b"
```

---

## 9 测试覆盖（36 个用例）

| 测试类 | 用例数 | 覆盖内容 |
|--------|--------|----------|
| `TestCoords` | 5 | col_to_letter / letter_to_col / point_to_gtp / gtp_to_point / roundtrip |
| `TestCheckRegion` | 4 | 区域内 / 行越界 / 列越界 / 自定义区域 |
| `TestCheckNoDuplicate` | 2 | 不重复 / 重复拒绝 |
| `TestCheckConnectivity` | 8 | 空棋盘 / 单禁点 / 小空洞 / 整行切断 / 边角点 / 角落绕行 / 整行阻断 / 整列阻断 |
| `TestSequence` | 4 | 默认序列 A→B→B→A→A→B→B→A→A→B / 自定义序列 / label 提交 / label 区域外 |
| `TestViolations` | 3 | 三次违例判负 / 分选手计数 / reset 清零 |
| `TestAIPick` | 5 | 随机始终合法 / 不重复 / auto fallback / mock GTP / 已结束拒绝 |
| `TestFullFlow` | 3 | 完整 10 次 ban / 重复拒绝 / 连通性阻止切割 |
| `TestConfig` | 2 | 区域越界校验 / 序列长度校验 |

运行命令：
```powershell
$env:PYTHONIOENCODING='utf-8'; python -m pytest test_ban.py -v
```

结果：**36 passed, 0 failed**

---

## 10 对其他 Agent 的接口约定

### 对 ENGINE（引擎规则工程师）

Ban 控制器依赖以下 GTP 命令（需 ENGINE 在 KataGo 中实现）：

| GTP 命令 | 格式 | 说明 |
|----------|------|------|
| `kata-set-bans` | `kata-set-bans D4 K10 F7 ...` | 设定禁点集合（空格分隔 GTP 坐标） |
| `kata-clear-bans` | `kata-clear-bans` | 清空所有禁点 |
| `kata-analyze` | `kata-analyze interval 1` | 返回含 `info ... winrate X.XX` 的分析行 |

### 对 FE（前端/工具工程师）

Ban 控制器提供的公共 API：

```python
from ban_controller import BanController, BanConfig

bc = BanController()                    # 或 BanController(BanConfig(...))
bc.current_player                       # "A" 或 "B"
bc.remaining                            # 剩余次数
bc.submit_label("D7")                   # 人类输入，返回 BanResult
bc.submit_ai()                          # AI 自动一步，返回 BanResult
bc.get_result()                         # 取最终结果
bc.reset()                              # 重置
```

---

## 11 已知限制与后续工作

1. **GTP 评估策略**：`ai_pick_gtp()` 当前仅解析 `winrate` 字段，未使用 `scoreLead` 等更精细指标。可在 ENGINE 的 `kata-analyze` 输出格式稳定后增强。
2. **候选池优化**：当前随机抽样 20 个候选，未做启发式预筛选（如中央优先、远离已有禁点）。可在二期叠加外部启发式。
3. **性能**：20×20 棋盘 BFS 遍历 400 点，单次 <1ms，满足实时交互需求。
4. **引擎联调**：当前使用 mock 引擎接口完成独立验证，待 ENGINE 的 `kata-set-bans` 就绪后进行联调。