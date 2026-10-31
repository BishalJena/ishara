"""Writes the README's animated architecture diagram, light and dark.

    python3 docs/media/architecture.py   # writes architecture-light.svg and architecture-dark.svg

Plain SVG with CSS animation (no script), so GitHub renders and animates it inside
<picture>. A request travels from the app through the backend and Bolna to the clinic;
the clinic's words travel back as captions. The 2-second bar fills in the app.
"""

from __future__ import annotations

from pathlib import Path

W, H = 1380, 560
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
THEMES = {
    "light": {"box": "#F6F8FA", "line": "#D0D7DE", "text": "#1F2328", "muted": "#59636E", "accent": "#8B3DFF",
              "back": "#1A7F37", "track": "#E7E9EC"},
    "dark": {"box": "#161B22", "line": "#30363D", "text": "#E6EDF3", "muted": "#9198A1", "accent": "#A371F7",
             "back": "#3FB950", "track": "#262C36"},
}
CYCLE = 9  # seconds for one request out and one reply back

# Columns: x, width, title, subtitle, rows of (headline, detail)
BOXES = [
    (30, 330, "Ishara app", "iPhone · SwiftUI", [
        ("Your request, typed", "plus photos or PDFs, read on the phone"),
        ("Both sides, captioned", "times and dates pulled out as you read"),
        ("Ishara's next line", "2 s to change it, or it is said"),
        ("Step in: type or sign", "MediaPipe + ASL model, on device"),
    ]),
    (470, 370, "Ishara backend", "FastAPI on Heroku", [
        ("Opens with your request", "reworded, never read out raw"),
        ("Decides every turn", "accept, answer from your files, or defer"),
        ("Polishes your words", "Groq · gpt-oss-120b"),
        ("Fact-checker", "no invented day, time, number or name"),
    ]),
    (950, 250, "Bolna", "voice agent · custom LLM", [
        ("Deepgram", "listens"),
        ("Sarvam Bulbul", "speaks"),
        ("Plivo", "connects the line"),
    ]),
]
CLINIC = (1290, 70)  # x, width
LINKS = [  # gap between boxes: x from, x to, label
    (360, 470, "WebSocket"),
    (840, 950, "custom LLM"),
    (1200, 1290, "phone call"),
]
TOP, BOX_H = 60, 440
OUT_Y, BACK_Y = 235, 395


def dot_css(name: str, x0: float, x1: float, start: float, length: float) -> str:
    a, b = start / CYCLE * 100, (start + length) / CYCLE * 100
    return (
        f"@keyframes {name}{{0%,{a:.2f}%{{transform:translateX({x0}px);opacity:0}}"
        f"{a + 0.6:.2f}%{{opacity:1}}{b - 0.6:.2f}%{{opacity:1}}"
        f"{b:.2f}%,100%{{transform:translateX({x1}px);opacity:0}}}}"
        f".{name}{{animation:{name} {CYCLE}s cubic-bezier(.45,0,.25,1) infinite}}"
    )


def svg(theme: dict[str, str]) -> str:
    t = theme
    css = [
        f"text{{font-family:{FONT}}}",
        f".h{{font-size:17px;font-weight:600;fill:{t['text']}}}",
        f".d{{font-size:13.5px;fill:{t['muted']}}}",
        f".title{{font-size:22px;font-weight:700;fill:{t['text']}}}",
        f".sub{{font-size:13px;fill:{t['muted']}}}",
        f".lab{{font-size:12.5px;font-weight:600;fill:{t['muted']}}}",
        f"@keyframes fill{{0%,8%{{transform:scaleX(0)}}30%{{transform:scaleX(1)}}34%,100%{{transform:scaleX(1);opacity:0}}}}",
        f".bar{{transform-box:fill-box;transform-origin:left;animation:fill {CYCLE / 3}s linear infinite}}",
        f"@keyframes talk{{0%,100%{{transform:scaleY(.55)}}50%{{transform:scaleY(1)}}}}",
        ".w{transform-box:fill-box;transform-origin:center;animation:talk 1.1s ease-in-out infinite}",
    ]
    out: list[str] = []
    # Request out: app → backend → Bolna → clinic. Reply back: clinic → Bolna → backend → app.
    timing_out = [(0.0, 0.9), (1.6, 0.9), (3.0, 0.8)]
    timing_back = [(4.6, 0.8), (5.8, 0.9), (7.2, 0.9)]
    for i, ((x0, x1, _), (start, length)) in enumerate(zip(LINKS, timing_out)):
        css.append(dot_css(f"o{i}", x0, x1 - 14, start, length))
        out.append(f'<circle class="o{i}" cx="7" cy="{OUT_Y}" r="7" fill="{t["accent"]}"/>')
    for i, ((x0, x1, _), (start, length)) in enumerate(zip(reversed(LINKS), timing_back)):
        css.append(dot_css(f"b{i}", x1 - 14, x0, start, length))
        out.append(f'<circle class="b{i}" cx="7" cy="{BACK_Y}" r="7" fill="{t["back"]}"/>')

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img">',
             f"<title>Ishara architecture: the app, the Ishara backend, Bolna and the clinic's phone</title>",
             f"<style>{''.join(css)}</style>"]
    # Links: two tracks per gap, labels above.
    for x0, x1, label in LINKS:
        parts.append(f'<text class="lab" x="{(x0 + x1) / 2}" y="{OUT_Y - 22}" text-anchor="middle">{label}</text>')
        for y in (OUT_Y, BACK_Y):
            parts.append(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="{t["line"]}" stroke-width="3" stroke-linecap="round"/>')
    parts.append(f'<text class="lab" x="{(LINKS[0][0] + LINKS[0][1]) / 2}" y="{BACK_Y + 30}" text-anchor="middle">captions</text>')
    parts.append(f'<text class="lab" x="{(LINKS[1][0] + LINKS[1][1]) / 2}" y="{BACK_Y + 30}" text-anchor="middle">transcript</text>')
    parts.append(f'<text class="lab" x="{(LINKS[2][0] + LINKS[2][1]) / 2}" y="{BACK_Y + 30}" text-anchor="middle">their voice</text>')

    for x, w, title, sub, rows in BOXES:
        parts.append(f'<rect x="{x}" y="{TOP}" width="{w}" height="{BOX_H}" rx="22" fill="{t["box"]}" stroke="{t["line"]}" stroke-width="1.5"/>')
        parts.append(f'<text class="title" x="{x + 24}" y="{TOP + 42}">{title}</text>')
        parts.append(f'<text class="sub" x="{x + 24}" y="{TOP + 64}">{sub}</text>')
        step = (BOX_H - 110) / len(rows)
        for i, (head, detail) in enumerate(rows):
            y = TOP + 112 + i * step
            parts.append(f'<circle cx="{x + 30}" cy="{y - 5}" r="4" fill="{t["accent"]}"/>')
            parts.append(f'<text class="h" x="{x + 44}" y="{y}">{head}</text>')
            parts.append(f'<text class="d" x="{x + 44}" y="{y + 21}">{detail}</text>')
            if title == "Ishara app" and head.startswith("Ishara's next line"):
                bx, by = x + 44, y + 32
                parts.append(f'<rect x="{bx}" y="{by}" width="200" height="6" rx="3" fill="{t["track"]}"/>')
                parts.append(f'<rect class="bar" x="{bx}" y="{by}" width="200" height="6" rx="3" fill="{t["accent"]}"/>')

    # The clinic: a phone with a talking waveform.
    cx, cw = CLINIC
    parts.append(f'<rect x="{cx}" y="{OUT_Y - 45}" width="{cw}" height="{BACK_Y - OUT_Y + 90}" rx="18" fill="{t["box"]}" stroke="{t["line"]}" stroke-width="1.5"/>')
    for i, h in enumerate([18, 30, 24, 14]):
        bx = cx + 17 + i * 10
        parts.append(f'<rect class="w" style="animation-delay:{i * 0.15:.2f}s" x="{bx}" y="{OUT_Y + 40 - h / 2}" width="6" height="{h}" rx="3" fill="{t["accent"]}"/>')
    parts.append(f'<text class="h" x="{cx + cw / 2}" y="{OUT_Y + 100}" text-anchor="middle">Clinic</text>')
    parts.append(f'<text class="d" x="{cx + cw / 2}" y="{OUT_Y + 122}" text-anchor="middle">any phone</text>')
    parts.append(f'<text class="d" x="{cx + cw / 2}" y="{OUT_Y + 140}" text-anchor="middle">no app</text>')

    parts.extend(out)
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    here = Path(__file__).parent
    for name, theme in THEMES.items():
        (here / f"architecture-{name}.svg").write_text(svg(theme))
    print("wrote architecture-light.svg and architecture-dark.svg")
