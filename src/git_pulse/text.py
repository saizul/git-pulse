"""Plain terminal output: aligned tables and Unicode bar charts, no dependencies."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

BLOCKS = " ▏▎▍▌▋▊▉"
SHADES = " ░▒▓█"


def fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def truncate(text: str, width: int) -> str:
    return text if len(text) <= width else text[: max(width - 1, 1)] + "…"


def table(headers: Sequence[str], rows: Sequence[Sequence], align: str = "", max_width: int = 60) -> str:
    """Render rows as an aligned table. ``align`` has one char per column: l or r."""
    cells = [[truncate(fmt(v), max_width) for v in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in cells:
        for i, c in enumerate(row):
            widths[i] = max(widths[i], len(c))
    align = (align or "").ljust(len(headers), "l")

    def line(values: Sequence[str]) -> str:
        out = []
        for i, v in enumerate(values):
            out.append(v.rjust(widths[i]) if align[i] == "r" else v.ljust(widths[i]))
        return "  ".join(out).rstrip()

    sep = "  ".join("-" * w for w in widths)
    return "\n".join([line(headers), sep, *(line(r) for r in cells)])


def bar(value: float, maximum: float, width: int = 30) -> str:
    if maximum <= 0 or value <= 0:
        return ""
    full = value / maximum * width
    whole = int(full)
    rest = full - whole
    tail = BLOCKS[int(rest * 8)] if rest > 0 and whole < width else ""
    return ("█" * whole + tail.strip()) or "▏"


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def title(text: str) -> str:
    return f"{text}\n{'=' * len(text)}"


# --------------------------------------------------------------------------- sections


def render_summary(s: dict) -> str:
    rows = [
        ("Commits", s["commits"]),
        ("Merge commits", s["merges"]),
        ("Authors", s["authors"]),
        ("First commit", s["first_commit"]),
        ("Last commit", s["last_commit"]),
        ("Age (days)", s["age_days"]),
        ("Active days", s["active_days"]),
        ("Files touched", s["files_touched"]),
        ("Lines added", s["lines_added"]),
        ("Lines removed", s["lines_removed"]),
    ]
    return title("Summary") + "\n" + table(["Metric", "Value"], rows, "lr")


def render_timeline(t: dict) -> str:
    rows = t["rows"]
    peak = max((r["commits"] for r in rows), default=0)
    body = table(
        ["Period", "Commits", "Authors", "+Lines", "-Lines", ""],
        [(r["period"], r["commits"], r["authors"], r["added"], r["removed"], bar(r["commits"], peak)) for r in rows],
        "lrrrrl",
    )
    return title(f"Commits per {t['period']}") + "\n" + body


def render_contributors(rows: list[dict]) -> str:
    body = table(
        ["Author", "Email", "Commits", "Share", "+Lines", "-Lines", "Files", "Days", "First", "Last"],
        [
            (
                r["name"],
                r["email"],
                r["commits"],
                pct(r["share"]),
                r["added"],
                r["removed"],
                r["files"],
                r["active_days"],
                r["first_commit"],
                r["last_commit"],
            )
            for r in rows
        ],
        "llrrrrrrll",
        max_width=36,
    )
    return title("Contributors") + "\n" + body


def render_bus_factor(b: dict) -> str:
    lines = [
        title("Bus factor"),
        f"Bus factor: {b['bus_factor']}  (people who would have to leave before more than "
        f"{pct(b['threshold'])} of {b['files']:,} files lose every knowledge holder)",
        f"Single-author files: {b['single_author_files']:,} ({pct(b['single_author_share'])})",
    ]
    if b["key_people"]:
        lines += [
            "",
            table(
                ["Key person", "Email", "Files held"],
                [(p["name"], p["email"], p["files_held"]) for p in b["key_people"]],
                "llr",
            ),
        ]
    if b["directories"]:
        lines += [
            "",
            table(
                ["Directory", "Files", "Bus factor", "Main author"],
                [(d["directory"], d["files"], d["bus_factor"], d["main_author"]) for d in b["directories"]],
                "lrrl",
            ),
        ]
    return "\n".join(lines)


def render_churn(rows: list[dict]) -> str:
    body = table(
        ["File", "Revisions", "+Lines", "-Lines", "Churn", "Authors", "Last change"],
        [
            (r["path"], r["revisions"], r["added"], r["removed"], r["churn"], r["authors"], r["last_change"])
            for r in rows
        ],
        "lrrrrrl",
        max_width=70,
    )
    return title("Code churn") + "\n" + body


def render_hotspots(rows: list[dict]) -> str:
    if not rows:
        return title("Hotspots") + "\nNo text files with history found."
    body = table(
        ["File", "Score", "Revisions", "LOC", "Complexity", "Max indent", "Authors"],
        [
            (r["path"], f"{r['score']:.3f}", r["revisions"], r["loc"], r["complexity"], r["max_indent"], r["authors"])
            for r in rows
        ],
        "lrrrrrr",
        max_width=70,
    )
    return title("Hotspots (revisions x indentation complexity)") + "\n" + body


def render_newcomers(n: dict) -> str:
    lines = [
        title("First-time contributors"),
        f"{n['total']:,} people made a first commit; {n['returned']:,} came back after "
        f"{n['retention_days']} days, {n['one_time']:,} did not.",
        "",
    ]
    peak = max((r["newcomers"] for r in n["per_period"]), default=0)
    lines.append(
        table(
            ["Period", "Newcomers", ""],
            [(r["period"], r["newcomers"], bar(r["newcomers"], peak, 20)) for r in n["per_period"]],
            "lrl",
        )
    )
    recent = list(reversed(n["people"]))[:10]
    if recent:
        lines += [
            "",
            "Most recent newcomers:",
            table(
                ["Date", "Author", "Commits", "Returned", "First commit"],
                [(p["first_commit"], p["name"], p["commits"], p["returned"], p["subject"]) for p in recent],
                "llrll",
                max_width=50,
            ),
        ]
    return "\n".join(lines)


def _hours(value) -> str:
    if value is None:
        return "-"
    if value < 48:
        return f"{value:.1f} h"
    return f"{value / 24:.1f} d"


def render_merges(m: dict) -> str:
    cpm = m["commits_per_merge"]
    lt = m["lead_time_hours"]
    lines = [
        title("Merges and pull requests"),
        f"Merge commits: {m['merges']:,} ({m['pull_request_merges']:,} pull requests, "
        f"{m['branch_merges']:,} branch merges); squash-merged PRs: {m['squash_merges']:,}",
        f"Commits per merge: median {fmt(cpm['median'])}, p90 {fmt(cpm['p90'])}, max {fmt(cpm['max'])}",
        f"Lead time (first branch commit to merge): median {_hours(lt['median'])}, p90 {_hours(lt['p90'])}",
    ]
    if m["top_mergers"]:
        lines += ["", table(["Merged by", "Merges"], [(r["name"], r["merges"]) for r in m["top_mergers"]], "lr")]
    if m["recent"]:
        lines += [
            "",
            table(
                ["Date", "Kind", "PR", "Commits", "Lead time", "Subject"],
                [
                    (
                        r["date"],
                        r["kind"],
                        f"#{r['number']}" if r["number"] else "-",
                        r["commits"],
                        _hours(r["lead_time_hours"]),
                        r["subject"],
                    )
                    for r in m["recent"]
                ],
                "llrrrl",
                max_width=60,
            ),
        ]
    return "\n".join(lines)


def render_heatmap(h: dict) -> str:
    grid = h["grid"]
    peak = max((max(row) for row in grid), default=0)
    lines = [title(f"Commit heatmap ({h['timezone']})"), "     " + "".join(f"{x:<3}" for x in range(0, 24, 3)).rstrip()]
    for name, row in zip(h["weekdays"], grid, strict=True):
        cells = ""
        for v in row:
            idx = 0 if not v or not peak else max(1, round(v / peak * (len(SHADES) - 1)))
            cells += SHADES[idx]
        lines.append(f"{name}  {cells}  {sum(row):>5,}")
    if h["peak"]:
        p = h["peak"]
        lines.append("")
        lines.append(
            f"Peak: {p['weekday']} {p['hour']:02d}:00 ({p['commits']:,} commits). "
            f"Weekend: {pct(h['weekend_share'])}. Weekday before 08:00 or after 19:00: {pct(h['after_hours_share'])}."
        )
    return "\n".join(lines)


RENDERERS = {
    "summary": render_summary,
    "timeline": render_timeline,
    "contributors": render_contributors,
    "bus_factor": render_bus_factor,
    "churn": render_churn,
    "hotspots": render_hotspots,
    "newcomers": render_newcomers,
    "merges": render_merges,
    "heatmap": render_heatmap,
}


def render(section: str, data) -> str:
    return RENDERERS[section](data)
