"""
test_perf.py — 性能基准（@pytest.mark.slow，默认跳过，--slow 启用）

依赖：INFRA ✅ + ENGINE ✅
复用 test_gtp_engine.py 的 GtpEngine 类（subprocess + GTP 通信）。
基准项：
  - test_startup_time：Popen → get_komi 返回的 wall-clock，断言 < 30s（tuner 缓存命中 ~10s）
  - test_genmove_latency_maxvisits10：20路 + maxVisits=10 的 genmove，断言 < 10s
  - test_genmove_default_visits：默认 visits 的 genmove，记录时延（不设硬阈值）

运行：python -m pytest test_perf.py -v --slow -s
"""

from __future__ import annotations

import os
import time

import pytest

from test_gtp_engine import GtpEngine, _BASE, _KOMI, CACHE_DIR

EXE = r"E:\小工具\new_go\dist_opencl\katago.exe"


@pytest.mark.slow
def test_startup_time():
    """启动一个引擎实例（带 gtp_override.cfg 缓存），测 Popen → get_komi wall-clock。

    断言 < 30s（x25 tuner 缓存命中应 ~10s；首次 tuning ~2min 会超时→反映缓存失效）。
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    t0 = time.time()
    eng = GtpEngine(_KOMI)
    ok, _, _ = eng.send("get_komi", timeout=120)
    elapsed = time.time() - t0
    eng.quit()
    assert ok, "get_komi 应成功"
    print(f"\n[perf] 启动时延 (Popen→get_komi): {elapsed:.2f}s")
    assert elapsed < 30.0, f"启动应 <30s（缓存命中），实际 {elapsed:.2f}s"


@pytest.mark.slow
def test_genmove_latency_maxvisits10():
    """20路 + maxVisits=10 的 genmove B，测 wall-clock。断言 < 10s。

    maxVisits=10 大幅限制搜索，genmove 应快速返回。
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    eng = GtpEngine(_KOMI)
    try:
        eng.send("boardsize 20")
        eng.send("clear_board")
        t0 = time.time()
        ok, _, status = eng.send("genmove B", timeout=60)
        elapsed = time.time() - t0
        assert ok, f"genmove 应成功: {status!r}"
        print(f"\n[perf] genmove 时延 (maxVisits=10, 20路): {elapsed:.2f}s → {status!r}")
        assert elapsed < 10.0, f"genmove(maxVisits=10) 应 <10s，实际 {elapsed:.2f}s"
    finally:
        eng.quit()


@pytest.mark.slow
def test_genmove_default_visits():
    """默认 visits（无 maxVisits override）的 genmove，记录时延（不设硬阈值）。

    用 _BASE（无 maxVisits=10），保留 default_gtp.cfg 的默认 maxVisits（通常 500-1000）。
    仅记录数据，供性能基线参考。
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    # _BASE 含 gtpForceMaxNNSize + homeDataDir，但无 maxVisits 限制、无 komi override
    eng = GtpEngine(_BASE)
    try:
        eng.send("boardsize 20")
        eng.send("clear_board")
        t0 = time.time()
        ok, _, status = eng.send("genmove B", timeout=120)
        elapsed = time.time() - t0
        assert ok, f"genmove 应成功: {status!r}"
        print(f"\n[perf] genmove 时延 (默认visits, 20路): {elapsed:.2f}s → {status!r}")
        # 不设硬阈值，仅记录。但 sanity：应在合理范围（<120s 不超时）
        assert elapsed < 120.0, f"genmove 不应超时，实际 {elapsed:.2f}s"
    finally:
        eng.quit()
