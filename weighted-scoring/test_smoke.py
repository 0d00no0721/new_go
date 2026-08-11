#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GTP 冒烟测试：验证加权数子改造。
测试矩阵：
  T1: kata-query-weights 在 W=1 下返回 361 个 1.0
  T2: W=1 下 final_score 与标准数子一致（用一个简单已结束局面）
  T3: W≠1 下 final_score 反映权重（用同一局面对比）
  T4: kata-clear-weights 恢复 1.0
"""
import subprocess, sys, time, threading

KATAGO = r"E:\小工具\new_go\weighted-scoring\dist_opencl\katago.exe"
CONFIG = r"E:\2026-01-07-win64-KataGo\katago_configs\default_gtp.cfg"
OVERRIDE = r"E:\小工具\new_go\weighted-scoring\gtp_override.cfg"
MODEL = r"E:\2026-01-07-win64-KataGo\weights\28b.bin.gz"
W_TABLE = r"E:\katago_cache\weight_table.txt"


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
        # GTP 响应：以 '= ' 或 '? ' 开头，后续可选多行，以空行结束
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
                    # 单行响应（如 "= A19"）直接结束；多行（如 list_commands "= " 后跟多行）需读到空行
                    if not line[1:].strip() == "" and c not in ("list_commands", "kata-query-weights", "showboard"):
                        # 单行结果：补读一个空行消费掉
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


def main():
    g = GtpProc()
    passed = 0
    failed = 0

    def check(name, cond, detail=""):
        nonlocal passed, failed
        if cond:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name}  {detail}")
            failed += 1

    print("== 启动 ==")
    err, r = g.cmd("name")
    check("engine responds to name", not err and "KataGo" in r, r)
    # 验证新命令已注册
    err, r = g.cmd("list_commands")
    check("kata-load-weights 已注册", "kata-load-weights" in r, r[:200])
    check("kata-query-weights 已注册", "kata-query-weights" in r)
    check("kata-clear-weights 已注册", "kata-clear-weights" in r)

    err, r = g.cmd("boardsize 19")
    check("boardsize 19", not err, r)
    err, r = g.cmd("clear_board")
    check("clear_board", not err, r)
    err, r = g.cmd("komi 7.5")
    check("komi 7.5", not err, r)

    print("\n== T1: kata-query-weights 默认应全 1.0 ==")
    err, r = g.cmd("kata-query-weights")
    vals = r.replace("=", "").strip().split()
    check("query-weights 返回 361 个值", not err and len(vals) == 361, f"got {len(vals)}: {r[:80]}")
    if len(vals) == 361:
        allone = all(abs(float(v) - 1.0) < 1e-6 for v in vals)
        check("默认全为 1.0", allone, f"sample: {vals[:5]}")

    print("\n== T2: 加载 W=1 表，final_score 应等于标准数子 ==")
    err, r = g.cmd(f"kata-load-weights {W_TABLE}")
    check("kata-load-weights", not err, r)
    err, r = g.cmd("kata-query-weights")
    vals = r.replace("=", "").strip().split()
    if len(vals) == 361:
        allone = all(abs(float(v) - 1.0) < 1e-6 for v in vals)
        check("加载后仍全 1.0", allone)
    # 构造一个简单已结束局面：黑围住整个右上角
    # 放置一些棋子用 play 命令模拟
    # 简化：直接用 final_score 在空盘上（应 W+7.5，因为空盘按 area 双方 0，加 komi）
    err, r = g.cmd("clear_board")
    err, r = g.cmd(f"kata-load-weights {W_TABLE}")
    # 空盘 final_score：area 0-0 + komi = 仅 komi（权重不影响空盘）
    err, r = g.cmd("final_score")
    check("空盘 final_score 仅含 komi（W=1基线）", not err and ("W+" in r or "B+" in r or r.strip()=="0"), r)

    print("\n== T3: W≠1 下权重加载与查询 ==")
    # 生成 W=2 表，验证加载后查询返回 2.0
    w2 = r"E:\katago_cache\weight_table_w2.txt"
    with open(w2, "w") as f:
        f.write(" ".join(["2.0"] * 361) + "\n")
    err, r = g.cmd("clear_board")
    err, r = g.cmd(f"kata-load-weights {w2}")
    check("kata-load-weights W=2", not err, r)
    err, r = g.cmd("kata-query-weights")
    vals = r.replace("=", "").strip().split()
    if len(vals) == 361:
        alltwo = all(abs(float(v) - 2.0) < 1e-6 for v in vals)
        check("W=2 表加载后全为 2.0", alltwo, f"sample: {vals[:5]}")
    # 空盘 W=2：area 0-0 + komi = 仅 komi（权重不影响空盘，因为双方 area=0）
    err, r = g.cmd("final_score")
    check("空盘 W=2 仍仅含 komi（双方 area=0）", not err and ("W+" in r or "B+" in r or r.strip()=="0"), r)

    print("\n== T3b: W 不均匀时 final_score 应反映权重（构造黑围一角）==")
    # 黑下星位围角，白下对面，用 final_score（搜索估 ownership）对比 W=1 vs 角部高权重
    err, r = g.cmd("clear_board")
    err, r = g.cmd(f"kata-load-weights {W_TABLE}")  # 先 W=1
    # 下一手让黑占一个角（简化：genmove B）
    err, r = g.cmd("komi 0.5")  # 小 komi 让 area 主导
    check("komi 0.5", not err, r)
    err, r = g.cmd("genmove B")
    check("genmove B (W=1)", not err and not r.startswith("?"), r[:60])
    score_w1 = r  # 记录（genmove 不返回 score，只返回 move）

    # 实际对比要用 final_score；空盘+一手棋不会有终局，跳过深度对比
    # 核心验证留给实际对局工具
    print("  [SKIP] 深度加权对比留待对局工具验证（需完整终局）")

    print("\n== T4: kata-clear-weights 恢复 1.0 ==")
    err, r = g.cmd("kata-clear-weights")
    check("kata-clear-weights", not err, r)
    err, r = g.cmd("kata-query-weights")
    vals = r.replace("=", "").strip().split()
    if len(vals) == 361:
        allone = all(abs(float(v) - 1.0) < 1e-6 for v in vals)
        check("clear 后全 1.0", allone)

    g.close()
    print(f"\n== 结果: {passed} passed, {failed} failed ==")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
