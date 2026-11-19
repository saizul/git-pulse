"""Read history from ``git log`` (through ``subprocess``) into plain dataclasses."""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime

RECORD = "\x1e"
UNIT = "\x1f"
LOG_FORMAT = UNIT.join(["%H", "%P", "%aN", "%aE", "%aI", "%cN", "%cE", "%cI", "%s"])

#: Generated files that drown out real signal in churn, hotspots and ownership.
GENERATED_PATTERNS: tuple[str, ...] = (
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
    "poetry.lock",
    "uv.lock",
    "Pipfile.lock",
    "Cargo.lock",
    "composer.lock",
    "Gemfile.lock",
    "go.sum",
    "*.min.js",
    "*.min.css",
    "*.map",
)

_BRACE_RENAME = re.compile(r"^(?P<pre>.*)\{(?P<old>.*) => (?P<new>.*)\}(?P<post>.*)$")


class GitError(RuntimeError):
    """Raised when git is missing or a git command fails."""


@dataclass(frozen=True)
class FileChange:
    path: str
    added: int
    removed: int
    binary: bool = False
    old_path: str | None = None

    @property
    def churn(self) -> int:
        return self.added + self.removed


@dataclass
class Commit:
    sha: str
    parents: tuple[str, ...]
    author_name: str
    author_email: str
    author_date: datetime
    committer_name: str
    committer_email: str
    committer_date: datetime
    subject: str
    files: list[FileChange] = field(default_factory=list)

    @property
    def is_merge(self) -> bool:
        return len(self.parents) > 1

    @property
    def added(self) -> int:
        return sum(f.added for f in self.files)

    @property
    def removed(self) -> int:
        return sum(f.removed for f in self.files)


@dataclass
class LogOptions:
    """What part of the history to read."""

    rev: str = "HEAD"
    all_refs: bool = False
    since: str | None = None
    until: str | None = None
    paths: Sequence[str] = ()
    mailmap: str | None = None
    first_parent: bool = False


def git(repo: str, *args: str, input_bytes: bytes | None = None) -> bytes:
    """Run ``git -C repo args`` and return stdout as bytes."""
    cmd = ["git", "-C", repo, "-c", "core.quotepath=off", "-c", "log.showSignature=false", *args]
    try:
        proc = subprocess.run(cmd, input=input_bytes, capture_output=True, check=False)
    except FileNotFoundError as exc:  # pragma: no cover - depends on the machine
        raise GitError("git executable not found; install git and make sure it is on PATH") from exc
    if proc.returncode != 0:
        msg = proc.stderr.decode("utf-8", "replace").strip() or f"git {' '.join(args)} failed"
        raise GitError(msg)
    return proc.stdout


def ensure_repo(repo: str) -> str:
    """Return the top-level directory of the repository containing ``repo``."""
    if not os.path.isdir(repo):
        raise GitError(f"not a directory: {repo}")
    out = git(repo, "rev-parse", "--show-toplevel")
    return out.decode("utf-8", "replace").strip() or repo


def _unquote(path: str) -> str:
    """Undo git's C-style quoting of unusual paths ("a\\tb", octal escapes)."""
    if len(path) < 2 or not (path.startswith('"') and path.endswith('"')):
        return path
    body = path[1:-1]
    raw = bytearray()
    i = 0
    simple = {"n": 10, "t": 9, "r": 13, '"': 34, "\\": 92, "a": 7, "b": 8, "f": 12, "v": 11}
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body):
            nxt = body[i + 1]
            if nxt in simple:
                raw.append(simple[nxt])
                i += 2
                continue
            if re.match(r"[0-7]{3}", body[i + 1 : i + 4]):
                raw.append(int(body[i + 1 : i + 4], 8))
                i += 4
                continue
        raw.extend(ch.encode("utf-8"))
        i += 1
    return raw.decode("utf-8", "replace")


def parse_numstat_path(spec: str) -> tuple[str, str | None]:
    """Return ``(new_path, old_path)`` for a numstat path, resolving rename syntax."""
    spec = _unquote(spec)
    m = _BRACE_RENAME.match(spec)
    if m:
        old = (m["pre"] + m["old"] + m["post"]).replace("//", "/")
        new = (m["pre"] + m["new"] + m["post"]).replace("//", "/")
        return new.lstrip("/"), old.lstrip("/")
    if " => " in spec:
        old, new = spec.split(" => ", 1)
        return _unquote(new), _unquote(old)
    return spec, None


def _parse_int(value: str) -> int:
    return int(value) if value.isdigit() else 0


def parse_log(text: str) -> list[Commit]:
    """Parse the output of ``git log --numstat --format=<LOG_FORMAT>`` (records split by RS)."""
    commits: list[Commit] = []
    for record in text.split(RECORD):
        if not record.strip():
            continue
        header, _, rest = record.partition("\n")
        parts = header.split(UNIT)
        if len(parts) < 9:
            continue
        sha, parents, an, ae, ad, cn, ce, cd = parts[:8]
        subject = UNIT.join(parts[8:])
        commit = Commit(
            sha=sha,
            parents=tuple(p for p in parents.split() if p),
            author_name=an.strip() or ae.strip() or "unknown",
            author_email=ae.strip().lower(),
            author_date=datetime.fromisoformat(ad),
            committer_name=cn.strip() or ce.strip() or "unknown",
            committer_email=ce.strip().lower(),
            committer_date=datetime.fromisoformat(cd),
            subject=subject.strip(),
        )
        for line in rest.splitlines():
            if not line.strip():
                continue
            cols = line.split("\t", 2)
            if len(cols) != 3:
                continue
            added, removed, spec = cols
            new, old = parse_numstat_path(spec)
            binary = added == "-" and removed == "-"
            commit.files.append(FileChange(new, _parse_int(added), _parse_int(removed), binary, old))
        commits.append(commit)
    return commits


def log_args(opts: LogOptions) -> list[str]:
    args = ["log", "--no-color", "--numstat", "-M", f"--format={RECORD}{LOG_FORMAT}", "--use-mailmap"]
    if opts.mailmap:
        args = ["-c", f"mailmap.file={opts.mailmap}", *args]
    if opts.first_parent:
        args.append("--first-parent")
    if opts.since:
        args.append(f"--since={opts.since}")
    if opts.until:
        args.append(f"--until={opts.until}")
    if opts.all_refs:
        args.append("--all")
    else:
        args.append(opts.rev)
    args.append("--")
    args.extend(opts.paths)
    return args


def resolve_renames(commits: Iterable[Commit]) -> None:
    """Attribute the history of renamed files to their latest name (commits are newest first)."""
    alias: dict[str, str] = {}

    def resolve(path: str) -> str:
        seen = set()
        while path in alias and path not in seen:
            seen.add(path)
            path = alias[path]
        return path

    for commit in commits:
        changed = False
        files = []
        for f in commit.files:
            current = resolve(f.path)
            if f.old_path and f.old_path != f.path:
                alias.setdefault(f.old_path, current)
            if current != f.path:
                changed = True
                f = FileChange(current, f.added, f.removed, f.binary, f.old_path)
            files.append(f)
        if changed:
            commit.files = files


def read_commits(repo: str, opts: LogOptions | None = None) -> list[Commit]:
    """Read commits (newest first) with per-file line counts."""
    opts = opts or LogOptions()
    try:
        out = git(repo, *log_args(opts))
    except GitError as exc:
        text = str(exc)
        no_history = ("does not have any commits", "bad default revision", "bad revision", "unknown revision")
        if opts.rev == "HEAD" and not opts.all_refs and any(m in text for m in no_history):
            return []
        raise
    commits = parse_log(out.decode("utf-8", "replace"))
    resolve_renames(commits)
    return commits


def tracked_files(repo: str, rev: str = "HEAD") -> dict[str, tuple[str, int]]:
    """Return ``{path: (blob_sha, size)}`` for regular files at ``rev``."""
    try:
        out = git(repo, "ls-tree", "-r", "-l", "-z", rev)
    except GitError:
        return {}
    files: dict[str, tuple[str, int]] = {}
    for entry in out.decode("utf-8", "replace").split("\0"):
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        bits = meta.split()
        if len(bits) != 4 or bits[1] != "blob":
            continue
        size = int(bits[3]) if bits[3].isdigit() else 0
        files[path] = (bits[2], size)
    return files


def read_blobs(repo: str, shas: Sequence[str]) -> Iterator[tuple[str, bytes]]:
    """Yield ``(sha, content)`` for each blob using one ``git cat-file --batch`` call."""
    if not shas:
        return
    out = git(repo, "cat-file", "--batch", input_bytes=("\n".join(shas) + "\n").encode())
    pos = 0
    while pos < len(out):
        nl = out.index(b"\n", pos)
        header = out[pos:nl].decode("utf-8", "replace").split()
        pos = nl + 1
        if len(header) < 3 or header[1] == "missing":
            continue
        size = int(header[2])
        yield header[0], out[pos : pos + size]
        pos += size + 1


def branch_commit_dates(repo: str, base: str, tip: str) -> list[datetime]:
    """Author dates of commits reachable from ``tip`` but not ``base`` (a merged branch)."""
    out = git(repo, "log", "--format=%aI", f"{base}..{tip}")
    return [datetime.fromisoformat(line) for line in out.decode().split() if line]


def is_excluded(path: str, patterns: Sequence[str]) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(path, p) or fnmatch.fnmatch(name, p) for p in patterns)
