#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
位置价值分析 + 权重矩阵设计。

数据语义（已验证）：
  scoreLead(P) = 黑在 P 落一手后（含白方最佳回手）的黑视角领先目数。
  其相对差异 = 位置围空价值差异（一线大负=极坏，三四线高=高效，中央中等）。
  500 visits 下 nnRandomize=false 使对称点精确一致，可复现。

产出：
  V(P) 位置价值矩阵（相对效率，目数单位，已中心化为正）
  W(P) 平衡权重矩阵（W = mean(V)/V，使角/边/中央加权效率趋同）
"""
import json, statistics

N = 19
RAW = r"E:\小工具\new_go\position-value-research\raw_data.json"
OUT = r"E:\小工具\new_go\position-value-research\weight_matrix.json"


def gtp(r, c):
    return chr(ord('A') + c + (1 if c >= 8 else 0)) + str(N - r)


def load():
    with open(RAW, encoding="utf-8") as f:
        return json.load(f)


def rebuild_scorelead(d):
    rd = d["rep_delta"]
    rep_sl = {}
    for k, v in rd.items():
        r, c = map(int, k.split(','))
        rep_sl[(r, c)] = v["scoreLead"]
    full = [[0.0] * N for _ in range(N)]
    for r in range(N):
        for c in range(N):
            orbit = {
                (r, c), (r, N - 1 - c), (N - 1 - r, c), (N - 1 - r, N - 1 - c),
                (c, r), (c, N - 1 - r), (N - 1 - c, r), (N - 1 - c, N - 1 - r),
            }
            full[r][c] = rep_sl[min(orbit)]
    return full


def dist_to_edge(r, c):
    return min(r, N - 1 - r, c, N - 1 - c)


def in_corner_zone(r, c):
    """6×6 角区内（距两边都 ≤5）。"""
    return (r < 6 or r > 12) and (c < 6 or c > 12)


def fine_region(r, c):
    """精细分区（排除一二线坏点干扰）：
    corner34 = 三四线角部（金角）
    edge34   = 三四线边中（银边）
    center   = 五线及以上（草肚皮）
    low12    = 一二线（不参与围空效率对比）"""
    d = dist_to_edge(r, c)
    if d < 2:
        return "low12"
    if d in (2, 3):
        return "corner34" if in_corner_zone(r, c) else "edge34"
    return "center"


def stats_by_line(full):
    by_line = {}
    for r in range(N):
        for c in range(N):
            by_line.setdefault(dist_to_edge(r, c), []).append(full[r][c])
    print("=== 按距边线数统计 scoreLead 均值 ===")
    print(f"{'线数':>4} {'点数':>4} {'均值':>8} {'中位':>8}")
    for d in sorted(by_line):
        v = by_line[d]
        print(f"{d:>4}线 {len(v):>4} {statistics.mean(v):>8.3f} {statistics.median(v):>8.3f}")


def stats_by_fine_region(full):
    by_reg = {}
    for r in range(N):
        for c in range(N):
            by_reg.setdefault(fine_region(r, c), []).append(full[r][c])
    print("\n=== 精细分区统计（金角银边草肚皮验证）===")
    print(f"{'区域':>9} {'点数':>4} {'均值':>8} {'中位':>8} {'min':>8} {'max':>8}")
    for reg in ["corner34", "edge34", "center", "low12"]:
        v = by_reg.get(reg, [])
        if v:
            print(f"{reg:>9} {len(v):>4} {statistics.mean(v):>8.3f} {statistics.median(v):>8.3f} {min(v):>8.3f} {max(v):>8.3f}")
    return by_reg


def build_value_matrix(full):
    """V(P) = scoreLead(P) - min(scoreLead over 三线及以上) + ε
    只用 d≥2 的点定 min，一二线 V 设为 0（不参与）。
    V 为正，单位近似目，反映相对围空效率。"""
    valid = [full[r][c] for r in range(N) for c in range(N) if dist_to_edge(r, c) >= 2]
    base = min(valid)
    eps = 0.01
    V = [[0.0] * N for _ in range(N)]
    for r in range(N):
        for c in range(N):
            if dist_to_edge(r, c) >= 2:
                V[r][c] = full[r][c] - base + eps
    return V, base


def build_weight_matrix(V):
    """W(P) = mean(V over d≥2) / V(P)，使 W×V = mean(V) 常数 → 三区加权效率相同。
    一二线 W = 0（不鼓励落子）。"""
    valid_V = [V[r][c] for r in range(N) for c in range(N) if dist_to_edge(r, c) >= 2]
    mean_V = statistics.mean(valid_V)
    W = [[0.0] * N for _ in range(N)]
    for r in range(N):
        for c in range(N):
            if dist_to_edge(r, c) >= 2:
                W[r][c] = mean_V / V[r][c]
    return W, mean_V


def verify_balance(V, W):
    """验证角/边/中央加权后效率 W×V 趋同。"""
    print("\n=== 平衡验证：各区加权效率 W×V ===")
    print(f"{'区域':>9} {'原始E均值':>10} {'加权W×V均值':>12} {'加权后/全局均值':>14}")
    mean_V = statistics.mean([V[r][c] for r in range(N) for c in range(N) if dist_to_edge(r, c) >= 2])
    for reg in ["corner34", "edge34", "center"]:
        vals_E, vals_WV = [], []
        for r in range(N):
            for c in range(N):
                if fine_region(r, c) == reg:
                    vals_E.append(V[r][c])
                    vals_WV.append(W[r][c] * V[r][c])
        if vals_E:
            print(f"{reg:>9} {statistics.mean(vals_E):>10.4f} {statistics.mean(vals_WV):>12.4f} {statistics.mean(vals_WV)/mean_V:>14.4f}")


def heatmap(mat, title, fmt=".2f", invert=False):
    """invert=True 时越小越亮（如 scoreLead 越高越好→越大越亮，invert=False）。"""
    print(f"\n=== {title} ===")
    mn, mx = min(min(row) for row in mat), max(max(row) for row in mat)
    span = mx - mn if mx > mn else 1
    ramp = " .:-=+*#%@"
    print("     " + " ".join(gtp(0, c)[0] for c in range(N)))
    for r in range(N):
        cells = []
        for c in range(N):
            v = mat[r][c]
            if v == 0.0:
                cells.append(" ")
            else:
                idx = (v - mn) / span * 9
                cells.append(ramp[min(9, int(idx))])
        print(f"{gtp(r,0)[1:]:>3}  " + " ".join(cells))
    print(f"范围 [{mn:.3f}, {mx:.3f}]  越亮( @ )=值越大")


def main():
    d = load()
    full = rebuild_scorelead(d)
    print(f"空盘 scoreLead 基线 = {d['meta']['base_scoreLead']:.4f}\n")

    stats_by_line(full)
    stats_by_fine_region(full)

    V, base = build_value_matrix(full)
    W, mean_V = build_weight_matrix(V)

    print(f"\n价值矩阵 V(P): base(min d≥2)={base:.4f}, mean(V)={mean_V:.4f}")
    print("权重矩阵 W(P): W = mean(V)/V，使 W×V = mean(V) 恒定")

    verify_balance(V, W)

    print(f"\n=== 关键点 V / W ===")
    print(f"{'位置':>6} {'gtp':>4} {'scoreLead':>10} {'V':>7} {'W':>6}")
    for name, (r, c) in [("星位D16", (3,3)), ("三三C17", (2,2)), ("小目D17", (2,3)),
                          ("天元K10", (9,9)), ("四线边中K16", (3,9)), ("三线边中K17", (2,9)),
                          ("五线E15", (4,3)), ("一线A19", (0,0))]:
        sl = full[r][c]
        v = V[r][c]; w = W[r][c]
        print(f"{name:>6} {gtp(r,c):>4} {sl:>10.3f} {v:>7.3f} {w:>6.3f}")

    heatmap(full, "scoreLead 原始矩阵（越大越好）")
    heatmap(V, "价值矩阵 V(P)（围空效率，越大越好）")
    heatmap(W, "权重矩阵 W(P)（平衡系数，越大=越需补偿）")

    # 保存
    out = {
        "meta": {
            "board_size": N,
            "method": "KataGo analysis scoreLead(P) 相对差异",
            "visits": d["meta"]["visits"],
            "model": d["meta"]["model"],
            "base_scoreLead": d["meta"]["base_scoreLead"],
            "value_base_min": base,
            "mean_V": mean_V,
            "timestamp": d["meta"]["timestamp"],
            "note": "V(P)=围空效率(目,相对); W(P)=mean(V)/V 平衡权重; 一二线 V=W=0",
        },
        "scoreLead": full,
        "V": V,
        "W": W,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n[saved] {OUT}")


if __name__ == "__main__":
    main()
