# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `--exclude-author PATTERN` (repeatable) drops commits whose author name or email matches
  from every section. Matching is case-insensitive and only `*` and `?` are wildcards, so
  `'*[bot]'` matches `dependabot[bot]` literally.
- `--exclude-bots` adds `'*[bot]'`, `'dependabot*'` and `'renovate*'`.
- The JSON `meta` block gains `exclude_authors` and `excluded_commits`; the HTML report
  shows them in its scope line.

## [0.1.0] - 2026-11-19

### Added

- History is read with one `git log --numstat` call through `subprocess`; no Python
  dependencies at runtime.
- `.mailmap` support (repository file and `--mailmap FILE`), grouping authors by email or name.
- Renamed files keep their history under the latest name.
- Commands: `summary`, `timeline`, `contributors`, `bus-factor`, `churn`, `hotspots`,
  `newcomers`, `merges`, `heatmap` and `report`.
- Bus factor overall and per top-level directory, with `--min N` to fail CI.
- Hotspots ranked by revisions x indentation-based complexity at the analysed revision.
- First-time contributors per period, with a "came back after 30 days" flag.
- Merge statistics: GitHub pull request merges, branch merges, squash-merged PRs (`(#123)`),
  commits per merge, lead time and who merges.
- Weekday x hour heatmap in each author's local time or UTC.
- Output as aligned terminal tables, JSON, or one self-contained HTML report with inline SVG
  charts, light and dark themes, no JavaScript and no external requests.
- Lock files and minified assets are left out of file metrics by default (`--include-generated`).
- Container image on `ghcr.io/saizul/git-pulse`.

[Unreleased]: https://github.com/saizul/git-pulse/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/saizul/git-pulse/releases/tag/v0.1.0
