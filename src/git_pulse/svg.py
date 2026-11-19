"""Tiny inline SVG chart builders. Colours come from CSS variables set by the report."""

from __future__ import annotations

import math
from collections.abc import Sequence
from html import escape


def _nice_max(value: float) -> float:
    if value <= 0:
        return 1
    exp = 10 ** math.floor(math.log10(value))
    for step in (1, 2, 2.5, 5, 10):
        if value <= step * exp:
            return step * exp
    return 10 * exp  # pragma: no cover


def _num(v: float) -> str:
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.1f}"


def empty(message: str = "No data") -> str:
    return f'<p class="empty">{escape(message)}</p>'


def bar_chart(
    labels: Sequence[str],
    values: Sequence[float],
    *,
    title: str,
    width: int = 900,
    height: int = 260,
    unit: str = "commits",
) -> str:
    """Vertical bar chart with y grid lines and sparse x labels."""
    if not values or not any(values):
        return empty()
    left, right, top, bottom = 48, 12, 12, 46
    plot_w, plot_h = width - left - right, height - top - bottom
    ymax = _nice_max(max(values))
    n = len(values)
    slot = plot_w / n
    bw = max(slot * 0.8, 1)
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}" '
        f'xmlns="http://www.w3.org/2000/svg"><title>{escape(title)}</title>'
    ]
    for i in range(5):
        y = top + plot_h - plot_h * i / 4
        parts.append(f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}"/>')
        parts.append(f'<text class="axis" x="{left - 6}" y="{y + 4:.1f}" text-anchor="end">{_num(ymax * i / 4)}</text>')
    every = max(1, math.ceil(n / 12))
    for i, (label, v) in enumerate(zip(labels, values, strict=True)):
        h = plot_h * v / ymax
        x = left + i * slot + (slot - bw) / 2
        y = top + plot_h - h
        parts.append(
            f'<rect class="bar" x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}">'
            f"<title>{escape(str(label))}: {_num(v)} {escape(unit)}</title></rect>"
        )
        if i % every == 0:
            cx = left + i * slot + slot / 2
            parts.append(
                f'<text class="axis" x="{cx:.1f}" y="{height - bottom + 16}" text-anchor="middle">'
                f"{escape(str(label))}</text>"
            )
    parts.append("</svg>")
    return "".join(parts)


def hbar_chart(
    labels: Sequence[str],
    values: Sequence[float],
    *,
    title: str,
    width: int = 900,
    row: int = 24,
    unit: str = "commits",
) -> str:
    """Horizontal bars, one row per label (top contributors)."""
    if not values or not any(values):
        return empty()
    label_w, right = 220, 70
    height = row * len(values) + 8
    vmax = max(values)
    plot_w = width - label_w - right
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}" '
        f'xmlns="http://www.w3.org/2000/svg"><title>{escape(title)}</title>'
    ]
    for i, (label, v) in enumerate(zip(labels, values, strict=True)):
        y = 4 + i * row
        w = plot_w * v / vmax if vmax else 0
        short = label if len(label) <= 30 else label[:29] + "…"
        parts.append(
            f'<text class="label" x="{label_w - 8}" y="{y + row * 0.65:.1f}" text-anchor="end">{escape(short)}</text>'
        )
        parts.append(
            f'<rect class="bar" x="{label_w}" y="{y + 3}" width="{max(w, 1):.1f}" height="{row - 6}" rx="2">'
            f"<title>{escape(label)}: {_num(v)} {escape(unit)}</title></rect>"
        )
        parts.append(f'<text class="value" x="{label_w + w + 6:.1f}" y="{y + row * 0.65:.1f}">{_num(v)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def heatmap(grid: Sequence[Sequence[int]], rows: Sequence[str], *, title: str, width: int = 900) -> str:
    """Weekday x hour grid; cell opacity encodes the commit count."""
    peak = max((max(r) for r in grid), default=0)
    if not peak:
        return empty()
    left, top = 44, 22
    cell = (width - left - 8) / 24
    ch = min(cell, 30)
    height = top + ch * len(grid) + 6
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height:.0f}" role="img" aria-label="{escape(title)}" '
        f'xmlns="http://www.w3.org/2000/svg"><title>{escape(title)}</title>'
    ]
    for h in range(24):
        parts.append(
            f'<text class="axis" x="{left + h * cell + cell / 2:.1f}" y="14" text-anchor="middle">{h:02d}</text>'
        )
    for d, (name, values) in enumerate(zip(rows, grid, strict=True)):
        y = top + d * ch
        parts.append(
            f'<text class="label" x="{left - 8}" y="{y + ch * 0.65:.1f}" text-anchor="end">{escape(name)}</text>'
        )
        for h, v in enumerate(values):
            opacity = 0.06 if not v else 0.18 + 0.82 * v / peak
            parts.append(
                f'<rect class="cell" x="{left + h * cell + 1:.1f}" y="{y + 1:.1f}" width="{cell - 2:.1f}" '
                f'height="{ch - 2:.1f}" rx="3" fill-opacity="{opacity:.2f}">'
                f"<title>{escape(name)} {h:02d}:00: {v:,} commits</title></rect>"
            )
    parts.append("</svg>")
    return "".join(parts)


def scatter(points: Sequence[dict], *, title: str, width: int = 900, height: int = 340) -> str:
    """Bubble chart: x = revisions, y = complexity, radius = churn, label = path."""
    if not points:
        return empty()
    left, right, top, bottom = 56, 16, 14, 40
    pw, ph = width - left - right, height - top - bottom
    xmax = _nice_max(max(p["revisions"] for p in points))
    ymax = _nice_max(max(p["complexity"] for p in points))
    cmax = max(p["churn"] for p in points) or 1
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}" '
        f'xmlns="http://www.w3.org/2000/svg"><title>{escape(title)}</title>'
    ]
    for i in range(5):
        y = top + ph - ph * i / 4
        x = left + pw * i / 4
        parts.append(f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}"/>')
        parts.append(f'<text class="axis" x="{left - 6}" y="{y + 4:.1f}" text-anchor="end">{_num(ymax * i / 4)}</text>')
        parts.append(
            f'<text class="axis" x="{x:.1f}" y="{top + ph + 16}" text-anchor="middle">{_num(xmax * i / 4)}</text>'
        )
    parts.append(f'<text class="axis" x="{left + pw / 2:.1f}" y="{height - 4}" text-anchor="middle">revisions</text>')
    parts.append(
        f'<text class="axis" x="12" y="{top + ph / 2:.1f}" text-anchor="middle" '
        f'transform="rotate(-90 12 {top + ph / 2:.1f})">complexity</text>'
    )
    for p in sorted(points, key=lambda p: -p["churn"]):
        cx = left + pw * p["revisions"] / xmax
        cy = top + ph - ph * p["complexity"] / ymax
        r = 4 + 14 * math.sqrt(p["churn"] / cmax)
        parts.append(
            f'<circle class="dot" cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}">'
            f"<title>{escape(p['path'])}: {p['revisions']} revisions, complexity {p['complexity']:,}, "
            f"churn {p['churn']:,}, score {p['score']:.3f}</title></circle>"
        )
    for p in points[:5]:
        cx = left + pw * p["revisions"] / xmax
        cy = top + ph - ph * p["complexity"] / ymax
        name = p["path"].rsplit("/", 1)[-1]
        parts.append(f'<text class="value" x="{cx + 8:.1f}" y="{cy - 8:.1f}">{escape(name)}</text>')
    parts.append("</svg>")
    return "".join(parts)
