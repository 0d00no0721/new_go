# Agent 1 — INFRA：发布与部署

**角色：** 构建/发布工程师 INFRA
**工作目录：** `E:\小工具\new_go\weighted-scoring\`
**关联文档：** `收敛报告.md`、`weight_table_final.txt`、根 `AGENTS.md`

---

## 更新日志

> 每次完成任务后在此追加一节。遇到阻塞立即在文档顶部标注 `🚫 BLOCKED`。

| 日期 | 状态 | 任务 | 摘要 |
|------|------|------|------|
| 2026-08-10 | ⬜ 待启动 | — | 等 Agent 2（exe+komi）和 Agent 4（website）产出 |
| 2026-08-10 | ▶️ 进行中 | 工作流+zip脚手架+README+smoke | 见下方"本轮完成"；zip 组装与 Pages 联调仍阻塞 |
| 2026-08-10 | ✅ 完成 | README komi 填 7.5 + .gitignore | README 填 7.5；根 .gitignore 补 `*.err`/`*.pid`；Agent 2 exe+komi / Agent 3 规则文档 / Agent 4 website 均已就绪 |
| 2026-08-10 | ✅ 完成 | 删除 NOTIFY_Agent1（已落地） | 通知文件清理 |
| 2026-08-11 | ✅ 完成 | WeightedGo.exe 打包 | build.bat + WeightedGo.spec（仿 ban-selection），PyInstaller --onefile --windowed，dist\WeightedGo.exe 可双击启动，AIvsAI 模式可用 |

---

## 本轮完成（2026-08-10，部分进行中）

1. **deploy-website.yml 已改**（根 `.github/workflows/`）
   - `paths:` 增加 `weighted-scoring/website/**`
   - `Assemble site` 增加 `mkdir -p staging/weighted-scoring` + `cp -r weighted-scoring/website/. staging/weighted-scoring/`
   - 未破坏 hub（`website/`）+ ban-selection（`staging/ban-selection/`）部署
   - ⚠️ **未 push**：等 Agent 4 的 `website/` 就绪再一起 push 验证（避免 Pages 部署空目录）

2. **发布 zip 脚手架 `make_release.ps1` 已建**
   - 最终 zip 含：`katago.exe` + `OpenCL.dll` + `z.dll` + `weight_table_final.txt` + `default_gtp.cfg` + `gtp_override.cfg` + `加权点目围棋规则.md` + `README.md`
   - `weights/28b.bin.gz` 不附（太大），README 给下载链接 `E:\2026-01-07-win64-KataGo\weights\28b.bin.gz`
   - 对缺失产物给明确告警（BLOCKED），不静默跳过；build 目录含缺项即 `exit 1`

3. **发布 README.md 框架已建**（`README.md`）
   - 安装、运行命令（GTP + 三条新命令 + smoke test）
   - 权重表说明（关键值 + 格式 + 回归保证）
   - komi 说明：**已填 7.5**（标准中国贴目；标定数据不可信，见 `收敛报告_komi_utility校准.md` §2）

4. **smoke test 通过**：`python test_smoke.py` → **19 passed, 0 failed**

### 🚫 仍阻塞
- **zip 实际组装 + Pages 联调 push 验证**：唯一剩余阻塞
  - Agent 2 exe+komi 已就绪（komi=7.5，无 C++ 改动，无需重 `build_opencl.ps1`）→ 已解除
  - 规则文档 Agent 3 已交付 `加权点目围棋规则.md` → 已解除
  - website Agent 4 已交付 `weighted-scoring/website/` → 已解除
  - 待统一提交后：填 7.5 已在 `gtp_override.cfg` + README → 跑 `make_release.ps1` 组装 zip → push main 验证 Pages

---

## 1 交付物（DoD）

1. **发布 zip 包**：含 `katago.exe` + `OpenCL.dll` + `z.dll` + `weight_table_final.txt` + `default_gtp.cfg` + `gtp_override.cfg` + `README.md`（权重文件 `28b.bin.gz` 不附，README 给下载链接）
2. **GitHub Pages 工作流**：在【根目录】`.github/workflows/` 增补 weighted-scoring 部署（或并入现有 `deploy-website.yml`），部署 `weighted-scoring/website/` 到 `github.io/new_go/weighted-scoring/`
3. **发布 README.md**：安装、运行命令、权重表说明、komi 说明（komi 值待 Agent 2 给）
4. **dist_opencl/katago.exe 回归 smoke test** 通过（`kata-load-weights`/`kata-query-weights`/`final_score`）

---

## 2 任务步骤

1. 跑 `test_smoke.py` 验证现有 exe 加权 GTP 命令可用；记录结果
2. 等 Agent 2 给最终 komi 值后，写入 `gtp_override.cfg`（`ignoreGTPAndForceKomi` 或默认 komi）
3. 等 Agent 4 给 `website/` 后，组装发布 zip（目录结构：`katago.exe` + DLL 同级，`weights/` 给链接说明）
4. 在根 `.github/workflows/` 加 weighted-scoring 的 Pages 部署步骤
   —— **铁律：工作流文件必须在根目录**，GitHub Actions 不识别子目录里的工作流
5. push main 验证 Pages 部署成功（~30s）

---

## 3 接口约定

### 依赖
- Agent 2：最终 exe + komi 值
- Agent 3：规则文档（进发布包）
- Agent 4：`website/` 整目录

### 产出
- 发布 zip 路径 + Pages URL，告知 Agent 5 验收

---

## 4 约束/坑

- 工作流必须在根目录 `.github/workflows/`（AGENTS.md 铁律，hard-learned lesson）
- 权重文件 `28b.bin.gz` 太大不入库不入 zip
- `katago-src/` 和 `dist_opencl/` 均 `.gitignore`，勿提交
- 中文路径 `E:\小工具\` 不影响运行，但 weight_table 文件路径给引擎时用英文路径（如 `E:/katago_cache/`）更稳
- `build_opencl.ps1` 可用（build 已完成，本 agent 通常无需重编译，除非 Agent 2 改了 C++）

---

## 5 验收

- [ ] zip 解压到干净目录可运行 `katago.exe` + 加载权重表
- [ ] Pages 部署成功，URL 可访问
- [ ] smoke test 全过
