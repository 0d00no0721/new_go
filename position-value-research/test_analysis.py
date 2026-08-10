#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最小连通测试：启动 katago analysis，发空盘请求，验证接口。用 28b 复用现成 tuner。"""
import json, subprocess, sys, time, threading

KATAGO = r"E:\小工具\new_go\ban-selection\dist_opencl\katago.exe"
CONFIG = r"E:\小工具\new_go\position-value-research\analysis.cfg"
MODEL = r"E:\2026-01-07-win64-KataGo\weights\28b.bin.gz"

def main():
    proc = subprocess.Popen(
        [KATAGO, "analysis", "-config", CONFIG, "-model", MODEL],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    # 异步实时打印 stderr（启动日志）
    def drain_stderr():
        for line in iter(proc.stderr.readline, ""):
            sys.stderr.write(f"[kgerr] {line}")
            sys.stderr.flush()
    t = threading.Thread(target=drain_stderr, daemon=True)
    t.start()

    req = {
        "id": "test-empty",
        "moves": [],
        "rules": "chinese",
        "komi": 7.5,
        "boardXSize": 19,
        "boardYSize": 19,
        "maxVisits": 50,
        "includeOwnership": False,
    }
    line = json.dumps(req) + "\n"
    print(f"[send] {line.strip()}", flush=True)
    proc.stdin.write(line)
    proc.stdin.flush()

    t0 = time.time()
    got = False
    while time.time() - t0 < 180:
        out = proc.stdout.readline()
        if not out:
            break
        try:
            resp = json.loads(out)
        except Exception:
            continue
        if resp.get("id") == "test-empty" and not resp.get("isDuringSearch", False):
            root = resp.get("rootInfo", {})
            moves = resp.get("moveInfos", [])
            print(f"[recv {time.time()-t0:.1f}s] rootInfo.scoreLead={root.get('scoreLead')} winrate={root.get('winrate')}", flush=True)
            print(f"[recv] moveInfos count={len(moves)}", flush=True)
            for m in sorted(moves, key=lambda m: -m.get("visits", 0))[:5]:
                print(f"        {m.get('move'):>4} visits={m.get('visits')} scoreLead={m.get('scoreLead')} order={m.get('order')}", flush=True)
            got = True
            break

    proc.stdin.close()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
    print(f"[done] got={got}", flush=True)
    sys.exit(0 if got else 1)

if __name__ == "__main__":
    main()
