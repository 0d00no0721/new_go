# Agent 1 — INFRA：构建环境工程师

**角色：** 构建环境工程师 INFRA
**关联计划书：** `新规则实现计划书.md` §7.1（WP1）
**关联规则：** `新规则.md`

---

## 更新日志

> 每次完成任务后在此追加一节。遇到阻塞立即在文档顶部标注 `🚫 BLOCKED`。

| 日期 | 状态 | 任务 | 摘要 |
|------|------|------|------|
| 2026-08-08 | ⚠️ 进行中 | WP1 | 已拉取 KataGo 源码，工具链安装待完成 |

---

## 1 交付物

| 文件 | 说明 |
|------|------|
| `katago-src/` | KataGo 源码（shallow clone） |
| `build_opencl.ps1` | OpenCL 后端编译脚本（待建立） |
| `katago.exe` | 编译产物（待产出） |

---

## 2 进度跟踪

### 2.1 任务清单（WP1）

- [ ] 确认源码版本为 v1.16.4
- [ ] 安装 VS Build Tools（MSVC x64 + Windows SDK）
- [ ] 安装 CMake
- [ ] 配置 OpenCL 头文件/库
- [ ] 建立编译脚本 `build_opencl.ps1`
- [ ] 编译产出 `katago.exe`（OpenCL 后端）
- [ ] benchmark 验证（用现有权重）

### 2.2 验收标准

- `cl /?` 可用
- `cmake --version` 可用
- `katago.exe benchmark` 正常运行

---

## 3 环境信息

| 项 | 值 |
|----|-----|
| OS | Windows |
| GPU | NVIDIA RTX 5060 Laptop (Blackwell, 4GB) |
| 现有 KataGo 包 | `E:\2026-01-07-win64-KataGo\` |
| 现有权重 | `E:\2026-01-07-win64-KataGo\weights\28b.bin.gz` |
| 现有配置 | `E:\2026-01-07-win64-KataGo\katago_configs\default_gtp.cfg` |
| 工作目录 | `E:\小工具\new_go\` |
| 源码目录 | `E:\小工具\new_go\katago-src\` |

---

## 4 对其他 Agent 的接口约定

### 对 ENGINE

INFRA 完成后，ENGINE 可在 `katago-src/` 上进行源码改造并使用 `build_opencl.ps1` 编译验证。

---

## 5 已知问题与后续工作

- 暂无
