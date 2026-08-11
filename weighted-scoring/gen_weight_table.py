#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成权重表文件（19×19，row-major，空格分隔）。
W=1 基线：全 1.0，用于回归验证（必须等于标准数子）。
"""
import json, sys

N = 19
OUT = sys.argv[1] if len(sys.argv) > 1 else r"E:\小工具\new_go\weighted-scoring\weight_table.txt"

# W=1 基线
weights = [1.0] * (N * N)

with open(OUT, "w", encoding="utf-8") as f:
    for i, w in enumerate(weights):
        if i % N == 0 and i > 0:
            f.write("\n")
        f.write(f"{w:.6f} ")
    f.write("\n")
print(f"[saved] {OUT}  ({len(weights)} values, all 1.0)")
