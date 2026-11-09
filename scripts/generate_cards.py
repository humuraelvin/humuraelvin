#!/usr/bin/env python3
"""Generate the profile's trophy, language and 3D-calendar cards as SVGs.

Uses only the GitHub GraphQL API and the Python standard library so it keeps
working without third-party card services. Writes dark and light variants of
each card into assets/cards/.

Environment:
  GH_TOKEN   token used for the GraphQL API (public data is enough)
  GH_USER    GitHub login to render (defaults to the repository owner)
"""

import datetime as dt
import html
import json
import math
import os
import sys
import urllib.request
from pathlib import Path

USER = os.environ.get("GH_USER") or "humuraelvin"
TOKEN = os.environ.get("GH_TOKEN")
OUT = Path(__file__).resolve().parent.parent / "assets" / "cards"

FONT = "-apple-system,BlinkMacSystemFont,'SF Pro Display','Segoe UI',Helvetica,Arial,sans-serif"

THEMES = {
    "dark": {
        "bg": "#0d1117", "card": "#161b22", "border": "#30363d",
        "title": "#f5f5f7", "text": "#e6edf3", "muted": "#8b949e",
        "accent": "#0A84FF", "track": "#21262d",
        "cal": ["#161b22", "#0b2a4a", "#0a4a8c", "#0A84FF", "#64D2FF"],
        "tiers": {"SSS": "#FF375F", "SS": "#FF9F0A", "S": "#FFD60A", "AAA": "#30D158", "AA": "#30D158",
                  "A": "#64D2FF", "B": "#0A84FF", "C": "#8E8E93", "-": "#8E8E93"},
    },
    "light": {
        "bg": "#ffffff", "card": "#f5f5f7", "border": "#d2d2d7",
        "title": "#1d1d1f", "text": "#1d1d1f", "muted": "#6e6e73",
        "accent": "#0071E3", "track": "#e5e5ea",
        "cal": ["#ebedf0", "#bfdcff", "#73b3ff", "#0071E3", "#003f8a"],
        "tiers": {"SSS": "#D70040", "SS": "#C93400", "S": "#B25000", "AAA": "#248A3D", "AA": "#248A3D",
                  "A": "#0071A4", "B": "#0040DD", "C": "#6E6E73", "-": "#6E6E73"},
    },
}


# --------------------------------------------------------------------------- data

def gql(query, variables=None):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "User-Agent": "profile-cards"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
    if body.get("errors"):
        raise RuntimeError(json.dumps(body["errors"], indent=2))
    return body["data"]


def fetch():
    base = gql(
        """query($login:String!){ user(login:$login){
             createdAt
             followers{ totalCount }
             pullRequests{ totalCount }
             issues{ totalCount }
             contributionsCollection{
               contributionYears
               contributionCalendar{ totalContributions
                 weeks{ contributionDays{ date contributionCount weekday } } }
             }
           } }""",
        {"login": USER},
    )["user"]

    repos, cursor = [], None
    while True:
        page = gql(
            """query($login:String!,$after:String){ user(login:$login){
                 repositories(first:100, after:$after, ownerAffiliations:OWNER, isFork:false){
                   pageInfo{ hasNextPage endCursor }
                   nodes{ stargazerCount
                     languages(first:20, orderBy:{field:SIZE, direction:DESC}){
                       edges{ size node{ name color } } } }
                 } } }""",
            {"login": USER, "after": cursor},
        )["user"]["repositories"]
        repos += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    commits = contributions = 0
    for year in base["contributionsCollection"]["contributionYears"]:
        c = gql(
            """query($login:String!,$from:DateTime!,$to:DateTime!){ user(login:$login){
                 contributionsCollection(from:$from, to:$to){
                   totalCommitContributions restrictedContributionsCount
                   contributionCalendar{ totalContributions } } } }""",
            {"login": USER, "from": f"{year}-01-01T00:00:00Z", "to": f"{year}-12-31T23:59:59Z"},
        )["user"]["contributionsCollection"]
        commits += c["totalCommitContributions"] + c["restrictedContributionsCount"]
        contributions += c["contributionCalendar"]["totalContributions"]

    # Each repository counts equally: its weight of 1 is split by its own
    # language shares, so a few repos with bundled libraries can't dominate.
    langs = {}
    for repo in repos:
        edges = [e for e in repo["languages"]["edges"] if e["node"]["name"] not in IGNORED]
        repo_total = sum(e["size"] for e in edges)
        for e in edges:
            name = e["node"]["name"]
            entry = langs.setdefault(name, {"size": 0, "color": e["node"]["color"] or "#8b949e"})
            entry["size"] += e["size"] / repo_total

    days = [d for w in base["contributionsCollection"]["contributionCalendar"]["weeks"]
            for d in w["contributionDays"]]
    created = dt.datetime.fromisoformat(base["createdAt"].replace("Z", "+00:00"))
    return {
        "followers": base["followers"]["totalCount"],
        "prs": base["pullRequests"]["totalCount"],
        "issues": base["issues"]["totalCount"],
        "repos": len(repos),
        "stars": sum(r["stargazerCount"] for r in repos),
        "commits": commits,
        "contributions": contributions,
        "years": max(1, (dt.datetime.now(dt.timezone.utc) - created).days // 365),
        "languages": langs,
        "weeks": base["contributionsCollection"]["contributionCalendar"]["weeks"],
        "days": days,
        "year_total": base["contributionsCollection"]["contributionCalendar"]["totalContributions"],
    }


# --------------------------------------------------------------------------- helpers

def esc(s):
    return html.escape(str(s), quote=True)


def fmt(n):
    if n >= 1000:
        return f"{n / 1000:.1f}k".replace(".0k", "k")
    return str(n)


def svg(width, height, body, t, style=""):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">
<style>
  text {{ font-family: {FONT}; }}
  .fade {{ animation: fade .7s cubic-bezier(.2,.8,.2,1) both; }}
  @keyframes fade {{ from {{ opacity: 0; transform: translateY(6px); }} }}
  @media (prefers-reduced-motion: reduce) {{ .fade, .ring, .bar {{ animation: none !important; }} }}
  {style}
</style>
<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="16" fill="{t['bg']}" stroke="{t['border']}"/>
{body}
</svg>
"""


# --------------------------------------------------------------------------- trophies

TIERS = ["C", "B", "A", "AA", "AAA", "S", "SS", "SSS"]
TROPHIES = [
    # title, key, thresholds for C..SSS
    ("Commits", "commits", [10, 50, 100, 200, 500, 1000, 2000, 4000]),
    ("Contributions", "contributions", [20, 100, 250, 500, 1000, 2000, 4000, 8000]),
    ("Repositories", "repos", [1, 10, 20, 30, 50, 80, 100, 150]),
    ("Stars", "stars", [1, 10, 30, 50, 100, 200, 500, 1000]),
    ("Followers", "followers", [1, 10, 20, 50, 100, 200, 500, 1000]),
    ("Pull Requests", "prs", [1, 10, 20, 50, 100, 200, 500, 1000]),
    ("Issues", "issues", [1, 10, 20, 50, 100, 200, 500, 1000]),
    ("Experience", "years", [1, 2, 3, 4, 5, 7, 10, 15]),
]


def rank(value, thresholds):
    tier, nxt = "-", thresholds[0]
    for name, th in zip(TIERS, thresholds):
        if value >= th:
            tier = name
    idx = TIERS.index(tier) if tier != "-" else -1
    if idx + 1 < len(thresholds):
        lo = thresholds[idx] if idx >= 0 else 0
        nxt = thresholds[idx + 1]
        progress = (value - lo) / max(1, nxt - lo)
    else:
        progress = 1.0
    return tier, max(0.04, min(1.0, progress))


def trophies_card(data, t):
    cols, tw, th, gap, pad = 4, 190, 150, 16, 24
    width = pad * 2 + cols * tw + (cols - 1) * gap
    height = 70 + 2 * th + gap + pad
    r = 30
    circ = 2 * math.pi * r
    parts = [f'<text x="{pad}" y="44" font-size="20" font-weight="600" fill="{t["title"]}">Trophies</text>',
             f'<text x="{width - pad}" y="44" font-size="13" text-anchor="end" fill="{t["muted"]}">Ranked by GitHub activity</text>']
    for i, (title, key, ths) in enumerate(TROPHIES):
        value = data[key]
        tier, prog = rank(value, ths)
        color = t["tiers"][tier]
        x = pad + (i % cols) * (tw + gap)
        y = 66 + (i // cols) * (th + gap)
        cx, cy = x + tw / 2, y + 52
        unit = " yrs" if key == "years" else ""
        parts.append(f'''<g class="fade" style="animation-delay:{i * 0.08:.2f}s">
  <rect x="{x}" y="{y}" width="{tw}" height="{th}" rx="14" fill="{t['card']}" stroke="{t['border']}"/>
  <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{t['track']}" stroke-width="6"/>
  <circle class="ring" cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="6" stroke-linecap="round"
          stroke-dasharray="{circ:.1f}" stroke-dashoffset="{circ * (1 - prog):.1f}" transform="rotate(-90 {cx} {cy})"
          style="animation: ring{i} 1.2s cubic-bezier(.2,.8,.2,1) {0.3 + i * 0.08:.2f}s both"/>
  <text x="{cx}" y="{cy + 7}" font-size="{20 if len(tier) < 3 else 16}" font-weight="700" text-anchor="middle" fill="{color}">{esc(tier)}</text>
  <text x="{cx}" y="{y + 114}" font-size="14" font-weight="600" text-anchor="middle" fill="{t['text']}">{esc(title)}</text>
  <text x="{cx}" y="{y + 134}" font-size="12" text-anchor="middle" fill="{t['muted']}">{esc(fmt(value))}{unit}</text>
</g>''')
    style = "".join(
        f"@keyframes ring{i} {{ from {{ stroke-dashoffset: {circ:.1f}; }} }}\n" for i in range(len(TROPHIES)))
    return svg(width, height, "\n".join(parts), t, style)


# --------------------------------------------------------------------------- languages

IGNORED = {"HTML", "CSS", "SCSS", "Batchfile", "Blade", "Procfile", "Makefile", "Dockerfile", "EJS", "Handlebars"}


def languages_card(data, t):
    width, pad = 856, 24
    langs = sorted(((n, v) for n, v in data["languages"].items() if n not in IGNORED),
                   key=lambda kv: kv[1]["size"], reverse=True)
    top, rest = langs[:8], langs[8:]
    total = sum(v["size"] for _, v in langs) or 1
    items = [(n, v["size"] / total, v["color"]) for n, v in top]
    if rest:
        items.append(("Other", sum(v["size"] for _, v in rest) / total, "#8E8E93"))

    rows = math.ceil(len(items) / 3)
    height = 120 + rows * 30 + pad
    bar_y, bar_w, bar_h = 66, width - 2 * pad, 12
    parts = [f'<text x="{pad}" y="44" font-size="20" font-weight="600" fill="{t["title"]}">Languages</text>',
             f'<text x="{width - pad}" y="44" font-size="13" text-anchor="end" fill="{t["muted"]}">Share of code across {data["repos"]} repositories</text>',
             f'<clipPath id="barclip"><rect x="{pad}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="6"/></clipPath>',
             f'<rect x="{pad}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="6" fill="{t["track"]}"/>',
             f'<g clip-path="url(#barclip)"><g class="bar">']
    x = pad
    for name, share, color in items:
        w = share * bar_w
        parts.append(f'<rect x="{x:.2f}" y="{bar_y}" width="{w + 0.5:.2f}" height="{bar_h}" fill="{color}"/>')
        x += w
    parts.append("</g></g>")
    col_w = (width - 2 * pad) / 3
    for i, (name, share, color) in enumerate(items):
        lx = pad + (i % 3) * col_w
        ly = 116 + (i // 3) * 30
        parts.append(f'''<g class="fade" style="animation-delay:{0.5 + i * 0.06:.2f}s">
  <circle cx="{lx + 6}" cy="{ly - 5}" r="6" fill="{color}"/>
  <text x="{lx + 20}" y="{ly}" font-size="14" font-weight="500" fill="{t['text']}">{esc(name)}</text>
  <text x="{lx + col_w - 24}" y="{ly}" font-size="13" text-anchor="end" fill="{t['muted']}">{share * 100:.1f}%</text>
</g>''')
    style = (f".bar {{ transform-origin: {pad}px 0; animation: grow 1.4s cubic-bezier(.2,.8,.2,1) .2s both; }}\n"
             "@keyframes grow { from { transform: scaleX(0); } }")
    return svg(width, height, "\n".join(parts), t, style)


# --------------------------------------------------------------------------- 3D calendar

def days_label(n):
    return f"{n} day" if n == 1 else f"{n} days"


def streaks(days):
    best = cur = run = 0
    for d in days:
        run = run + 1 if d["contributionCount"] > 0 else 0
        best = max(best, run)
    today = dt.date.today().isoformat()
    for d in reversed(days):
        if d["date"] > today:
            continue
        if d["contributionCount"] > 0:
            cur += 1
        elif d["date"] != today:
            break
    return best, cur


def calendar_card(data, t):
    weeks = data["weeks"]
    width, height = 856, 460
    cw, ch, maxh = 9.0, 5.2, 56
    ox, oy = 24, 128

    counts = sorted(d["contributionCount"] for d in data["days"] if d["contributionCount"] > 0)
    peak = counts[-1] if counts else 1
    q = [counts[int(len(counts) * f)] if counts else 1 for f in (0.25, 0.5, 0.75)]

    def level(c):
        if c == 0:
            return 0
        return 1 + sum(c > v for v in q)

    def shade(hex_color, f):
        hc = hex_color.lstrip("#")
        rgb = [int(hc[i:i + 2], 16) for i in (0, 2, 4)]
        return "#" + "".join(f"{max(0, min(255, int(c * f))):02x}" for c in rgb)

    cubes = []
    for wi, week in enumerate(weeks):
        for d in week["contributionDays"]:
            di = d["weekday"]
            c = d["contributionCount"]
            h = 2 + (maxh * math.sqrt(c / peak) if c else 0)
            col = t["cal"][level(c)]
            x = ox + (wi - di) * cw + 7 * cw
            y = oy + (wi + di) * ch
            top = f"M{x:.1f},{y - h:.1f} l{cw:.1f},{-ch:.1f} l{cw:.1f},{ch:.1f} l{-cw:.1f},{ch:.1f} z"
            left = f"M{x:.1f},{y - h:.1f} l{cw:.1f},{ch:.1f} v{h:.1f} l{-cw:.1f},{-ch:.1f} z"
            right = f"M{x + cw:.1f},{y - h + ch:.1f} l{cw:.1f},{-ch:.1f} v{h:.1f} l{-cw:.1f},{ch:.1f} z"
            cubes.append((wi + di, wi, f'<path d="{top}" fill="{col}"/>'
                                       f'<path d="{left}" fill="{shade(col, 0.78)}"/>'
                                       f'<path d="{right}" fill="{shade(col, 0.6)}"/>'))
    # Draw back-to-front so nearer cubes overlap farther ones; fade in week by week.
    cubes.sort(key=lambda c: c[0])
    body = [f'<g class="fade" style="animation-delay:{wi * 0.018:.3f}s">{p}</g>' for _, wi, p in cubes]

    best, cur = streaks(data["days"])
    busiest = max(data["days"], key=lambda d: d["contributionCount"])
    active = sum(1 for d in data["days"] if d["contributionCount"] > 0)
    stats = [
        (fmt(data["year_total"]), "contributions in the last year"),
        (days_label(best), "longest streak"),
        (days_label(cur), "current streak"),
        (f"{busiest['contributionCount']}", f"busiest day · {dt.date.fromisoformat(busiest['date']).strftime('%b %-d')}"),
        (f"{active}", "active days"),
    ]
    sx, sy = 560, 40
    parts = [f'<text x="24" y="44" font-size="20" font-weight="600" fill="{t["title"]}">Contributions</text>']
    parts += body
    for i, (big, small) in enumerate(stats):
        yy = sy + 30 + i * 46
        parts.append(f'''<g class="fade" style="animation-delay:{0.6 + i * 0.1:.2f}s">
  <text x="{width - 24}" y="{yy}" font-size="22" font-weight="700" text-anchor="end" fill="{t['accent'] if i == 0 else t['text']}">{esc(big)}</text>
  <text x="{width - 24}" y="{yy + 17}" font-size="12" text-anchor="end" fill="{t['muted']}">{esc(small)}</text>
</g>''')
    # legend
    lx, ly = 24, height - 26
    parts.append(f'<text x="{lx}" y="{ly + 9}" font-size="11" fill="{t["muted"]}">Less</text>')
    for i, col in enumerate(t["cal"]):
        parts.append(f'<rect x="{lx + 32 + i * 16}" y="{ly}" width="11" height="11" rx="3" fill="{col}" stroke="{t["border"]}" stroke-width=".5"/>')
    parts.append(f'<text x="{lx + 32 + 5 * 16 + 4}" y="{ly + 9}" font-size="11" fill="{t["muted"]}">More</text>')
    return svg(width, height, "\n".join(parts), t)


# --------------------------------------------------------------------------- main

def main():
    if not TOKEN:
        sys.exit("GH_TOKEN is not set")
    data = fetch()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, t in THEMES.items():
        (OUT / f"trophies-{name}.svg").write_text(trophies_card(data, t))
        (OUT / f"languages-{name}.svg").write_text(languages_card(data, t))
        (OUT / f"calendar-{name}.svg").write_text(calendar_card(data, t))
    summary = {k: v for k, v in data.items() if k not in ("languages", "weeks", "days")}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
