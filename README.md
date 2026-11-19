# git-pulse

[![CI](https://github.com/saizul/git-pulse/actions/workflows/ci.yml/badge.svg)](https://github.com/saizul/git-pulse/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/saizul/git-pulse?sort=semver)](https://github.com/saizul/git-pulse/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Container image](https://img.shields.io/badge/ghcr.io-saizul%2Fgit--pulse-2496ED?logo=docker&logoColor=white)](https://github.com/saizul/git-pulse/pkgs/container/git-pulse)
![Python](https://img.shields.io/badge/python-3.11%E2%80%933.13-blue)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**Git repository analytics from plain `git log`.** Who works on what, where knowledge is
concentrated, which files keep changing and are hard to change, how fast branches get merged,
and when people actually commit. As terminal tables, JSON, or **one self-contained HTML file**
with inline SVG charts that you can attach to an issue or open offline.

- No dependencies: Python standard library plus the `git` you already have (no GitPython,
  no libgit2, no server, no database)
- Respects `.mailmap`, follows renames, ignores lock files by default
- The HTML report has no JavaScript and makes no network requests

```text
$ git-pulse bus-factor
Bus factor
==========
Bus factor: 2  (people who would have to leave before more than 50.0% of 7 files lose every knowledge holder)
Single-author files: 6 (85.7%)

Key person    Email              Files held
------------  -----------------  ----------
Alice Anders  alice@example.com           4
Bob Brown     bob@example.com             2

Directory  Files  Bus factor  Main author
---------  -----  ----------  ------------
assets/        1           1  Bob Brown
src/           4           2  Alice Anders
```

## Contents

- [Quick start](#quick-start)
- [Commands](#commands)
- [Options](#options)
- [How the metrics work](#how-the-metrics-work)
- [Examples](#examples)
- [JSON output](#json-output)
- [FAQ](#faq)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

## Quick start

### pip

```bash
pip install git+https://github.com/saizul/git-pulse
cd ~/src/your-project
git-pulse summary
git-pulse report            # writes git-pulse-report.html
```

### Docker

```bash
docker run --rm -v "$PWD:/repo:ro" ghcr.io/saizul/git-pulse contributors
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/repo:ro" -v "$PWD:/out" ghcr.io/saizul/git-pulse report -o /out/pulse.html
```

The image contains git and trusts mounted repositories (`safe.directory`), so it works on
checkouts owned by any user. Mount the repository read-only.

> Analysing a CI checkout? Clone with full history (`fetch-depth: 0` in `actions/checkout`);
> a shallow clone has one commit.

## Commands

| Command | What it answers |
| --- | --- |
| `summary` | How big and how old is this, how many people, how many active days? |
| `timeline` | Commits, active authors and lines changed per day / week / month / quarter / year (gaps filled) |
| `contributors` | Who contributed how much: commits, share, lines, files, active days, first and last commit |
| `bus-factor` | How many people can leave before most files have nobody who knows them? Overall and per top-level directory |
| `churn` | Which files change the most (lines added + removed, revisions, distinct authors) |
| `hotspots` | Which files change often **and** are complex? The best place to refactor, test and review |
| `newcomers` | First-time contributors per period, their first commit, and whether they came back |
| `merges` | Pull request and branch merges, squash-merged PRs, commits per merge, lead time, who merges |
| `heatmap` | Commits by weekday and hour, in each author's own time zone or UTC |
| `report` | Every section at once: HTML (default), JSON or text |

Every command prints a table by default and accepts `--format json`. `report` writes
`git-pulse-report.html` unless you pass `-o FILE` (`-o -` for standard output).

## Options

All commands accept these options:

| Option | Meaning |
| --- | --- |
| `-C, --repo PATH` | Repository to analyse (default: current directory) |
| `--rev REV` | Revision or range, e.g. `main`, `v1.0..v2.0` (default `HEAD`) |
| `--all` | Every branch and tag |
| `--since DATE`, `--until DATE` | Anything git understands: `2024-01-01`, `"6 months ago"` |
| `--path PATHSPEC` | Only history touching these paths (repeatable) |
| `--first-parent` | Follow only the first parent of merges (the "main line") |
| `--mailmap FILE` | Extra mailmap file on top of the repository's `.mailmap` |
| `--exclude GLOB` | Leave matching files out of file metrics (repeatable), e.g. `--exclude 'vendor/*'` |
| `--include-generated` | Keep lock files and minified assets (`package-lock.json`, `go.sum`, `*.min.js`, ...) |
| `--include-deleted` | Include files that no longer exist in churn and ownership |
| `--group-by email\|name` | How to identify authors after the mailmap (default `email`) |
| `--period auto\|day\|week\|month\|quarter\|year` | Time bucket for timeline, newcomers and merges |
| `--top N` | Rows in ranked lists (default 20, `0` for all) |
| `--utc` | Heatmap in UTC instead of the author's local time |
| `--max-merges N` | Newest merges to inspect for size and lead time (default 300) |
| `-f, --format` | `table` or `json` (`report`: `html`, `json` or `table`) |
| `-o, --output FILE` | Write to a file instead of standard output |

`bus-factor` also takes `--threshold` (default `0.5`) and `--min N`, which exits with status 1
when the bus factor is below `N`, handy as a scheduled CI check.

Exit codes: `0` success, `1` `--min` check failed, `2` usage error or git error.

## How the metrics work

**Authors.** git-pulse asks git for `%aN`/`%aE` with `--use-mailmap`, so `.mailmap` entries
merge old emails and fix names exactly the way `git shortlog` does. Authors are grouped by
email (or by name with `--group-by name`).

**Renames.** `git log -M` reports renames; history recorded under an old name is credited to
the file's latest name, so a moved file keeps its churn and its authors.

**Bus factor.** For every file that exists at the analysed revision, its *knowledge holders*
are the author who added the most lines plus anyone who wrote at least 25% of it (every
commit also counts as one line, so files that only shrank still have owners). git-pulse then
removes the person holding the most files, again and again, until more than half of the files
have no holder left. The number of people removed is the bus factor. The same calculation
runs per top-level directory. This is a simplified version of the truck-factor algorithm of
Avelino et al. (2016).

**Churn** is lines added plus lines removed per file, from `--numstat`. Binary files count as
revisions with zero lines. Merge commits are not counted twice.

**Hotspots** combine how often a file changes with how complex it is now. Complexity is
measured by indentation, a language-independent proxy that tracks nesting well (the indent
unit is detected per file; tabs count as one level). Score = (revisions / max revisions) x
(complexity / max complexity), from 0 to 1. Only text files up to 1 MB are measured.

**Newcomers.** Each author's first commit in the analysed range, grouped by month (or
`--period`). "Returned" means they committed again more than 30 days later.

**Merges.** Merge commits are classified from their subject: `Merge pull request #N from ...`
(GitHub), `Merge branch '...'` and `Merge remote-tracking branch '...'`. Squash or rebase
merges are recognised by a trailing `(#N)` in the subject. For each merge, git-pulse lists the
commits it brought in (`git log first-parent..second-parent`): their number is the merge size
and the time from the oldest of them to the merge is the lead time.

**Heatmap.** Author dates are kept in the author's own time zone, so 09:00 means 09:00 for the
person who committed. Use `--utc` for a single clock. The report also shows the share of
weekend commits and of weekday commits before 08:00 or after 19:00.

## Examples

```bash
# Last year on the main branch, monthly
git-pulse timeline --since "1 year ago" --period month

# Hotspots in the backend only, ignoring generated code
git-pulse hotspots --path backend/ --exclude 'backend/migrations/*' --top 10

# Contributors between two releases, as JSON
git-pulse contributors --rev v1.0..v2.0 --format json > contributors.json

# Fail a scheduled job when knowledge gets too concentrated
git-pulse bus-factor --min 2

# Everything as one HTML file for a quarterly review
git-pulse report --since 2026-07-01 --until 2026-10-01 -o q3.html

# Who merges, and how long branches live
git-pulse merges --first-parent
```

More in [`examples/`](examples/):

- [`github-actions.yml`](examples/github-actions.yml): weekly report as a build artifact plus a bus factor gate
- [`mailmap.example`](examples/mailmap.example): how to merge identities
- [`demo-repo.sh`](examples/demo-repo.sh): build a small repository to try every command

## JSON output

`--format json` prints the same data the tables show, with ISO 8601 timestamps. For example
`git-pulse summary -f json`:

```json
{
  "commits": 16,
  "merges": 1,
  "authors": 4,
  "first_commit": "2024-01-01T09:00:00+02:00",
  "last_commit": "2024-05-02T10:00:00-05:00",
  "age_days": 122,
  "active_days": 15,
  "files_touched": 9,
  "lines_added": 550,
  "lines_removed": 3
}
```

`git-pulse report -f json` returns every section under one object with a `meta` block
(tool version, revision, filters). New keys may be added in minor versions; existing keys are
not renamed without a changelog entry.

## FAQ

**Why not GitPython or pygit2?** One `git log --numstat` call is fast, works with every git
feature (mailmap, pathspecs, revision ranges, partial clones) and needs nothing to install.
A repository with 90,000 commits reports half a year of history in a few seconds.

**The numbers differ from GitHub's contributor graph.** GitHub counts commits on the default
branch, ignores merges and maps emails to accounts. git-pulse counts what `git log` shows for
your revision (merges included in commit counts; never in line counts) and maps identities
with `.mailmap`. Use `--first-parent` or a `.mailmap` to get closer.

**Is indentation really a measure of complexity?** It is a proxy, but a well-studied one: it
correlates with cyclomatic complexity across languages and needs no parser. Combined with
change frequency it reliably points at the files that cost the most.

**Someone appears twice.** Add a `.mailmap` (see `examples/mailmap.example`) or pass
`--group-by name`.

**My lock files dominate the churn.** They are excluded by default. Add your own generated
paths with `--exclude`, or keep everything with `--include-generated`.

**Does the report phone home?** No. It is one HTML file with inline CSS and SVG, no scripts,
no fonts, no images from the network. It contains names, emails and commit subjects from your
history, so share it like you would share the repository.

**"detected dubious ownership" errors.** That is git refusing a repository owned by another
user. Run `git config --global --add safe.directory /path/to/repo`, or use the Docker image,
which trusts mounted repositories.

## Roadmap

Ideas marked "good first issue" are described in [CONTRIBUTING.md](CONTRIBUTING.md#good-first-issues).

- [ ] GitLab `See merge request !N` detection (good first issue)
- [ ] `--format csv` and `--format markdown` (good first issue)
- [ ] `--exclude-author` to drop bots (good first issue)
- [ ] Churn by language / file extension (good first issue)
- [ ] Per-contributor sparklines in the HTML report (good first issue)
- [ ] Directory-level hotspots (good first issue)
- [ ] Compare two ranges (this quarter vs last quarter)
- [ ] Knowledge loss report: files whose main author has not committed for N months
- [ ] Coupled files (files that usually change together)

## Contributing

Contributions of every size are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md) for the
setup, the project layout, how to add a metric and a list of good first issues. Please follow
the [Code of Conduct](CODE_OF_CONDUCT.md) and report security problems privately as described
in [SECURITY.md](SECURITY.md).

```bash
pip install -e .[dev]
pytest
ruff check . && ruff format --check .
```

## License

[MIT](LICENSE) © Saizul Amin
