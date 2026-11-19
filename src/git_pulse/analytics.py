"""Pure functions that turn a list of commits into statistics.

Nothing in here runs git except :func:`complexity` and :func:`merge_stats`, which take a
callable so tests and other front-ends can swap the data source.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from git_pulse.gitlog import Commit, is_excluded

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
PERIODS = ("day", "week", "month", "quarter", "year")


@dataclass(frozen=True)
class Identity:
    key: str
    name: str
    email: str


def identity_of(commit: Commit, group_by: str = "email") -> Identity:
    """Return the identity used to group a commit's author (after .mailmap)."""
    if group_by == "name":
        key = commit.author_name.casefold()
    else:
        key = commit.author_email or commit.author_name.casefold()
    return Identity(key, commit.author_name, commit.author_email)


def _names(commits: Iterable[Commit], group_by: str) -> dict[str, Identity]:
    """Map identity key -> identity, using the most recent name/email for display."""
    out: dict[str, Identity] = {}
    for c in commits:  # newest first, so the first one wins
        ident = identity_of(c, group_by)
        out.setdefault(ident.key, ident)
    return out


def file_changes(commits: Iterable[Commit], exclude: Sequence[str] = ()):
    """Yield ``(commit, change)`` for non-merge commits, skipping excluded paths."""
    for c in commits:
        if c.is_merge:
            continue
        for f in c.files:
            if exclude and is_excluded(f.path, exclude):
                continue
            yield c, f


# --------------------------------------------------------------------------- summary


def summary(commits: Sequence[Commit], group_by: str = "email") -> dict:
    if not commits:
        return {
            "commits": 0,
            "merges": 0,
            "authors": 0,
            "first_commit": None,
            "last_commit": None,
            "age_days": 0,
            "active_days": 0,
            "files_touched": 0,
            "lines_added": 0,
            "lines_removed": 0,
        }
    dates = [c.author_date for c in commits]
    first, last = min(dates), max(dates)
    files = {f.path for c in commits for f in c.files}
    return {
        "commits": len(commits),
        "merges": sum(1 for c in commits if c.is_merge),
        "authors": len({identity_of(c, group_by).key for c in commits}),
        "first_commit": first,
        "last_commit": last,
        "age_days": (last - first).days,
        "active_days": len({d.date() for d in dates}),
        "files_touched": len(files),
        "lines_added": sum(c.added for c in commits if not c.is_merge),
        "lines_removed": sum(c.removed for c in commits if not c.is_merge),
    }


# --------------------------------------------------------------------------- timeline


def period_start(d: date, period: str) -> date:
    if period == "day":
        return d
    if period == "week":
        return d - timedelta(days=d.weekday())
    if period == "month":
        return d.replace(day=1)
    if period == "quarter":
        return d.replace(month=(d.month - 1) // 3 * 3 + 1, day=1)
    if period == "year":
        return d.replace(month=1, day=1)
    raise ValueError(f"unknown period {period!r}; choose from {', '.join(PERIODS)}")


def next_period(d: date, period: str) -> date:
    if period == "day":
        return d + timedelta(days=1)
    if period == "week":
        return d + timedelta(days=7)
    months = {"month": 1, "quarter": 3, "year": 12}[period]
    month = d.month - 1 + months
    return date(d.year + month // 12, month % 12 + 1, 1)


def period_label(d: date, period: str) -> str:
    if period == "day":
        return d.isoformat()
    if period == "week":
        iso = d.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if period == "month":
        return f"{d.year}-{d.month:02d}"
    if period == "quarter":
        return f"{d.year}-Q{(d.month - 1) // 3 + 1}"
    return str(d.year)


def auto_period(commits: Sequence[Commit]) -> str:
    if not commits:
        return "month"
    dates = [c.author_date.date() for c in commits]
    span = (max(dates) - min(dates)).days
    if span <= 45:
        return "day"
    if span <= 365:
        return "week"
    if span <= 365 * 8:
        return "month"
    return "quarter"


def timeline(commits: Sequence[Commit], period: str = "auto", group_by: str = "email") -> dict:
    """Commits, authors and line changes per period, with empty periods filled in."""
    if period == "auto":
        period = auto_period(commits)
    if period not in PERIODS:
        raise ValueError(f"unknown period {period!r}; choose from auto, {', '.join(PERIODS)}")
    buckets: dict[date, dict] = {}
    authors: dict[date, set[str]] = defaultdict(set)
    for c in commits:
        start = period_start(c.author_date.date(), period)
        b = buckets.setdefault(start, {"commits": 0, "added": 0, "removed": 0})
        b["commits"] += 1
        if not c.is_merge:
            b["added"] += c.added
            b["removed"] += c.removed
        authors[start].add(identity_of(c, group_by).key)
    rows = []
    if buckets:
        cur, end = min(buckets), max(buckets)
        while cur <= end:
            b = buckets.get(cur, {"commits": 0, "added": 0, "removed": 0})
            rows.append(
                {
                    "period": period_label(cur, period),
                    "start": cur,
                    "commits": b["commits"],
                    "authors": len(authors.get(cur, ())),
                    "added": b["added"],
                    "removed": b["removed"],
                }
            )
            cur = next_period(cur, period)
    return {"period": period, "rows": rows}


# --------------------------------------------------------------------------- contributors


def contributors(commits: Sequence[Commit], group_by: str = "email", exclude: Sequence[str] = ()) -> list[dict]:
    names = _names(commits, group_by)
    stats: dict[str, dict] = {}
    for c in commits:
        key = identity_of(c, group_by).key
        s = stats.setdefault(
            key, {"commits": 0, "merges": 0, "added": 0, "removed": 0, "files": set(), "days": set(), "dates": []}
        )
        s["commits"] += 1
        s["days"].add(c.author_date.date())
        s["dates"].append(c.author_date)
        if c.is_merge:
            s["merges"] += 1
            continue
        for f in c.files:
            if exclude and is_excluded(f.path, exclude):
                continue
            s["added"] += f.added
            s["removed"] += f.removed
            s["files"].add(f.path)
    total = len(commits) or 1
    rows = []
    for key, s in stats.items():
        ident = names[key]
        rows.append(
            {
                "name": ident.name,
                "email": ident.email,
                "commits": s["commits"],
                "share": round(s["commits"] / total, 4),
                "merges": s["merges"],
                "added": s["added"],
                "removed": s["removed"],
                "files": len(s["files"]),
                "active_days": len(s["days"]),
                "first_commit": min(s["dates"]),
                "last_commit": max(s["dates"]),
            }
        )
    rows.sort(key=lambda r: (-r["commits"], -r["added"], r["name"].casefold()))
    return rows


# --------------------------------------------------------------------------- ownership / bus factor


def ownership(
    commits: Sequence[Commit],
    group_by: str = "email",
    exclude: Sequence[str] = (),
    alive: Iterable[str] | None = None,
) -> dict[str, Counter]:
    """Return ``{path: Counter(author_key -> lines added + commits)}``.

    Every commit counts as one line so files that only ever shrink still have authors.
    """
    alive_set = set(alive) if alive is not None else None
    own: dict[str, Counter] = defaultdict(Counter)
    for c, f in file_changes(commits, exclude):
        if alive_set is not None and f.path not in alive_set:
            continue
        own[f.path][identity_of(c, group_by).key] += f.added + 1
    return own


def _authors_of(counter: Counter, min_share: float) -> set[str]:
    total = sum(counter.values())
    if not total:
        return set()
    top = max(counter.values())
    return {a for a, n in counter.items() if n == top or n / total >= min_share}


def _truck(files: Mapping[str, set[str]], threshold: float) -> tuple[int, list[tuple[str, int]]]:
    """Greedily remove the author covering most files until > threshold of files are orphaned."""
    if not files:
        return 0, []
    remaining = {p: set(a) for p, a in files.items()}
    removed: list[tuple[str, int]] = []
    total = len(remaining)
    while True:
        orphaned = sum(1 for a in remaining.values() if not a)
        if orphaned / total > threshold:
            return len(removed), removed
        counts = Counter(a for authors in remaining.values() for a in authors)
        if not counts:  # pragma: no cover - loop exits above first
            return len(removed), removed
        author, covered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        removed.append((author, covered))
        for authors in remaining.values():
            authors.discard(author)


def bus_factor(
    commits: Sequence[Commit],
    group_by: str = "email",
    exclude: Sequence[str] = (),
    alive: Iterable[str] | None = None,
    threshold: float = 0.5,
    min_share: float = 0.25,
    top: int = 10,
) -> dict:
    """Estimate the bus (truck) factor.

    A file's *knowledge holders* are its top author plus anyone who wrote at least
    ``min_share`` of it. The bus factor is the smallest number of people who, if they
    left, would leave more than ``threshold`` of the files with no knowledge holder.
    """
    names = _names(commits, group_by)
    own = ownership(commits, group_by, exclude, alive)
    holders = {p: _authors_of(c, min_share) for p, c in own.items()}
    factor, key_people = _truck(holders, threshold)

    by_dir: dict[str, dict[str, set[str]]] = defaultdict(dict)
    for path, h in holders.items():
        top_dir = path.split("/", 1)[0] + "/" if "/" in path else "."
        by_dir[top_dir][path] = h
    directories = []
    for d, files in by_dir.items():
        f, people = _truck(files, threshold)
        main: Counter = Counter()
        for p in files:
            main.update(own[p])
        main_key = main.most_common(1)[0][0] if main else ""
        directories.append(
            {
                "directory": d,
                "files": len(files),
                "bus_factor": f,
                "main_author": names[main_key].name if main_key in names else main_key,
                "key_people": [names[a].name if a in names else a for a, _ in people],
            }
        )
    directories.sort(key=lambda r: (r["bus_factor"], -r["files"], r["directory"]))

    single = sorted(p for p, c in own.items() if len(c) == 1)
    return {
        "bus_factor": factor,
        "threshold": threshold,
        "files": len(own),
        "single_author_files": len(single),
        "single_author_share": round(len(single) / len(own), 4) if own else 0.0,
        "key_people": [
            {"name": names[a].name, "email": names[a].email, "files_held": n} for a, n in key_people if a in names
        ],
        "directories": directories[:top] if top else directories,
    }


# --------------------------------------------------------------------------- churn and hotspots


def churn(
    commits: Sequence[Commit],
    group_by: str = "email",
    exclude: Sequence[str] = (),
    alive: Iterable[str] | None = None,
) -> list[dict]:
    """Per-file revisions, added/removed lines and number of distinct authors."""
    alive_set = set(alive) if alive is not None else None
    rows: dict[str, dict] = {}
    for c, f in file_changes(commits, exclude):
        if alive_set is not None and f.path not in alive_set:
            continue
        r = rows.setdefault(
            f.path,
            {"path": f.path, "revisions": 0, "added": 0, "removed": 0, "authors": set(), "first": None, "last": None},
        )
        r["revisions"] += 1
        r["added"] += f.added
        r["removed"] += f.removed
        r["authors"].add(identity_of(c, group_by).key)
        d = c.author_date
        r["first"] = d if r["first"] is None or d < r["first"] else r["first"]
        r["last"] = d if r["last"] is None or d > r["last"] else r["last"]
    out = []
    for r in rows.values():
        out.append(
            {
                "path": r["path"],
                "revisions": r["revisions"],
                "added": r["added"],
                "removed": r["removed"],
                "churn": r["added"] + r["removed"],
                "authors": len(r["authors"]),
                "first_change": r["first"],
                "last_change": r["last"],
            }
        )
    out.sort(key=lambda r: (-r["churn"], -r["revisions"], r["path"]))
    return out


def indentation_complexity(content: bytes) -> dict | None:
    """Indentation-based complexity proxy for a text file (``None`` for binary files).

    Each non-blank line contributes its logical indentation depth. The indent unit is
    detected from the file (smallest common space indent, minimum 2); a tab is one level.
    """
    if b"\0" in content[:8000]:
        return None
    lines = content.decode("utf-8", "replace").splitlines()
    space_indents = []
    parsed = []
    for line in lines:
        stripped = line.lstrip(" \t")
        if not stripped:
            continue
        lead = line[: len(line) - len(stripped)]
        tabs = lead.count("\t")
        spaces = lead.count(" ")
        if spaces:
            space_indents.append(spaces)
        parsed.append((tabs, spaces))
    unit = max(2, min(space_indents)) if space_indents else 4
    unit = min(unit, 8)
    levels = [tabs + spaces // unit for tabs, spaces in parsed]
    return {
        "loc": len(parsed),
        "complexity": sum(levels),
        "mean_indent": round(sum(levels) / len(levels), 2) if levels else 0.0,
        "max_indent": max(levels) if levels else 0,
    }


def complexity(
    paths: Sequence[str],
    tracked: Mapping[str, tuple[str, int]],
    read_blobs: Callable[[Sequence[str]], Iterable[tuple[str, bytes]]],
    max_bytes: int = 1_000_000,
) -> dict[str, dict]:
    """Compute :func:`indentation_complexity` for ``paths`` at the analysed revision."""
    wanted: dict[str, list[str]] = defaultdict(list)
    for p in paths:
        if p in tracked and tracked[p][1] <= max_bytes:
            wanted[tracked[p][0]].append(p)
    out: dict[str, dict] = {}
    for sha, content in read_blobs(list(wanted)):
        metrics = indentation_complexity(content)
        if metrics is None:
            continue
        for p in wanted.get(sha, ()):
            out[p] = metrics
    return out


def hotspots(churn_rows: Sequence[dict], metrics: Mapping[str, dict], top: int = 20) -> list[dict]:
    """Rank files by normalised revisions x normalised complexity (0..1)."""
    rows = [r for r in churn_rows if r["path"] in metrics and metrics[r["path"]]["loc"] > 0]
    if not rows:
        return []
    max_rev = max(r["revisions"] for r in rows) or 1
    max_cx = max(metrics[r["path"]]["complexity"] for r in rows) or 1
    out = []
    for r in rows:
        m = metrics[r["path"]]
        score = (r["revisions"] / max_rev) * (max(m["complexity"], 0) / max_cx)
        out.append(
            {
                "path": r["path"],
                "score": round(score, 4),
                "revisions": r["revisions"],
                "churn": r["churn"],
                "authors": r["authors"],
                "loc": m["loc"],
                "complexity": m["complexity"],
                "mean_indent": m["mean_indent"],
                "max_indent": m["max_indent"],
            }
        )
    out.sort(key=lambda r: (-r["score"], -r["revisions"], r["path"]))
    return out[:top] if top else out


# --------------------------------------------------------------------------- newcomers


def newcomers(
    commits: Sequence[Commit],
    group_by: str = "email",
    period: str = "month",
    retention_days: int = 30,
) -> dict:
    """First-time contributors: who, when, with what, and whether they came back."""
    names = _names(commits, group_by)
    history: dict[str, list[Commit]] = defaultdict(list)
    for c in commits:
        history[identity_of(c, group_by).key].append(c)
    people = []
    for key, cs in history.items():
        cs.sort(key=lambda c: c.author_date)
        first = cs[0]
        later = [c for c in cs if c.author_date - first.author_date > timedelta(days=retention_days)]
        people.append(
            {
                "name": names[key].name,
                "email": names[key].email,
                "first_commit": first.author_date,
                "sha": first.sha,
                "subject": first.subject,
                "commits": len(cs),
                "returned": bool(later),
            }
        )
    people.sort(key=lambda p: p["first_commit"])
    per_period: Counter = Counter()
    for p in people:
        per_period[period_start(p["first_commit"].date(), period)] += 1
    rows = []
    if per_period:
        cur, end = min(per_period), max(per_period)
        while cur <= end:
            rows.append({"period": period_label(cur, period), "start": cur, "newcomers": per_period.get(cur, 0)})
            cur = next_period(cur, period)
    returned = sum(1 for p in people if p["returned"])
    return {
        "period": period,
        "retention_days": retention_days,
        "total": len(people),
        "returned": returned,
        "one_time": len(people) - returned,
        "per_period": rows,
        "people": people,
    }


# --------------------------------------------------------------------------- merges / pull requests

_GITHUB_MERGE = re.compile(r"^Merge pull request #(?P<num>\d+) from (?P<branch>\S+)")
_BRANCH_MERGE = re.compile(
    r"^Merge (?:remote-tracking )?branch '(?P<branch>[^']+)'(?: of \S+)?(?: into '?(?P<into>[^']+)'?)?"
)
_SQUASH = re.compile(r"\(#(?P<num>\d+)\)\s*$")


def classify_merge(subject: str) -> dict:
    m = _GITHUB_MERGE.match(subject)
    if m:
        return {"kind": "pull-request", "number": int(m["num"]), "branch": m["branch"]}
    m = _BRANCH_MERGE.match(subject)
    if m:
        return {"kind": "branch", "number": None, "branch": m["branch"]}
    return {"kind": "other", "number": None, "branch": None}


def _pct(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        result = float(values[0])
    else:
        result = float(statistics.quantiles(values, n=100, method="inclusive")[int(q * 100) - 1])
    return int(result) if result.is_integer() else round(result, 2)


def merge_stats(
    commits: Sequence[Commit],
    branch_dates: Callable[[str, str], list[datetime]] | None = None,
    max_merges: int = 300,
    period: str = "month",
    recent: int = 10,
) -> dict:
    """Pull-request style statistics from merge commits and squash merges.

    ``branch_dates(base, tip)`` returns author dates of the commits a merge brought in;
    it is called for at most ``max_merges`` of the newest merges.
    """
    merges = [c for c in commits if c.is_merge]
    squash = [c for c in commits if not c.is_merge and _SQUASH.search(c.subject)]
    per_period: Counter = Counter()
    mergers: Counter = Counter()
    sizes: list[int] = []
    lead_hours: list[float] = []
    items = []
    for i, c in enumerate(merges):
        info = classify_merge(c.subject)
        per_period[period_start(c.committer_date.date(), period)] += 1
        mergers[c.committer_name] += 1
        size = None
        lead = None
        if branch_dates is not None and i < max_merges:
            dates = branch_dates(c.parents[0], c.parents[1])
            size = len(dates)
            if dates:
                sizes.append(size)
                lead = (c.committer_date - min(dates)).total_seconds() / 3600
                lead = max(lead, 0.0)
                lead_hours.append(lead)
        items.append(
            {
                "sha": c.sha,
                "date": c.committer_date,
                "merged_by": c.committer_name,
                "subject": c.subject,
                "kind": info["kind"],
                "number": info["number"],
                "branch": info["branch"],
                "commits": size,
                "lead_time_hours": round(lead, 2) if lead is not None else None,
            }
        )
    for c in squash:
        per_period[period_start(c.committer_date.date(), period)] += 1
        mergers[c.committer_name] += 1
    rows = []
    if per_period:
        cur, end = min(per_period), max(per_period)
        while cur <= end:
            rows.append({"period": period_label(cur, period), "start": cur, "merges": per_period.get(cur, 0)})
            cur = next_period(cur, period)
    return {
        "merges": len(merges),
        "pull_request_merges": sum(1 for i in items if i["kind"] == "pull-request"),
        "branch_merges": sum(1 for i in items if i["kind"] == "branch"),
        "squash_merges": len(squash),
        "analysed": min(len(merges), max_merges) if branch_dates else 0,
        "commits_per_merge": {
            "median": _pct(sizes, 0.5),
            "p90": _pct(sizes, 0.9),
            "max": max(sizes) if sizes else None,
        },
        "lead_time_hours": {
            "median": round(_pct(lead_hours, 0.5), 2) if lead_hours else None,
            "p90": round(_pct(lead_hours, 0.9), 2) if lead_hours else None,
        },
        "per_period": rows,
        "top_mergers": [{"name": n, "merges": k} for n, k in mergers.most_common(10)],
        "recent": items[:recent],
    }


# --------------------------------------------------------------------------- heatmap


def heatmap(commits: Sequence[Commit], utc: bool = False) -> dict:
    """7 x 24 matrix of commit counts by weekday (Mon=0) and hour of the author's clock."""
    grid = [[0] * 24 for _ in range(7)]
    for c in commits:
        d = c.author_date.astimezone(UTC) if utc else c.author_date
        grid[d.weekday()][d.hour] += 1
    by_day = [sum(row) for row in grid]
    by_hour = [sum(grid[d][h] for d in range(7)) for h in range(24)]
    total = sum(by_day)
    weekend = by_day[5] + by_day[6]
    off_hours = sum(grid[d][h] for d in range(5) for h in range(24) if h < 8 or h >= 19)
    peak = max(((d, h) for d in range(7) for h in range(24)), key=lambda dh: grid[dh[0]][dh[1]])
    return {
        "timezone": "UTC" if utc else "author local time",
        "weekdays": list(WEEKDAYS),
        "grid": grid,
        "by_weekday": by_day,
        "by_hour": by_hour,
        "weekend_share": round(weekend / total, 4) if total else 0.0,
        "after_hours_share": round(off_hours / total, 4) if total else 0.0,
        "peak": {"weekday": WEEKDAYS[peak[0]], "hour": peak[1], "commits": grid[peak[0]][peak[1]]} if total else None,
    }
