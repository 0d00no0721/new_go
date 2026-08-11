#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成极端测试权重表：中央高(10)、角部低(0.1)、边中(1)。
用于验证 AI 是否对权重有响应（改变下棋位置）。"""
import sys

N = 19
OUT = sys.argv[1] if len(sys.argv) > 1 else r"E:\katago_cache\weight_table_test.txt"

def dist_to_edge(r, c):
    return min(r, N-1-r, c, N-1-c)

def in_corner(r, c):
    return (r < 6 or r > 12) and (c < 6 or c > 12)

weights = []
for r in range(N):
    for c in range(N):
        d = dist_to_edge(r, c)
        if d < 2:
            w = 0.5  # 一二线
        elif d in (2, 3) and in_corner(r, c):
            w = 0.1  # 角部三四线
        elif d >= 5:
            w = 10.0  # 中央
        else:
            w = 1.0  # 边
        weights.append(w)

with open(OUT, "w") as f:
    for i, w in enumerate(weights):
        if i % N == 0 and i > 0:
            f.write("\n")
        f.write(f"{w:.4f} ")
    f.write("\n")
print(f"[saved] {OUT}  (ΣW={sum(weights):.1f}, center=10, corner=0.1)")
