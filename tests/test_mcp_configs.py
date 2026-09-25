"""The shipped MCP client configs must list every server the host launches, by a real console script."""

import json
import tomllib
from pathlib import Path

import pytest

from dev_radar.hub import SERVERS

ROOT = Path(__file__).parent.parent
SCRIPTS = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["scripts"]


@pytest.mark.parametrize("config", [".mcp.json", "examples/claude_desktop_config.json"])
def test_config_covers_every_server(config):
    servers = json.loads((ROOT / config).read_text())["mcpServers"]
    scripts = {entry["args"][-1] for entry in servers.values()}
    modules = {SCRIPTS[s].split(":")[0] for s in scripts}  # KeyError = a script pyproject doesn't define
    assert modules == set(SERVERS.values())
