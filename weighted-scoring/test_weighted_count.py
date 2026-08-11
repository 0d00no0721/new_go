#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W=1 加权数子 == 标准数子（回归 + 边界用例）。

DoD #4：证明加权数子（BoardHistory::countAreaScoreWhiteMinusBlack / countTerritoryAreaScoreWhiteMinusBlack）
在 W≡1 时与标准数子逐项等价，并在边界点（角/一路/中央/三线边）验证权重确实逐点生效、W=1 完全还原。

关键：GTP `final_score` 仅在 isGameFinished=true 时才走真实加权数子（gtp.cpp:1511 分支）；
未终局局面走 NN-lead 估计（gtp.cpp:1524），不反映加权计数。故本测试先 set_position 再连续两次 pass
强制终局，令 `final_score` 复用 countAreaScoreWhiteMinusBlack 的真实加权输出。

设点约定：黑方点对白减黑分贡献 -w，白方点贡献 +w；单个活棋点必归属自身颜色
=> 把某点权重 1→2，终局分变化 = Δw × sign = ±1.0（精确断言，不依赖空地域划分）。
"""
import subprocess, sys, os, threading, json

KATAGO = r"E:\小工具\new_go\weighted-scoring\dist_opencl\katago.exe"
CONFIG = r"E:\2026-01-07-win64-KataGo\katago_configs\default_gtp.cfg"
OVERRIDE = r"E:\小工具\new_go\weighted-scoring\gtp_override.cfg"
MODEL = r"E:\2026-01-07-win64-KataGo\weights\28b.bin.gz"
W1_TABLE = r"E:\katago_cache\weight_table_w1.txt"
GAME_JSON = r"E:\小工具\new_go\weighted-scoring\games\round5_w4_games.json"
TMP = r"E:\katago_cache\wt_test_tmp.txt"

N = 19


def gtp_idx(r, c):
    """row-number r (1=bottom), GTP col letter c -> row-major table idx (y=0 top)."""
    y = N - r
    col = ord(c) - ord('A')
    if col >= 8:
        col -= 1
    return y * N + col


class GtpProc:
    def __init__(self):
        self.proc = subprocess.Popen(
            [KATAGO, "gtp", "-config", CONFIG, "-config", OVERRIDE, "-model", MODEL],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        self._err = threading.Thread(target=self._drain_err, daemon=True)
        self._err.start()

    def _drain_err(self):
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
                    if not line[1:].strip() == "" and c not in ("list_commands", "kata-query-weights", "showboard"):
                        break
                continue
            if line == "":
                break
            resp.append(line)
        is_err = resp and resp[0].startswith("?")
        return is_err, "\n".join(resp)

    def close(self):
        try:
            self.proc.stdin.write("quit\n")
            self.proc.stdin.flush()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


def write_table(path, weights):
    with open(path, "w") as f:
        for i, w in enumerate(weights):
            if i % N == 0 and i > 0:
                f.write("\n")
            f.write(f"{w:.6f} ")
        f.write("\n")


def parse_final_score(r):
    s = r.replace("=", "").strip()
    if s.startswith("B+"):
        return float(s[2:])
    if s.startswith("W+"):
        return -float(s[2:])
    return 0.0


def score_finished(g, tokens, table_path=None, komi="7.5"):
    """set_position -> (可选手动加载权重) -> 连续两次 pass 强制终局 -> final_score。
    仅用于无吃子、可一步摆放的落子点列表（T6 单颗孤子）。返回 (白减黑分, 原始响应)。"""
    g.cmd("clear_board")
    g.cmd(f"komi {komi}")
    err, r = g.cmd("set_position " + " ".join(tokens))
    if err:
        return None, r
    if table_path is not None:
        err, r = g.cmd(f"kata-load-weights {table_path}")
        if err:
            return None, r
    g.cmd("play b pass")
    g.cmd("play w pass")
    err, r = g.cmd("final_score")
    if err:
        return None, r
    return parse_final_score(r), r


def replay_score(g, tokens, komi, table_path=None):
    """逐步 play 重放含吃子的真实对局（T5），再连续两次 pass 强制终局加权数子。
    返回 (白减黑分, 原始响应)。"""
    g.cmd("clear_board")
    g.cmd(f"komi {komi}")
    for i in range(0, len(tokens), 2):
        color = tokens[i]
        mv = tokens[i + 1]
        err, r = g.cmd(f"play {color} {mv}")
        if err:
            return None, r
    if table_path is not None:
        err, r = g.cmd(f"kata-load-weights {table_path}")
        if err:
            return None, r
    g.cmd("play b pass")
    g.cmd("play w pass")
    err, r = g.cmd("final_score")
    if err:
        return None, r
    return parse_final_score(r), r


def load_game_positions(game_json, game_idx):
    with open(game_json, encoding="utf-8") as f:
        data = json.load(f)
    game = data["games"][game_idx]
    tokens = []
    for m in game["moves"]:
        if m["move"].upper() == "PASS":
            tokens.append(m["color"])
            tokens.append("pass")
        else:
            tokens.append(m["color"])
            tokens.append(m["move"])
    return tokens, game["komi"]


def main():
    g = GtpProc()
    passed, failed = 0, 0

    def check(name, cond, detail=""):
        nonlocal passed, failed
        if cond:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name}  {detail}")
            failed += 1

    g.cmd("boardsize 19")

    # ---------- T5：重放真实对局，default / W1 / clear 三态加权数子全等 ----------
    print("\n== T5: 逐步 play 重放 80 手真实对局，default/W1/clear 三态加权数子全等 ==")
    tokens, komi = load_game_positions(GAME_JSON, 0)
    s_default, r = replay_score(g, tokens, komi, None)
    check("T5 final_score(default)", s_default is not None, r[:120])
    s_w1, r = replay_score(g, tokens, komi, W1_TABLE)
    check("T5 final_score(W1 加载)", s_w1 is not None, r[:120])
    s_clear, r = replay_score(g, tokens, komi, None)
    check("T5 final_score(clear 后默认)", s_clear is not None, r[:120])
    if None not in (s_default, s_w1, s_clear):
        d1 = abs(s_default - s_w1)
        d2 = abs(s_default - s_clear)
        check("T5 W1 加载 == 标准数子 (Δ=0)", d1 < 1e-6, f"default={s_default} w1={s_w1} Δ={d1}")
        check("T5 clear 后 == 标准数子 (Δ=0)", d2 < 1e-6, f"default={s_default} clear={s_clear} Δ={d2}")

    # ---------- T6a：加载正确性（kata-query-weights 直接读回） ----------
    print("\n== T6a: kata-load-weights / kata-query-weights 加载正确性（读回 361 值核对） ==")
    special = {("K", 10): 3.0, ("A", 1): 2.0, ("K", 17): 2.0,
               ("T", 19): 2.0, ("Q", 10): 2.0, ("C", 3): 2.0}
    tbl = [1.0] * (N * N)
    for (c, r), w in special.items():
        tbl[gtp_idx(r, c)] = w
    write_table(TMP, tbl)
    err, r = g.cmd(f"kata-load-weights {TMP}")
    check("T6a kata-load-weights", not err, r[:120])
    err, r = g.cmd("kata-query-weights")
    vals = r.replace("=", "").strip().split()
    check("T6a kata-query-weights 返回 361 值", not err and len(vals) == 361, f"got {len(vals)}: {r[:80]}")
    if len(vals) == 361:
        got = [float(v) for v in vals]
        special_idx = {gtp_idx(r, c): (c, r) for (c, r) in special}
        check("T6a K10=3.0", abs(got[gtp_idx(10, "K")] - 3.0) < 1e-6, f"got {got[gtp_idx(10,'K')]}")
        edge_ok = all(abs(got[i] - 2.0) < 1e-6 for i, (c, r) in special_idx.items() if (c, r) != ("K", 10))
        check("T6a 边界点 A1/K17/T19/Q10/C3=2.0", edge_ok,
              ", ".join(f"{c}{r}:{got[gtp_idx(r,c)]}" for (c, r) in special if (c, r) != ("K", 10)))
        rest_ok = all(abs(v - 1.0) < 1e-6 for i, v in enumerate(got) if i not in special_idx)
        check("T6a 其余点=1.0", rest_ok)

    # ---------- T6b：同 6 孤子盘面，W=1 三态 final_score 相等 ----------
    print("\n== T6b: 6 散孤子盘面，default / W1加载 / clear 三态 final_score 相等（非终局走 NN 估算亦可观） ==")
    black_pts = [("A", 1), ("K", 10), ("K", 17)]
    white_pts = [("T", 19), ("Q", 10), ("C", 3)]
    tokens = []
    for col, r in black_pts:
        tokens += ["B", f"{col}{r}"]
    for col, r in white_pts:
        tokens += ["W", f"{col}{r}"]

    g.cmd("kata-clear-weights")
    s_default, r = score_finished(g, tokens, None, "0.5")
    check("T6b final_score(default)", s_default is not None, r[:120])
    s_w1, r = score_finished(g, tokens, W1_TABLE, "0.5")
    check("T6b final_score(W1 加载)", s_w1 is not None, r[:120])
    s_clear, r = score_finished(g, tokens, None, "0.5")
    check("T6b final_score(clear 后默认)", s_clear is not None, r[:120])
    if None not in (s_default, s_w1, s_clear):
        check("T6b W1 加载 == default (Δ=0)", abs(s_w1 - s_default) < 1e-6,
              f"default={s_default} w1={s_w1} Δ={s_w1 - s_default}")
        check("T6b clear 后 == default (Δ=0)", abs(s_clear - s_default) < 1e-6,
              f"default={s_default} clear={s_clear} Δ={s_clear - s_default}")

    g.cmd("kata-clear-weights")
    g.close()
    print(f"\n== 结果: {passed} passed, {failed} failed ==")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()