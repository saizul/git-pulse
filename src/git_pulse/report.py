"""Single-file HTML report: inline CSS and SVG, no JavaScript, no external requests."""

from __future__ import annotations

from datetime import datetime
from html import escape

from git_pulse import svg

CSS = """
:root{--bg:#f7f7f9;--card:#fff;--fg:#1d1f24;--muted:#6b7080;--line:#e3e5ea;--accent:#3b6fe0;--accent2:#e0703b}
@media (prefers-color-scheme:dark){:root{--bg:#121318;--card:#1b1d24;--fg:#e8e9ee;--muted:#9a9fb0;--line:#2c2f39;
--accent:#6f9bff;--accent2:#ff9d6f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1000px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:28px;margin:0 0 4px}h2{font-size:19px;margin:0 0 12px}.sub{color:var(--muted);margin:0 0 24px}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;margin:0 0 20px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:0 0 20px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.kpi b{display:block;font-size:24px}.kpi span{color:var(--muted);font-size:13px}
table{width:100%;border-collapse:collapse;font-size:13.5px;margin-top:12px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600}td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
td.p{word-break:break-all}
.chart{width:100%;height:auto;display:block}.chart .bar{fill:var(--accent)}.chart .bar:hover{fill:var(--accent2)}
.chart .cell{fill:var(--accent)}.chart .dot{fill:var(--accent2);fill-opacity:.55;stroke:var(--accent2)}
.chart .grid{stroke:var(--line)}.chart text{fill:var(--muted);font-size:11px}
.chart .label{fill:var(--fg);font-size:12px}
.chart .value{fill:var(--fg);font-size:11px}
.note{color:var(--muted);font-size:13px}.empty{color:var(--muted)}
.badge{display:inline-block;padding:1px 8px;border-radius:99px;background:var(--line);font-size:12px}
footer{color:var(--muted);font-size:12px;text-align:center}
nav{margin:0 0 20px;font-size:13px}nav a{color:var(--accent);margin-right:12px;text-decoration:none}
"""


def _v(value) -> str:
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
    return escape(str(value))


def _table(
    headers: list[str], rows: list[list], numeric: set[int] | None = None, path_cols: set[int] | None = None
) -> str:
    numeric = numeric or set()
    path_cols = path_cols or set()
    head = "".join(
        f'<th class="n">{escape(h)}</th>' if i in numeric else f"<th>{escape(h)}</th>" for i, h in enumerate(headers)
    )
    body = []
    for row in rows:
        cells = []
        for i, v in enumerate(row):
            cls = "n" if i in numeric else ("p" if i in path_cols else "")
            cells.append(f'<td class="{cls}">{_v(v)}</td>' if cls else f"<td>{_v(v)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    if not body:
        return svg.empty()
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def _hours(v) -> str:
    if v is None:
        return "-"
    return f"{v:.1f} h" if v < 48 else f"{v / 24:.1f} days"


def render_html(data: dict) -> str:
    meta, s = data["meta"], data["summary"]
    tl, contrib, bus = data["timeline"], data["contributors"], data["bus_factor"]
    churn, hot, new, merges, heat = data["churn"], data["hotspots"], data["newcomers"], data["merges"], data["heatmap"]

    scope = [f"revision <b>{escape(str(meta['revision']))}</b>"]
    if meta.get("since"):
        scope.append(f"since {escape(meta['since'])}")
    if meta.get("until"):
        scope.append(f"until {escape(meta['until'])}")
    if meta.get("paths"):
        scope.append("paths " + ", ".join(f"<code>{escape(p)}</code>" for p in meta["paths"]))

    kpis = [
        ("Commits", _v(s["commits"])),
        ("Authors", _v(s["authors"])),
        ("Bus factor", _v(bus["bus_factor"])),
        ("Active days", _v(s["active_days"])),
        ("Lines added", _v(s["lines_added"])),
        ("Lines removed", _v(s["lines_removed"])),
    ]
    out = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>git-pulse: {escape(meta['repository'])}</title>",
        f"<style>{CSS}</style></head><body><main>",
        f"<h1>{escape(meta['repository'])}</h1>",
        f'<p class="sub">{"; ".join(scope)}. History from {_v(s["first_commit"])} to {_v(s["last_commit"])}.</p>',
        '<nav><a href="#timeline">Timeline</a><a href="#contributors">Contributors</a><a href="#bus">Bus factor</a>'
        '<a href="#hotspots">Hotspots</a><a href="#churn">Churn</a><a href="#newcomers">Newcomers</a>'
        '<a href="#merges">Merges</a><a href="#heatmap">Heatmap</a></nav>',
        '<div class="kpis">'
        + "".join(f'<div class="kpi"><b>{v}</b><span>{k}</span></div>' for k, v in kpis)
        + "</div>",
    ]

    rows = tl["rows"]
    out.append(
        f'<section id="timeline"><h2>Commits per {escape(tl["period"])}</h2>'
        + svg.bar_chart([r["period"] for r in rows], [r["commits"] for r in rows], title="Commits over time")
        + "</section>"
    )

    out.append(
        '<section id="contributors"><h2>Top contributors</h2>'
        + svg.hbar_chart(
            [c["name"] for c in contrib[:15]], [c["commits"] for c in contrib[:15]], title="Commits per author"
        )
        + _table(
            ["Author", "Commits", "Share", "+Lines", "-Lines", "Files", "Active days", "First", "Last"],
            [
                [
                    c["name"],
                    c["commits"],
                    _pct(c["share"]),
                    c["added"],
                    c["removed"],
                    c["files"],
                    c["active_days"],
                    c["first_commit"],
                    c["last_commit"],
                ]
                for c in contrib
            ],
            numeric={1, 2, 3, 4, 5, 6},
        )
        + "</section>"
    )

    out.append(
        f'<section id="bus"><h2>Bus factor: {bus["bus_factor"]}</h2>'
        f'<p class="note">The smallest number of people who would have to leave before more than '
        f"{_pct(bus['threshold'])} of the {bus['files']:,} current files have nobody who wrote a large part of them. "
        f"{bus['single_author_files']:,} files ({_pct(bus['single_author_share'])}) have exactly one author.</p>"
        + _table(["Key person", "Files held"], [[p["name"], p["files_held"]] for p in bus["key_people"]], numeric={1})
        + _table(
            ["Directory", "Files", "Bus factor", "Main author"],
            [[d["directory"], d["files"], d["bus_factor"], d["main_author"]] for d in bus["directories"]],
            numeric={1, 2},
            path_cols={0},
        )
        + "</section>"
    )

    out.append(
        '<section id="hotspots"><h2>Hotspots</h2><p class="note">Files that change often <i>and</i> are complex '
        "(indentation-based complexity at the analysed revision). Bubble size is churn. Start refactoring and "
        "reviewing here.</p>"
        + svg.scatter(hot, title="Hotspots: revisions vs complexity")
        + _table(
            ["File", "Score", "Revisions", "LOC", "Complexity", "Authors"],
            [[h["path"], f"{h['score']:.3f}", h["revisions"], h["loc"], h["complexity"], h["authors"]] for h in hot],
            numeric={1, 2, 3, 4, 5},
            path_cols={0},
        )
        + "</section>"
    )

    out.append(
        '<section id="churn"><h2>Code churn</h2>'
        + _table(
            ["File", "Revisions", "+Lines", "-Lines", "Churn", "Authors", "Last change"],
            [
                [c["path"], c["revisions"], c["added"], c["removed"], c["churn"], c["authors"], c["last_change"]]
                for c in churn
            ],
            numeric={1, 2, 3, 4, 5},
            path_cols={0},
        )
        + "</section>"
    )

    pp = new["per_period"]
    out.append(
        f'<section id="newcomers"><h2>First-time contributors</h2><p class="note">{new["total"]:,} people made a first '
        f"commit; {new['returned']:,} came back more than {new['retention_days']} days later.</p>"
        + svg.bar_chart(
            [r["period"] for r in pp],
            [r["newcomers"] for r in pp],
            title="Newcomers per period",
            height=200,
            unit="newcomers",
        )
        + _table(
            ["First commit", "Author", "Commits", "Returned", "Subject"],
            [
                [p["first_commit"], p["name"], p["commits"], p["returned"], p["subject"]]
                for p in list(reversed(new["people"]))[:15]
            ],
            numeric={2},
        )
        + "</section>"
    )

    mp = merges["per_period"]
    cpm, lt = merges["commits_per_merge"], merges["lead_time_hours"]
    out.append(
        '<section id="merges"><h2>Merges and pull requests</h2>'
        f'<p class="note">{merges["merges"]:,} merge commits ({merges["pull_request_merges"]:,} pull requests, '
        f"{merges['branch_merges']:,} branch merges) and {merges['squash_merges']:,} squash-merged pull requests. "
        f"Median {_v(cpm['median'])} commits per merge; median lead time {_hours(lt['median'])} "
        f"(p90 {_hours(lt['p90'])}).</p>"
        + svg.bar_chart(
            [r["period"] for r in mp], [r["merges"] for r in mp], title="Merges per period", height=200, unit="merges"
        )
        + _table(
            ["Date", "Kind", "PR", "Commits", "Lead time", "Merged by", "Subject"],
            [
                [
                    r["date"],
                    r["kind"],
                    f"#{r['number']}" if r["number"] else "-",
                    r["commits"],
                    _hours(r["lead_time_hours"]),
                    r["merged_by"],
                    r["subject"],
                ]
                for r in merges["recent"]
            ],
            numeric={3, 4},
        )
        + "</section>"
    )

    peak = heat["peak"]
    peak_txt = f"Busiest slot: {peak['weekday']} {peak['hour']:02d}:00. " if peak else ""
    out.append(
        f'<section id="heatmap"><h2>When commits happen <span class="badge">{escape(heat["timezone"])}</span></h2>'
        f'<p class="note">{peak_txt}Weekend commits: {_pct(heat["weekend_share"])}. '
        f"Weekday commits before 08:00 or after 19:00: {_pct(heat['after_hours_share'])}.</p>"
        + svg.heatmap(heat["grid"], heat["weekdays"], title="Commits by weekday and hour")
        + "</section>"
    )

    out.append(
        f"<footer>Generated by git-pulse {escape(meta['version'])} on {_v(meta['generated_at'])}. "
        "This file is self-contained and makes no network requests.</footer>"
    )
    out.append("</main></body></html>")
    return "\n".join(out) + "\n"
