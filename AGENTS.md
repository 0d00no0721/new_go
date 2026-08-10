# AGENTS.md — new_go（围棋新规则探索工作区）

> 本文件为 `E:\小工具\new_go\` 工作区指引。各方向的专属指引见对应子目录的 `AGENTS.md`。工作区其他项目（QuickPaste / go / website）见 `E:\小工具\AGENTS.md`。

## 这是什么

围棋新规则变体的探索工作区。每个子目录是一个独立方向，自包含规则文档、实现代码与测试。GitHub 仓库 `0d00no0721/new_go`。

## 方向

| 目录 | 方向 | 入手文档 |
|------|------|----------|
| `ban-selection/` | Ban 选围棋 | `ban-selection/AGENTS.md` → `ban-selection/进度总览.md` |
| `position-value-research/` | 位置价值研究（前置研究）| `position-value-research/README.md` |

新增方向时在此表格追加一行，并在工作区根建对应子目录。

## 约定

- 每个方向**自包含**：自带 `AGENTS.md`、`README.md`、规则文档、源码、测试
- 方向间**不共享源码**，但可共享外部依赖（KataGo 权重、工具链等）
- 构建产物（`dist/` `dist_opencl/` `katago-src/` `build/`）均 `.gitignore`，不入库

## GitHub Pages 部署（关键）

- 工作流文件 **必须在根目录** `.github/workflows/`（GitHub Actions 不识别子目录里的工作流——这是 hard-learned lesson）
- 工作流将根 `website/`（hub 首页）+ `ban-selection/website/`（方向站点）合并部署
- 线上 URL 结构：hub 在 `github.io/new_go/`，ban-selection 在 `github.io/new_go/ban-selection/`
- 改 `ban-selection/website/` 后 push main 即自动部署（~30s）

## 测试

```powershell
cd ban-selection
$env:PYTHONIOENCODING='utf-8'; python -m pytest test_ban.py -q
```

- PowerShell 下中文输出**必须**先设 `$env:PYTHONIOENCODING='utf-8'`，否则报 cp950 编码错
- 无 lint / typecheck；语法验证用 `python -m py_compile *.py`
- `@pytest.mark.slow` 性能测试默认跳过，`--slow` 启用

## Tags / Releases

- Tag 命名：`<方向名>-v<版本>`（如 `ban-selection-v1.0.1`）
- Release 附 zip 含 exe + 改造版 katago.exe + DLL + 配置 + README（权重文件太大不附，给下载链接）
