from __future__ import annotations

import logging
import sys
from importlib import import_module

build_metadata = import_module("build.lib.agentlab.metadata")
build_metadata.__name__ = "agentlab.metadata"
build_metadata.__package__ = "agentlab"
sys.modules["agentlab.metadata"] = build_metadata

build_garmin_cli = import_module("build.lib.agentlab.cli.garmin_fetch")
build_garmin_cli.logger = logging.getLogger("agentlab.cli.garmin_fetch")
build_garmin_cli.__name__ = "agentlab.cli.garmin_fetch"
build_garmin_cli.__package__ = "agentlab.cli"
sys.modules["agentlab.cli.garmin_fetch"] = build_garmin_cli

agentlab_cli_pkg = import_module("agentlab.cli")
setattr(agentlab_cli_pkg, "garmin_fetch", build_garmin_cli)

pytest_plugins = ("tests.withings_l0._utils",)
