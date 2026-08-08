# 20路Ban选围棋 — KataGo 实现

在 KataGo 上实现「20路Ban选围棋」变体规则的完整可玩实现。

## 项目简介

- **棋盘**：20×20 交叉点
- **两阶段**：Ban 选阶段（10 次禁点选择）→ 正式围棋对局
- **贴子**：黑贴 4.25 子（有效点位 390，基准 195）
- **AI**：基于 KataGo v1.16.4 源码改造，支持禁点规则与 20 路棋盘

## 文档

| 文档 | 说明 |
|------|------|
| [新规则.md](新规则.md) | 完整规则文档（V1.0 修订版） |
| [新规则实现计划书.md](新规则实现计划书.md) | KataGo 实现计划书（V0.1 草案） |
| [文件索引.md](文件索引.md) | KataGo 整合包文件分类索引 |

## 技术要点

- 必须重新编译 KataGo（预编译版 `Board::MAX_LEN=19`，拒绝 20 路）
- GTP `komi` 不接受 4.25，需通过 `-override-config` 或规则层实现
- 禁点（banned point）作为外边界参与气/提子/打劫/数子计算

## 目录结构（规划）

```
new_go/
├── katago-src/          # KataGo 改造源码（INFRA 拉取）
├── ban_controller.py    # Ban 阶段控制器（RULES）
├── player/              # CLI 对弈工具（FE）
├── tests/               # 测试用例（QA）
└── docs/                # 文档
```

## 开发角色

| 角色 | 职责 |
|------|------|
| INFRA | 构建工具链与环境 |
| ENGINE | KataGo 源码改造（MAX_LEN / 禁点 / komi） |
| RULES | Ban 控制器（序列 / 校验 / AI 选点） |
| FE | CLI 对弈工具 + SGF |
| QA | 测试与验收 |
