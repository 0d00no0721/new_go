# Agent 5 — QA：测试与验收

**角色：** 测试验收工程师 QA
**工作目录：** `E:\小工具\new_go\weighted-scoring\`
**关联文档：** `收敛报告.md`、`test_smoke.py`（已有）、`ban-selection/test_e2e.py`（参考）

---

## 更新日志

> 每次完成任务后在此追加一节。遇到阻塞立即在文档顶部标注 `🚫 BLOCKED`。

| 日期 | 状态 | 任务 | 摘要 |
|------|------|------|------|
| 2026-08-10 | 🔄 进行中 | 转进行中 | Agent 3（test_scoring 16/16）、Agent 4（cli_player 可用）已产出 |
| 2026-08-10 | ✅ 完成 | 补 W₄ ↔ 引擎一致性 | 新增 `test_engine_consistency_w4`：真实权重表下引擎 `final_score`==`scoring.py`（B+191.5），`--slow` 通过 |
| 2026-08-10 | ✅ 完成 | 写 CLI e2e | 新增 `test_e2e.py`：aivai 对局 + query-weights，验权重加载/komi 7.5/终局加权分/SGF，`--slow` 通过 |
| 2026-08-10 | ✅ 完成 | 建验收矩阵 | 新建 `验收矩阵.md`，签署 ✅ 项，⏳ 项标待依赖 |
| 2026-08-10 | ✅ 完成 | komi 7.5 同步重跑 | test_e2e 断言改 7.5；test_scoring/test_e2e/test_weighted_count/test_smoke 四项 --slow 全过 |
| 2026-08-11 | ✅ 完成 | #10/#11 文案修正 | 证据从"Agent 4 未签署"改为"已签署，待独立验证"（Agent 4 FE.md §6 已签署） |

---

## 1 背景

实验阶段 `test_smoke.py` 已有 17/19 通过（验证 GTP 命令注册、权重加载/查询/清空、空盘 scoring）。现在要把测试补成验收矩阵，覆盖成品（CLI/GUI/website/发布包）。

---

## 2 交付物（DoD）

1. **test_e2e.py**：端到端测试
   - 起引擎 → `kata-load-weights` → 下几手 → 终局 → 加权分
   - `scoring.py` ↔ 引擎 `final_score` 一致性对照（W=1 和 W₄ 各一局）
2. **test_scoring.py 回归补充**（与 Agent 3 协作）：
   - W=1 等价标准 area scoring
   - 已知小盘面手工算加权分
3. **komi 标定验证**（依赖 Agent 2）：选定 komi 下黑胜率 ≈50%
4. **验收矩阵**（DoD 清单表格）：列所有交付物 + 通过/未通过 + 证据
5. **回归**：`test_smoke.py` 全过（补齐之前 2 个未过项）

---

## 3 任务步骤

1. 先跑现有 `test_smoke.py`，确认基线
2. 等 Agent 3 的 `scoring.py` 后，写一致性对照测试
3. 等 Agent 2 的 komi 标定后，验证胜率
4. 等 Agent 4 的 CLI/GUI 后，写 e2e
5. 汇总验收矩阵

---

## 4 接口约定

### 依赖
- 所有 agent 交付物

### 给 PM
- 验收矩阵签署

---

## 5 约束/坑

- PowerShell 跑 pytest 中文输出需 `$env:PYTHONIOENCODING='utf-8'`
- `@pytest.mark.slow` 性能测试默认跳过，`--slow` 启用
- 线程非确定性：一致性测试看加权分总量级，不看单点 ownership
- 引擎起停慢，e2e 用 fixture `scope=session` 复用引擎
- **引擎坑（QA 实测发现）**：`clear_board` 会把 `pointWeights` 重置回 1.0 → 「加载权重后再 clear_board」会使 `final_score` 回退 W=1。正确顺序：**先 clear_board 再 `kata-load-weights`**（`cli_player.py` 引擎初始化即先 clear 后 load，符合）
- 一致性对照用**确定性可精确数子**的盘面（黑整列+白整列+双 pass）；`final_score` 对非正式终局局面返回搜索 lead 估计（非确定性），勿作精确断言

---

## 6 验收

- [x] `test_scoring.py` 16/16（W=1）→ 17/17（含本次 W₄ 用例）`--slow` 全过
- [x] `test_e2e.py` CLI 端到端 2/2 `--slow` 全过
- [x] 验收矩阵 `验收矩阵.md` 已建并签署 ✅ 项；⏳ 项（komi 标定 / GUI / 发布包）待对应 Agent 完成

### 测试命令

```powershell
cd weighted-scoring
$env:PYTHONIOENCODING='utf-8'; python -m pytest test_scoring.py -q --slow
$env:PYTHONIOENCODING='utf-8'; python -m pytest test_e2e.py -q --slow
```

> 引擎一致性 + e2e 均为 `@pytest.mark.slow`，需 `--slow` 才跑（起引擎慢）。
