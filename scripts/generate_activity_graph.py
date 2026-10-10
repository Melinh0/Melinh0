#!/usr/bin/env python3
"""Generate a Tokyo Night themed GitHub activity graph (last 31 days) as SVG."""

import calendar
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

WIDTH, HEIGHT = 820, 280
PAD_L, PAD_R, PAD_T, PAD_B = 56, 24, 56, 48

BG = "#1A1B26"
GRID = "#24283B"
LINE = "#7AA2F7"
AREA_TOP = "#7AA2F7"
AREA_BOTTOM = "#1A1B26"
POINT = "#BB9AF7"
TEXT = "#A9B1D6"
MUTED = "#565F89"
TITLE = "#7AA2F7"
ACCENT = "#9ECE6A"

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks {
          contributionDays { date contributionCount }
        }
      }
    }
  }
}
"""


def fetch_events(login: str, token: str, days: int = 31):
    now = datetime.now(timezone.utc)
    frm = (now - timedelta(days=days - 1)).strftime("%Y-%m-%dT00:00:00Z")
    to = now.strftime("%Y-%m-%dT23:59:59Z")
    body = json.dumps(
        {"query": QUERY, "variables": {"login": login, "from": frm, "to": to}}
    ).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "activity-graph",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if payload.get("errors"):
        print(payload["errors"], file=sys.stderr)
        sys.exit(1)
    days_map = {}
    for week in payload["data"]["user"]["contributionsCollection"][
        "contributionCalendar"
    ]["weeks"]:
        for d in week["contributionDays"]:
            days_map[d["date"]] = d["contributionCount"]

    series = []
    for i in range(days):
        day = (now - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        series.append((day, days_map.get(day, 0)))
    return series


def smooth(points):
    """Catmull-Rom to cubic bezier path."""
    if len(points) < 2:
        return ""
    p = [points[0]] + points + [points[-1]]
    d = f"M {points[0][0]:.1f} {points[0][1]:.1f}"
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        c1x, c1y = p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6
        c2x, c2y = p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6
        d += (
            f" C {c1x:.1f} {c1y:.1f}, {c2x:.1f} {c2y:.1f},"
            f" {p2[0]:.1f} {p2[1]:.1f}"
        )
    return d


def render(series, login: str) -> str:
    values = [v for _, v in series]
    total = sum(values)
    peak = max(values)
    vmax = max(peak, 1)
    step = 5 if vmax <= 20 else (10 if vmax <= 50 else 20)
    top = int(round(vmax / step)) * step

    plot_w = WIDTH - PAD_L - PAD_R
    plot_h = HEIGHT - PAD_T - PAD_B

    def xy(i, v):
        x = PAD_L + (plot_w * i / max(len(series) - 1, 1))
        y = PAD_T + plot_h - (v / top) * plot_h
        return x, y

    pts = [xy(i, v) for i, (_, v) in enumerate(series)]
    line_d = smooth(pts)
    area_d = f"{line_d} L {pts[-1][0]:.1f} {PAD_T + plot_h:.1f}" \
        f" L {pts[0][0]:.1f} {PAD_T + plot_h:.1f} Z"

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}"'
        f' height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}"'
        ' role="img" aria-label="GitHub activity, last 31 days">',
        "<defs>",
        f'<linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{AREA_TOP}" stop-opacity="0.35"/>'
        f'<stop offset="100%" stop-color="{AREA_BOTTOM}" stop-opacity="0"/>'
        "</linearGradient>",
        "</defs>",
        f'<rect width="{WIDTH}" height="{HEIGHT}" rx="12" fill="{BG}"/>',
    ]

    for gv in range(0, top + 1, step):
        _, y = xy(0, gv)
        parts.append(
            f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{WIDTH - PAD_R}"'
            f' y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{PAD_L - 10}" y="{y + 4:.1f}" text-anchor="end"'
            f' font-family="Segoe UI, Ubuntu, Sans-Serif" font-size="11"'
            f' fill="{MUTED}">{gv}</text>'
        )

    parts.append(f'<path d="{area_d}" fill="url(#fill)"/>')
    parts.append(
        f'<path d="{line_d}" fill="none" stroke="{LINE}"'
        ' stroke-width="2.5" stroke-linecap="round"'
        ' stroke-linejoin="round"/>'
    )

    for i, ((date, v), (x, y)) in enumerate(zip(series, pts)):
        if v == 0:
            continue
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{POINT}"/>'
        )
        if v == peak:
            parts.append(
                f'<text x="{x:.1f}" y="{y - 10:.1f}" text-anchor="middle"'
                f' font-family="Segoe UI, Ubuntu, Sans-Serif"'
                f' font-size="11" font-weight="600" fill="{ACCENT}">{v}</text>'
            )

    every = 5
    for i, (date, _) in enumerate(series):
        if i % every != 0 and i != len(series) - 1:
            continue
        x = PAD_L + (plot_w * i / max(len(series) - 1, 1))
        label = datetime.strptime(date, "%Y-%m-%d").strftime("%d %b")
        parts.append(
            f'<text x="{x:.1f}" y="{HEIGHT - PAD_B + 22}"'
            f' text-anchor="middle" font-family="Segoe UI, Ubuntu,'
        f' Sans-Serif" font-size="11" fill="{MUTED}">{label}</text>'
        )

    active = sum(1 for v in values if v > 0)
    parts.append(
        f'<text x="{PAD_L}" y="30" font-family="Segoe UI, Ubuntu,'
        f' Sans-Serif" font-size="16" font-weight="700" fill="{TITLE}">'
        f"{login}&apos;s GitHub Activity</text>"
    )
    parts.append(
        f'<text x="{PAD_L}" y="47" font-family="Segoe UI, Ubuntu,'
        f' Sans-Serif" font-size="11.5" fill="{MUTED}">'
        f"Last 31 days &middot; {total} contributions"
        f" &middot; {active} active days &middot; peak {peak}</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts)


def main():
    login = os.environ.get("GITHUB_ACTOR") or (sys.argv[1] if len(sys.argv) > 1 else "Melinh0")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("Set GITHUB_TOKEN or GH_TOKEN")

    series = fetch_events(login, token)
    out_dir = os.environ.get("OUT_DIR", "dist")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "github-activity-graph.svg")
    with open(path, "w", encoding="utf-8") as f:
        f.write(render(series, login))
    print(f"Wrote {path} ({sum(v for _, v in series)} contributions)")


if __name__ == "__main__":
    main()
