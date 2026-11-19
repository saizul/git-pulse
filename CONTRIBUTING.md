# Contributing to git-pulse

Thank you for helping! New metrics, better charts, documentation and bug reports are all
welcome.

- [Ways to contribute](#ways-to-contribute)
- [Good first issues](#good-first-issues)
- [Development setup](#development-setup)
- [Project layout](#project-layout)
- [Add a metric](#add-a-metric)
- [Guidelines](#guidelines)
- [Pull request process](#pull-request-process)

## Ways to contribute

| Size | Idea |
| --- | --- |
| 10 minutes | Fix a typo, clarify how a metric is computed, add a FAQ entry |
| 30 minutes | Improve an error message, add a missing test case, polish a chart |
| 1-2 hours | One of the good first issues below |
| Larger | New report sections, trend comparisons between two ranges (open an issue first) |

Comment on an issue before you start so nobody else picks the same one.

## Good first issues

Each of these is self-contained and touches one or two files.

1. **GitLab merge requests.** Recognise `See merge request group/project!123` in merge commit
   bodies. This needs `%b` in the log format for merge commits only, or a second
   `git log --merges --format=%H%x1f%b` call. (`gitlog.py`, `analytics.classify_merge`, tests)
2. **`--format csv`** for the ranked lists (`contributors`, `churn`, `hotspots`) using the
   `csv` module. (`cli.py`, `text.py` or a new `csvout.py`, tests)
3. **Markdown output** (`--format markdown`) so the report can be pasted into an issue or a
   pull request comment. (`text.py`, tests)
4. **Pair-programming credit.** Credit the extra authors listed in commit message trailers in
   `contributors` behind a `--trailer-authors` flag. Needs `%(trailers:key=...)` in the
   format string. (`gitlog.py`, `analytics.contributors`, tests)
5. **Exclude bots.** `--exclude-author GLOB` (repeatable) to drop `*[bot]` and
   `dependabot*` from every section. (`cli.py`, `collect.py`, tests)
6. **Language breakdown.** Churn grouped by file extension, as a table and a horizontal bar
   chart in the report. (`analytics.py`, `text.py`, `report.py`, tests)
7. **Sparkline per contributor** in the HTML report: weekly commits over the last year as a
   tiny inline SVG. (`svg.py`, `report.py`, tests)
8. **`--period` for the heatmap**: show only the last N weeks with `--since`, and document it
   in the README FAQ. (`README.md`)
9. **Directory hotspots.** Aggregate hotspot scores per directory (depth configurable with
   `--depth`). (`analytics.py`, `cli.py`, tests)

## Development setup

```bash
git clone https://github.com/saizul/git-pulse
cd git-pulse
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e .[dev]
pytest
ruff check . && ruff format --check .
```

Python 3.11+ and git 2.28+ are needed. Tests never touch the network or your git config:
the `repo` fixture in `tests/conftest.py` builds a repository in a temporary directory with
fixed authors, dates, time zones, a pull request merge, a squash merge, a rename, a lock file
and a `.mailmap` alias. Add commits there (and update the counts in the tests) or build your
own with the `Repo` helper.

Try the CLI on any repository:

```bash
git-pulse report -C ~/src/some-project -o /tmp/pulse.html
sh examples/demo-repo.sh /tmp/pulse-demo && git-pulse merges -C /tmp/pulse-demo
```

## Project layout

| Path | Responsibility |
| --- | --- |
| `src/git_pulse/gitlog.py` | Runs `git`, parses `--numstat` output, renames, mailmap, blobs |
| `src/git_pulse/analytics.py` | Pure functions: summary, timeline, contributors, bus factor, churn, hotspots, newcomers, merges, heatmap |
| `src/git_pulse/collect.py` | `Analysis`: reads the repository once and computes sections lazily |
| `src/git_pulse/text.py` | Terminal tables and bar charts |
| `src/git_pulse/svg.py` | Inline SVG charts (bar, horizontal bar, heatmap, scatter) |
| `src/git_pulse/report.py` | Self-contained HTML report |
| `src/git_pulse/cli.py` | Argument parsing and output |
| `tests/` | pytest suite; `conftest.py` has the scripted repository |

## Add a metric

1. Write a pure function in `analytics.py` that takes `Sequence[Commit]` (newest first) and
   returns plain dicts and lists. Use `identity_of(commit, group_by)` to group authors and
   `file_changes(commits, exclude)` to iterate over file changes without merges.
2. Unit test it with hand-made `Commit` objects (see `make()` in `tests/test_analytics.py`)
   and with the scripted `repo` fixture.
3. Expose it: a method on `Analysis`, a name in `SECTIONS`, a renderer in `text.RENDERERS`, a
   command in `cli.COMMANDS` and a section in `report.render_html`.
4. Document it in the README command table and add a line under "Unreleased" in
   `CHANGELOG.md`.

## Guidelines

- No runtime dependencies. Standard library and the `git` executable only.
- Only read-only git commands (`log`, `ls-tree`, `cat-file`, `rev-parse`).
- Escape every value from the repository in the HTML report (`html.escape`); no JavaScript,
  no external URLs.
- JSON output is an API: add keys, do not rename or remove them without a changelog entry.
- Type hints everywhere; `ruff check` and `ruff format` clean.
- Tests are deterministic: fixed dates with explicit time zones, no reliance on the local clock.

## Pull request process

1. Fork and create a branch (`feat/csv-output`, `fix/rename-parsing`).
2. Keep pull requests focused; fill in the checklist in the template.
3. Add an entry to `CHANGELOG.md` under "Unreleased".
4. A maintainer reviews within a few days.

By contributing you agree that your work is released under the MIT License and
that you follow the [Code of Conduct](CODE_OF_CONDUCT.md).
