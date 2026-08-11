# AGENTS.md — weighted-scoring（加权点目围棋）

> 本方向技术指引。PM 状态见 `进度总览.md`，迭代细节见 `收敛报告.md`。
> 工作区级指引见根 `AGENTS.md`。

## 这是什么

用位置权重表 W(P)（19×19）替代"每点 1 目"的标准数子：`加权分 = Σ(子×W) + Σ(空×W)`。
角部 W<1（高效，压低）、中央 W>1（低效，补偿），逆转"金角银边"，让下天元值得考虑。
ΣW=421.59（标准 361），范围 [0.66, 1.97]，天元 K10=1.72、星位 D16=0.79。
基于 KataGo v1.16.4 改造引擎（~50 行 C++）+ CLI/GUI + 静态官网。

## 引擎改造（KataGo v1.16.4，katago-src/ gitignored）

| 位置 | 改动 |
|------|------|
| `board.h`/`board.cpp` | `Board::pointWeights[MAX_ARR_SIZE]` + `setPointWeights`/`resetPointWeights`/`getPointWeight` |
| `boardhistory.cpp` | 3 处数子 `±1` → `±pointWeights[loc]`，`int`→`double` |
| `searchresults.cpp:486` | `scoreMean += Σ(W-1)×ownership`（报告路径：日志/analyze 显示值）|
| `searchupdatehelpers.cpp:93` | `addCurrentNNOutputAsLeafValue` 加 `(W-1)×ownership` 调整（**搜索路径：驱动 MCTS 选点**）|
| `search.cpp:85` + `gtp.cpp:1209/1474` | `alwaysIncludeOwnerMap` 固定 `true`（叶子需 ownerMap 才能调整）|
| `gtp.cpp` | 3 条新命令（见下）|

**回归保证**：W≡1 时 `Σown == Σ(W×own)`，数学等价标准 KataGo。

**GTP 命令**：
- `kata-load-weights <file>` — 加载 361 浮点（row-major 19×19）
- `kata-query-weights` — 返回当前 361 值
- `kata-clear-weights` — 重置为 1.0

## 关键坑（hard-learned）

- **`clear_board` 会重置 `pointWeights` 为 1.0** → 必须先 `clear_board` 再 `kata-load-weights`，顺序反了 `final_score` 回退 W=1。`cli_player.py` 引擎初始化已按此顺序；`gui.py` `new_game()` 已在 `clear_board` 后补 `load_weights` 重载（2026-08-11）。

- **`final_score` 对非终局局面返回 NN 估算**（非确定性、四舍五入），不是真实加权数子。确定性对照需用强制终局盘面（如黑整列+白整列+双 pass，令 `isGameFinished=true`）。半整数 komi 下出现和局 = 读到 NN 估算的佐证。

- **CLI/GUI 动态追加 `ignoreGTPAndForceKomi={komi}`**（`cli_player.py:392` / `gui.py:604`），**覆盖** `gtp_override.cfg`。有效 komi 跟随代码里的 `DEFAULT_KOMI`（`cli_player.py:58`）+ `gui.py` 5 处默认 + `settings.py`，**改 cfg 无效**。改 komi 要改代码。

- **komi=7.5 是 PM 决策，非标定结果**。3 轮标定数据全部不可信（move-cap 截断、未自然双 pass、读 NN 估算）。真实加权 komi 标定是后续可选研究，**不要重新跑 `calibrate_komi.py`** 期望得到可用值（需先修工具让对局自然双 pass）。

- **Windows 中文路径致 KataGo `fopen` 失败**：`kata-load-weights` 无法打开 `小工具\` 下的文件。CLI/GUI 用 `ascii_safe_copy()` 复制权重表到 ASCII 临时路径（如 `E:\katago_cache\`）再加载。改加载逻辑时保留此处理。

- **Utility/sqrtBoardArea 未随加权调整**：`scoreMean` 单位是加权目（421.59），但 `scoreStdev`/`sqrtBoardArea` 仍是标准目（361）。偏差 ~1-3% 对黑白对称，不影响 komi 50% 点。**决策：不改 C++**（无单一标量可修正，重编译成本高）。

- **加权调整原误放报告函数**：`searchresults.cpp:486` 的 `scoreMean += Σ(W-1)×ownership` 只改报告值（日志/analyze），不驱动 MCTS 选点。搜索路径 `searchupdatehelpers.cpp` 的 `addCurrentNNOutputAsLeafValue` 漏改 → AI 实际用 W=1 选点，「AI 对 AI 看不出区别」。已在 `addCurrentNNOutputAsLeafValue` 补同样调整（2026-08-11）。

- **`alwaysIncludeOwnerMap` 必须为 `true`**：加权调整依赖叶子节点的 `whiteOwnerMap`，但 `alwaysIncludeOwnerMap` 默认 `false` → genmove 时叶子无 ownerMap，调整被跳过。已改 `search.cpp:85` 默认 `true` + `gtp.cpp:1209/1474` 两处 `false→true`（2026-08-11）。

## 权重表

- 文件：`weight_table_final.txt`，19 行 × 19 浮点（6 位小数），row-major，空格分隔。行 0 = 顶部（GTP 行 19），列 0 = 最左（A）。
- **D4 对称化是强制的**：`iterate.py` 的 `d4_symmetrize()` 在 `avg_ownership()` 后立即做 8 重轨道平均（`w_old` 加载后也对称化）。对局噪声 + 线程非确定性会使对称点估值不一致；对称化保 ΣW 不变。**重新跑迭代不要删此步骤**。
- 重新生成：`python iterate.py <games.json> <out.txt> --w-old <prev.txt> --beta 0.5`（games.json 含 ownership）
- `gen_weight_table.py` 只生成 W=1 基线（全 1.0），非最终权重。

## 测试

```powershell
cd weighted-scoring
$env:PYTHONIOENCODING='utf-8'
python -m pytest test_scoring.py test_e2e.py -q --slow   # 引擎一致性 + e2e（17+2）
python test_smoke.py                                      # GTP 命令（19，需引擎）
python test_weighted_count.py                             # T5/T6a/T6b（15，需引擎）
python -m py_compile *.py                                 # 语法检查（无 lint/typecheck）
```

- **`@pytest.mark.slow` 默认跳过**（`conftest.py`），`--slow` 启用。引擎测试（一致性/e2e）全标 slow，起引擎慢。
- 测试用 W=1 表（不变）或 `score_game(..., REAL_W, ...)` 动态读表 + 不等式断言（`!= "B+163.5"`）+ 一致性断言（`engine == mine`）。改权重表后测试不会破，但 `验收矩阵.md` #3 的具体 final_score 值需重测更新。
- W4 一致性盘面：黑整列 col10 + 白整列 col19 + 双 pass → 当前 B+196.9（对称化后）。

## 打包

- `build.bat` + `WeightedGo.spec`（PyInstaller `--onefile --windowed`）→ `dist\WeightedGo.exe`。仿 `ban-selection/build.bat`。`dist/` gitignored。
- `make_release.ps1` 打 release zip：katago.exe + OpenCL.dll/z.dll + weight_table_final.txt + configs + README。**权重文件 `28b.bin.gz` 不附**（~2GB），README 给下载链接。
- GUI 模式：人vsAI / **AIvsAI**（下拉选，有暂停/继续）/ 人vs人。引擎后台线程（queue/poll + `root.after`），analyze/genmove 须互斥（共用 GTP 管道）。

## Agent 协作文档

本方向用 PM/agent 协作模型，修改时回填对应文档：
- `进度总览.md` — PM 全局状态（Agent 状态表 / 决策记录 / 交付物清单）
- `Agent N — *.md`（N=1..5）— 各 agent 任务文档，含更新日志。改某 agent 职责域的代码后在其文档追加日志行。
- `NOTIFY_AgentN_*.md` — 跨 agent 通知，**应用后删除**（勿入库）。
- `验收矩阵.md` — QA 验收清单（#1-#12），改测试/权重后更新对应项证据。
- `收敛报告.md` / `收敛报告_komi_utility校准.md` — 迭代与标定细节。

## 外部依赖（工作区共享，不入库）

| 项 | 路径 |
|----|------|
| KataGo 权重 | `E:\2026-01-07-win64-KataGo\weights\28b.bin.gz`（~2GB）|
| 引擎基础配置 | `E:\2026-01-07-win64-KataGo\katago_configs\default_gtp.cfg` |
| OpenCL tuner 缓存 | `E:\katago_cache\`（勿删，复用 tuner）|
| 构建中间目录 | `E:\katabuild_ws\`（英文路径，MSVC）|
| vcpkg | `E:\vcpkg`（opencl/zlib）|
| 改造源码 | `weighted-scoring/katago-src/`（gitignored）|
| 编译产物 | `weighted-scoring/dist_opencl/katago.exe`（gitignored）|
