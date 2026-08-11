#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Komi 标定：用 W4 权重跑 AI vs AI，扫描 komi，统计黑胜率，拟合 50% 胜率 komi。

用法：
  python calibrate_komi.py --weights E:/katago_cache/weight_table_final.txt \
      --komis 6.5,7.5,8.5,9.5 --games 5 --visits 100 --max-moves 200

输出：games/calibration_<ts>.json（每局增量保存，中断也能取部分结果）
"""
import sys, os, time, json, argparse, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from play_game import GtpEngine, play_one_game

GAMES_DIR = r"E:\小工具\new_go\weighted-scoring\games"


def parse_winner(final_score):
    s = (final_score or "").replace("= ", "").strip()
    if s == "0" or s == "":
        return "draw", 0.0
    if s.startswith("B+"):
        return "B", float(s[2:])
    if s.startswith("W+"):
        return "W", float(s[2:])
    return "draw", 0.0


def black_stats(results):
    n = len(results)
    bw = sum(1 for r in results if r["winner"] == "B")
    ww = sum(1 for r in results if r["winner"] == "W")
    dr = sum(1 for r in results if r["winner"] == "draw")
    decisive = bw + ww
    rate = bw / decisive if decisive > 0 else float('nan')
    return rate, bw, ww, dr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True)
    ap.add_argument("--komis", default="6.5,7.5,8.5,9.5")
    ap.add_argument("--games", type=int, default=5)
    ap.add_argument("--max-moves", type=int, default=200)
    ap.add_argument("--visits", type=int, default=100)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    komis = [float(k) for k in args.komis.split(",")]
    os.makedirs(GAMES_DIR, exist_ok=True)
    out_path = args.out or os.path.join(GAMES_DIR, f"calibration_{int(time.time())}.json")

    summary = {
        "meta": {
            "weights_file": args.weights, "komis": komis, "games_per_komi": args.games,
            "max_moves": args.max_moves, "visits": args.visits,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "results": {str(k): [] for k in komis},
    }

    def save():
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

    save()
    print(f"[calibrate] weights={args.weights}", flush=True)
    print(f"[calibrate] komis={komis} games/komi={args.games} visits={args.visits} max-moves={args.max_moves}", flush=True)
    print(f"[calibrate] out={out_path}", flush=True)

    engine = GtpEngine(visits=args.visits)
    t0 = time.time()
    total = len(komis) * args.games
    done = 0
    try:
        for k in komis:
            for gi in range(args.games):
                done += 1
                print(f"\n== komi={k} game {gi+1}/{args.games}  ({done}/{total} total, {time.time()-t0:.0f}s) ==", flush=True)
                game = play_one_game(engine, args.weights, args.max_moves, k)
                winner, margin = parse_winner(game["final_score"])
                rec = {
                    "komi": k, "game_idx": gi, "final_score": game["final_score"],
                    "winner": winner, "margin": margin, "num_moves": game["num_moves"],
                    "elapsed": game["elapsed"],
                }
                summary["results"][str(k)].append(rec)
                save()
                print(f"  -> {winner}+{margin}  ({game['num_moves']} moves, {game['elapsed']}s)  score={game['final_score']}", flush=True)
    except Exception as e:
        summary["error"] = repr(e)
        save()
        print(f"[error] {e!r} — 已保存部分结果", flush=True)
    finally:
        try:
            engine.close()
        except Exception:
            pass

    # 汇总 + 拟合
    print("\n========= 标定汇总 =========", flush=True)
    print(f"{'komi':>6} {'B胜':>4} {'W胜':>4} {'平':>3} {'B胜率':>7} {'均B-margin':>10}", flush=True)
    curve = []
    for k in komis:
        res = summary["results"][str(k)]
        rate, bw, ww, dr = black_stats(res)
        margins = [r["margin"] * (1 if r["winner"] == "B" else -1) for r in res if r["winner"] != "draw"]
        avg_m = sum(margins) / len(margins) if margins else float('nan')
        print(f"{k:>6.1f} {bw:>4} {ww:>4} {dr:>3} {rate:>7.3f} {avg_m:>+10.2f}", flush=True)
        curve.append({"komi": k, "black_wins": bw, "white_wins": ww, "draws": dr,
                      "black_winrate": rate, "avg_black_margin": avg_m, "n": len(res)})
    summary["curve"] = curve

    # 线性插值找 50% komi
    pts = [(c["komi"], c["black_winrate"]) for c in curve
           if not math.isnan(c["black_winrate"]) and c["n"] > 0]
    pts.sort()
    fair_komi = None
    if len(pts) >= 2:
        for i in range(len(pts) - 1):
            r0, r1 = pts[i][1], pts[i + 1][1]
            if r0 != r1 and (r0 - 0.5) * (r1 - 0.5) <= 0:
                k0, k1 = pts[i][0], pts[i + 1][0]
                fair_komi = k0 + (0.5 - r0) * (k1 - k0) / (r1 - r0)
                break
    if fair_komi is not None:
        summary["fair_komi_estimate"] = fair_komi
        print(f"\n[fit] 50% 胜率 komi ≈ {fair_komi:.3f} (线性插值)", flush=True)
    else:
        # 外推提示
        if pts:
            lo, hi = pts[0], pts[-1]
            if hi[1] < 0.5:
                print(f"\n[fit] 所有 komi 黑胜率<0.5（最高 {hi[1]:.3f}@komi={hi[0]}），fair komi < {hi[0]}", flush=True)
            elif lo[1] > 0.5:
                print(f"\n[fit] 所有 komi 黑胜率>0.5（最低 {lo[1]:.3f}@komi={lo[0]}），fair komi > {lo[0]}", flush=True)
            else:
                print("\n[fit] 无法插值，请检查数据", flush=True)

    save()
    print(f"\n[saved] {out_path}", flush=True)


if __name__ == "__main__":
    main()
