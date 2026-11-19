from datetime import timedelta

import pytest

from git_pulse import gitlog
from git_pulse.gitlog import LogOptions, parse_numstat_path, read_commits

from .conftest import ALICE, BOB, Repo


@pytest.mark.parametrize(
    ("spec", "new", "old"),
    [
        ("src/app.py", "src/app.py", None),
        ("old.py => new.py", "new.py", "old.py"),
        ("src/{app.py => main.py}", "src/main.py", "src/app.py"),
        ("{lib => src}/util.py", "src/util.py", "lib/util.py"),
        ("src/{ => sub}/x.py", "src/sub/x.py", "src/x.py"),
        ('"tab\\there.txt"', "tab\there.txt", None),
        ('"caf\\303\\251.txt"', "café.txt", None),
    ],
)
def test_parse_numstat_path(spec, new, old):
    assert parse_numstat_path(spec) == (new, old)


def test_read_commits_basic(repo):
    commits = read_commits(str(repo.path))
    assert len(commits) == 16
    first = commits[-1]
    assert first.subject == "Initial commit"
    assert first.author_date.utcoffset() == timedelta(hours=2)
    assert {f.path for f in first.files} == {"README.md", "src/main.py", ".mailmap"}  # renamed later


def test_mailmap_is_applied(repo):
    commits = read_commits(str(repo.path))
    core = next(c for c in commits if c.subject == "Add core")
    assert core.author_name == ALICE[0]
    assert core.author_email == ALICE[1]


def test_external_mailmap_file(repo, tmp_path):
    mm = tmp_path / "extra.mailmap"
    mm.write_text(f"Robert Brown <bob@example.com> {BOB[0]} <{BOB[1]}>\n")
    commits = read_commits(str(repo.path), LogOptions(mailmap=str(mm)))
    docs = next(c for c in commits if c.subject == "Docs")
    assert docs.author_name == "Robert Brown"


def test_binary_and_merge(repo):
    commits = read_commits(str(repo.path))
    logo = next(c for c in commits if c.subject == "Logo")
    assert logo.files[0].binary and logo.files[0].churn == 0
    merge = next(c for c in commits if c.is_merge)
    assert len(merge.parents) == 2 and merge.files == []


def test_since_until_and_paths(repo):
    commits = read_commits(str(repo.path), LogOptions(since="2024-03-01"))
    assert {c.subject for c in commits} == {"Add CLI (#12)", "One-off typo fix", "Carol again", "Remove docs"}
    only_docs = read_commits(str(repo.path), LogOptions(paths=("docs",)))
    assert {c.subject for c in only_docs} == {"Docs", "Remove docs"}


def test_first_parent_skips_branch_commits(repo):
    commits = read_commits(str(repo.path), LogOptions(first_parent=True))
    assert "Feature part 1" not in {c.subject for c in commits}


def test_empty_repository(tmp_path):
    r = Repo(tmp_path / "empty")
    assert read_commits(str(r.path)) == []


def test_unknown_revision_raises(repo):
    with pytest.raises(gitlog.GitError):
        read_commits(str(repo.path), LogOptions(rev="does-not-exist"))


def test_not_a_repository(tmp_path):
    with pytest.raises(gitlog.GitError):
        gitlog.ensure_repo(str(tmp_path / "missing"))
    (tmp_path / "plain").mkdir()
    with pytest.raises(gitlog.GitError):
        gitlog.ensure_repo(str(tmp_path / "plain"))


def test_tracked_files_and_blobs(repo):
    tracked = gitlog.tracked_files(str(repo.path))
    assert "src/main.py" in tracked and "docs/guide.md" not in tracked
    sha = tracked["README.md"][0]
    assert dict(gitlog.read_blobs(str(repo.path), [sha])) == {sha: b"# demo project\n"}


def test_is_excluded():
    assert gitlog.is_excluded("web/package-lock.json", gitlog.GENERATED_PATTERNS)
    assert gitlog.is_excluded("static/app.min.js", gitlog.GENERATED_PATTERNS)
    assert not gitlog.is_excluded("src/package.py", gitlog.GENERATED_PATTERNS)
    assert gitlog.is_excluded("vendor/x/y.go", ["vendor/*"])
