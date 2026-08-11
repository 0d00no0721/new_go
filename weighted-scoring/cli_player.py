# -*- coding: utf-8 -*-
"""
cli_player.py — 加权点目围棋 CLI 对弈工具

职责：
  1. GtpEngine 类：通过 subprocess 管道与改造版 KataGo 通信（GTP 协议）
     支持加权专属命令：kata-load-weights / kata-clear-weights / kata-query-weights
  2. run_game()：人 vs AI / AI vs AI 对弈（单引擎交替 genmove），终局显示加权分
  3. review_sgf()：SGF 导入复盘（打印棋谱 + 终局棋盘 + 加权分）
  4. query_weight()：查任意点权重（kata-query-weights）
  5. main()：命令行入口

引擎：使用 ENGINE 改造后的 KataGo（19 路 + 加权数子 + kata-load-weights）。
       komi 7.5 经标准 GTP komi 命令生效（标准半整数，无需 override）。
       权重表经 kata-load-weights 注入，W=1 时退化为标准围棋。

GTP 协议响应格式：
  成功：= <内容>\\n[后续行]\\n\\n   失败：? <错误>\\n\\n
  kata-analyze 为流式输出，靠新命令终止。

坐标系：全模块统一 0-indexed (r,c)，r=0 顶部，c=0 左侧（见 sgf_io.py）。
"""

from __future__ import annotations

import argparse
import datetime
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Optional

from scoring import load_weights, score_game
from sgf_io import (
    COL_LETTERS,
    N,
    ReplayBoard,
    SgfGame,
    export_sgf,
    gtp_to_rc,
    import_sgf,
    rc_to_gtp,
)

# ── 默认资源路径 ────────────────────────────────────────────────────────────

DEFAULT_ENGINE = r"E:\小工具\new_go\weighted-scoring\dist_opencl\katago.exe"
DEFAULT_MODEL = r"E:\2026-01-07-win64-KataGo\weights\28b.bin.gz"
DEFAULT_CONFIG = r"E:\2026-01-07-win64-KataGo\katago_configs\default_gtp.cfg"
DEFAULT_OVERRIDE = r"E:\小工具\new_go\weighted-scoring\gtp_override.cfg"
DEFAULT_WEIGHTS = r"E:\小工具\new_go\weighted-scoring\weight_table_final.txt"
DEFAULT_KOMI = 7.5   # 标准中国贴目（标定数据不可信，见收敛报告_komi_utility校准.md §2）


# ── 路径处理（规避 Windows 中文路径致 KataGo fopen 失败）────────────────────

def _ascii_temp_dir() -> str:
    """返回一个可写的 ASCII 临时目录（KataGo 的 fopen 不支持 UTF-8 中文路径）。"""
    candidates = [
        tempfile.gettempdir(),
        os.environ.get("SYSTEMDRIVE", "C:") + "\\Temp",
        "E:\\katago_cache",
        os.environ.get("SYSTEMDRIVE", "C:") + "\\",
    ]
    for cand in candidates:
        if not cand:
            continue
        try:
            cand.encode("ascii")
        except UnicodeEncodeError:
            continue
        if os.path.isdir(cand):
            return cand
    return os.path.abspath(os.sep)


def ascii_safe_copy(path: str, label: str = "ws_weights_tmp.txt") -> str:
    """若 path 含非 ASCII 字符，复制到 ASCII 临时路径后返回；否则原样返回。"""
    try:
        path.encode("ascii")
        return path
    except UnicodeEncodeError:
        pass
    dst = os.path.join(_ascii_temp_dir(), label)
    shutil.copyfile(path, dst)
    return dst


# ── GtpEngine：subprocess 管道通信 ──────────────────────────────────────────

class GtpEngine:
    """与一个 KataGo 实例通信的 GTP 客户端。

    读线程持续把 stdout 行放入 queue，send/analyze 从 queue 消费。
    流式命令（kata-analyze）与标准命令可共用同一读取通道。
    """

    def __init__(
        self,
        exe_path: str,
        model_path: str,
        config_path: str,
        boardsize: int = N,
        stderr_path: Optional[str] = None,
        extra_configs: Optional[list[str]] = None,
        override_configs: Optional[list[str]] = None,
        init_timeout: float = 900.0,
    ):
        if not os.path.isfile(exe_path):
            raise FileNotFoundError(f"引擎不存在: {exe_path}")
        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"权重不存在: {model_path}")
        if not os.path.isfile(config_path):
            raise FileNotFoundError(f"配置不存在: {config_path}")

        args = [exe_path, "gtp", "-config", config_path]
        for ec in (extra_configs or []):
            args += ["-config", ec]
        for oc in (override_configs or []):
            args += ["-override-config", oc]
        args += ["-model", model_path]
        self._init_timeout = init_timeout

        self._stderr_file = None
        if stderr_path:
            self._stderr_file = open(stderr_path, "w", encoding="utf-8")
            stderr_target = self._stderr_file
        else:
            stderr_target = subprocess.DEVNULL

        self.boardsize = boardsize
        self._closed = False

        try:
            popen_kwargs = dict(
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr_target,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            self._proc = subprocess.Popen(args, **popen_kwargs)
        except Exception as e:
            if self._stderr_file:
                self._stderr_file.close()
            raise RuntimeError(f"启动引擎失败: {e}") from e

        self._read_queue: queue.Queue[str] = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

        self.send(f"boardsize {boardsize}", timeout=self._init_timeout)
        self.send("clear_board", timeout=self._init_timeout)

    def _read_loop(self) -> None:
        try:
            while True:
                line = self._proc.stdout.readline()
                if not line:
                    break
                self._read_queue.put(line)
        except Exception:
            pass

    def send(self, cmd: str, timeout: float = 120.0) -> str:
        """发送 GTP 命令，返回去掉 = / ? 前缀的响应内容。失败抛 RuntimeError。"""
        if self._closed or self._proc.poll() is not None:
            raise RuntimeError(f"引擎已退出，无法发送: {cmd}")
        try:
            self._proc.stdin.write(cmd + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise RuntimeError(f"写入引擎管道失败: {e}") from e

        deadline = time.time() + timeout
        header: Optional[str] = None
        while header is None:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(f"等待 GTP 响应超时 [{cmd}]")
            try:
                line = self._read_queue.get(timeout=min(1.0, remaining))
            except queue.Empty:
                if self._proc.poll() is not None:
                    raise RuntimeError(f"引擎进程已退出 (code={self._proc.returncode}) [{cmd}]")
                continue
            stripped = line.strip()
            if stripped.startswith("=") or stripped.startswith("?"):
                header = stripped

        prefix = header[0]
        rest = header[1:].strip()

        body: list[str] = []
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(f"等待 GTP 响应空行超时 [{cmd}]")
            try:
                line = self._read_queue.get(timeout=min(1.0, remaining))
            except queue.Empty:
                if self._proc.poll() is not None:
                    raise RuntimeError(f"引擎进程已退出 (code={self._proc.returncode}) [{cmd}]")
                continue
            if line.strip() == "":
                break
            body.append(line.rstrip("\r\n"))

        content = rest
        if body:
            content = (rest + "\n" + "\n".join(body)) if rest else "\n".join(body)

        if prefix == "?":
            raise RuntimeError(f"GTP 命令失败 [{cmd}]: {content}")
        return content

    def analyze(self, interval: float = 1.0) -> str:
        """kata-analyze 流式输出，读取 interval 秒内的所有行并返回。"""
        if self._closed or self._proc.poll() is not None:
            raise RuntimeError("引擎已退出，无法 analyze")
        cmd = f"kata-analyze interval {int(interval * 100)}"
        try:
            self._proc.stdin.write(cmd + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise RuntimeError(f"写入引擎管道失败: {e}") from e

        lines: list[str] = []
        deadline = time.time() + interval
        while time.time() < deadline:
            remaining = deadline - time.time()
            try:
                line = self._read_queue.get(timeout=max(0.01, remaining))
            except queue.Empty:
                break
            s = line.strip()
            if s == "":
                continue
            lines.append(s)
        return "\n".join(lines)

    # ── 高级封装 ──

    def clear_board(self, timeout: Optional[float] = None) -> str:
        return self.send("clear_board", timeout=timeout)

    def komi(self, k: float) -> str:
        return self.send(f"komi {k}")

    def genmove(self, color: str) -> str:
        """生成一手。color 为 'black' 或 'white'。返回 GTP 坐标 / pass / resign。"""
        return self.send(f"genmove {color}").strip()

    def play(self, color: str, coord: str) -> str:
        """通知引擎落子。color 为 'black'/'white'，coord 为 GTP 坐标或 pass。"""
        return self.send(f"play {color} {coord}")

    def final_score(self) -> str:
        """终局加权数子。返回引擎原始结果，如 'B+4.5' / 'W+3.75' / '0'。"""
        return self.send("final_score").strip()

    def load_weights(self, path: str) -> str:
        return self.send(f"kata-load-weights {path}")

    def clear_weights(self) -> str:
        return self.send("kata-clear-weights")

    def query_weights(self) -> list[float]:
        """查询当前权重表，返回长度 N*N 的浮点列表。"""
        r = self.send("kata-query-weights")
        vals = [float(x) for x in r.replace("=", "").strip().split()]
        return vals

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._proc.poll() is None:
                self._proc.stdin.write("quit\n")
                self._proc.stdin.flush()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass
        if self._stderr_file:
            try:
                self._stderr_file.close()
            except Exception:
                pass


# ── 棋盘打印 ────────────────────────────────────────────────────────────────

def print_board(stones: dict[tuple[int, int], str], last: Optional[tuple[int, int]] = None) -> None:
    """打印棋盘。stones: (r,c)->'B'/'W'；last 最后一手用红点标记（终端用 '*'）。"""
    header = "   " + " ".join(COL_LETTERS[:N])
    print(header)
    for r in range(N):
        row_num = N - r
        parts = [f"{row_num:>2} "]
        for c in range(N):
            if (r, c) in stones:
                parts.append(stones[(r, c)])
            else:
                parts.append(".")
            parts.append(" ")
        parts.append(f"{row_num:<2}")
        print("".join(parts))
    print(header)
    if last is not None:
        r, c = last
        print(f"  最后一手: {rc_to_gtp(r, c)}")


# ── 对局配置 ────────────────────────────────────────────────────────────────

@dataclass
class GameConfig:
    mode: str = "aivai"            # aivai / human
    color: str = "B"               # human 模式下人类棋色 B/W
    engine: str = DEFAULT_ENGINE
    model: str = DEFAULT_MODEL
    config: str = DEFAULT_CONFIG
    extra_configs: Optional[list[str]] = None
    override_configs: Optional[list[str]] = None
    weights: str = DEFAULT_WEIGHTS
    komi: float = DEFAULT_KOMI
    max_moves: int = 0             # 最大手数（0=不限）
    visits: int = 200              # 每手搜索 visits（经 override-config 生效）
    sgf_out: Optional[str] = None
    no_sgf: bool = False


# ── 权重摘要 ────────────────────────────────────────────────────────────────

def _flatten_weights(weights) -> list[float]:
    """权重表归一为 flat list（长度 N*N）。接受 flat list 或 2D list（load_weights 产物）。"""
    if weights and isinstance(weights[0], (list, tuple)):
        return [float(x) for row in weights for x in row]
    return [float(x) for x in weights]


def _stones_to_1based(stones_0idx: dict[tuple[int, int], str]) -> dict[tuple[int, int], str]:
    """0-indexed (r,c) stones → 1-based (row,col)（RULES scoring.py 约定：row=1 顶、col=1 左）。"""
    return {(r + 1, c + 1): col for (r, c), col in stones_0idx.items()}


def print_weight_summary(weights) -> None:
    """打印权重表摘要（ΣW / min / max / 关键点）。接受 flat 或 2D 权重表。"""
    w = _flatten_weights(weights)
    wsum = sum(w)
    wmin = min(w)
    wmax = max(w)
    print(f"[权重] ΣW = {wsum:.2f}  (标准 19 路 Σ=361)  范围 [{wmin:.3f}, {wmax:.3f}]")
    # 关键点：天元 K10=(9,9)，星位 D16/D4/Q16/Q4 = (3,3)/(15,3)/(3,15)/(15,15)
    keypts = {
        "天元 K10": (9, 9),
        "星位 D16": (3, 3), "星位 D4": (15, 3),
        "星位 Q16": (3, 15), "星位 Q4": (15, 15),
        "一线 A19": (0, 0),
    }
    parts = []
    for name, (r, c) in keypts.items():
        parts.append(f"{name}={w[r * N + c]:.3f}")
    print("[权重] " + "  ".join(parts))


# ── 对局主流程 ──────────────────────────────────────────────────────────────

def run_game(cfg: GameConfig) -> None:
    """完整对局：加载权重 → 正式对局 → 终局加权数子。"""
    human_color = cfg.color

    # ── 启动引擎 ──
    override = list(cfg.override_configs) if cfg.override_configs else []
    override.append(f"maxVisits={cfg.visits}")
    override.append(f"ignoreGTPAndForceKomi={cfg.komi}")  # 绕过 GTP komi 半整数限制
    extra = list(cfg.extra_configs) if cfg.extra_configs else []
    if cfg.config and os.path.isfile(cfg.config) and not extra:
        # 默认附加 gtp_override.cfg（若存在且未显式提供）
        if os.path.isfile(DEFAULT_OVERRIDE):
            extra = [DEFAULT_OVERRIDE]

    print(f"[启动] 加权点目 KataGo 引擎 ...")
    eng = GtpEngine(
        cfg.engine, cfg.model, cfg.config,
        boardsize=N, stderr_path="engine_cli.log",
        extra_configs=extra,
        override_configs=override,
    )

    try:
        # ── 贴目（经 override-config 生效，绕过 GTP komi 半整数限制）──
        try:
            actual_komi = eng.send("get_komi").strip()
            print(f"[确认] komi = {actual_komi}（经 ignoreGTPAndForceKomi 生效）")
        except RuntimeError:
            print(f"[确认] komi = {cfg.komi}（override-config）")

        # ── 加载权重表 ──
        if cfg.weights and os.path.isfile(cfg.weights):
            w_path = ascii_safe_copy(cfg.weights)
            eng.load_weights(w_path)
            print(f"[权重] 已加载: {cfg.weights}" + (
                f"  (经 ASCII 临时路径 {w_path})" if w_path != cfg.weights else ""))
            try:
                w = eng.query_weights()
                if len(w) == N * N:
                    print_weight_summary(w)
            except RuntimeError:
                # 某些引擎版本可能不支持 query，从文件读
                print_weight_summary(load_weights(cfg.weights))
        else:
            print(f"[权重] 未加载（W=1 标准围棋）")

        # ═══════════ 正式对局 ═══════════
        mode_desc = "人 vs AI" if cfg.mode == "human" else "AI vs AI"
        print(f"\n=== {mode_desc}（19 路，黑先，komi={cfg.komi}）===")
        if cfg.mode == "human":
            print(f"您执{'黑(先手)' if human_color == 'B' else '白(后手)'}")

        board = ReplayBoard(N)
        turn = "B"  # 黑先
        consecutive_pass = 0
        move_no = 0
        resigned_by: Optional[str] = None
        game_moves: list[tuple[str, str]] = []  # (color, gtp_coord or "pass")
        game_result = ""

        while True:
            if cfg.max_moves and move_no >= cfg.max_moves:
                print(f"\n[达到最大手数 {cfg.max_moves}，停止对局]")
                break

            color_gtp = "black" if turn == "B" else "white"
            role = "黑" if turn == "B" else "白"

            if cfg.mode == "human" and turn == human_color:
                while True:
                    try:
                        coord = input(f"\n第{move_no + 1}手 您({role})落子 "
                                      f"(坐标如 D4 / pass / resign): ").strip()
                    except EOFError:
                        print("\n[输入结束]")
                        return
                    if coord:
                        break
                coord = coord if coord.lower() in ("pass", "resign") else coord.upper()
            else:
                print(f"\n第{move_no + 1}手 {role}(AI) 思考中 ...")
                coord = eng.genmove(color_gtp)
                print(f"  {role} → {coord}")

            move_no += 1
            coord_norm = coord.strip().lower()

            if coord_norm == "resign":
                resigned_by = turn
                game_moves.append((turn, "resign"))
                print(f"  {role} 认输")
                break

            if coord_norm == "pass":
                game_moves.append((turn, "pass"))
                consecutive_pass += 1
                print(f"  {role} pass（连续 pass: {consecutive_pass}）")
                if consecutive_pass >= 2:
                    print("  双方连续 pass，终局")
                    break
            else:
                game_moves.append((turn, coord.strip()))
                consecutive_pass = 0
                try:
                    r, c = gtp_to_rc(coord)
                    board.play(turn, r, c)
                except (ValueError, IndexError):
                    print(f"  [警告] 无法解析坐标 {coord}")
                # 同步给引擎（人 vs AI 时人类落子需通知引擎；AI 落子引擎已记录）
                if cfg.mode == "human" and turn == human_color:
                    try:
                        eng.play(color_gtp, coord)
                    except RuntimeError as e:
                        print(f"  [警告] 同步引擎失败: {e}")
                print_board(board.stones, last=(r, c) if coord_norm != "pass" else None)

            turn = "W" if turn == "B" else "B"

        # ═══════════ 终局加权数子 ═══════════
        print(f"\n=== 终局加权数子 ===")
        if resigned_by is not None:
            winner = "W" if resigned_by == "B" else "B"
            game_result = f"{winner}+R"
            print(f"认输结局: {'黑' if winner == 'B' else '白'}胜")
        else:
            try:
                score = eng.final_score()
                print(f"引擎 final_score（加权）: {score}")
                game_result = score
            except RuntimeError as e:
                print(f"final_score 失败: {e}")
                game_result = ""

            # scoring.py 盘面加权统计（未标记死子，仅供参考）
            try:
                w = load_weights(cfg.weights) if cfg.weights and os.path.isfile(cfg.weights) else None
                res = score_game(_stones_to_1based(board.stones), w, komi=cfg.komi)
                d = res["detail"]
                print(f"[盘面加权] 黑 {res['black_weighted']:.2f} "
                      f"(子 {d['black_stones_weight']:.1f} + 独占空 {d['black_territory_weight']:.1f})")
                print(f"[盘面加权] 白 {res['white_weighted']:.2f} "
                      f"(子 {d['white_stones_weight']:.1f} + 独占空 {d['white_territory_weight']:.1f})")
                print(f"[盘面加权] 中性空 {d['neutral']} 点  贴目 {cfg.komi}")
                print(f"[盘面加权] 差分（白−黑+贴目）{res['final_white_minus_black_score']:.2f}  "
                      f"→ {res['result']}（注：未标记死子，以引擎 final_score 为准）")
            except Exception as e:
                print(f"[盘面加权] 计算失败: {e}")

        # ═══════════ SGF 导出 ═══════════
        if not cfg.no_sgf:
            sgf_path = cfg.sgf_out or (
                f"game_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.sgf"
            )
            sgf_game = SgfGame(
                boardsize=N,
                komi=cfg.komi,
                player_b="人类" if (cfg.mode == "human" and human_color == "B") else "AI",
                player_a="人类" if (cfg.mode == "human" and human_color == "W") else "AI",
                date=datetime.date.today().isoformat(),
                weights_file=cfg.weights,
                moves=game_moves,
                result=game_result,
            )
            try:
                export_sgf(sgf_game, sgf_path)
                print(f"[SGF] 已导出: {sgf_path}")
            except Exception as e:
                print(f"[SGF] 导出失败: {e}")

    finally:
        print("\n[关闭引擎 ...")
        eng.close()
        print("[完成]")


# ── SGF 复盘 ────────────────────────────────────────────────────────────────

def review_sgf(path: str, weights: Optional[str] = None) -> None:
    """导入 SGF 并打印棋谱 + 终局棋盘 + 加权分。"""
    game = import_sgf(path)

    print(f"=== SGF 复盘: {path} ===")
    print(f"棋盘: {game.boardsize}路 | 贴目: {game.komi} | "
          f"黑: {game.player_b} | 白: {game.player_a} | 日期: {game.date}")
    if game.weights_file:
        print(f"权重表: {game.weights_file}")
    if game.result:
        print(f"结果: {game.result}")
    if game.boardsize != N:
        print(f"[提示] 棋盘尺寸 {game.boardsize} 非 19 路")

    print(f"\n手谱 ({len(game.moves)} 手):")
    for i, (color, coord) in enumerate(game.moves):
        role = "黑" if color == "B" else "白"
        print(f"  {i + 1:>3}. {role} {coord}")

    board = ReplayBoard(game.boardsize)
    for color, coord in game.moves:
        if coord.lower() == "pass":
            continue
        r, c = gtp_to_rc(coord)
        board.play(color, r, c)

    print(f"\n终局棋盘:")
    print_board(board.stones)

    # 加权分（scoring.py，未标记死子）
    w = None
    if weights and os.path.isfile(weights):
        w = load_weights(weights)
        print(f"\n[加权分] 权重表: {weights}")
    elif game.weights_file:
        # 尝试用同目录权重表
        cand = os.path.join(os.path.dirname(path), game.weights_file)
        if os.path.isfile(cand):
            w = load_weights(cand)
            print(f"\n[加权分] 权重表: {cand}")
    res = score_game(_stones_to_1based(board.stones), w, komi=game.komi)
    d = res["detail"]
    print(f"[加权分] 黑 {res['black_weighted']:.2f} (子 {d['black_stones_weight']:.1f} "
          f"+ 独占空 {d['black_territory_weight']:.1f})")
    print(f"[加权分] 白 {res['white_weighted']:.2f} (子 {d['white_stones_weight']:.1f} "
          f"+ 独占空 {d['white_territory_weight']:.1f})")
    print(f"[加权分] 中性空 {d['neutral']}  贴目 {game.komi}  "
          f"→ {res['result']}（注：未标记死子，仅供参考）")


# ── 权重查询 ────────────────────────────────────────────────────────────────

def query_weight(cfg: GameConfig, point: Optional[str]) -> None:
    """启动引擎，加载权重，查询单点或全表摘要。"""
    override = list(cfg.override_configs) if cfg.override_configs else []
    override.append(f"maxVisits={cfg.visits}")
    extra = list(cfg.extra_configs) if cfg.extra_configs else []
    if os.path.isfile(DEFAULT_OVERRIDE):
        extra = extra or [DEFAULT_OVERRIDE]

    eng = GtpEngine(cfg.engine, cfg.model, cfg.config, boardsize=N,
                    stderr_path="engine_cli.log", extra_configs=extra,
                    override_configs=override)
    try:
        w_path = ascii_safe_copy(cfg.weights)
        eng.load_weights(w_path)
        w = eng.query_weights()
        if len(w) != N * N:
            print(f"[错误] query-weights 返回 {len(w)} 个值（期望 {N * N}）")
            return
        print_weight_summary(w)
        if point:
            r, c = gtp_to_rc(point)
            print(f"\n[查询] {point} (r={r}, c={c}) 权重 W = {w[r * N + c]:.6f}")
    finally:
        eng.close()


# ── 命令行入口 ──────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="加权点目围棋 CLI 对弈工具（KataGo 引擎托管）",
    )
    p.add_argument("--mode", choices=["aivai", "human"], default="aivai",
                   help="对局模式：aivai=AI对AI，human=人对AI（默认 aivai）")
    p.add_argument("--color", choices=["B", "W"], default="B",
                   help="human 模式下人类棋色：B=黑先手，W=白后手（默认 B）")
    p.add_argument("--engine", default=DEFAULT_ENGINE, help="katago.exe 路径")
    p.add_argument("--model", default=DEFAULT_MODEL, help="权重文件路径")
    p.add_argument("--config", default=DEFAULT_CONFIG, help="GTP 配置文件路径")
    p.add_argument("--extra-config", action="append", default=None,
                   help="附加 GTP 配置（可多次），覆盖主 config")
    p.add_argument("--override-config", action="append", default=None,
                   help="override-config（可多次，如 maxVisits=200）")
    p.add_argument("--weights", default=DEFAULT_WEIGHTS,
                   help="加权表文件路径（默认 weight_table_final.txt）")
    p.add_argument("--komi", type=float, default=DEFAULT_KOMI,
                   help="贴目（默认 7.5，ENGINE 标定值）")
    p.add_argument("--visits", type=int, default=200,
                   help="每手搜索 visits（经 override-config 生效，默认 200）")
    p.add_argument("--max-moves", type=int, default=0,
                   help="最大手数（0=不限，调试时可设小值）")
    p.add_argument("--sgf-out", default=None,
                   help="SGF 导出路径（默认自动生成 game_YYYYMMDD_HHMMSS.sgf）")
    p.add_argument("--sgf-in", default=None,
                   help="导入 SGF 复盘（不启动新对局）")
    p.add_argument("--no-sgf", action="store_true", help="不导出 SGF 文件")
    p.add_argument("--query-weight", default=None,
                   help="查询单点权重（如 D16），不启动对局；留空则打印全表摘要")
    p.add_argument("--query-weights", action="store_true",
                   help="加载权重并打印全表摘要后退出（不启动对局）")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    cfg = GameConfig(
        mode=args.mode,
        color=args.color,
        engine=args.engine,
        model=args.model,
        config=args.config,
        extra_configs=args.extra_config,
        override_configs=args.override_config,
        weights=args.weights,
        komi=args.komi,
        max_moves=args.max_moves,
        visits=args.visits,
        sgf_out=args.sgf_out,
        no_sgf=args.no_sgf,
    )

    # 权重查询模式（不启动对局）
    if args.query_weights or args.query_weight is not None:
        try:
            query_weight(cfg, args.query_weight)
        except Exception as e:
            print(f"[错误] {e}", file=sys.stderr)
            return 1
        return 0

    # SGF 导入复盘模式
    if args.sgf_in:
        try:
            review_sgf(args.sgf_in, weights=args.weights)
        except FileNotFoundError as e:
            print(f"[错误] {e}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"[错误] {e}", file=sys.stderr)
            raise
        return 0

    mode_desc = "人 vs AI" if cfg.mode == "human" else "AI vs AI"
    print(f"模式: {mode_desc} | 棋盘: 19×19 | komi: {cfg.komi} | visits: {cfg.visits}")
    if cfg.mode == "human":
        print(f"人类: {'黑(先手)' if cfg.color == 'B' else '白(后手)'}")

    try:
        run_game(cfg)
    except KeyboardInterrupt:
        print("\n[中断]")
        return 130
    except Exception as e:
        print(f"\n[错误] {e}", file=sys.stderr)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
