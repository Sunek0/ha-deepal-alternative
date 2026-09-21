"""Tests that the shipped examples are standalone."""

import importlib.util
import sys
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
SDK_ROOT = str(EXAMPLES_DIR.parent)


def _load_example(path: Path):
    spec = importlib.util.spec_from_file_location(f"deepal_example_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("path", sorted(EXAMPLES_DIR.glob("*.py")), ids=lambda p: p.name)
def test_example_adds_sdk_root_to_sys_path(monkeypatch, path):
    monkeypatch.setattr(sys, "path", [entry for entry in sys.path if entry != SDK_ROOT])
    _load_example(path)
    assert sys.path[0] == SDK_ROOT


@pytest.mark.parametrize("path", sorted(EXAMPLES_DIR.glob("*.py")), ids=lambda p: p.name)
def test_example_defines_main(path):
    module = _load_example(path)
    assert callable(module.main)
