# -*- coding: utf-8 -*-
"""
settings.py — GUI 设置持久化（settings.json）

管理 AI 搜索参数（maxVisits/maxTime/numSearchThreads/ponderingEnabled）+ 权重路径。
路径：开发模式用 gui.py 同目录；exe 模式用 sys.executable 所在目录。
"""

from __future__ import annotations

import json
import os
import sys

DEFAULT_SETTINGS = {
    "level": "业余",            # 新手/业余/高级/自定义
    "maxVisits": 800,
    "maxTime": 10.0,
    "numSearchThreads": 6,
    "ponderingEnabled": False,
    "model_path": r"E:\2026-01-07-win64-KataGo\weights\28b.bin.gz",
    "board_rows": 20,
    "board_cols": 20,
    "game_mode": "人vsAI",      # "人vsAI" / "AIvsAI" / "人vs人"
}

PRESETS = {
    "新手": {"maxVisits": 50, "maxTime": 2.0, "numSearchThreads": 6},
    "业余": {"maxVisits": 800, "maxTime": 10.0, "numSearchThreads": 6},
    "高级": {"maxVisits": 3000, "maxTime": 30.0, "numSearchThreads": 6},
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
