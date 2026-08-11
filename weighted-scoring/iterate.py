#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迭代分析 + 权重表生成。

输入：多局对局 JSON（含 ownership）
输出：
  1. 各位置平均 |ownership|（占领频率）
  2. 新权重表 W_new = clamp(C / |own_avg|, Wmin, Wmax)
  3. 预测的加权贡献 |own| × W_new（应比 W=1 更均匀）

用法：
  python iterate.py <games_json> <out_weight_table> [--clamp-max 3.0] [--alpha 1.0]
"""
import json, sys, argparse, statistics

N = 19


def dist_to_edge(r, c):
    return min(r, N-1-r, c, N-1-c)


def in_corner(r, c):
    return (r < 6 or r > 12) and (c < 6 or c > 12)


def region_of(r, c):
    d = dist_to_edge(r, c)
    if d < 2: return "low12"
    if d in (2, 3): return "corner34" if in_corner(r, c) else "edge34"
    return "center"


def load_games(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def avg_ownership(games_data):
    """计算各位置平均 |ownership|（跨多局）。返回 361 列表。"""
    own_sums = [0.0] * (N * N)
    count = 0
    for game in games_data["games"]:
        own = game.get("ownership")
        if own is None or len(own) != N * N:
            continue
        for i in range(N * N):
            own_sums[i] += abs(own[i])
        count += 1
    if count == 0:
        return None, 0
    return [s / count for s in own_sums], count


def d4_symmetrize(values):
    """对 19×19 逐位置值做 D4 对称化（8 重对称轨道平均）。

    棋盘 D4 群 = 4 旋转 × 2 镜像 = 8 个对称对应点。逐位置独立采样会因
    对局噪声/线程非确定性使对称点得到不一致估值，导致权重矩阵不对称。
    对每个位置的 D4 轨道取算术平均，保证 ΣW 不变（轨道内平均保总量）。
    """
    sym = [0.0] * (N * N)
    for r in range(N):
        for c in range(N):
            orbit = {(r, c), (c, N - 1 - r), (N - 1 - r, N - 1 - c),
                     (N - 1 - c, r), (N - 1 - r, c), (r, N - 1 - c),
                     (c, r), (N - 1 - c, N - 1 - r)}
            vals = [values[rr * N + cc] for rr, cc in orbit]
            avg = sum(vals) / len(vals)
            for rr, cc in orbit:
                sym[rr * N + cc] = avg
    return sym


def design_weights(own_avg, clamp_max=3.0, alpha=1.0, target=None, w_old=None, beta=0.5):
    """设计权重表。
    模式 1（无 w_old）: W(P) = clamp((C / |own(P)|)^alpha, 1/clamp_max, clamp_max)
    模式 2（有 w_old，阻尼迭代）: W_new = clamp(W_old × (C / contrib_old)^beta, ...)
      其中 contrib_old = |own| × W_old，C = target 贡献（中位 contrib_old）
      beta < 1 防止过冲（默认 0.5）
    """
    valid = [o for o in own_avg if o > 0.01]
    if not valid:
        return [1.0] * (N * N)

    if w_old is not None:
        # 阻尼迭代模式
        contrib_old = [own_avg[i] * w_old[i] for i in range(N * N)]
        valid_contrib = [c for c in contrib_old if c > 0.01]
        C = statistics.median(valid_contrib) if valid_contrib else 1.0
        weights = []
        for i in range(N * N):
            if contrib_old[i] < 0.01:
                w = w_old[i] * 1.5  # 极低贡献：适度提高
            else:
                ratio = C / contrib_old[i]
                w = w_old[i] * (ratio ** beta)
            w = max(1.0 / clamp_max, min(clamp_max, w))
            weights.append(w)
        return weights
    else:
        # 初始模式：反比占领频率
        C = statistics.median(valid)
        weights = []
        for o in own_avg:
            if o < 0.01:
                w = clamp_max
            else:
                w = (C / o) ** alpha
            w = max(1.0 / clamp_max, min(clamp_max, w))
            weights.append(w)
        return weights


def predict_contrib(own_avg, weights):
    """预测加权贡献 |own| × W。"""
    return [own_avg[i] * weights[i] for i in range(N * N)]


def region_stats(values, n=N*N):
    """按分区统计。"""
    stats = {}
    for i in range(n):
        r, c = i // N, i % N
        reg = region_of(r, c)
        if reg not in stats:
            stats[reg] = []
        stats[reg].append(values[i])
    result = {}
    for reg, vals in stats.items():
        result[reg] = {
            "count": len(vals),
            "mean": statistics.mean(vals),
            "median": statistics.median(vals),
            "min": min(vals),
            "max": max(vals),
        }
    return result


def print_heatmap(values, title, width=N):
    """打印 19×19 热力图。"""
    print(f"\n=== {title} ===")
    valid = [v for v in values if v is not None]
    if not valid:
        print("  (no data)")
        return
    mn, mx = min(valid), max(valid)
    span = mx - mn if mx > mn else 1
    ramp = " .:-=+*#%@"
    cols = "ABCDEFGHIJKLMNOPQRST"[:N]
    print("     " + " ".join(cols))
    for r in range(N):
        row_str = ""
        for c in range(N):
            v = values[r * N + c]
            if v is None:
                row_str += "  "
            else:
                idx = int((v - mn) / span * 9)
                row_str += ramp[min(9, max(0, idx))] + " "
        print(f"{N-r:>2}  {row_str}")
    print(f"范围 [{mn:.4f}, {mx:.4f}]  越亮(@)=值越大")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("games_json", help="对局 JSON 路径")
    ap.add_argument("out_weights", help="输出权重表路径")
    ap.add_argument("--clamp-max", type=float, default=3.0, help="权重 clamp 上限")
    ap.add_argument("--alpha", type=float, default=1.0, help="补偿强度（1=完全反比，<1=部分）")
    ap.add_argument("--w-old", default=None, help="上一轮权重表路径（阻尼迭代模式）")
    ap.add_argument("--beta", type=float, default=0.5, help="阻尼系数（<1 防过冲，默认 0.5）")
    args = ap.parse_args()

    data = load_games(args.games_json)
    own_avg, n_games = avg_ownership(data)
    if own_avg is None:
        print("[error] 无 ownership 数据", flush=True)
        sys.exit(1)

    # D4 对称化：对局噪声/线程非确定性使对称点估值不一致，先做轨道平均
    own_avg = d4_symmetrize(own_avg)
    print("== D4 对称化已应用（8 重轨道平均，Σ 不变）==", flush=True)

    # 加载上一轮权重（阻尼模式）
    w_old = None
    if args.w_old:
        with open(args.w_old) as f:
            w_old = [float(x) for x in f.read().split()]
        w_old = d4_symmetrize(w_old)  # 旧表也对称化，避免继承历史不对称
        print(f"== 阻尼迭代模式（w_old={args.w_old}, beta={args.beta}，已对称化）==", flush=True)

    print(f"== 基线分析（{n_games} 局平均）==", flush=True)
    print(f"Σ|own| = {sum(own_avg):.2f}  (标准 19路满占≈361)", flush=True)

    # 分区统计
    own_stats = region_stats(own_avg)
    print(f"\n{'区域':>9} {'avg|own|':>9} {'中位':>9} {'min':>9} {'max':>9}")
    for reg in ["corner34", "edge34", "center", "low12"]:
        s = own_stats.get(reg, {})
        if s:
            print(f"{reg:>9} {s['mean']:>9.4f} {s['median']:>9.4f} {s['min']:>9.4f} {s['max']:>9.4f}")

    # 热力图
    print_heatmap(own_avg, "平均 |ownership| 热力图（W=1 基线，越大=越常被占领）")

    # 设计 W
    weights = design_weights(own_avg, clamp_max=args.clamp_max, alpha=args.alpha,
                             w_old=w_old, beta=args.beta)
    w_sum = sum(weights)
    print(f"\n== W₁ 设计（clamp_max={args.clamp_max}, alpha={args.alpha}）==", flush=True)
    print(f"ΣW = {w_sum:.2f}  (标准 361)", flush=True)

    w_stats = region_stats(weights)
    print(f"{'区域':>9} {'avg W':>9} {'中位':>9} {'min':>9} {'max':>9}")
    for reg in ["corner34", "edge34", "center", "low12"]:
        s = w_stats.get(reg, {})
        if s:
            print(f"{reg:>9} {s['mean']:>9.4f} {s['median']:>9.4f} {s['min']:>9.4f} {s['max']:>9.4f}")

    print_heatmap(weights, "W₁ 权重矩阵（越大=越需补偿）")

    # 预测加权贡献
    contrib = predict_contrib(own_avg, weights)
    contrib_stats = region_stats(contrib)
    print(f"\n== 预测加权贡献 |own|×W（应比 W=1 更均匀）==")
    print(f"{'区域':>9} {'avg贡献':>9} {'中位':>9} {'min':>9} {'max':>9}")
    for reg in ["corner34", "edge34", "center", "low12"]:
        s = contrib_stats.get(reg, {})
        if s:
            print(f"{reg:>9} {s['mean']:>9.4f} {s['median']:>9.4f} {s['min']:>9.4f} {s['max']:>9.4f}")

    # 均匀度指标：变异系数 CV = std/mean
    all_contrib = [c for c in contrib if c is not None]
    cv = statistics.stdev(all_contrib) / statistics.mean(all_contrib) if statistics.mean(all_contrib) > 0 else 0
    print(f"\n加权贡献变异系数 CV = {cv:.4f}  (越小越均匀，W=1 基线 CV 应更大)")

    print_heatmap(contrib, "预测加权贡献 |own|×W（越均匀越好）")

    # 保存权重表
    with open(args.out_weights, "w") as f:
        for i, w in enumerate(weights):
            if i % N == 0 and i > 0:
                f.write("\n")
            f.write(f"{w:.6f} ")
        f.write("\n")
    print(f"\n[saved] {args.out_weights}  ({len(weights)} 值, ΣW={w_sum:.2f})", flush=True)


if __name__ == "__main__":
    main()
