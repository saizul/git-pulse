# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | yes |

## What counts as a vulnerability

- Commit messages, author names, branch names or file paths from a repository being able to
  inject markup or script into the HTML report (every value must be escaped)
- The HTML report loading anything from the network (it must be fully self-contained)
- Crafted repository content (paths, refs, config, `.mailmap`) making git-pulse run commands
  other than read-only `git` subcommands, or write files other than the requested output
- Crashes or unbounded memory use caused by crafted history that a normal repository of the
  same size would not trigger

git-pulse runs `git` on the repository you point it at. Like `git` itself, it trusts that
repository's configuration: do not analyse untrusted repositories outside a container.

## Reporting

Please **do not** open a public issue. Use
[GitHub private vulnerability reporting](https://github.com/saizul/git-pulse/security/advisories/new)
with the version, the impact and steps to reproduce (ideally a script that builds the
repository).

You will get an answer within 5 working days. Fixes are released as soon as
possible and credited in the changelog unless you prefer otherwise.

## Notes for users

- The container image adds `safe.directory '*'` to its system git config so mounted
  repositories owned by another user can be read. Mount repositories read-only (`:ro`).
- Reports contain names, emails and commit subjects from the history. Treat them like the
  repository itself before sharing them publicly.
