from importlib import import_module


def test_import_agentlab_package() -> None:
    module = import_module("agentlab")
    assert module.__name__ == "agentlab"
