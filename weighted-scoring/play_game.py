#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
加权点目对局工具 — 迭代循环的核心。

功能：
  1. 启动改造版 KataGo，加载权重表
  2. AI vs AI 对弈至终局（双 pass 或达手数上限）
  3. 终局提取：final_score（加权分）、kata-analyze ownership（每点归属概率）
  4. 保存：SGF 棋谱 + JSON（手数/分/ownership/加权贡献）

用法：
  python play_game.py --weights E:/katago_cache/weight_table.txt --games 3
  python play_game.py --weights E:/katago_cache/weight_table.txt --max-moves 80
"""
import subprocess, sys, time, threading, json, argparse, os

KATAGO = r"E:\小工具\new_go\weighted-scoring\dist_opencl\katago.exe"
CONFIG = r"E:\2026-01-07-win64-KataGo\katago_configs\default_gtp.cfg"
OVERRIDE = r"E:\小工具\new_go\weighted-scoring\gtp_override.cfg"
MODEL = r"E:\2026-01-07-win64-KataGo\weights\28b.bin.gz"
GAMES_DIR = r"E:\小工具\new_go\weighted-scoring\games"
N = 19


class GtpEngine:
    def __init__(self, visits=200, max_time=None):
        args = [KATAGO, "gtp", "-config", CONFIG, "-config", OVERRIDE, "-model", MODEL,
                "-override-config", f"maxVisits={visits}"]
        if max_time:
            args += ["-override-config", f"maxTime={max_time}"]
        self.proc = subprocess.Popen(
            args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        self._err = threading.Thread(target=self._drain, daemon=True)
        self._err.start()
        self.cmd("boardsize 19")
        self.cmd("clear_board")

    def _drain(self):
        for _ in iter(self.proc.stderr.readline, ""):
            pass

    def cmd(self, c):
        self.proc.stdin.write(c + "\n")
        self.proc.stdin.flush()
        resp = []
        started = False
        while True:
            line = self.proc.stdout.readline()
            if not line:
                break
            line = line.rstrip("\n")
            if not started:
                if line.startswith("=") or line.startswith("?"):
                    started = True
                    resp.append(line)
                    cmd_name = c.split()[0] if c.split() else c
                    if cmd_name in ("list_commands", "kata-query-weights", "showboard", "kata-analyze", "lz-analyze", "kata-raw-nn"):
                        continue
                    break
                continue
            if line == "":
                break
            resp.append(line)
        is_err = resp and resp[0].startswith("?")
        return is_err, "\n".join(resp)

    def genmove(self, color):
        err, r = self.cmd(f"genmove {color}")
        if err:
            return None, r
        return r.replace("= ", "").strip(), None

    def play(self, color, move):
        return self.cmd(f"play {color} {move}")

    def load_weights(self, path):
        return self.cmd(f"kata-load-weights {path}")

    def clear_weights(self):
        return self.cmd("kata-clear-weights")

    def final_score(self):
        err, r = self.cmd("final_score")
        if err:
            return None
        return r.replace("= ", "").strip()

    def get_ownership(self):
        """用 kata-raw-nn 获取 NN 的 ownership 预测（当前盘面）。
        返回长度 361 的列表，值 [-1,1]，正=黑占，负=白占（black-positive）。
        kata-raw-nn all 输出：标量行 + 'policy' + 19行 + 'policyPass' + 'whiteOwnership' + 19行。
        whiteOwnership 正=白，需取反转为 black-positive。"""
        err, r = self.cmd("kata-raw-nn all")
        if err:
            return None
        lines = r.split("\n")
        # 找 whiteOwnership 行，其后 19 行是 19×19 矩阵
        for i, line in enumerate(lines):
            if "whiteOwnership" in line:
                own_lines = lines[i + 1:i + 20]
                vals = []
                for ol in own_lines:
                    parts = ol.split()
                    for v in parts:
                        try:
                            vals.append(-float(v))  # 取反：white-positive → black-positive
                        except ValueError:
                            pass
                if len(vals) == N * N:
                    return vals
                break
        return None

    def close(self):
        try:
            self.proc.stdin.write("quit\n")
            self.proc.stdin.flush()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


def gtp_coord(move_idx):
    """0-indexed (r,c) → GTP 坐标；r=0 顶，列跳过 I。"""
    r, c = move_idx // N, move_idx % N
    col = chr(ord('A') + c + (1 if c >= 8 else 0))
    return f"{col}{N - r}"


def play_one_game(engine, weight_path, max_moves, komi=7.5):
    """下一局，返回 dict（moves/score/ownership）。"""
    engine.cmd("clear_board")
    engine.cmd(f"komi {komi}")
    if weight_path:
        err, r = engine.load_weights(weight_path)
        if err:
            print(f"  [warn] load_weights failed: {r}", flush=True)

    moves = []
    color = "B"
    passes = 0
    t0 = time.time()
    for i in range(max_moves):
        move, err = engine.genmove(color)
        if move is None:
            print(f"  [error] genmove {color} failed: {err}", flush=True)
            break
        moves.append({"color": color, "move": move, "turn": i})
        if move.upper() == "PASS":
            passes += 1
            if passes >= 2:
                break
        else:
            passes = 0
        color = "W" if color == "B" else "B"
        if (i + 1) % 20 == 0:
            print(f"  [progress] {i+1} moves, {time.time()-t0:.0f}s", flush=True)

    score = engine.final_score()
    ownership = engine.get_ownership()
    elapsed = time.time() - t0
    return {
        "moves": moves,
        "num_moves": len(moves),
        "final_score": score,
        "ownership": ownership,
        "elapsed": round(elapsed, 1),
        "komi": komi,
    }


def analyze_game(game, weights):
    """分析单局：计算每位置的加权贡献与分区统计。"""
    own = game["ownership"]
    if own is None or weights is None:
        return None
    # own: 361 值 [-1,1]，正=黑占，负=白占
    # weighted contribution: |own| * W（绝对贡献）, own * W（ signed）
    contributions = []
    for i in range(N * N):
        w = weights[i] if i < len(weights) else 1.0
        o = own[i]
        contributions.append({"loc": i, "ownership": o, "weight": w, "contrib": abs(o) * w})
    # 分区统计
    def region(r, c):
        d = min(r, N-1-r, c, N-1-c)
        if d < 2: return "low12"
        if d in (2,3):
            return "corner34" if (r<6 or r>12) and (c<6 or c>12) else "edge34"
        return "center"
    region_stats = {}
    for i in range(N*N):
        r, c = i // N, i % N
        reg = region(r, c)
        if reg not in region_stats:
            region_stats[reg] = {"count": 0, "sum_contrib": 0, "sum_abs_own": 0}
        region_stats[reg]["count"] += 1
        region_stats[reg]["sum_contrib"] += contributions[i]["contrib"]
        region_stats[reg]["sum_abs_own"] += abs(own[i])
    for reg in region_stats:
        s = region_stats[reg]
        s["avg_contrib"] = s["sum_contrib"] / s["count"] if s["count"] else 0
        s["avg_abs_own"] = s["sum_abs_own"] / s["count"] if s["count"] else 0
    return {"contributions": contributions, "region_stats": region_stats}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default=None, help="权重表文件路径（None=W=1）")
    ap.add_argument("--games", type=int, default=1, help="对局数")
    ap.add_argument("--max-moves", type=int, default=250, help="每局手数上限")
    ap.add_argument("--visits", type=int, default=200, help="每手搜索 visits")
    ap.add_argument("--komi", type=float, default=7.5)
    ap.add_argument("--out", default=None, help="输出 JSON 路径")
    args = ap.parse_args()

    os.makedirs(GAMES_DIR, exist_ok=True)
    # 读权重表
    weights = None
    if args.weights:
        with open(args.weights) as f:
            weights = [float(x) for x in f.read().split()]
        print(f"[info] 加载权重表: {args.weights}  ({len(weights)} 值)", flush=True)
        wsum = sum(weights)
        print(f"[info] ΣW = {wsum:.2f}  (标准 19路 Σ=361)", flush=True)

    engine = GtpEngine(visits=args.visits)
    games = []
    for gi in range(args.games):
        print(f"\n== 第 {gi+1}/{args.games} 局 ==", flush=True)
        game = play_one_game(engine, args.weights, args.max_moves, args.komi)
        games.append(game)
        print(f"  [done] {game['num_moves']} 手, score={game['final_score']}, {game['elapsed']}s", flush=True)
        if game["ownership"]:
            print(f"  [ownership] 已获取 ({len(game['ownership'])} 点)", flush=True)
            analysis = analyze_game(game, weights)
            if analysis:
                print(f"  [分区] avg_contrib:", flush=True)
                for reg, s in sorted(analysis["region_stats"].items()):
                    print(f"    {reg:>9}: contrib={s['avg_contrib']:.4f}  abs_own={s['avg_abs_own']:.4f}  n={s['count']}", flush=True)
        # 保存 SGF（简化）
        sgf_lines = ["(;GM[1]FF[4]CA[UTF-8]SZ[19]KM[{}]".format(args.komi)]
        for m in game["moves"]:
            if m["move"].upper() == "PASS":
                sgf_lines.append(f";{m['color']}[]")
            else:
                mv = m["move"]
                col = mv[0].upper()
                if col >= 'J': col = chr(ord(col) - 1)  # I 跳过逆转
                row = mv[1:]
                sgf_lines.append(f";{m['color']}[{col.lower()}{chr(ord('a')+int(row)-1)}]")
        sgf_lines.append(")")
        sgf_path = os.path.join(GAMES_DIR, f"game_{int(time.time())}_{gi}.sgf")
        with open(sgf_path, "w", encoding="utf-8") as f:
            f.write("".join(sgf_lines))
        print(f"  [sgf] {sgf_path}", flush=True)

    engine.close()

    # 保存汇总 JSON
    out_path = args.out or os.path.join(GAMES_DIR, f"session_{int(time.time())}.json")
    summary = {
        "meta": {
            "weights_file": args.weights,
            "num_games": args.games,
            "visits": args.visits,
            "komi": args.komi,
            "max_moves": args.max_moves,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "games": games,
    }
    if weights:
        summary["meta"]["weights"] = weights
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n[saved] {out_path}", flush=True)


if __name__ == "__main__":
    main()
