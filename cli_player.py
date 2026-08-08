"""
cli_player.py — 20路Ban选围棋 CLI 对弈工具

职责：
  1. GtpEngine 类：通过 subprocess 管道与 KataGo 通信（GTP 协议）
  2. run_game()：Ban 阶段（调用 BanController）+ 正式对局（双引擎交替 genmove）
  3. main()：命令行入口（aivai / human 模式）

策略：先用原版 19 路引擎开发框架，等 ENGINE 完成后切 20 路。
      kata-set-bans 暂用占位实现（打印日志），数子暂用引擎 final_score。

GTP 协议响应格式：
  成功：= <内容>\n[后续行]\n\n   （以等号开头，空行结束）
  失败：? <错误>\n\n             （以问号开头，空行结束）
  kata-analyze 为流式输出：info 行持续输出，不以 = 开头，靠新命令终止。
"""

from __future__ import annotations

import argparse
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Optional

from ban_controller import (
    BanConfig,
    BanController,
    col_to_letter,
    gtp_to_point,
    point_to_gtp,
)

# ── 默认资源路径 ────────────────────────────────────────────────────────────

DEFAULT_ENGINE = r"E:\2026-01-07-win64-KataGo\katago_opencl\katago.exe"
DEFAULT_MODEL = r"E:\2026-01-07-win64-KataGo\weights\28b.bin.gz"
DEFAULT_CONFIG = r"E:\2026-01-07-win64-KataGo\katago_configs\default_gtp.cfg"

# 选手 ↔ 棋色映射（规则：选手 B 执黑，选手 A 执白）
PLAYER_TO_COLOR = {"B": "B", "A": "W"}      # 选手 → 棋色 B/W
COLOR_TO_PLAYER = {"B": "B", "W": "A"}      # 棋色 → 选手


# ── GtpEngine：subprocess 管道通信 ──────────────────────────────────────────

class GtpEngine:
    """与一个 KataGo 实例通信的 GTP 客户端。

    读线程持续把 stdout 行放入 queue，send/analyze 从 queue 消费。
    这样流式命令（kata-analyze）与标准命令可共用同一读取通道，
    analyze 的残留 info 行会被下一次 send 自动跳过。
    """

    def __init__(
        self,
        exe_path: str,
        model_path: str,
        config_path: str,
        boardsize: int = 19,
        color: str = "B",
        stderr_path: Optional[str] = None,
        extra_configs: Optional[list[str]] = None,
        init_timeout: float = 900.0,
    ):
        if not os.path.isfile(exe_path):
            raise FileNotFoundError(f"引擎不存在: {exe_path}")
        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"权重不存在: {model_path}")
        if not os.path.isfile(config_path):
            raise FileNotFoundError(f"配置不存在: {config_path}")
        for ec in (extra_configs or []):
            if not os.path.isfile(ec):
                raise FileNotFoundError(f"附加配置不存在: {ec}")

        args = [exe_path, "gtp", "-config", config_path]
        for ec in (extra_configs or []):
            args += ["-config", ec]
        args += ["-model", model_path]
        self._init_timeout = init_timeout

        # stderr 重定向到文件便于调试启动失败，避免污染主输出
        self._stderr_file = None
        if stderr_path:
            self._stderr_file = open(stderr_path, "w", encoding="utf-8")
            stderr_target = self._stderr_file
        else:
            stderr_target = subprocess.DEVNULL

        self.color = color
        self.boardsize = boardsize
        self._closed = False

        try:
            self._proc = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr_target,
                text=True,
                encoding="utf-8",
                bufsize=1,  # 行缓冲
            )
        except Exception as e:
            if self._stderr_file:
                self._stderr_file.close()
            raise RuntimeError(f"启动引擎失败: {e}") from e

        # 守护读线程：持续 readline → queue
        self._read_queue: queue.Queue[str] = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

        # 初始化棋盘（首次启动可能触发 OpenCL tuning，用大超时）
        self.boardsize_n(boardsize, timeout=self._init_timeout)
        self.clear_board(timeout=self._init_timeout)

    # ── 读线程 ──

    def _read_loop(self) -> None:
        try:
            while True:
                line = self._proc.stdout.readline()
                if not line:
                    break  # stdout 关闭（进程退出）
                self._read_queue.put(line)
        except Exception:
            pass

    # ── 标准命令 ──

    def send(self, cmd: str, timeout: float = 120.0) -> str:
        """发送 GTP 命令，返回去掉 = / ? 前缀的响应内容。

        失败（? 前缀）抛 RuntimeError。流式命令残留的 info 行会被跳过。
        """
        if self._closed or self._proc.poll() is not None:
            raise RuntimeError(f"引擎已退出，无法发送: {cmd}")

        try:
            self._proc.stdin.write(cmd + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise RuntimeError(f"写入引擎管道失败: {e}") from e

        deadline = time.time() + timeout
        header: Optional[str] = None

        # 找到响应头（以 = 或 ? 开头），跳过 analyze 残留的 info 行
        while header is None:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(f"等待 GTP 响应超时 [{cmd}]")
            try:
                line = self._read_queue.get(timeout=min(1.0, remaining))
            except queue.Empty:
                if self._proc.poll() is not None:
                    raise RuntimeError(
                        f"引擎进程已退出 (code={self._proc.returncode}) [{cmd}]"
                    )
                continue
            stripped = line.strip()
            if stripped.startswith("=") or stripped.startswith("?"):
                header = stripped
            # 否则丢弃（analyze 流式残留）

        prefix = header[0]
        rest = header[1:].strip()

        # 读取后续行直到空行
        body: list[str] = []
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(f"等待 GTP 响应空行超时 [{cmd}]")
            try:
                line = self._read_queue.get(timeout=min(1.0, remaining))
            except queue.Empty:
                if self._proc.poll() is not None:
                    raise RuntimeError(
                        f"引擎进程已退出 (code={self._proc.returncode}) [{cmd}]"
                    )
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

    # ── 流式分析命令 ──

    def analyze(self, interval: float = 1.0) -> str:
        """kata-analyze 流式输出。读取 interval 秒内的所有行并返回。

        注意：调用后引擎处于流式模式，下一次 send 会自动终止并跳过残留。
        interval 参数单位为秒，内部转换为厘秒（KataGo 要求）。
        """
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

    def boardsize_n(self, n: int, timeout: Optional[float] = None) -> str:
        return self.send(f"boardsize {n}", timeout=timeout)

    def clear_board(self, timeout: Optional[float] = None) -> str:
        return self.send("clear_board", timeout=timeout)

    def komi(self, k: float) -> str:
        return self.send(f"komi {k}")

    def genmove(self, color: str) -> str:
        """生成一手。color 为 'black' 或 'white'。返回 GTP 坐标 / pass / resign。"""
        return self.send(f"genmove {color}").strip()

    def play(self, color: str, coord: str) -> str:
        """通知引擎对方落子。color 为 'black'/'white'，coord 为 GTP 坐标或 pass。"""
        return self.send(f"play {color} {coord}")

    def final_score(self) -> str:
        """终局数子。返回引擎原始结果，如 'B+4.5' / 'W+3.75' / '0'。"""
        return self.send("final_score").strip()

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

def print_board(
    stones: dict[tuple[int, int], str],
    banned: set[tuple[int, int]],
    boardsize: int,
) -> None:
    """打印棋盘。stones: (row,col)->'B'/'W'；banned 禁点用 X；空点用 ."""
    cols = "".join(col_to_letter(c) for c in range(1, boardsize + 1))
    # 列标头（每两字符一列）
    header = "   " + " ".join(cols)
    print(header)
    for r in range(boardsize, 0, -1):
        parts = [f"{r:>2} "]
        for c in range(1, boardsize + 1):
            if (r, c) in banned:
                parts.append("X")
            elif (r, c) in stones:
                parts.append(stones[(r, c)])
            else:
                parts.append(".")
            parts.append(" ")
        parts.append(f"{r:<2}")
        print("".join(parts))
    print(header)


# ── 对局配置 ────────────────────────────────────────────────────────────────

@dataclass
class GameConfig:
    mode: str = "aivai"            # aivai / human
    color: str = "B"               # human 模式下人类棋色 B/W
    boardsize: int = 19
    engine: str = DEFAULT_ENGINE
    model: str = DEFAULT_MODEL
    config: str = DEFAULT_CONFIG
    extra_configs: Optional[list[str]] = None  # 附加 config（如 homeDataDir 缓存）
    ban_strategy: str = "random"   # random / gtp / auto
    max_moves: int = 0             # 正式对局最大手数（0=不限）
    komi: float = 4.25             # 贴子（传给引擎 final_score 用）


# ── 对局主流程 ──────────────────────────────────────────────────────────────

def run_game(cfg: GameConfig) -> None:
    """完整对局：Ban 阶段 → 正式对局 → 终局数子。"""
    boardsize = cfg.boardsize

    # 选手 ↔ 棋色
    human_color = cfg.color                # "B" 或 "W"
    human_player = COLOR_TO_PLAYER[human_color]  # 选手 "A" 或 "B"

    # ── 启动两个引擎：黑(选手B) / 白(选手A) ──
    print(f"[启动] 黑方引擎 (选手B) ...")
    eng_black = GtpEngine(
        cfg.engine, cfg.model, cfg.config,
        boardsize=boardsize, color="B",
        stderr_path="engine_black.log",
        extra_configs=cfg.extra_configs,
    )
    print(f"[启动] 白方引擎 (选手A) ...")
    eng_white = GtpEngine(
        cfg.engine, cfg.model, cfg.config,
        boardsize=boardsize, color="W",
        stderr_path="engine_white.log",
        extra_configs=cfg.extra_configs,
    )

    try:
        # 设置贴子（让 final_score 用 4.25）
        try:
            eng_black.komi(cfg.komi)
            eng_white.komi(cfg.komi)
        except RuntimeError as e:
            print(f"[警告] 设置 komi 失败（占位接受）: {e}")

        # ═══════════ Ban 阶段 ═══════════
        margin = 3
        ban_cfg = BanConfig(
            board_size=boardsize,
            region_row_min=margin + 1,
            region_row_max=boardsize - margin,
            region_col_min=margin + 1,
            region_col_max=boardsize - margin,
        )
        bc = BanController(ban_cfg)

        # 注入 GTP 引擎接口（框架阶段用 random，不实际调用 gtp 分析；
        # 此处注入仅占位，便于后续切换 gtp 策略）
        def _engine_stub(cmd: str) -> str:
            # kata-set-bans / kata-clear-bans：原版不支持，占位返回成功
            if cmd.startswith("kata-set-bans") or cmd.startswith("kata-clear-bans"):
                print(f"  [placeholder] {cmd}")
                return "= \n"
            # kata-analyze：走 analyze 流式
            if cmd.startswith("kata-analyze"):
                return eng_black.analyze(interval=1.0)
            return eng_black.send(cmd)

        bc.set_gtp_engine(_engine_stub)

        print(f"\n=== Ban 阶段（{boardsize}路，区域 "
              f"{ban_cfg.region_row_min}-{ban_cfg.region_row_max}，"
              f"共 {ban_cfg.ban_count} 次）===")

        while not bc.is_finished:
            player = bc.current_player
            role = "黑" if player == "B" else "白"
            print(f"\n--- 第 {bc.step + 1}/{ban_cfg.ban_count} 次 ban "
                  f"(选手 {player}/{role}) ---")

            if cfg.mode == "human" and player == human_player:
                # 人类输入
                while True:
                    try:
                        label = input(f"您(选手{player})输入禁点坐标 (如 D7): ").strip()
                    except EOFError:
                        print("\n[输入结束]")
                        return
                    if not label:
                        continue
                    res = bc.submit_label(label)
                    if res.valid:
                        print(f"  已禁: {label}")
                        break
                    print(f"  无效: {res.reason}（违例 {bc.violations[player]}/"
                          f"{ban_cfg.max_violations}），请重试")
            else:
                # AI 选点
                res = bc.submit_ai(cfg.ban_strategy)
                if res.valid and bc.history:
                    last = bc.history[-1]
                    print(f"  AI 禁: {last.label}")
                elif not res.valid:
                    print(f"  AI ban 失败: {res.reason}")
                    if bc.is_finished:
                        break

            print_board({}, bc.banned, boardsize)

        # Ban 结果
        result = bc.get_result()
        ban_labels = sorted(point_to_gtp(r, c) for r, c in result.banned_points)
        print(f"\n[Ban 阶段结束] 结论: {result.concluded_by}")
        print(f"[禁点集合] ({len(ban_labels)} 个): {' '.join(ban_labels)}")
        print(f"[placeholder] would set bans: {' '.join(ban_labels)}")

        # ═══════════ 正式对局 ═══════════
        print(f"\n=== 正式对局（黑先，komi={cfg.komi}）===")

        engines = {"B": eng_black, "W": eng_white}
        stones: dict[tuple[int, int], str] = {}
        turn = "B"  # 黑先 = 选手 B
        consecutive_pass = 0
        move_no = 0
        resigned_by: Optional[str] = None

        while True:
            if cfg.max_moves and move_no >= cfg.max_moves:
                print(f"\n[达到最大手数 {cfg.max_moves}，停止对局]")
                break

            color_gtp = "black" if turn == "B" else "white"
            role = "黑" if turn == "B" else "白"
            eng = engines[turn]

            if cfg.mode == "human" and turn == human_color:
                # 人类走子
                while True:
                    try:
                        coord = input(f"\n第{move_no+1}手 您({role})落子 "
                                      f"(坐标如 D4 / pass / resign): ").strip()
                    except EOFError:
                        print("\n[输入结束]")
                        return
                    if coord:
                        break
                coord = coord.upper() if coord not in ("pass", "resign") else coord.lower()
            else:
                # AI 走子
                print(f"\n第{move_no+1}手 {role}(AI) 思考中 ...")
                coord = eng.genmove(color_gtp)
                coord_norm = coord.strip().lower()
                print(f"  {role} → {coord}")

            move_no += 1
            coord_norm = coord.strip().lower()

            if coord_norm == "resign":
                resigned_by = turn
                print(f"  {role} 认输")
                break

            if coord_norm == "pass":
                consecutive_pass += 1
                print(f"  {role} pass（连续 pass: {consecutive_pass}）")
                if consecutive_pass >= 2:
                    print("  双方连续 pass，终局")
                    break
            else:
                consecutive_pass = 0
                try:
                    row, col = gtp_to_point(coord)
                except (ValueError, IndexError):
                    print(f"  [警告] 无法解析坐标 {coord}，跳过同步")
                    row, col = None, None

                if row is not None:
                    stones[(row, col)] = turn
                    # 落在禁点？（原版引擎不知禁点，占位警告）
                    if (row, col) in bc.banned:
                        print(f"  [警告] {coord} 落在禁点上 "
                              f"（原版引擎不支持 bans，占位接受）")
                    # 同步给另一个引擎
                    other_key = "W" if turn == "B" else "B"
                    try:
                        engines[other_key].play(color_gtp, coord)
                    except RuntimeError as e:
                        print(f"  [警告] 同步对手引擎失败: {e}")

                print_board(stones, bc.banned, boardsize)

            turn = "W" if turn == "B" else "B"

        # ═══════════ 终局数子 ═══════════
        print(f"\n=== 终局数子 ===")
        if resigned_by is not None:
            winner = "W" if resigned_by == "B" else "B"
            print(f"认输结局: {'黑' if winner == 'B' else '白'}(选手"
                  f"{'B' if winner == 'B' else 'A'})胜")
        else:
            try:
                score = eng_black.final_score()
                print(f"[占位] 引擎 final_score: {score}")
            except RuntimeError as e:
                print(f"[占位] final_score 失败: {e}")
                score = "?"
            print(f"[TODO] 后续按 20 路公式判定（禁点 {len(ban_labels)} 个）：")
            print(f"       有效点 = 400 - {len(ban_labels)} = "
                  f"{400 - len(ban_labels)}，基准 = "
                  f"{(400 - len(ban_labels)) / 2}")
            print(f"       黑胜: 黑子数 > {195 + cfg.komi:.2f}  "
                  f"白胜: 白子数 > {195 - cfg.komi:.2f}")

    finally:
        print("\n[关闭引擎 ...")
        eng_black.close()
        eng_white.close()
        print("[完成]")


# ── 命令行入口 ──────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="20路Ban选围棋 CLI 对弈工具（KataGo 引擎托管）",
    )
    p.add_argument("--mode", choices=["aivai", "human"], default="aivai",
                   help="对局模式：aivai=AI对AI，human=人对AI（默认 aivai）")
    p.add_argument("--color", choices=["B", "W"], default="B",
                   help="human 模式下人类棋色：B=黑先手，W=白后手（默认 B）")
    p.add_argument("--boardsize", type=int, default=19,
                   help="棋盘尺寸（默认 19，ENGINE 就绪后切 20）")
    p.add_argument("--engine", default=DEFAULT_ENGINE, help="katago.exe 路径")
    p.add_argument("--model", default=DEFAULT_MODEL, help="权重文件路径")
    p.add_argument("--config", default=DEFAULT_CONFIG, help="GTP 配置文件路径")
    p.add_argument("--extra-config", action="append", default=None,
                   help="附加 GTP 配置（可多次，如 homeDataDir 缓存），覆盖主 config")
    p.add_argument("--ban-strategy", choices=["random", "gtp", "auto"],
                   default="random", help="Ban 阶段 AI 策略（默认 random 保底）")
    p.add_argument("--max-moves", type=int, default=0,
                   help="正式对局最大手数（0=不限，调试时可设小值）")
    p.add_argument("--komi", type=float, default=4.25,
                   help="贴子（默认 4.25，传给引擎 final_score）")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    cfg = GameConfig(
        mode=args.mode,
        color=args.color,
        boardsize=args.boardsize,
        engine=args.engine,
        model=args.model,
        config=args.config,
        extra_configs=args.extra_config,
        ban_strategy=args.ban_strategy,
        max_moves=args.max_moves,
        komi=args.komi,
    )

    print(f"模式: {cfg.mode} | 棋盘: {cfg.boardsize}路 | "
          f"ban策略: {cfg.ban_strategy} | komi: {cfg.komi}")
    if cfg.mode == "human":
        print(f"人类: {'黑(先手,选手B)' if cfg.color == 'B' else '白(后手,选手A)'}")

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
