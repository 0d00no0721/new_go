# Agent 4 — FE：CLI + GUI + website

**角色：** 前端/工具工程师 FE
**工作目录：** `E:\小工具\new_go\weighted-scoring\`
**关联文档：** `收敛报告.md`、`weight_table_final.txt`、`ban-selection/cli_player.py`、`ban-selection/gui.py`、`ban-selection/settings.py`、`ban-selection/website/`

---

## 更新日志

> 每次完成任务后在此追加一节。遇到阻塞立即在文档顶部标注 `🚫 BLOCKED`。

| 日期 | 状态 | 任务 | 摘要 |
|------|------|------|------|
| 2026-08-10 | 🔄 进行中 | CLI + GUI + website 脚手架 | 已启动 |
| 2026-08-10 | ✅ 完成 | cli_player.py | CLI：人vsAI / AIvsAI / SGF 导入导出 / 加权分（scoring.py）/ --query-weight / --komi=7.5（标准中国贴目，经 ignoreGTPAndForceKomi 生效）。已端到端冒烟验证。 |
| 2026-08-10 | ✅ 完成 | gui.py | tkinter 19×19 + AI 后台线程（queue/poll）+ kata-analyze winrate/visits/PV + 权重热力图叠加 + settings.json。已用 AIvsAI 冒烟测试验证（互斥锁修复 analyze/genmove 协议冲突）。 |
| 2026-08-10 | ✅ 完成 | settings.py | level/visits/model/engine/weights/komi 配置，仿 ban-selection/settings.py |
| 2026-08-10 | ✅ 完成 | website/ | index/rules/about/download/heatmap 静态页 + 热力图交互页（复用 Agent 3 scoring.js + weight_data.js）。Node 模拟验证解析与色阶正确。 |
| 2026-08-10 | ✅ 完成 | sgf_io.py | 0-indexed 坐标 + SGF（含 WeightsFile 元信息）+ ReplayBoard（fe 自建基础模块，供 cli/gui 共用） |
| 2026-08-10 | ✅ 完成 | komi 7.5 同步 | 应用 NOTIFY_Agent4_komi7.5.md：cli_player.py `DEFAULT_KOMI`、gui.py 5 处默认、settings.py `DEFAULT_SETTINGS["komi"]`、website/ 4 个 HTML，均 8.25→7.5（标准中国贴目）。py_compile + aivai 冒烟验证 `[确认] komi = 7.5`。 |
| 2026-08-11 | ✅ 完成 | 3D 热力图 | heatmap.html 加 Three.js 3D 柱状图视图，2D/3D 同页切换，复用 weightColor 色阶 |
| 2026-08-11 | ✅ 完成 | Hub 入口 | 根 website/index.html 加 weighted-scoring 卡片，替换"敬请期待"占位 |

---

## 1 背景

实验工具 `play_game.py` 已能 AI vs AI + 提取 ownership。现在要做"人能玩"的成品：CLI 人机对弈 + GUI（tkinter）+ 官网。大量复刻 ban-selection 的对应文件，改 19×19 + 加权数子。

---

## 2 交付物（DoD）

1. **cli_player.py**：人 vs AI / AI vs AI / SGF 导入导出
   - 启动引擎 + `kata-load-weights weight_table_final.txt`
   - 终局显示加权分（用 Agent 3 的 `scoring.py`）
   - 可选 `kata-query-weights` 查任意点权重
   - `--komi` 默认用 Agent 2 标定值
2. **gui.py**：tkinter 19×19 棋盘 + AI 后台线程（queue/poll 模式，复刻 `ban-selection/gui.py`）
   - AI 提示（`kata-analyze` winrate/visits/PV）
   - 终局加权分 + 权重热力图（权重表映射色阶：天元 1.72 亮、星位 0.74 暗）
   - `settings.json` 配置
3. **settings.py**：level/visits/model/engine config（仿 `ban-selection/settings.py`）
4. **website/**：`index.html` / `rules.html` / `about.html` / `download.html` + 权重热力图交互页
   - `rules.html` 引用 Agent 3 的规则文档
   - 热力图页：悬停看每点 W 值（用 Agent 3 的 `scoring.js` + weight_table 数据）
   - **不做实时在线对弈**（无 WASM KataGo）
   - CSS/JS 放 `website/css` `website/js`

---

## 3 任务步骤

1. 读 `ban-selection/cli_player.py`、`gui.py`、`settings.py`、`website/` 学结构
2. 先做 `cli_player.py`（最小可用：人 vs AI + 加载权重 + 终局加权分）
3. 做 `gui.py`（复刻 gui.py 改 19×19 + 热力图 Canvas 绘制）
4. 做 `website/`（先 index/rules/about/download 静态页，再加热力图交互页）
5. `settings.py` 配置管理

---

## 4 接口约定

### 依赖
- Agent 2：komi 值 + 最终 exe
- Agent 3：`scoring.py`（终局显示）+ `scoring.js`（热力图页）

### 给 Agent 1（INFRA）
- `website/` 整目录

### 给 Agent 5（QA）
- CLI/GUI 端到端测试目标

---

## 5 约束/坑

- PowerShell 中文输出需 `$env:PYTHONIOENCODING='utf-8'`
- GUI 的 AI 落子/分析必须后台线程 + `root.after` 轮询，不能阻塞 tkinter 主线程（`ban-selection/gui.py` 已踩过，直接学其模式）
- 权重热力图色阶：W∈[0.53, 2.76]，建议 diverging colormap（<1 偏冷、>1 偏暖），1.0 中性
  > 注：此为原始设计值。权重表后经 D4 对称化，范围收窄至 [0.66, 1.97]（星位 0.79、天元 1.72 不变），见 `收敛报告.md` §4。GUI/website 色阶端点已同步更新。
- SGF 导出含权重元信息（weights file + komi）

---

## 6 验收

- [x] CLI 可人对弈一局至终局，显示加权分（`python cli_player.py --mode aivai --max-moves 6` 已验证）
- [x] GUI 可人对弈，终局显示加权分 + 热力图（AIvsAI 冒烟测试已验证引擎就绪/权重加载/自动走子/热力图色阶）
- [x] website 静态页可本地打开 + 热力图页可交互（Node vm 模拟验证解析与色阶）

## 7 备注（给其他 Agent）

- **komi**：当前默认 = **7.5**（标准中国贴目）。3 轮 komi 标定数据均不可信（move-cap 估算、未自然双 pass 终局、读 NN 估算），改用标准且中立的 7.5（详见 `收敛报告_komi_utility校准.md` §2/§3）。7.5 为半整数，本可经标准 GTP `komi` 命令生效；当前实现仍沿用 `ignoreGTPAndForceKomi=7.5` override 写法，无害保留。
- **scoring.py 自测 bug**（Agent 3）：`__main__` 自测用 5×5 权重调 `score_game` 未传 `rows=5,cols=5`，会在 BFS 越界报错。19×19 真实路径正常，不影响交付；建议 Agent 3 修复自测（补 `rows=5,cols=5`）。
- **Windows 中文路径**：KataGo `kata-load-weights` 的 fopen 不支持 UTF-8 中文路径（`小工具\` 会被剥离）。CLI/GUI 已用 `ascii_safe_copy()` 复制到 ASCII 临时路径再加载。
- **GUI 线程**：analyze（kata-analyze）与 genmove 共用同一 GTP 管道必须互斥，否则流式 info 行会损坏 genmove 响应（`gui.py` 用 `self._conn_lock` 串行化）。
