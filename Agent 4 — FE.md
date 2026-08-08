# Agent 4 — FE：前端/工具工程师

**角色：** 前端/工具工程师 FE
**关联计划书：** `新规则实现计划书.md` §7.5（WP5）
**关联规则：** `新规则.md` §6（流程总览）

---

## 更新日志

> 每次完成任务后在此追加一节。遇到阻塞立即在文档顶部标注 `🚫 BLOCKED`。

| 日期 | 状态 | 任务 | 摘要 |
|------|------|------|------|

---

## 1 交付物

| 文件 | 说明 |
|------|------|
| （待填充） | CLI 对弈工具 |

---

## 2 进度跟踪

### 2.1 WP5 — 对弈工具 + 前端

- [ ] `GtpEngine` 类（subprocess + GTP 通信）
- [ ] Ban 阶段整合（调用 BanController）
- [ ] 正式对局流程（黑先交替 genmove）
- [ ] 终局判定（双方 pass / 认输）
- [ ] 数子判胜负（195 / 199.25 / 4.25）
- [ ] AI vs AI 模式
- [ ] 人 vs AI 模式
- [ ] SGF 导出（20×20 + ban 标记）
- [ ] 命令行参数解析

---

## 3 架构设计（待填充）

```
cli_player.py
├── GtpEngine 类 ── subprocess 管道通信
├── run_game() ──── Ban 阶段 + 正式对局流程
└── main() ──────── 命令行入口
```

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

- 暂无
