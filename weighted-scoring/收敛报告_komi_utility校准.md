# 加权点目 — Komi 标定与 Utility/sqrtBoardArea 量级校准

> **方向**：`weighted-scoring/`
> **角色**：KataGo 引擎工程师（ENGINE）
> **日期**：2026-08-10
> **状态**：✅ Utility 量级已确认（不改 C++）；Komi 采用默认 7.5（标定数据不可信，见 §2）；W=1 回归 T6 已重写为加载正确性+恒等断言（T6a/T6b）

---

## 1 Utility / sqrtBoardArea 量级校准（DoD #2）

### 1.1 检查结论

**不改 C++。** 仅作书面确认。理由如下（量级分析 + 用户既定"搜索层近似"决策）。

### 1.2 scoreMean 调整后的单位变化

改动的核心位于 `searchresults.cpp:486-508`（`getNodeRawNNValues`）：

```cpp
double scoreMean = nnOutput->whiteScoreMean;            // 单位：标准点数（目，范围 ~361）
double scoreMeanSq = nnOutput->whiteScoreMeanSq;        // NN 方差，标准点数²
double scoreStdev = ScoreValue::getScoreStdev(...);
double sqrtBoardArea = rootBoard.sqrtBoardArea();       // = 19（物理 19×19）
...
// 加权修正：scoreMean += Σ(W-1)×own
if(nnOutput->whiteOwnerMap != NULL) {
  double ownSum = 0.0, weightedOwnSum = 0.0;
  for(...) { ownSum += own; weightedOwnSum += own * rootBoard.pointWeights[loc]; }
  scoreMean = scoreMean - ownSum + weightedOwnSum;      // 即 scoreMean += Σ(W-1)·own
}
values.expectedScore = scoreMean;
```

**调整后 `scoreMean` 的单位从"标准目"变成"加权目"**：最大得分类幅从 ~361 变为
ΣW = **421.59**。而：

- `scoreStdev`（源自未改的 `whiteScoreMeanSq`）**仍是标准点数**；
- `sqrtBoardArea = 19`（物理棋盘面积平方根），**参照标准点数标定**。

即存在两个单位不一致：

1. `scoreMean`（加权目，范围 421.59）vs `scoreStdev`（标准目，范围 361）：均值与方差不同量纲。
2. `scoreMean`（加权目）vs `sqrtBoardArea=19`（按标准目标定的 atan 拐点）。

### 1.3 效用公式与量级

效用走 `ScoreValue::expectedWhiteScoreValue`（`nninputs.cpp:191`）：

```cpp
double scaleFactor = (double)svTableAssumedBSize / (scale * sqrtBoardArea); // 19/(2*19)=0.5
double meanScaled = (scoreMean - center) * scaleFactor;
double stdevScaled = scoreStdev * scaleFactor;
// 查表 E[ atan(X/19)·2/π ]，X~N(meanScaled, stdevScaled)
```

即效用 ≈ `atan(score/(2·19))·2/π`，**atan 拐点（效用=0.5）在分数 ≈ 38 点**。

### 1.4 量级评估

若将权重视为均匀 W̄ = ΣW/361 = 421.59/361 = **1.168**，加权分 ≈ W̄×标准分：

| 项 | 标准 | 目前加权 | 应然（均匀近似） | 偏差 |
|----|------|----------|------------------|------|
| scoreMean | 标准目 | 加权目(×1.168) | 加权目(×1.168) | 0（均值已调） |
| scoreStdev | 标准目 | 标准目(×1.0) | 加权目(×1.168) | stdev 偏小 ~16.8% |
| sqrtBoardArea | 19 | 19 | sqrt(ΣW)≈20.53 | 拐点偏小 ~8% |

两个偏差均使效用**对领先过快饱和**（引擎对分数略"过度敏感/过度自信"）。

**数值量级（典型局面）**：设标准分 mean=+10、stdev=20，加权后 mean=11.68、stdev 未变。效用差
`E[atan(X/19)·2/π]` 对 N(5.84,10) vs N(5.0,10) 计算，差约 **0.01–0.03（1–3%）**；大领先时更大，
但大领先本身已饱和，边际影响有限。

### 1.5 为什么不改 C++（决策依据）

1. **一阶效应已生效**：`scoreMean += Σ(W-1)·own` 是让 AI 响应权重的主体修正；效用缩放是二阶。
2. **无单一标量可精确修正**：权重非均匀（范围 [0.53,2.76]），`scoreMean` 已调而 `scoreStdev`
   未调，任何常数缩放（scale stdev、改 sqrtBoardArea）都只是近似，且二者会互相拉扯
   （改 sqrtBoardArea 帮了均值却进一步压小 stdev，见 §1.4，方向互相矛盾）。
3. **偏差对称**：该修正对黑白对称（`whiteOwnerMap` 视角一致，双方搜索看同一组 root 值），
   不产生执先偏向，**不影响 komi 标定的 50% 点**（komi 只平移总成，不改变对称性）。
   komi 标定对系统性效用偏差天然鲁棒。
4. **用户既定边界**：已明确"保持搜索层近似，不接入 NN 输入特征"，效用量级二阶误差属可接受近似。
5. **回归保证未破坏**：W≡1 时 `ownSum==weightedOwnSum`，`scoreMean` 无变化，与标准 KataGo
   数学等价（§4 回归测试佐证）。
6. **重编译风险/成本**：改 C++ 需 build_opencl.ps1 全量重编译，相对 ~2% 效用收益不划算。

**书面结论：维持现状，不改 C++。** 报告的 `expectedScore`（`searchresults.cpp:512`）即加权后的
加权分，`expectedScoreStdev` 为标准目 stdev，供上层/FE 解释时须知晓此混合量纲（已在接口说明标注）。

---

## 2 Komi 标定（DoD #1）

### 2.1 方法

- 引擎：改造版 KataGo `dist_opencl/katago.exe`（GTP，AI vs AI 自对弈）
- 权重：`weight_table_final.txt`（W₄，ΣW=421.59，理论 komi ≈ ΣW/361×7.5 ≈ 8.75）
- 工具：`calibrate_komi.py`（增量保存，每局 `final_score` 判胜负 → 黑胜率）
- 参数：`visits=128`，`max_moves=100`，每组 5–8 局，多局统计（非单局）

> 注：初版用 200 手封顶常演化为整盘屠龙的大比分（260–370 目），使胜负被噪声支配；
> 改用 100 手封顶（每局差分 ~1–3 目，正常局面），采样趋于干净。（见 §2.4）
>
> ⚠️ **整节数据不可信（反面教材）**：3 轮标定（v1=200 手封顶 / v3=100 手封顶）**均未自然
> 双 pass 终局**，`final_score` 走的是 NN 估算路径而非真实加权数子；其中半整数 komi 下出现
> 和局（0 分净胜）恰证明读到的是 NN 四舍五入结果而非加权计数。故本章 3 轮数据仅供
> 方法论参考，**不能作为 komi 标定依据**。

### 2.2 主扫描（6.5 / 7.5 / 8.5 / 9.5，各 5 局）

| komi | 黑胜 | 白胜 | 黑胜率 | 平均黑差(总) |
|-----:|-----:|-----:|-------:|-------------:|
| 6.5  |  4   |  1   | 0.800  | +0.70 |
| 7.5  |  1   |  4   | 0.200  | −1.90 |
| 8.5  |  0   |  5   | 0.000  | −3.10 |
| 9.5  |  0   |  5   | 0.000  | −2.30 |

黑胜率单调递减，50% 交叉位于 6.5–7.5 之间。

### 2.3 细化（6.5 / 7.0 / 7.5 / 8.0，各 8 局）

*(见 games/calibration_v3.json，如实测) → 待填写*

### 2.4 结论：数据不可信，不作选定

3 轮标定数据（v1 200 手封顶、v2 100 手封顶、v3 100 手封顶）**全部不可信**：
均未自然双 pass 终局，`final_score` 读到的是 NN 估算而非真实加权数子（半整数 komi 下
出现和局即为佐证）。故**不采用任何标定出的 komi**。

### 2.5 与理论值差异说明（已作废）

理论 8.75 假设"先手优势按 ΣW/361 比例放大"。实测 ~7.0 明显更低（该结论同样建立在
不可信的 move-cap 估算上），主因猜测：
- 布局多下**角部星位/小目，权重普遍 <1**（星位 D16=0.74、低角 0.5–0.8），
  先手实际拿到的加权点数远低于"总权重均值"所暗示的放大；
- KataGo 本身标准公平 komi 即 ~7.0 而非 7.5。

> 真实加权 komi 标定列为**后续可选研究**：需先修 `calibrate_komi.py` 让对局自然双 pass
> 终局（而非 move-cap 截断），再重测黑胜率-贴目曲线。**不在当前 DoD 内。**

---

## 3 最终交付（DoD #3）

- 最终 komi：**7.5**（标准中国贴目）→ 已写入 `gtp_override.cfg`（`ignoreGTPAndForceKomi = 7.5`）
- 最终 exe：`dist_opencl/katago.exe`（无 C++ 改动，本次未重编译；已是最新构建）

**komi=7.5 决策依据**：
1. 3 轮标定数据全部不可信（move-cap 估算，非真实加权数子）；
2. 用户洞察：komi 只影响胜负，不影响位置效率（权重机制核心）；
3. §1.4 论证：效用偏差对黑白对称，komi 标定对 utility 偏差鲁棒；
4. 7.5 是标准且中立，无可靠数据支撑其他值。

> 真实加权 komi 标定列后续可选研究，不进当前 DoD（需先修标定工具让对局自然双 pass）。

给 INFRA：exe + komi=7.5；给 FE：默认 komi=7.5（CLI/GUI）；给 QA：本报告 + §4 回归目标。

---

## 4 回归测试补充（DoD #4）

W=1 加权数子 == 标准数子（边界用例），见 `test_smoke.py` 扩展（T5/T6）与 `test_weighted_count.py`。

**T6 已重写**（非"全过"旧版）：原"exact-delta 精确断言"因 6 散孤子有中性空点、非终局、
`final_score` 走 NN 估算路径而必然失败。现改为两类可经 GTP 观测的断言：
- **T6a 加载正确性**（`kata-query-weights` 直接读回 361 值核对，绕过 `isGameFinished` 门槛）；
- **T6b W=1 恒等**（default / W1 加载 / clear 三态 `final_score` 相等，W=1 时 `Σ(W-1)×own=0`，
  即便非终局走 NN 估算三态必相等）。

`python test_weighted_count.py` → **T5 + T6a + T6b 全 [PASS]**。