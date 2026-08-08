# Agent 2 — ENGINE：引擎规则工程师

**角色：** 引擎规则工程师 ENGINE
**关联计划书：** `新规则实现计划书.md` §7.2（WP2）+ §7.3（WP3）
**关联规则：** `新规则.md` §3（正式对局）+ §4（胜负计算）

---

## 更新日志

> 每次完成任务后在此追加一节。遇到阻塞立即在文档顶部标注 `🚫 BLOCKED`。

| 日期 | 状态 | 任务 | 摘要 |
|------|------|------|------|

---

## 1 交付物

| 文件 | 说明 |
|------|------|
| （待填充） | KataGo 源码改造 |

---

## 2 进度跟踪

### 2.1 WP2 — 编译基础设施改造

- [ ] 定位 `Board::MAX_LEN` 并调大至 20+（建议 25）
- [ ] 排查 MAX_LEN 依赖的数组/模板，同步扩展
- [ ] 校验 NNPos / 网络棋盘上限，确认 20 路可用
- [ ] komi 4.25 注入（绕过 GTP komi 限制）
- [ ] 20×20 × chinese 规则冒烟测试

### 2.2 WP3 — 禁点规则引擎

- [ ] 禁点数据结构（Board 增加 banned set）
- [ ] 落子合法性（isLegal / legalMoves 排除禁点）
- [ ] 气计算（禁点视作外边界）
- [ ] 提子 / 禁自杀 / 劫争（禁点邻接正确）
- [ ] 数子（area/territory 剔除禁点）
- [ ] 新 GTP 命令：`kata-set-bans`
- [ ] 新 GTP 命令：`kata-clear-bans`
- [ ] 新 GTP 命令：`kata-query-bans`
- [ ] 单元用例（气/提/劫/数子边界）

---

## 3 源码结构理解（待填充）

### 3.1 MAX_LEN

- 文件路径：
- 当前行号：
- 当前值：
- 依赖项：

### 3.2 网络棋盘上限（NNPos）

- 文件路径：
- 当前值：
- 20 路是否可用：

### 3.3 气计算逻辑

- 文件路径：
- 改动点：

### 3.4 GTP 命令注册

- 文件路径：
- 注册方式示例：

---

## 4 改动方案（待填充）

> 每个文件的改动点：路径 + 行号范围 + 改动意图

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

- 暂无
