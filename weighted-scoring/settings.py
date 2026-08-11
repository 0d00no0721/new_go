# -*- coding: utf-8 -*-
"""
settings.py — 加权点目围棋 GUI 设置持久化（settings.json）

管理 AI 搜索参数（maxVisits/maxTime/numSearchThreads/ponderingEnabled）
+ 引擎/模型/配置/权重表路径 + 贴目。
路径：开发模式用 gui.py 同目录；exe 模式用 sys.executable 所在目录。
"""

from __future__ import annotations

import json
import os
import sys

from sgf_io import N

DEFAULT_SETTINGS = {
    "level": "业余",                       # 新手/业余/高级/自定义
    "maxVisits": 800,
    "maxTime": 10.0,
    "numSearchThreads": 20,
    "ponderingEnabled": False,
    "engine_path": r"E:\小工具\new_go\weighted-scoring\dist_opencl\katago.exe",
    "config_path": r"E:\2026-01-07-win64-KataGo\katago_configs\default_gtp.cfg",
    "extra_config_path": "gtp_override.cfg",  # 相对脚本/exe 目录
    "model_path": r"E:\2026-01-07-win64-KataGo\weights\28b.bin.gz",
    "weights_path": "weight_table_final.txt",  # 加权表（相对脚本/exe 目录）
    "komi": 7.5,                           # 标准中国贴目（标定数据不可信，见收敛报告_komi_utility校准.md §2）
    "board_size": N,                       # 固定 19（权重表为 19×19）
    "game_mode": "人vsAI",                 # "人vsAI" / "AIvsAI" / "人vs人"
    "show_heatmap": False,                 # GUI 是否叠加权重热力图
}

PRESETS = {
    "新手": {"maxVisits": 50, "maxTime": 2.0, "numSearchThreads": 20},
    "业余": {"maxVisits": 800, "maxTime": 10.0, "numSearchThreads": 20},
    "高级": {"maxVisits": 3000, "maxTime": 30.0, "numSearchThreads": 20},
}


def _settings_dir() -> str:
    """设置文件所在目录：exe 模式用 exe 目录，开发模式用脚本目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def settings_path() -> str:
    return os.path.join(_settings_dir(), "settings.json")


def load_settings() -> dict:
    """读取 settings.json，不存在或损坏返回 DEFAULT_SETTINGS 副本。"""
    path = settings_path()
    if not os.path.isfile(path):
        return dict(DEFAULT_SETTINGS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULT_SETTINGS)
        merged.update(data)
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict) -> None:
    """写入 settings.json。"""
    path = settings_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def settings_exist() -> bool:
    return os.path.isfile(settings_path())


def build_override_configs(settings: dict) -> list[str]:
    """根据 settings 生成 KataGo override-config 列表（搜索限制部分）。"""
    return [
        f"maxVisits={int(settings['maxVisits'])}",
        f"maxTime={float(settings['maxTime'])}",
        f"numSearchThreads={int(settings['numSearchThreads'])}",
        f"ponderingEnabled={'true' if settings['ponderingEnabled'] else 'false'}",
    ]
