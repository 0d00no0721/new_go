# Agent 2 — ENGINE：komi + utility 标定

**角色：** KataGo 引擎工程师 ENGINE
**工作目录：** `E:\小工具\new_go\weighted-scoring\`
**关联文档：** `收敛报告.md`、`katago-src/cpp/`（已改造）、`play_game.py`、`iterate.py`、`build_opencl.ps1`

---

## 更新日志

> 每次完成任务后在此追加一节。遇到阻塞立即在文档顶部标注 `🚫 BLOCKED`。

| 日期 | 状态 | 任务 | 摘要 |
|------|------|------|------|
| 2026-08-10 | 🔄 进行中 | komi 标定 + utility 校准 | 已启动 |
| 2026-08-10 | ✅ 完成 | **全部子任务完成** | komi 报告（§2，数据不可信→7.5 由 PM 决策）/ utility 说明（§1）/ W=1 回归（T5+T6a+T6b 15/15 PASS）/ cfg 写入（ignoreGTPAndForceKomi=7.5）均交付，详见 §7 |
| 2026-08-10 | ✅ 完成 | §1 Utility 量级校准 | 书面确认：不改 C++（scoreMean 已调、stdev/sqrtBoardArea 未调，偏差对称，见收敛报告 §1） |
| 2026-08-10 | ✅ 完成 | Komi 标定（3 轮） | v1 200 手 / v3 100 手封顶均未自然双 pass → 数据不可信（见 §2），作反面教材 |
| 2026-08-10 | ✅ 完成 | T6 诊断 + 重写 | 根因：6 散孤子有中性空点，isGameFinished 恒 false，final_score 走 NN 估算四舍五入吞掉单点 Δ；tromp-taylor 无效；改用 kata-query-weights 加载正确性（T6a）+ W=1 恒等（T6b） |
| 2026-08-10 | ✅ 完成 | Komi 决策 | 采用 7.5（标准中国贴目），不采标定数据；真实加权 komi 标定列后续可选研究 |
| 2026-08-10 | ✅ 完成 | cfg 写入 | gtp_override.cfg 加 `ignoreGTPAndForceKomi = 7.5` |
| 2026-08-11 | ✅ 完成 | 搜索路径加权修复 | `addCurrentNNOutputAsLeafValue`（searchupdatehelpers.cpp:93）补 `(W-1)×ownership` 调整——原仅 `searchresults.cpp`（报告路径）有调整，MCTS 选点用 W=1；另改 `alwaysIncludeOwnerMap` 固定 true（search.cpp:85 + gtp.cpp:1209/1474）使叶子带 ownerMap。重编译+回归 pytest 19/19（44.57s）+ test_smoke 19/19 + test_weighted_count 15/15 PASS（实测复核 2026-08-11 15:19），AIvsAI PV 已变化（前 20 手含 F17 R3 Q3 S6 C6 D6 D7 E6 等非星位点，非全星位；天元 Q10 未入 PV） |

---

## 1 背景

实验阶段已完成 KataGo v1.16.4 全链路加权改造（~50 行 C++）：
- `board.h`/`cpp`：`Board::pointWeights[MAX_ARR_SIZE]` + `setPointWeights`/`resetPointWeights`/`getPointWeight`
- `boardhistory.cpp`：3 处数子 `±1` → `±pointWeights[loc]`，`int`→`double`
- `searchresults.cpp:486`（`getValuesFromNN`）：`scoreMean += Σ(W-1)×ownership`
- `gtp.cpp`：`kata-load-weights` / `kata-clear-weights` / `kata-query-weights`

回归保证：W=1 时数学等价标准 KataGo。产物 `dist_opencl/katago.exe` 可用。

用户已决定：**保持搜索层近似，不接入 NN 输入特征(18/19 板)**。

---

## 2 交付物（DoD）

1. **Komi 经验标定报告**：用 W₄ 权重跑多局 AI vs AI，测黑胜率-贴目曲线，标出胜率≈50% 的 komi（理论值 ≈ ΣW/361×7.5 ≈ 8.75，需实测）
2. **Utility/sqrtBoardArea 量级校准说明**：检查 `searchresults.cpp` 的 scoreMean 调整后与 `expectedScoreUtility` 的缩放是否匹配；不匹配则校准（可能改 C++ 并用 `build_opencl.ps1` 重编译）
3. **最终 komi 值**（写入 `gtp_override.cfg`）+ **最终 exe**（若有 C++ 改动）
4. **回归测试补充**：W=1 加权数子 == 标准数子（边界用例）

---

## 3 任务步骤

1. 用 `play_game.py` 跑 W₄ 多局（komi 扫描 6.5/7.5/8.5/9.5），统计黑胜率，拟合胜率=50% 的 komi
   —— 线程非确定性：每 komi 至少 5 局，看统计不是单局
2. 读 `searchresults.cpp:486` 附近，确认 scoreMean 调整量与 `expectedScoreUtility` 量级匹配
   —— 标准 KataGo 的 scoreMean 单位是"目"，加权后单位变成"W·目"，ΣW=421.59≠361，需确认 utility 缩放
3. 若需改 C++，改完用 `build_opencl.ps1` 重编译，跑 `test_smoke.py` 回归
4. 把标定 komi 写入 `gtp_override.cfg`，告知 Agent 1/Agent 4

---

## 4 接口约定

### 给 Agent 1（INFRA）
- 最终 exe（若有 C++ 改动）+ komi 值

### 给 Agent 4（FE）
- komi 值（CLI/GUI 默认 komi）

### 给 Agent 5（QA）
- komi 标定报告 + 回归测试目标

---

## 5 约束/坑

- `analysis.cpp` 可能对非半整数 komi 有校验（ban-selection 踩过 4.25 在 analysis 模式被拒），首期仅支持 GTP 对弈，analysis 模式二期处理
- 线程非确定性：20 线程即使 `nnRandomize=false` 也有 move 级非确定性，komi 标定看多局统计
- 中文路径：weight_table 文件放英文路径 `E:/katago_cache/` 给 `std::ifstream`
- `build_opencl.ps1` 内部经 `vcvars64.bat` 注入 MSVC 环境，普通终端 `cl`/`cmake` "not recognized" 属正常
- 构建中间目录 `E:\katabuild_ws\`（英文路径）

---

## 6 验收

- [x] komi 标定报告含胜率-贴目曲线 + 选定 komi 的胜率≈50% 验证（注：3 轮标定数据不可信，曲线见 §2 但不作选定依据；komi=7.5 由 PM 决策，依据见 §7.4）
- [x] utility 量级校准说明（无论改没改 C++，都需书面确认）（见收敛报告 §1、本文件 §7.2：不改 C++）
- [x] W=1 回归测试全过（T5 + T6a + T6b，15/15 PASS，见 §7.3）
- [x] 最终 komi 写入 gtp_override.cfg（`ignoreGTPAndForceKomi = 7.5`，见 §7.5）

---

## 7 收尾更新日志（Agent 2 接手前任 Agent 2，2026-08-10）

### 7.1 Komi 标定：3 轮 → 数据不可信

- **v1**（200 手封顶）：常演化为整盘屠龙大比分（260–370 目），胜负被噪声支配；
- **v3**（100 手封顶）：虽差分收敛到 ~1–3 目，但**仍未自然双 pass 终局**；
- **判定**：3 轮 `final_score` 全部走 NN 估算路径（非真实加权数子）。半整数 komi 下出现
  和局（0 分净胜）恰证明读到的是 NN 四舍五入结果。**全部数据作废**，仅留作方法论反面教材
  （见 `收敛报告_komi_utility校准.md` §2）。

### 7.2 Utility 量级校准（§1 完成）

- 结论：**不改 C++**。`scoreMean += Σ(W-1)×own` 已生效；`scoreStdev`/`sqrtBoardArea` 未随
  加权调整（仍标准点数量纲），导致对领先轻微过度饱和（~1–3%），但偏差对黑白对称，
  **不影响 komi 50% 点**。书面确认交付（`收敛报告` §1）。

### 7.3 T6 诊断 + 重写

- **根因**：6 颗散孤子产生大片中性空点，`isGameFinished` 恒为 false（终局判定要求棋盘
  完全归属、无中性空），故 `final_score` 走 NN 估算（四舍五入），单点权重 Δ 被吃掉；
- **tromp-taylor 无效**：它只改死子判定，不改终局判定；
- **解法**：改用 `kata-query-weights` 走**加载正确性**路径（绕过 isGameFinished 门槛），
  配合 **W=1 恒等**断言：
  - **T6a**：构造权重表（K10=3.0、A1/K17/T19/Q10/C3=2.0、其余 1.0），load 后 query 读回
    361 值逐点核对；
  - **T6b**：6 孤子盘面 + 双 pass，default / W1 加载 / clear 三态 `final_score` 相等
    （W=1 时 Σ(W-1)×own=0，即便非终局估算三态必相等）；
  - `python test_weighted_count.py` → **T5 + T6a + T6b 全 [PASS]**（15/15）。

### 7.4 Komi 决策：7.5（PM 已定）

1. 3 轮标定数据全部不可信（move-cap 估算，非真实加权数子）；
2. 用户洞察：komi 只影响胜负，不影响位置效率（权重机制核心）；
3. §1.4：效用偏差对黑白对称，komi 标定对 utility 偏差鲁棒；
4. 7.5 是标准且中立，无可靠数据支撑其他值。

**不再跑 `calibrate_komi.py`。** 真实加权 komi 标定列后续可选研究（需先修标定工具让对局
自然双 pass），不进当前 DoD。

### 7.5 cfg 写入

`gtp_override.cfg` 追加：
```
ignoreGTPAndForceKomi = 7.5
```

### 7.6 已通知

- **Agent 4（FE）**：`cli_player.py:58 DEFAULT_KOMI = 8.25` → 改为 `7.5`（见通知文件）；
- **Agent 1（INFRA）**：README.md 的 `<TBD>` 占位 → 填 `7.5`（见通知文件）。
