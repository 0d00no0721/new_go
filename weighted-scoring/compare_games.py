#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对比两局棋的前 N 手，判断 AI 是否对权重有响应。"""
import json, sys

f1 = sys.argv[1] if len(sys.argv) > 1 else r"E:\小工具\new_go\weighted-scoring\games\baseline_w1.json"
f2 = sys.argv[2] if len(sys.argv) > 2 else r"E:\小工具\new_go\weighted-scoring\games\test_w_central.json"
n = int(sys.argv[3]) if len(sys.argv) > 3 else 10

w1 = json.load(open(f1, encoding="utf-8"))
wc = json.load(open(f2, encoding="utf-8"))

print("=== W=1 基线前 {} 手 ===".format(n))
for m in w1["games"][0]["moves"][:n]:
    print("  {:>2}. {} {}".format(m["turn"], m["color"], m["move"]))

print("\n=== W=加权前 {} 手 ===".format(n))
for m in wc["games"][0]["moves"][:n]:
    print("  {:>2}. {} {}".format(m["turn"], m["color"], m["move"]))

same = sum(1 for a, b in zip(w1["games"][0]["moves"][:n], wc["games"][0]["moves"][:n]) if a["move"] == b["move"])
print("\n=== 对比: 前 {} 手相同位置 {}/{} ===".format(n, same, n))
if same == n:
    print("AI 对权重无响应（搜索未使用权重）")
else:
    print("AI 对权重有响应（{} 处不同）".format(n - same))
