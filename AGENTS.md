# AGENTS.md — new_go（围棋新规则探索工作区）

> 本文件为 `E:\小工具\new_go\` 工作区指引。各方向的专属指引见对应子目录的 `AGENTS.md`。

## 这是什么

围棋新规则变体的探索工作区。每个子目录是一个独立方向，自包含规则文档、实现代码与测试。工作区其他项目（QuickPaste / go / website）见 `E:\小工具\AGENTS.md`。

## 方向

| 目录 | 方向 | 入手文档 |
|------|------|----------|
| `ban-selection/` | Ban 选围棋 | `ban-selection/AGENTS.md` → `ban-selection/进度总览.md` |

新增方向时在此表格追加一行，并在工作区根建对应子目录。

## 约定

- 每个方向**自包含**：自带 `AGENTS.md`、`README.md`、规则文档、源码、测试
- 方向间**不共享源码**，但可共享外部依赖（KataGo 权重、工具链等）
- GitHub 仓库 `0d00no0721/new_go` 为本工作区唯一远程仓库
- `ban-selection/website/` 经 GitHub Actions 部署到 `github.io/new_go/`
