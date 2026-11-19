"""Fixtures that script small, fully deterministic git repositories."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ALICE = ("Alice Anders", "alice@example.com")
ALICE_OLD = ("alice", "alice@old-laptop.local")
BOB = ("Bob Brown", "bob@example.com")
CAROL = ("Carol Chen", "carol@example.com")
DAVE = ("Dave Doe", "dave@example.com")


class Repo:
    """Create commits with fixed authors and dates."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q", "-b", "main")

    def git(self, *args: str, env: dict | None = None) -> str:
        full_env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, **(env or {})}
        proc = subprocess.run(["git", *args], cwd=self.path, env=full_env, capture_output=True, text=True, check=True)
        return proc.stdout.strip()

    def write(self, path: str, content: str | bytes | None) -> None:
        target = self.path / path
        if content is None:
            self.git("rm", "-q", path)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content)
        self.git("add", path)

    def commit(
        self,
        message: str,
        files: dict[str, str | bytes | None] | None = None,
        author: tuple[str, str] = ALICE,
        date: str = "2024-01-01T10:00:00+00:00",
        committer: tuple[str, str] | None = None,
    ) -> str:
        for path, content in (files or {}).items():
            self.write(path, content)
        committer = committer or author
        env = {
            "GIT_AUTHOR_NAME": author[0],
            "GIT_AUTHOR_EMAIL": author[1],
            "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_NAME": committer[0],
            "GIT_COMMITTER_EMAIL": committer[1],
            "GIT_COMMITTER_DATE": date,
        }
        self.git("commit", "-q", "--allow-empty", "-m", message, env=env)
        return self.git("rev-parse", "HEAD")

    def merge(self, branch: str, message: str, author: tuple[str, str], date: str) -> str:
        env = {
            "GIT_AUTHOR_NAME": author[0],
            "GIT_AUTHOR_EMAIL": author[1],
            "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_NAME": author[0],
            "GIT_COMMITTER_EMAIL": author[1],
            "GIT_COMMITTER_DATE": date,
        }
        self.git("merge", "-q", "--no-ff", "-m", message, branch, env=env)
        return self.git("rev-parse", "HEAD")


@pytest.fixture(autouse=True)
def isolated_git(tmp_path_factory, monkeypatch):
    """Never read the developer's ~/.gitconfig or the system config."""
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(var, raising=False)


def nested(depth: int, lines: int = 3) -> str:
    out = []
    for d in range(depth):
        out.extend("    " * d + f"line_{d}_{i}" for i in range(lines))
    return "\n".join(out) + "\n"


@pytest.fixture(scope="session")
def repo_template(tmp_path_factory) -> Path:
    """Build the scripted repository once per test session."""
    return build_project(tmp_path_factory.mktemp("template") / "project").path


@pytest.fixture
def repo(repo_template, tmp_path) -> Repo:
    """A fresh copy of the scripted project (tests may add commits to it)."""
    target = tmp_path / "project"
    shutil.copytree(repo_template, target, symlinks=True)
    r = Repo.__new__(Repo)
    r.path = target
    return r


def build_project(path: Path) -> Repo:
    """A small project with renames, a PR merge, a squash merge, a lock file and a mailmap alias."""
    r = Repo(path)
    r.commit(
        "Initial commit",
        {"README.md": "# demo\n", "src/app.py": nested(2), ".mailmap": f"{ALICE[0]} <{ALICE[1]}> <{ALICE_OLD[1]}>\n"},
        author=ALICE,
        date="2024-01-01T09:00:00+02:00",
    )
    r.commit("Add core", {"src/core.py": nested(4)}, author=ALICE_OLD, date="2024-01-02T10:30:00+02:00")
    r.commit("Lock deps", {"package-lock.json": "{}\n" * 500}, author=ALICE, date="2024-01-03T11:00:00+02:00")
    r.commit("Tune core", {"src/core.py": nested(5)}, author=ALICE, date="2024-01-08T14:00:00+02:00")
    r.commit("Docs", {"docs/guide.md": "hello\nworld\n"}, author=BOB, date="2024-01-09T21:15:00-05:00")
    r.commit("Logo", {"assets/logo.bin": b"\x00\x01\x02binary"}, author=BOB, date="2024-01-13T12:00:00-05:00")

    r.git("checkout", "-q", "-b", "feature")
    r.commit("Feature part 1", {"src/feature.py": nested(3)}, author=BOB, date="2024-02-01T09:00:00-05:00")
    r.commit("Feature part 2", {"src/feature.py": nested(4)}, author=BOB, date="2024-02-02T09:00:00-05:00")
    r.git("checkout", "-q", "main")
    r.commit("Hotfix", {"src/app.py": nested(3)}, author=ALICE, date="2024-02-02T12:00:00+02:00")
    r.merge("feature", "Merge pull request #7 from bob/feature", author=ALICE, date="2024-02-03T09:00:00-05:00")

    r.commit("Rename app", {}, author=ALICE, date="2024-02-04T10:00:00+02:00")
    r.git("mv", "src/app.py", "src/main.py")
    r.commit("Move app to main", {}, author=ALICE, date="2024-02-05T10:00:00+02:00")
    r.commit("Add CLI (#12)", {"src/cli.py": nested(2)}, author=CAROL, date="2024-03-10T08:00:00+01:00")
    r.commit("One-off typo fix", {"README.md": "# demo project\n"}, author=DAVE, date="2024-03-16T23:30:00+00:00")
    r.commit("Carol again", {"src/cli.py": nested(3)}, author=CAROL, date="2024-05-01T08:00:00+01:00")
    r.commit("Remove docs", {"docs/guide.md": None}, author=BOB, date="2024-05-02T10:00:00-05:00")
    return r
