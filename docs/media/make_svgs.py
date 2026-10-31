"""Writes the README's animated diagrams, each in a light and a dark version.

    python3 docs/media/make_svgs.py

- architecture-{light,dark}.svg: the app, the backend, Bolna and the clinic's phone, with
  your words travelling out and theirs travelling back, lighting each part as they arrive.
- steps-{light,dark}.svg: one call in six steps, lit one after another.
- cost-{light,dark}.svg: what one 10-minute call costs with a human relay and with an AI agent.

Plain SVG with CSS animation and no script, so GitHub renders and animates it inside
<picture>. The figures in cost-*.svg come from MARKET.md (S8, S9).
"""

from __future__ import annotations

from pathlib import Path

FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
THEMES = {
    "light": {"zone": "#F6F8FA", "card": "#FFFFFF", "line": "#D0D7DE", "text": "#1F2328", "muted": "#59636E",
              "accent": "#8B3DFF", "soft": "#EFE6FF", "back": "#1A7F37", "track": "#E7E9EC", "chip": "#F3F4F6"},
    "dark": {"zone": "#0F141B", "card": "#161B22", "line": "#30363D", "text": "#E6EDF3", "muted": "#9198A1",
             "accent": "#A371F7", "soft": "#2A2142", "back": "#3FB950", "track": "#262C36", "chip": "#21262D"},
}


def base_css(t: dict[str, str]) -> list[str]:
    return [
        f"text{{font-family:{FONT}}}",
        f".zone{{font-size:13px;font-weight:700;letter-spacing:.12em;fill:{t['muted']}}}",
        f".title{{font-size:24px;font-weight:700;fill:{t['text']}}}",
        f".sub{{font-size:14px;fill:{t['muted']}}}",
        f".row{{font-size:16px;fill:{t['text']}}}",
        f".chip{{font-size:12.5px;font-weight:600;fill:{t['muted']}}}",
        f".lab{{font-size:12.5px;font-weight:700;fill:{t['muted']}}}",
    ]


def open_svg(w: int, h: int, title: str, css: list[str]) -> list[str]:
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img">',
            f"<title>{title}</title>", f"<style>{''.join(css)}</style>"]


def chips(x: float, y: float, names: list[str], t: dict[str, str]) -> list[str]:
    out, cx = [], x
    for name in names:
        w = 14 + 7.4 * len(name)
        out.append(f'<rect x="{cx}" y="{y}" width="{w}" height="26" rx="13" fill="{t["chip"]}" stroke="{t["line"]}"/>')
        out.append(f'<text class="chip" x="{cx + w / 2}" y="{y + 17.5}" text-anchor="middle">{name}</text>')
        cx += w + 8
    return out


# ---- icons (24×24 strokes, drawn at x, y) ---------------------------------------------------

def icon(kind: str, x: float, y: float, color: str) -> str:
    s = f'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
    paths = {
        "phone": f'<rect x="{x + 6}" y="{y + 2}" width="12" height="20" rx="3" {s}/><line x1="{x + 10}" y1="{y + 18}" x2="{x + 14}" y2="{y + 18}" {s}/>',
        "server": f'<rect x="{x + 3}" y="{y + 3}" width="18" height="7" rx="2" {s}/><rect x="{x + 3}" y="{y + 14}" width="18" height="7" rx="2" {s}/>'
                  f'<circle cx="{x + 7}" cy="{y + 6.5}" r="1" fill="{color}"/><circle cx="{x + 7}" cy="{y + 17.5}" r="1" fill="{color}"/>',
        "wave": "".join(f'<line x1="{x + 4 + i * 5}" y1="{y + 12 - h}" x2="{x + 4 + i * 5}" y2="{y + 12 + h}" {s}/>' for i, h in enumerate([4, 8, 6, 3])),
        "handset": f'<path d="M{x + 5} {y + 3} l4 0 l2 5 l-3 2 a12 12 0 0 0 6 6 l2 -3 l5 2 l0 4 a2 2 0 0 1 -2 2 a17 17 0 0 1 -16 -16 a2 2 0 0 1 2 -2" {s}/>',
    }
    return paths[kind]


# ---- architecture ---------------------------------------------------------------------------

ARCH_W, ARCH_H, CYCLE = 1400, 600, 9
LANE_OUT, LANE_BACK = 250, 430
CARDS = [  # x, width, icon, title, subtitle, rows, chips
    (40, 370, "phone", "Ishara app", "on the iPhone", [
        "Type the request, attach a PDF",
        "Both sides captioned, live",
        "Ishara's line: 2 s to change it",
        "Step in: type, or sign",
        "Live Activity on the lock screen",
    ], ["SwiftUI", "Vision", "PDFKit", "MediaPipe", "LiteRT"]),
    (500, 390, "server", "Ishara backend", "FastAPI on Heroku", [
        "Opens with your request, reworded",
        "Decides every turn: accept, answer, defer",
        "Quotes your documents, verbatim only",
        "Polishes your words: Groq gpt-oss-120b",
        "Fact-checker: no invented day, time, name",
    ], ["FastAPI", "Groq", "WebSocket"]),
    (980, 230, "wave", "Bolna", "voice agent", [
        "Deepgram listens",
        "Sarvam speaks",
        "Plivo connects",
    ], ["Deepgram", "Sarvam", "Plivo"]),
]
CLINIC = (1260, 110)
GAPS = [(410, 500, "WebSocket"), (890, 980, "custom LLM"), (1210, 1260, "call")]
CARD_TOP, CARD_H = 70, 470


def pulse(name: str, x0: float, x1: float, start: float, length: float) -> str:
    a, b = start / CYCLE * 100, (start + length) / CYCLE * 100
    return (f"@keyframes {name}{{0%,{a:.2f}%{{transform:translateX({x0}px);opacity:0}}{a + 0.8:.2f}%{{opacity:1}}"
            f"{b - 0.8:.2f}%{{opacity:1}}{b:.2f}%,100%{{transform:translateX({x1}px);opacity:0}}}}"
            f".{name}{{animation:{name} {CYCLE}s cubic-bezier(.45,0,.25,1) infinite}}")


def flash(name: str, at: float) -> str:
    a = at / CYCLE * 100
    return (f"@keyframes {name}{{0%,{max(0, a - 0.1):.2f}%{{opacity:0}}{a + 1:.2f}%{{opacity:1}}{a + 9:.2f}%,100%{{opacity:0}}}}"
            f".{name}{{animation:{name} {CYCLE}s linear infinite}}")


def architecture(t: dict[str, str]) -> str:
    css = base_css(t) + [
        f"@keyframes fill{{0%,10%{{transform:scaleX(0)}}32%{{transform:scaleX(1)}}36%,100%{{transform:scaleX(1);opacity:0}}}}",
        f".bar{{transform-box:fill-box;transform-origin:left;animation:fill {CYCLE / 3}s linear infinite}}",
        "@keyframes talk{0%,100%{transform:scaleY(.5)}50%{transform:scaleY(1)}}",
        ".w{transform-box:fill-box;transform-origin:center;animation:talk 1.1s ease-in-out infinite}",
    ]
    out_t = [(0.2, 0.9), (1.5, 0.9), (2.8, 0.6)]
    back_t = [(4.6, 0.6), (5.6, 0.9), (6.9, 0.9)]
    dots = []
    for i, ((x0, x1, _), (s, ln)) in enumerate(zip(GAPS, out_t)):
        css.append(pulse(f"o{i}", x0, x1 - 14, s, ln))
        dots.append(f'<circle class="o{i}" cx="7" cy="{LANE_OUT}" r="7" fill="{t["accent"]}"/>')
    for i, ((x0, x1, _), (s, ln)) in enumerate(zip(reversed(GAPS), back_t)):
        css.append(pulse(f"b{i}", x1 - 14, x0, s, ln))
        dots.append(f'<circle class="b{i}" cx="7" cy="{LANE_BACK}" r="7" fill="{t["back"]}"/>')
    # Each part lights as a pulse reaches it: out to the right, then back to the left.
    arrivals = {1: [out_t[0][0] + out_t[0][1], back_t[1][0] + back_t[1][1]], 2: [out_t[1][0] + out_t[1][1], back_t[0][0] + back_t[0][1]],
                3: [out_t[2][0] + out_t[2][1]], 0: [back_t[2][0] + back_t[2][1]]}
    for card, times in arrivals.items():
        for j, at in enumerate(times):
            css.append(flash(f"f{card}{j}", at))

    p = open_svg(ARCH_W, ARCH_H, "Ishara architecture: the Ishara app, the Ishara backend, Bolna and the clinic's phone", css)
    # Zones
    for x0, x1, label in [(20, 430, "ON THE IPHONE"), (480, 910, "ISHARA CLOUD"), (960, 1390, "THE PHONE NETWORK")]:
        p.append(f'<rect x="{x0}" y="20" width="{x1 - x0}" height="{ARCH_H - 40}" rx="26" fill="{t["zone"]}"/>')
        p.append(f'<text class="zone" x="{x0 + 22}" y="50">{label}</text>')
    # Lanes
    for x0, x1, label in GAPS:
        for y in (LANE_OUT, LANE_BACK):
            p.append(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="{t["line"]}" stroke-width="3" stroke-linecap="round"/>')
        p.append(f'<text class="lab" x="{(x0 + x1) / 2}" y="{LANE_OUT - 16}" text-anchor="middle">{label}</text>')
    # Cards
    for idx, (x, w, ic, title, sub, rows, tech) in enumerate(CARDS):
        p.append(f'<rect x="{x}" y="{CARD_TOP}" width="{w}" height="{CARD_H}" rx="20" fill="{t["card"]}" stroke="{t["line"]}" stroke-width="1.5"/>')
        for j in range(len(arrivals.get(idx, []))):
            p.append(f'<rect class="f{idx}{j}" x="{x}" y="{CARD_TOP}" width="{w}" height="{CARD_H}" rx="20" fill="none" stroke="{t["accent"]}" stroke-width="2.5" opacity="0"/>')
        p.append(f'<rect x="{x + 22}" y="{CARD_TOP + 22}" width="44" height="44" rx="12" fill="{t["soft"]}"/>')
        p.append(icon(ic, x + 32, CARD_TOP + 32, t["accent"]))
        p.append(f'<text class="title" x="{x + 80}" y="{CARD_TOP + 44}">{title}</text>')
        p.append(f'<text class="sub" x="{x + 80}" y="{CARD_TOP + 64}">{sub}</text>')
        step = 52 if len(rows) > 3 else 64
        for j, row in enumerate(rows):
            y = CARD_TOP + 118 + j * step
            p.append(f'<path d="M{x + 26} {y - 5} l4 4 l8 -9" fill="none" stroke="{t["accent"]}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>')
            p.append(f'<text class="row" x="{x + 48}" y="{y}">{row}</text>')
            if row.startswith("Ishara's line"):
                p.append(f'<rect x="{x + 48}" y="{y + 12}" width="190" height="5" rx="2.5" fill="{t["track"]}"/>')
                p.append(f'<rect class="bar" x="{x + 48}" y="{y + 12}" width="190" height="5" rx="2.5" fill="{t["accent"]}"/>')
        p.extend(chips(x + 22, CARD_TOP + CARD_H - 46, tech, t))
    # The clinic
    cx, cw = CLINIC
    top, height = LANE_OUT - 60, LANE_BACK - LANE_OUT + 120
    p.append(f'<rect x="{cx}" y="{top}" width="{cw}" height="{height}" rx="20" fill="{t["card"]}" stroke="{t["line"]}" stroke-width="1.5"/>')
    p.append(f'<rect class="f30" x="{cx}" y="{top}" width="{cw}" height="{height}" rx="20" fill="none" stroke="{t["accent"]}" stroke-width="2.5" opacity="0"/>')
    p.append(f'<rect x="{cx + cw / 2 - 22}" y="{top + 30}" width="44" height="44" rx="12" fill="{t["soft"]}"/>')
    p.append(icon("handset", cx + cw / 2 - 12, top + 40, t["accent"]))
    for i, h in enumerate([14, 26, 20, 10]):
        p.append(f'<rect class="w" style="animation-delay:{i * 0.15:.2f}s" x="{cx + 32 + i * 12}" y="{top + 120 - h / 2}" width="7" height="{h}" rx="3.5" fill="{t["accent"]}"/>')
    p.append(f'<text class="title" x="{cx + cw / 2}" y="{top + 180}" text-anchor="middle" style="font-size:20px">Clinic</text>')
    p.append(f'<text class="sub" x="{cx + cw / 2}" y="{top + 202}" text-anchor="middle">any phone</text>')
    p.append(f'<text class="sub" x="{cx + cw / 2}" y="{top + 220}" text-anchor="middle">no app</text>')
    # Legend
    p.append(f'<circle cx="490" cy="{ARCH_H - 2 + -18}" r="6" fill="{t["accent"]}"/><text class="lab" x="503" y="{ARCH_H - 16}">your words, out</text>')
    p.append(f'<circle cx="640" cy="{ARCH_H - 2 + -18}" r="6" fill="{t["back"]}"/><text class="lab" x="653" y="{ARCH_H - 16}">their words, back as captions</text>')
    p.extend(dots)
    p.append("</svg>")
    return "\n".join(p) + "\n"


# ---- one call in six steps ---------------------------------------------------------------------

STEPS = [
    ("Type the request", ["The number, what it's about,", "and a PDF they might need"]),
    ("Ishara calls", ["It says who it is, then", "asks in its own words"]),
    ("Read every word", ["Both sides captioned,", "times pulled out for you"]),
    ("Ishara handles it", ["Each reply waits 2 s", "for you, then it is said"]),
    ("Step in any time", ["Tap, type or sign; polished", "and fact-checked, then said"]),
    ("The gist", ["What was agreed, quoted,", "with any follow-ups"]),
]
STEP_W, STEP_H, STEP_CYCLE, STEP_GAP = 1400, 300, 13.0, 1.8


def steps(t: dict[str, str]) -> str:
    n = len(STEPS)
    x0, x1, line_y = 120, 1280, 80
    xs = [x0 + i * (x1 - x0) / (n - 1) for i in range(n)]
    end = (n - 1) * STEP_GAP / STEP_CYCLE * 100
    css = base_css(t) + [
        f"@keyframes prog{{0%{{transform:scaleX(0)}}{end:.1f}%{{transform:scaleX(1)}}92%{{transform:scaleX(1);opacity:1}}100%{{transform:scaleX(1);opacity:0}}}}",
        f".prog{{transform-box:fill-box;transform-origin:left;animation:prog {STEP_CYCLE}s linear infinite}}",
        f".st{{font-size:21px;font-weight:700;fill:{t['text']}}}",
        f".sd{{font-size:15.5px;fill:{t['muted']}}}",
        f".num{{font-size:17px;font-weight:700}}",
    ]
    for i in range(n):
        a = i * STEP_GAP / STEP_CYCLE * 100
        css.append(f"@keyframes on{i}{{0%,{max(0, a - 0.1):.2f}%{{opacity:0}}{a + 1.5:.2f}%,92%{{opacity:1}}100%{{opacity:0}}}}"
                   f".on{i}{{animation:on{i} {STEP_CYCLE}s ease-out infinite}}")
    p = open_svg(STEP_W, STEP_H, "One Ishara call in six steps", css)
    p.append(f'<line x1="{x0}" y1="{line_y}" x2="{x1}" y2="{line_y}" stroke="{t["track"]}" stroke-width="6" stroke-linecap="round"/>')
    p.append(f'<rect class="prog" x="{x0}" y="{line_y - 3}" width="{x1 - x0}" height="6" rx="3" fill="{t["accent"]}"/>')
    for i, (title, lines) in enumerate(STEPS):
        x = xs[i]
        # Card under each step; it lights when the step is reached.
        p.append(f'<rect x="{x - 105}" y="{line_y + 40}" width="210" height="140" rx="16" fill="{t["card"]}" stroke="{t["line"]}" stroke-width="1.5"/>')
        p.append(f'<rect class="on{i}" x="{x - 105}" y="{line_y + 40}" width="210" height="140" rx="16" fill="{t["soft"]}" stroke="{t["accent"]}" stroke-width="2" opacity="0"/>')
        p.append(f'<circle cx="{x}" cy="{line_y}" r="20" fill="{t["card"]}" stroke="{t["line"]}" stroke-width="2"/>')
        p.append(f'<circle class="on{i}" cx="{x}" cy="{line_y}" r="20" fill="{t["accent"]}" opacity="0"/>')
        p.append(f'<text class="num" x="{x}" y="{line_y + 6}" text-anchor="middle" fill="{t["muted"]}">{i + 1}</text>')
        p.append(f'<text class="num on{i}" x="{x}" y="{line_y + 6}" text-anchor="middle" fill="#FFFFFF" opacity="0">{i + 1}</text>')
        p.append(f'<text class="st" x="{x}" y="{line_y + 82}" text-anchor="middle">{title}</text>')
        for j, line in enumerate(lines):
            p.append(f'<text class="sd" x="{x}" y="{line_y + 112 + j * 22}" text-anchor="middle">{line}</text>')
    p.append("</svg>")
    return "\n".join(p) + "\n"


# ---- the cost of one call ------------------------------------------------------------------------

COST_W, COST_H, COST_CYCLE = 1400, 570, 10.0
BASE, PER_DOLLAR = 470, 4.2


def cost(t: dict[str, str]) -> str:
    css = base_css(t) + [
        f"@keyframes grow{{0%{{transform:scaleY(0)}}14%{{transform:scaleY(1)}}94%{{transform:scaleY(1);opacity:1}}100%{{transform:scaleY(1);opacity:0}}}}",
        f".g1{{transform-box:fill-box;transform-origin:bottom;animation:grow {COST_CYCLE}s cubic-bezier(.2,.8,.2,1) infinite}}",
        f"@keyframes grow2{{0%,12%{{transform:scaleY(0)}}26%{{transform:scaleY(1)}}94%{{transform:scaleY(1);opacity:1}}100%{{transform:scaleY(1);opacity:0}}}}",
        f".g2{{transform-box:fill-box;transform-origin:bottom;animation:grow2 {COST_CYCLE}s cubic-bezier(.2,.8,.2,1) infinite}}",
        f"@keyframes show{{0%,28%{{opacity:0}}34%,94%{{opacity:1}}100%{{opacity:0}}}}",
        f".show{{animation:show {COST_CYCLE}s ease-out infinite}}",
        f".big{{font-size:150px;font-weight:800;fill:{t['accent']};letter-spacing:-6px}}",
        f".val{{font-size:22px;font-weight:700;fill:{t['text']}}}",
        f".axis{{font-size:14px;fill:{t['muted']}}}",
        f".h2{{font-size:28px;font-weight:700;fill:{t['text']}}}",
    ]
    p = open_svg(COST_W, COST_H, "One 10-minute call: $40.70 to $80.60 with a human relay, $0.60 with an AI voice agent", css)
    p.append(f'<text class="h2" x="120" y="50">One 10-minute call</text>')
    for v in [0, 20, 40, 60, 80]:
        y = BASE - v * PER_DOLLAR
        p.append(f'<line x1="130" y1="{y}" x2="820" y2="{y}" stroke="{t["text"] if v == 0 else t["line"]}" stroke-width="{2 if v == 0 else 1}"/>')
        p.append(f'<text class="axis" x="118" y="{y + 5}" text-anchor="end">${v}</text>')
    low, high, ai = 40.70 * PER_DOLLAR, (80.60 - 40.70) * PER_DOLLAR, max(4, 0.60 * PER_DOLLAR)
    hx, ax, w = 260, 600, 170
    p.append(f'<rect class="g1" x="{hx}" y="{BASE - low}" width="{w}" height="{low}" rx="8" fill="{t["accent"]}"/>')
    p.append(f'<rect class="g2" x="{hx}" y="{BASE - low - high}" width="{w}" height="{high}" rx="8" fill="{t["accent"]}" fill-opacity=".35"/>')
    p.append(f'<rect class="g1" x="{ax}" y="{BASE - ai}" width="{w}" height="{ai}" rx="2" fill="{t["accent"]}"/>')
    p.append(f'<text class="val show" x="{hx + w / 2}" y="{BASE - low - high - 14}" text-anchor="middle">$40.70–$80.60</text>')
    p.append(f'<text class="val show" x="{ax + w / 2}" y="{BASE - 20}" text-anchor="middle" style="fill:{t["accent"]}">$0.60</text>')
    for x, title, sub in [(hx, "Human video relay", "$4.07–$8.06 a minute"), (ax, "AI voice agent", "from $0.06 a minute")]:
        p.append(f'<text class="row" x="{x + w / 2}" y="{BASE + 34}" text-anchor="middle" style="font-weight:700">{title}</text>')
        p.append(f'<text class="sub" x="{x + w / 2}" y="{BASE + 56}" text-anchor="middle">{sub}</text>')
    p.append(f'<g class="show"><text class="big" x="900" y="270">99%</text>')
    p.append(f'<text class="h2" x="906" y="320">less, every minute</text>')
    p.append(f'<text class="sub" x="906" y="350">Up to: ($8.06 − $0.06) ÷ $8.06, before telephony</text></g>')
    p.append("</svg>")
    return "\n".join(p) + "\n"


if __name__ == "__main__":
    here = Path(__file__).parent
    for name, theme in THEMES.items():
        (here / f"architecture-{name}.svg").write_text(architecture(theme))
        (here / f"steps-{name}.svg").write_text(steps(theme))
        (here / f"cost-{name}.svg").write_text(cost(theme))
    print("wrote architecture, steps and cost, light and dark")
