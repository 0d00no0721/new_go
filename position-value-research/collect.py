#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
位置价值数据采集 —— 围棋盘每位置"第一手目数价值" Δ(P) 测量。

方法：
  对 19×19 棋盘每个位置 P，用 KataGo analysis 评估"黑在 P 落一手后"的盘面，
  读 rootInfo.scoreLead（黑方领先目数）。Δ(P) = scoreLead(P) - scoreLead(空盘)。
  利用 D4 对称性（8 重）只需查询 55 个轨道代表，nnRandomize=false 下对称点
  结果精确一致，可无损还原 361 个位置。

用法：
  python collect.py --limit 5 --visits 500     # 小样本验证
  python collect.py --visits 500               # 全量采集
"""
import json, subprocess, sys, time, threading, argparse, os

KATAGO = r"E:\小工具\new_go\ban-selection\dist_opencl\katago.exe"
CONFIG = r"E:\小工具\new_go\position-value-research\analysis.cfg"
MODEL = r"E:\2026-01-07-win64-KataGo\weights\28b.bin.gz"
N = 19
OUT = r"E:\小工具\new_go\position-value-research\raw_data.json"


def gtp_coord(r, c):
    """0-indexed (r,c) → GTP 坐标字符串，r=0 顶部，列跳过 I。"""
    col = chr(ord('A') + c + (1 if c >= 8 else 0))
    row = N - r
    return f"{col}{row}"


def orbit_reps():
    """计算 D4 对称轨道代表。返回 (reps列表, 位置→代表 映射)。"""
    seen = set()
    reps = []
    mapping = {}
    for r in range(N):
        for c in range(N):
            if (r, c) in seen:
                continue
            orbit = {
                (r, c), (r, N - 1 - c), (N - 1 - r, c), (N - 1 - r, N - 1 - c),
                (c, r), (c, N - 1 - r), (N - 1 - c, r), (N - 1 - c, N - 1 - r),
            }
            rep = min(orbit)
            reps.append(rep)
            for p in orbit:
                seen.add(p)
                mapping[p] = rep
    return reps, mapping


def run(reps, visits, limit=None):
    """启动 KataGo，发送空盘 + 每代表点的查询，收集 scoreLead。"""
    target = reps[:limit] if limit else reps
    reqs = []
    reqs.append({"id": "empty", "moves": [], "rules": "chinese", "komi": 7.5,
                 "boardXSize": N, "boardYSize": N, "maxVisits": visits,
                 "includeOwnership": False})
    for (r, c) in target:
        reqs.append({"id": f"b-{r}-{c}", "moves": [["B", gtp_coord(r, c)]],
                     "rules": "chinese", "komi": 7.5,
                     "boardXSize": N, "boardYSize": N, "maxVisits": visits,
                     "includeOwnership": False})

    proc = subprocess.Popen(
        [KATAGO, "analysis", "-config", CONFIG, "-model", MODEL],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )

    def drain_stderr():
        for line in iter(proc.stderr.readline, ""):
            pass  # 静默吞掉，避免刷屏；需要调试可改为 sys.stderr.write

    t = threading.Thread(target=drain_stderr, daemon=True)
    t.start()

    print(f"[info] 发送 {len(reqs)} 个查询（空盘 + {len(target)} 代表点），visits={visits}", flush=True)
    for q in reqs:
        proc.stdin.write(json.dumps(q) + "\n")
    proc.stdin.flush()

    results = {}
    t0 = time.time()
    while len(results) < len(reqs) and time.time() - t0 < 600:
        out = proc.stdout.readline()
        if not out:
            break
        try:
            resp = json.loads(out)
        except Exception:
            continue
        if resp.get("isDuringSearch", False):
            continue
        rid = resp.get("id")
        root = resp.get("rootInfo", {})
        results[rid] = {
            "scoreLead": root.get("scoreLead"),
            "winrate": root.get("winrate"),
        }
        if len(results) % 10 == 0 or len(results) == len(reqs):
            print(f"[progress] {len(results)}/{len(reqs)}  ({time.time()-t0:.1f}s)", flush=True)

    proc.stdin.close()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
    return results, reqs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="只跑前 N 个代表点（验证用）")
    ap.add_argument("--visits", type=int, default=500)
    args = ap.parse_args()

    reps, mapping = orbit_reps()
    print(f"[info] 19×19 D4 轨道代表数 = {len(reps)}", flush=True)

    results, reqs = run(reps, args.visits, args.limit)

    if "empty" not in results:
        print("[error] 未收到空盘基线响应", flush=True)
        sys.exit(1)
    base = results["empty"]["scoreLead"]
    print(f"[result] 空盘 scoreLead = {base:.4f}  winrate = {results['empty']['winrate']:.4f}", flush=True)

    rep_delta = {}
    print(f"[result] 各代表点 Δ(P) = scoreLead(P) - 空盘：", flush=True)
    print(f"         {'coord':>4} {'gtp':>4} {'scoreLead':>10} {'Δ':>8}", flush=True)
    for (r, c) in reps:
        rid = f"b-{r}-{c}"
        if rid not in results:
            continue
        sl = results[rid]["scoreLead"]
        d = sl - base
        rep_delta[f"{r},{c}"] = {"scoreLead": sl, "delta": d}
        if args.limit:  # 小样本时详细打印
            print(f"         ({r},{c}) {gtp_coord(r,c):>4} {sl:>10.4f} {d:>8.4f}", flush=True)

    # 对称性还原 361 矩阵
    full = [[None] * N for _ in range(N)]
    for r in range(N):
        for c in range(N):
            rep = mapping[(r, c)]
            key = f"{rep[0]},{rep[1]}"
            if key in rep_delta:
                full[r][c] = rep_delta[key]["delta"]

    # 简要统计（仅全量时）
    if not args.limit:
        vals = [full[r][c] for r in range(N) for c in range(N) if full[r][c] is not None]
        if vals:
            print(f"[stat] Δ 范围 [{min(vals):.4f}, {max(vals):.4f}]  均值 {sum(vals)/len(vals):.4f}", flush=True)

    data = {
        "meta": {
            "board_size": N,
            "num_reps": len(reps),
            "num_queries": len(reqs),
            "visits": args.visits,
            "komi": 7.5,
            "model": MODEL,
            "rules": "chinese",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "base_scoreLead": base,
            "base_winrate": results["empty"]["winrate"],
        },
        "rep_delta": rep_delta,
        "full_matrix": full,
    }
    if not args.limit:
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[saved] {OUT}", flush=True)
    else:
        print(f"[skip] limit 模式不保存文件", flush=True)


if __name__ == "__main__":
    main()
