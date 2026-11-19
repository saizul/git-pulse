"""Command line interface: ``git-pulse <command> [options]``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from git_pulse import text
from git_pulse._version import __version__
from git_pulse.collect import SECTIONS, Analysis, Settings, to_jsonable
from git_pulse.gitlog import GitError, LogOptions
from git_pulse.report import render_html

COMMANDS = {
    "summary": ("summary", "Totals: commits, authors, age, active days, lines changed"),
    "timeline": ("timeline", "Commits, authors and lines per day/week/month/quarter/year"),
    "contributors": ("contributors", "Authors ranked by commits, with lines, files and activity span"),
    "bus-factor": ("bus_factor", "Knowledge concentration: bus factor overall and per directory"),
    "churn": ("churn", "Files ranked by lines added + removed"),
    "hotspots": ("hotspots", "Files that change often and are complex (churn x complexity proxy)"),
    "newcomers": ("newcomers", "First-time contributors per period and whether they came back"),
    "merges": ("merges", "Merge / pull request stats: counts, size, lead time, who merges"),
    "heatmap": ("heatmap", "Commits by weekday and hour"),
}


def _common(
    p: argparse.ArgumentParser, default_format: str = "table", formats: Sequence[str] = ("table", "json")
) -> None:
    g = p.add_argument_group("repository and history")
    g.add_argument("-C", "--repo", default=".", help="path inside the repository (default: current directory)")
    g.add_argument(
        "--rev", default="HEAD", help="revision or range to analyse, e.g. main or v1.0..v2.0 (default: HEAD)"
    )
    g.add_argument("--all", dest="all_refs", action="store_true", help="analyse every branch and tag")
    g.add_argument("--since", help='only commits after this date, e.g. "2024-01-01" or "6 months ago"')
    g.add_argument("--until", help="only commits before this date")
    g.add_argument(
        "--path", dest="paths", action="append", default=[], metavar="PATHSPEC", help="limit to paths (repeatable)"
    )
    g.add_argument("--first-parent", action="store_true", help="follow only the first parent of merges")
    g.add_argument("--mailmap", metavar="FILE", help="use this mailmap file in addition to the repository's .mailmap")
    a = p.add_argument_group("analysis")
    a.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="ignore files matching GLOB in file metrics (repeatable)",
    )
    a.add_argument(
        "--include-generated", action="store_true", help="keep lock files and minified assets in file metrics"
    )
    a.add_argument(
        "--include-deleted", action="store_true", help="include files that no longer exist in churn and ownership"
    )
    a.add_argument(
        "--group-by", choices=("email", "name"), default="email", help="identify authors by email (default) or name"
    )
    a.add_argument(
        "--period", default="auto", choices=("auto", "day", "week", "month", "quarter", "year"), help="time bucket"
    )
    a.add_argument("--top", type=int, default=20, help="rows to show in ranked lists (0 = all, default 20)")
    a.add_argument("--utc", action="store_true", help="heatmap in UTC instead of each author's local time")
    a.add_argument(
        "--max-merges", type=int, default=300, help="newest merges to inspect for size and lead time (default 300)"
    )
    o = p.add_argument_group("output")
    o.add_argument(
        "-f", "--format", choices=formats, default=default_format, help=f"output format (default {default_format})"
    )
    o.add_argument("-o", "--output", metavar="FILE", help="write to FILE instead of standard output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="git-pulse",
        description="Git repository analytics from plain `git log`: activity, contributors, bus factor, churn, "
        "hotspots, newcomers, merges and a commit heatmap, as tables, JSON or one self-contained HTML report.",
    )
    parser.add_argument("--version", action="version", version=f"git-pulse {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    for name, (_, help_text) in COMMANDS.items():
        p = sub.add_parser(name, help=help_text, description=help_text)
        _common(p)
        if name == "bus-factor":
            p.add_argument(
                "--threshold", type=float, default=0.5, help="share of files that must be orphaned (default 0.5)"
            )
            p.add_argument(
                "--min", type=int, metavar="N", help="exit with status 1 if the bus factor is below N (for CI)"
            )
    p = sub.add_parser(
        "report",
        help="Everything at once: a self-contained HTML report (default), JSON or text",
        description="Write every section. HTML goes to git-pulse-report.html unless -o is given.",
    )
    _common(p, default_format="html", formats=("html", "json", "table"))
    p.add_argument("--threshold", type=float, default=0.5, help="bus factor orphaned-file share (default 0.5)")
    return parser


def settings_from(args: argparse.Namespace) -> Settings:
    return Settings(
        repo=args.repo,
        log=LogOptions(
            rev=args.rev,
            all_refs=args.all_refs,
            since=args.since,
            until=args.until,
            paths=tuple(args.paths),
            mailmap=args.mailmap,
            first_parent=args.first_parent,
        ),
        exclude=tuple(args.exclude),
        include_generated=args.include_generated,
        include_deleted=args.include_deleted,
        group_by=args.group_by,
        period=args.period,
        top=max(args.top, 0),
        utc=args.utc,
        max_merges=max(args.max_merges, 0),
        threshold=getattr(args, "threshold", 0.5),
    )


def _write(content: str, output: str | None) -> None:
    if output and output != "-":
        with open(output, "w", encoding="utf-8") as fh:
            fh.write(content)
    else:
        sys.stdout.write(content)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    if hasattr(args, "threshold") and not 0 < args.threshold < 1:
        parser.error("--threshold must be between 0 and 1")
    try:
        analysis = Analysis(settings_from(args))
        if args.command == "report":
            data = analysis.everything()
            if args.format == "json":
                content = json.dumps(to_jsonable(data), indent=2) + "\n"
            elif args.format == "table":
                content = "\n\n".join(text.render(s, data[s]) for s in SECTIONS) + "\n"
            else:
                content = render_html(data)
                if not args.output:
                    args.output = "git-pulse-report.html"
            _write(content, args.output)
            if args.output and args.output != "-":
                print(f"wrote {args.output} ({len(analysis.commits):,} commits)", file=sys.stderr)
            return 0
        section = COMMANDS[args.command][0]
        data = analysis.section(section)
        if args.format == "json":
            _write(json.dumps(to_jsonable(data), indent=2) + "\n", args.output)
        else:
            _write(text.render(section, data) + "\n", args.output)
        if args.command == "bus-factor" and args.min is not None and data["bus_factor"] < args.min:
            print(f"bus factor {data['bus_factor']} is below the required minimum of {args.min}", file=sys.stderr)
            return 1
        return 0
    except (GitError, ValueError) as exc:
        print(f"git-pulse: error: {exc}", file=sys.stderr)
        return 2
    except BrokenPipeError:  # pragma: no cover - e.g. piping into head
        return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
