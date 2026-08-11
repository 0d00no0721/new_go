# 加权点目围棋（weighted-scoring）— 发布说明

> 用位置权重表替代"每点 1 目"的标准数子，让"下天元"值得考虑。
> 权重表基于 KataGo 迭代收敛（见 `收敛报告.md`）。

---

## 1 安装

发布 zip 解压到任意目录，包含：

```
katago.exe              加权重改造引擎
OpenCL.dll / z.dll      运行时依赖
weight_table_final.txt  最终权重表（19×19）
default_gtp.cfg         引擎全局配置
gtp_override.cfg        本方向覆盖配置（含 komi）
加权点目围棋规则.md      规则文档
README.md               本说明
```

**权重文件 `28b.bin.gz` 不随包附带**（体积过大）。请自行下载后放到引擎同级的
`weights/` 目录（或用后文命令指定路径）：

> 下载：`E:\2026-01-07-win64-KataGo\weights\28b.bin.gz`（本地 KataGo 权重，约 2GB）

### 依赖要求
- Windows x64，需 OpenCL 驱动（NVIDIA/AMD/Intel 均可，脚本已按 `E:/katago_cache` 缓存 tuner）
- 首次运行会做 OpenCL tuner（可在 `gtp_override.cfg` 里改 `homeDataDir` 指向已缓存目录以加快启动）

---

## 2 运行命令

### 2.1 引擎自检（冒烟测试）

```powershell
# 先设编码，避免中文输出报错
$env:PYTHONIOENCODING='utf-8'
python .\test_smoke.py
```

### 2.2 走 GTP 协议对弈（接入 Sabaki / Lizzie / 自定义前端）

```
katago.exe gtp -config default_gtp.cfg -config gtp_override.cfg -model <权重路径>
```

例如：
```
katago.exe gtp -config default_gtp.cfg -config gtp_override.cfg -model weights\28b.bin.gz
```

> 未随包权重时，`-model` 指向你下载的 `28b.bin.gz` 绝对路径。

### 2.3 加载权重表（GTP 命令）

改造引擎新增三条 GTP 命令：

| 命令 | 作用 |
|------|------|
| `kata-load-weights <file>` | 加载权重表（361 个浮点数，row-major 19×19） |
| `kata-query-weights`      | 返回当前权重表（361 个值） |
| `kata-clear-weights`      | 恢复默认全 1.0（标准数子回归） |

引擎启动时若存在 `weight_table_final.txt` 并配置了自动加载，则开枱即生效；
否则用 `kata-load-weights weight_table_final.txt` 手动加载。

---

## 3 权重表说明

- 文件：`weight_table_final.txt`，19 行 × 19 个浮点数，row-major（行从上往下，列从左往右）。
- 语义：某点的权重大于 1 → 该点占领价值倍率提升；小于 1 → 降低。
- 定稿关键值（来自 `收敛报告.md`）：

| 位置 | W | 说明 |
|------|---|------|
| 星位 D16 | 0.74 | 角部高效，权重低 |
| 天元 K10 | 1.72 | 中央低效，权重高（逆转金角银边）|
| 一线 A19 | 0.76 | 一线适度低 |
| 三线边 K17 | 1.13 | 边中适度补偿 |

- 权重范围 `[0.53, 2.76]`，ΣW = 421.59（标准为 361）。
- **回归保证**：加载全 1.0 的表即等效标准数子规则。

---

## 4 Komi（贴目）说明

本方向在 `gtp_override.cfg` 里通过 `ignoreGTPAndForceKomi`（或默认 komi）强制
固定贴目，避免对局双方因 GTP 命令差异而失效。

- 当前默认：**7.5**（标准中国贴目；标定数据不可信，见收敛报告_komi_utility校准.md §2）
- 修改方式：编辑 `gtp_override.cfg` 中的 komi 相关行。

---

## 5 常见问题

- **OpenCL tuner 每次都要跑？** 已用 `E:/katago_cache` 缓存，勿删除该目录可复用。
- **想回归标准数子？** `kata-clear-weights`，或加载全 1.0 的表。
- **权重表格式错误？** 确保 361 个浮点数、空格/换行分隔均可。

---

## 6 变更记录

| 版本 | 日期 | 说明 |
|------|------|------|
| 1.0.0 | 2026-08-10 | 首次发布脚手架（komi 待定）|
| 1.0.1 | 2026-08-10 | komi 填 7.5（标准中国贴目）|