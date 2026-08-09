"""conftest.py — pytest 共享配置。

注册 markers + 提供 --slow 开关（性能测试默认跳过，--slow 启用）。
"""

import pytest


def pytest_addoption(parser):
    parser.addoption("--slow", action="store_true", default=False,
                     help="启用 @pytest.mark.slow 性能测试（默认跳过）")


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: 性能/基准测试，默认跳过，--slow 启用")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--slow"):
        skip_slow = pytest.mark.skip(reason="性能测试，加 --slow 启用")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)
