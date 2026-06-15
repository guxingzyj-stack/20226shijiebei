from __future__ import annotations

import builtins
import importlib
import sys
from pathlib import Path


def test_api_directory_has_no_model_imports():
    for path in Path("api").rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        assert "from model" not in text, path
        assert "import model" not in text, path


def test_api_main_imports_without_model_package(monkeypatch):
    removed_model_modules = {
        name: module
        for name, module in list(sys.modules.items())
        if name == "model" or name.startswith("model.")
    }
    for name in removed_model_modules:
        sys.modules.pop(name, None)
    for name in ("api.main", "api.vig", "api.betting_open_gate", "api.ops_health_check"):
        sys.modules.pop(name, None)

    original_import = builtins.__import__

    def blocked_model_import(name, *args, **kwargs):
        if name == "model" or name.startswith("model."):
            raise ModuleNotFoundError("blocked model import in API test")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_model_import)
    try:
        module = importlib.import_module("api.main")
    finally:
        sys.modules.update(removed_model_modules)

    assert module.app.title == "World Cup Jingcai Simulation API"
