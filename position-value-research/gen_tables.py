#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成干净的 19×19 矩阵 markdown 表格（UTF-8）。"""
import json

d = json.load(open(r"E:\小工具\new_go\position-value-research\weight_matrix.json", encoding="utf-8"))
N = 19
W, V = d["W"], d["V"]


def col(c):
    return chr(ord('A') + c + (1 if c >= 8 else 0))


def fmt(v):
    return f"{v:.3f}" if v > 0 else "·"


lines = []
for name, mat in [("W", W), ("V", V)]:
    lines.append(f"### {name} 矩阵（19×19）\n")
    hdr = "| 行\\列 |" + "|".join(col(c) for c in range(N)) + "|"
    sep = "|---|" + "|".join(["---"] * N) + "|"
    lines.append(hdr)
    lines.append(sep)
    for r in range(N):
        row = f"|{19 - r}|" + "|".join(fmt(mat[r][c]) for c in range(N)) + "|"
        lines.append(row)
    lines.append("")

with open(r"E:\小工具\new_go\position-value-research\_tables_clean.md", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("done")
