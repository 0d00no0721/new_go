# Agent 3 — RULES：scoring.py + JS 端口 + 规则文档

**角色：** 规则流程工程师 RULES
**工作目录：** `E:\小工具\new_go\weighted-scoring\`
**关联文档：** `收敛报告.md`、`weight_table_final.txt`、`ban-selection/scoring.py`（参考结构）

---

## 更新日志

> 每次完成任务后在此追加一节。遇到阻塞立即在文档顶部标注 `🚫 BLOCKED`。

| 日期 | 状态 | 任务 | 摘要 |
|------|------|------|------|
| 2026-08-10 | 🔄 进行中 | scoring.py + scoring.js + 规则文档 + 测试 | 已启动 |
| 2026-08-10 | ✅ 完成 | scoring.py + scoring.js + 规则文档 + test_scoring.py | 17/17 --slow 通过（含 W₄ 引擎一致性）；规则文档已核对 komi=7.5 |

---

## 1 背景

weighted-scoring 的"规则"不是阶段控制器（如 ban-selection 的 BanController），而是"加权 area scoring"——用位置权重表替代每点 1 目。本方向需要一个纯 Python 的 `scoring.py`，GUI/CLI/web 共用，并与改造引擎的 `final_score` 对照一致。

---

## 2 交付物（DoD）

1. **scoring.py**：纯 Python 加权 area scoring
   - 输入：`stones` dict `(row,col)->"B"/"W"`、`weights` 19×19、`komi`、`dead_stones`
   - BFS 数空（仿 `ban-selection/scoring.py`）+ 每点权重累加（子×W + 空×W）
   - 返回：`black_weighted` / `white_weighted` / `result` / `winner` / `detail`
2. **scoring.js**：JS 端口，与 scoring.py 1:1 对应（给 Agent 4 web 端用）
3. **加权点目围棋规则.md**：权重表说明、komi、回归保证（W=1≡标准）、ΣW=421.59 说明、"逆转金角银边"机制
4. **test_scoring.py**：单元测试
   - W=1 等价标准 area scoring
   - 已知终局加权分（手工算一个小盘面）
   - 边界：空盘、单子、全占
   - 与引擎 `final_score` 一致性（需起引擎，可标 `@pytest.mark.slow`）

---

## 3 任务步骤

1. 读 `ban-selection/scoring.py` 学结构（BFS 数空 + dead_stones 处理）
2. 读 `weight_table_final.txt` 确认格式（19 行 row-major，空格分隔）
3. 实现 `scoring.py`，加权累加：`black_score = Σ(黑子位置 W) + Σ(黑空位置 W)`
4. 移植 `scoring.js`（与 py 1:1，dict/set 用 JS Map/Set）
5. 写规则文档
6. 写 `test_scoring.py`，跑 pytest 验证

---

## 4 接口约定

### 给 Agent 4（FE）
- `scoring.score_game(...)` API（GUI 终局显示用）
- `scoring.js`（热力图页/网页终局展示用）

### 给 Agent 5（QA）
- `test_scoring.py` + 测试目标

### 给 Agent 1（INFRA）
- 规则文档进发布包

---

## 5 约束/坑

- `scoring.py` 不依赖引擎，纯 Python，可独立测试
- 与引擎 `final_score` 一致性是 Agent 5 验收项，需对齐 `dead_stones` 处理逻辑
- PowerShell 跑 pytest 中文输出需 `$env:PYTHONIOENCODING='utf-8'`
- `@pytest.mark.slow` 性能测试默认跳过，`--slow` 启用

---

## 6 验收

- [x] `test_scoring.py` 全过
- [x] `scoring.py` ↔ 引擎 `final_score` 在 W=1 时一致（Agent 5 复核）
- [x] 规则文档完整可读
