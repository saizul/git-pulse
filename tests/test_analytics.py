from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from git_pulse import analytics
from git_pulse.gitlog import GENERATED_PATTERNS, Commit, FileChange, read_commits, tracked_files

from .conftest import ALICE, BOB, CAROL, DAVE


def make(sha, author, when, files=(), parents=("p",), subject="change"):
    return Commit(
        sha=sha,
        parents=tuple(parents),
        author_name=author[0],
        author_email=author[1],
        author_date=when,
        committer_name=author[0],
        committer_email=author[1],
        committer_date=when,
        subject=subject,
        files=[FileChange(p, a, r) for p, a, r in files],
    )


@pytest.fixture
def commits(repo):
    return read_commits(str(repo.path))


def test_summary(commits):
    s = analytics.summary(commits)
    assert s["commits"] == 16
    assert s["merges"] == 1
    assert s["authors"] == 4
    assert s["first_commit"].date() == date(2024, 1, 1)
    assert s["active_days"] == 15


def test_summary_empty():
    assert analytics.summary([])["commits"] == 0


def test_timeline_fills_gaps(commits):
    t = analytics.timeline(commits, "month")
    assert [r["period"] for r in t["rows"]] == ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05"]
    assert [r["commits"] for r in t["rows"]] == [6, 6, 2, 0, 2]
    assert t["rows"][0]["authors"] == 2


def test_timeline_auto_and_invalid(commits):
    assert analytics.timeline(commits)["period"] == "week"
    with pytest.raises(ValueError):
        analytics.timeline(commits, "decade")


@pytest.mark.parametrize(
    ("period", "start", "label"),
    [
        ("day", date(2024, 5, 15), "2024-05-15"),
        ("week", date(2024, 5, 13), "2024-W20"),
        ("month", date(2024, 5, 1), "2024-05"),
        ("quarter", date(2024, 4, 1), "2024-Q2"),
        ("year", date(2024, 1, 1), "2024"),
    ],
)
def test_periods(period, start, label):
    assert analytics.period_start(date(2024, 5, 15), period) == start
    assert analytics.period_label(start, period) == label
    assert analytics.next_period(start, period) > start


def test_next_period_wraps_year():
    assert analytics.next_period(date(2024, 12, 1), "month") == date(2025, 1, 1)
    assert analytics.next_period(date(2024, 10, 1), "quarter") == date(2025, 1, 1)


def test_contributors(commits):
    rows = analytics.contributors(commits, exclude=GENERATED_PATTERNS)
    assert [r["name"] for r in rows] == [ALICE[0], BOB[0], CAROL[0], DAVE[0]]
    alice = rows[0]
    assert alice["commits"] == 8  # mailmap folded the old laptop identity in
    assert alice["merges"] == 1
    assert alice["share"] == 0.5
    with_lock = analytics.contributors(commits)[0]
    assert with_lock["added"] == alice["added"] + 500


def test_group_by_name():
    a1 = make("1", ("Same Name", "a@x.org"), datetime(2024, 1, 1, tzinfo=UTC))
    a2 = make("2", ("same name", "b@x.org"), datetime(2024, 1, 2, tzinfo=UTC))
    assert len(analytics.contributors([a2, a1])) == 2
    assert len(analytics.contributors([a2, a1], group_by="name")) == 1


def test_bus_factor_counts_knowledge_holders(repo, commits):
    alive = tracked_files(str(repo.path))
    b = analytics.bus_factor(commits, exclude=GENERATED_PATTERNS, alive=alive)
    assert b["files"] == 7  # docs/guide.md was deleted, package-lock.json is excluded
    assert b["bus_factor"] == 2
    assert b["key_people"][0]["name"] == ALICE[0]
    dirs = {d["directory"]: d for d in b["directories"]}
    assert dirs["src/"]["main_author"] == ALICE[0]
    assert dirs["assets/"]["bus_factor"] == 1


def test_bus_factor_single_author():
    t = datetime(2024, 1, 1, tzinfo=UTC)
    cs = [make(str(i), ALICE, t, [(f"f{i}.py", 10, 0)]) for i in range(5)]
    b = analytics.bus_factor(cs)
    assert b["bus_factor"] == 1
    assert b["single_author_share"] == 1.0


def test_bus_factor_shared_files():
    t = datetime(2024, 1, 1, tzinfo=UTC)
    cs = []
    for i in range(6):
        cs.append(make(f"a{i}", ALICE, t, [(f"f{i}.py", 10, 0)]))
        cs.append(make(f"b{i}", BOB, t, [(f"f{i}.py", 9, 0)]))
        cs.append(make(f"c{i}", CAROL, t, [(f"f{i}.py", 8, 0)]))
    assert analytics.bus_factor(cs)["bus_factor"] == 3
    assert analytics.bus_factor([])["bus_factor"] == 0


def test_churn_follows_renames_and_skips_deleted(repo, commits):
    rows = analytics.churn(commits, exclude=GENERATED_PATTERNS, alive=tracked_files(str(repo.path)))
    by_path = {r["path"]: r for r in rows}
    assert "src/app.py" not in by_path
    assert by_path["src/main.py"]["revisions"] == 3
    assert "docs/guide.md" not in by_path
    assert "package-lock.json" not in by_path
    assert by_path["README.md"]["authors"] == 2
    assert rows == sorted(rows, key=lambda r: (-r["churn"], -r["revisions"], r["path"]))
    every = analytics.churn(commits)
    assert {"docs/guide.md", "package-lock.json"} <= {r["path"] for r in every}


def test_indentation_complexity():
    src = b"def f():\n    if x:\n        return 1\n\n    return 2\n"
    m = analytics.indentation_complexity(src)
    assert m == {"loc": 4, "complexity": 4, "mean_indent": 1.0, "max_indent": 2}
    two = analytics.indentation_complexity(b"a:\n  b:\n    c: 1\n")
    assert two["complexity"] == 3
    tabs = analytics.indentation_complexity(b"x\n\ty\n\t\tz\n")
    assert tabs["max_indent"] == 2
    assert analytics.indentation_complexity(b"\x00\x01binary") is None
    assert analytics.indentation_complexity(b"")["loc"] == 0


def test_hotspots_rank(repo, commits):
    tracked = tracked_files(str(repo.path))
    churn = analytics.churn(commits, exclude=GENERATED_PATTERNS, alive=tracked)
    from git_pulse.gitlog import read_blobs

    metrics = analytics.complexity([r["path"] for r in churn], tracked, lambda s: read_blobs(str(repo.path), s))
    assert "assets/logo.bin" not in metrics
    hot = analytics.hotspots(churn, metrics, top=3)
    assert hot[0]["path"] == "src/core.py"
    assert hot[0]["score"] == pytest.approx(2 / 3, abs=1e-3)
    assert len(hot) == 3
    assert analytics.hotspots([], {}) == []


def test_newcomers(commits):
    n = analytics.newcomers(commits)
    assert n["total"] == 4
    assert [p["name"] for p in n["people"]] == [ALICE[0], BOB[0], CAROL[0], DAVE[0]]
    dave = n["people"][-1]
    assert dave["returned"] is False and dave["subject"] == "One-off typo fix"
    assert n["people"][2]["returned"] is True  # Carol came back in May
    assert [r["newcomers"] for r in n["per_period"]] == [2, 0, 2]


def test_classify_merge():
    assert analytics.classify_merge("Merge pull request #42 from org/fix-x") == {
        "kind": "pull-request",
        "number": 42,
        "branch": "org/fix-x",
    }
    assert analytics.classify_merge("Merge branch 'feature/a' into 'main'")["branch"] == "feature/a"
    assert analytics.classify_merge("Merge remote-tracking branch 'origin/dev'")["kind"] == "branch"
    assert analytics.classify_merge("Merged stuff")["kind"] == "other"


def test_merge_stats_with_git(repo, commits):
    from git_pulse.gitlog import branch_commit_dates

    m = analytics.merge_stats(commits, lambda a, b: branch_commit_dates(str(repo.path), a, b))
    assert m["merges"] == 1
    assert m["pull_request_merges"] == 1
    assert m["squash_merges"] == 1
    assert m["commits_per_merge"]["median"] == 2
    # first branch commit 2024-02-01 09:00 -05:00, merged 2024-02-03 09:00 -05:00
    assert m["lead_time_hours"]["median"] == 48.0
    assert m["recent"][0]["number"] == 7
    assert {r["name"] for r in m["top_mergers"]} == {ALICE[0], CAROL[0]}


def test_merge_stats_without_lookup(commits):
    m = analytics.merge_stats(commits, None)
    assert m["analysed"] == 0
    assert m["commits_per_merge"]["median"] is None
    assert m["recent"][0]["commits"] is None


def test_heatmap_local_and_utc():
    when = datetime(2024, 1, 1, 23, 30, tzinfo=timezone(timedelta(hours=-5)))  # Monday 23:30 local
    h = analytics.heatmap([make("1", ALICE, when)])
    assert h["grid"][0][23] == 1
    assert h["after_hours_share"] == 1.0
    u = analytics.heatmap([make("1", ALICE, when)], utc=True)
    assert u["grid"][1][4] == 1  # Tuesday 04:30 UTC
    assert analytics.heatmap([])["peak"] is None


def test_heatmap_repo(commits):
    h = analytics.heatmap(commits)
    assert sum(h["by_weekday"]) == 16
    assert sum(h["by_hour"]) == 16
