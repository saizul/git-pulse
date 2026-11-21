"""Glue between git and the analytics: read the repository once, compute any section."""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import cached_property

from git_pulse import analytics, gitlog
from git_pulse._version import __version__

BOT_PATTERNS = ("*[bot]", "dependabot*", "renovate*")
"""Author patterns ``--exclude-bots`` adds: GitHub App bots (``dependabot[bot]``), Dependabot and Renovate."""

SECTIONS = ("summary", "timeline", "contributors", "bus_factor", "churn", "hotspots", "newcomers", "merges", "heatmap")


@dataclass
class Settings:
    repo: str = "."
    log: gitlog.LogOptions = field(default_factory=gitlog.LogOptions)
    exclude: Sequence[str] = ()
    include_generated: bool = False
    group_by: str = "email"
    period: str = "auto"
    top: int = 20
    utc: bool = False
    max_merges: int = 300
    threshold: float = 0.5
    include_deleted: bool = False
    exclude_authors: Sequence[str] = ()
    """Drop commits whose author name or email matches one of these patterns from every section."""


def author_matcher(patterns: Sequence[str]) -> re.Pattern[str] | None:
    """Compile author patterns into one case-insensitive regex.

    Only ``*`` (any text) and ``?`` (one character) are wildcards. Everything else, ``[``
    and ``]`` included, is literal, so ``*[bot]`` matches ``dependabot[bot]`` as written.
    """
    parts = []
    for pattern in patterns:
        pattern = pattern.strip()
        if not pattern:
            raise ValueError("--exclude-author pattern must not be empty")
        parts.append(re.escape(pattern).replace(r"\*", ".*").replace(r"\?", "."))
    if not parts:
        return None
    return re.compile("(?:" + "|".join(parts) + r")\Z", re.IGNORECASE | re.DOTALL)


def is_excluded_author(commit: gitlog.Commit, matcher: re.Pattern[str] | None) -> bool:
    if matcher is None:
        return False
    return bool(matcher.match(commit.author_name) or matcher.match(commit.author_email))


class Analysis:
    """Lazily computed statistics for one repository and one set of settings."""

    def __init__(self, settings: Settings, commits: Sequence[gitlog.Commit] | None = None) -> None:
        self.settings = settings
        self.root = gitlog.ensure_repo(settings.repo)
        self._commits = list(commits) if commits is not None else None
        self._author_matcher = author_matcher(settings.exclude_authors)
        self.excluded_commits = 0

    @cached_property
    def commits(self) -> list[gitlog.Commit]:
        commits = self._commits if self._commits is not None else gitlog.read_commits(self.root, self.settings.log)
        if self._author_matcher is None:
            return commits
        kept = [c for c in commits if not is_excluded_author(c, self._author_matcher)]
        self.excluded_commits = len(commits) - len(kept)
        return kept

    @property
    def file_exclude(self) -> tuple[str, ...]:
        extra = () if self.settings.include_generated else gitlog.GENERATED_PATTERNS
        return (*self.settings.exclude, *extra)

    @cached_property
    def tracked(self) -> dict[str, tuple[str, int]]:
        rev = "HEAD" if self.settings.log.all_refs else self.settings.log.rev
        return gitlog.tracked_files(self.root, rev)

    @property
    def alive(self) -> set[str] | None:
        if self.settings.include_deleted or not self.tracked:
            return None
        return set(self.tracked)

    # sections -------------------------------------------------------------

    def summary(self) -> dict:
        return analytics.summary(self.commits, self.settings.group_by)

    def timeline(self) -> dict:
        return analytics.timeline(self.commits, self.settings.period, self.settings.group_by)

    def contributors(self) -> list[dict]:
        rows = analytics.contributors(self.commits, self.settings.group_by, self.file_exclude)
        return rows[: self.settings.top] if self.settings.top else rows

    def bus_factor(self) -> dict:
        return analytics.bus_factor(
            self.commits,
            self.settings.group_by,
            self.file_exclude,
            self.alive,
            threshold=self.settings.threshold,
            top=self.settings.top,
        )

    @cached_property
    def _churn(self) -> list[dict]:
        return analytics.churn(self.commits, self.settings.group_by, self.file_exclude, self.alive)

    def churn(self) -> list[dict]:
        return self._churn[: self.settings.top] if self.settings.top else self._churn

    def hotspots(self) -> list[dict]:
        candidates = [r["path"] for r in sorted(self._churn, key=lambda r: -r["revisions"])[:500]]
        metrics = analytics.complexity(candidates, self.tracked, lambda shas: gitlog.read_blobs(self.root, shas))
        return analytics.hotspots(self._churn, metrics, self.settings.top)

    def newcomers(self) -> dict:
        period = self.settings.period
        if period in ("auto", "day", "week"):
            period = "month"
        return analytics.newcomers(self.commits, self.settings.group_by, period)

    def merges(self) -> dict:
        def dates(base: str, tip: str) -> list[datetime]:
            try:
                return gitlog.branch_commit_dates(self.root, base, tip)
            except gitlog.GitError:
                return []

        period = self.settings.period
        if period in ("auto", "day"):
            period = "month"
        return analytics.merge_stats(self.commits, dates, self.settings.max_merges, period)

    def heatmap(self) -> dict:
        return analytics.heatmap(self.commits, self.settings.utc)

    def section(self, name: str):
        if name not in SECTIONS:
            raise ValueError(f"unknown section {name!r}")
        return getattr(self, name)()

    def everything(self) -> dict:
        return {
            "meta": self.meta(),
            **{name: self.section(name) for name in SECTIONS},
        }

    def meta(self) -> dict:
        log = self.settings.log
        self.commits  # noqa: B018 - load the history so excluded_commits is known
        return {
            "tool": "git-pulse",
            "version": __version__,
            "repository": os.path.basename(os.path.abspath(self.root)),
            "revision": "--all" if log.all_refs else log.rev,
            "since": log.since,
            "until": log.until,
            "paths": list(log.paths),
            "group_by": self.settings.group_by,
            "exclude_authors": list(self.settings.exclude_authors),
            "excluded_commits": self.excluded_commits,
            "generated_at": datetime.now().astimezone().replace(microsecond=0),
        }


def to_jsonable(value):
    """Convert datetimes, dates, sets and tuples so ``json.dumps`` accepts the result."""
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
