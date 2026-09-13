"""Opt-in requirements for the native Qt release-evidence lane."""
from __future__ import annotations

import os

import pytest


def pytest_addoption(parser):
    parser.addoption("--require-qt", action="store_true",
                     help="Require real Anki Qt bindings and reject skipped release evidence.")


def pytest_configure(config):
    if not config.getoption("--require-qt"):
        return
    os.environ.setdefault("ANKI_GARDEN_SKIP_STARTUP", "1")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from aqt.qt import QApplication
        from PyQt6.QtCore import QT_VERSION_STR
        from PyQt6.QtTest import QTest
        if not QApplication.__module__.startswith("PyQt6.") or not QT_VERSION_STR or QTest is None:
            raise ImportError("real Qt bindings are required")
    except ImportError as error:
        raise pytest.UsageError(f"Required Anki Qt runtime is unavailable: {error}") from error


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if (item.config.getoption("--require-qt")
            and item.get_closest_marker("release_evidence") and report.skipped):
        report.outcome = "failed"
        report.longrepr = f"Required release evidence was skipped: {report.longrepr}"
