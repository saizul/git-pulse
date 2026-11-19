## What does this pull request do?

<!-- One or two sentences. Link the issue: "Closes #123". -->

## Type

- [ ] New metric or section
- [ ] Output change (table, JSON, HTML report)
- [ ] Bug fix
- [ ] Documentation

## Checklist

- [ ] Tests added or updated (`pytest` passes; tests build scripted repositories in a temp dir, no network)
- [ ] `ruff check . && ruff format --check .` passes
- [ ] New metrics are pure functions in `analytics.py` with unit tests on hand-made `Commit` objects
- [ ] JSON output stays backwards compatible (new keys only) or the change is called out in CHANGELOG.md
- [ ] The HTML report still has no `<script>`, no external URLs, and escapes every value from git
- [ ] README updated for new commands or flags
- [ ] CHANGELOG.md updated under "Unreleased"
