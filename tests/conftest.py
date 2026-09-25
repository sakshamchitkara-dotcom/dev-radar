import subprocess
from pathlib import Path

import pytest


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=Ada", "-c", "user.email=ada@example.com", *args],
        check=True, capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway repo: app.py changed 3x, README once, a lockfile 2x, two authors."""
    _git(tmp_path, "init", "-q", "-b", "main")
    for i in range(3):
        (tmp_path / "app.py").write_text(f"print({i})\n" * (i + 1))
        (tmp_path / "uv.lock").write_text(f"lock {i}\n")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-qm", f"feat: app v{i}")
    (tmp_path / "README.md").write_text("hi\n")
    _git(tmp_path, "add", "-A")
    subprocess.run(
        ["git", "-C", str(tmp_path), "-c", "user.name=Grace", "-c", "user.email=grace@example.com",
         "commit", "-qm", "docs: readme"],
        check=True, capture_output=True,
    )
    return tmp_path


@pytest.fixture(autouse=True)
def no_user_config(tmp_path_factory, monkeypatch):
    """Keep a developer's ~/.config/dev-radar/config.toml out of the tests."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path_factory.mktemp("xdg-config")))
