"""Writes the README's animated diagrams, each in a light and a dark version.

    python3 docs/media/make_svgs.py

- architecture-{light,dark}.svg: one turn of a call travels a loop. Their words reach your
  screen along the top (Deepgram, then Ishara decides); yours reach their phone along the
  bottom (Groq, the fact-checker, Sarvam). Each stop lights as the light passes.
- steps-{light,dark}.svg: one call in six steps, lit one after another.
- cost-{light,dark}.svg: what one 10-minute call costs by human relay and by AI voice agent.

Plain SVG with CSS and SMIL animation and no script, so GitHub renders and animates it inside
<picture>. Motion follows a few rules: strong ease-out for things arriving, ease-in-out for
movement, linear only for constant motion, transform and opacity only, and no motion at all
under prefers-reduced-motion (every diagram reads fully when still). The figures in cost-*.svg
come from MARKET.md (S8, S9).
"""

from __future__ import annotations

import math
from pathlib import Path

FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, Helvetica, Arial, sans-serif"
EASE_OUT = "0.23 1 0.32 1"
EASE_IN_OUT = "0.77 0 0.175 1"
LINEAR = "0 0 1 1"

THEMES = {
    "light": dict(bg0="#FFFFFF", bg1="#F6F3FF", border="#E7E2F5", dot="#E4DEF3", card="#FFFFFF", cardline="#E6E1F2",
                  text="#17141F", muted="#6B6680", accent="#7C3AED", soft="#F1EBFF", green="#16A34A", track="#ECE8F6",
                  shadow="#2B1A66", shadow_op="0.10", chip="#F5F2FC"),
    "dark": dict(bg0="#0D0B17", bg1="#15112A", border="#2A2442", dot="#262040", card="#17142A", cardline="#2E2849",
                 text="#F2EEFF", muted="#A39CBF", accent="#A78BFA", soft="#2A2150", green="#4ADE80", track="#2A2442",
                 shadow="#000000", shadow_op="0.45", chip="#201B38"),
}

ICONS = {  # 24×24 strokes
    "phone": '<rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M11 18.5h2"/>',
    "handset": '<path d="M6.5 3.5h3l1.5 4.2-2 1.3a11 11 0 0 0 6 6l1.3-2 4.2 1.5v3a2 2 0 0 1-2.2 2A16.5 16.5 0 0 1 4.5 5.7a2 2 0 0 1 2-2.2z"/>',
    "spark": '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M18.5 15.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z"/>',
    "shield": '<path d="M12 3l7.5 3v5.5c0 4.6-3.2 8.5-7.5 9.5-4.3-1-7.5-4.9-7.5-9.5V6z"/><path d="M8.7 12.2l2.3 2.3 4.4-4.6"/>',
    "branch": '<circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="12" r="2.5"/><path d="M6 8.5v7M8.5 6h2a5 5 0 0 1 5 5M8.5 18h2a5 5 0 0 0 5-5"/>',
    "mic": '<rect x="9" y="2.5" width="6" height="11.5" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5v4"/>',
    "speaker": '<path d="M11 5L6.5 9H3.5v6h3L11 19z"/><path d="M15.5 9a4.5 4.5 0 0 1 0 6M18.5 6a8.5 8.5 0 0 1 0 12"/>',
}


def ic(name, x, y, size, color, width=2.0):
    return (f'<g transform="translate({x:.1f} {y:.1f}) scale({size / 24:.3f})" fill="none" stroke="{color}" '
            f'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</g>')


def glow_anim(dur, a, b, c, peak=1.0, first=False):
    """Opacity that lights fast (ease-out) as the light arrives and fades more gently."""
    if first:  # lit at the very start (and the very end) of the cycle
        return (f'<animate attributeName="opacity" dur="{dur}s" repeatCount="indefinite" calcMode="spline" '
                f'values="{peak};0;0;{peak}" keyTimes="0;0.07;0.96;1" keySplines="0.4 0 0.2 1;{LINEAR};{EASE_OUT}"/>')
    return (f'<animate attributeName="opacity" dur="{dur}s" repeatCount="indefinite" calcMode="spline" '
            f'values="0;0;{peak};0;0" keyTimes="0;{a:.3f};{b:.3f};{c:.3f};1" keySplines="{LINEAR};{EASE_OUT};0.4 0 0.2 1;{LINEAR}"/>')


def frame(t, w, h, title, eyebrow, extra_css=""):
    """The shared card: soft gradient, dot grid, rounded border, and the type and motion rules."""
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img">',
        f"<title>{title}</title>",
        f"<style>text{{font-family:{FONT}}}"
        f".t1{{font-size:19px;font-weight:700;fill:{t['text']}}}.t2{{font-size:15px;font-weight:650;fill:{t['text']}}}"
        f".s{{font-size:13px;fill:{t['muted']}}}.eye{{font-size:12px;font-weight:700;letter-spacing:.14em;fill:{t['muted']}}}"
        "@keyframes breathe{0%,100%{transform:scaleY(1)}50%{transform:scaleY(.7)}}"
        ".breathe{transform-box:fill-box;transform-origin:center;animation:breathe 1.6s cubic-bezier(.77,0,.175,1) infinite}"
        f"{extra_css}"
        "@media (prefers-reduced-motion:reduce){.mv{display:none}.breathe{animation:none}}</style>",
        f"""<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{t['bg0']}"/><stop offset="1" stop-color="{t['bg1']}"/></linearGradient>
<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1.1" fill="{t['dot']}"/></pattern>
<linearGradient id="mark" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#B07BFF"/><stop offset=".55" stop-color="#8B3DFF"/><stop offset="1" stop-color="#5B16D6"/></linearGradient>
<filter id="sh" x="-30%" y="-30%" width="160%" height="180%"><feDropShadow dx="0" dy="8" stdDeviation="12" flood-color="{t['shadow']}" flood-opacity="{t['shadow_op']}"/></filter>
<radialGradient id="halo"><stop offset="0" stop-color="{t['accent']}" stop-opacity=".35"/><stop offset="1" stop-color="{t['accent']}" stop-opacity="0"/></radialGradient>
</defs>""",
        f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="28" fill="url(#bg)" stroke="{t["border"]}"/>',
        f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="28" fill="url(#dots)"/>',
        f'<text class="eye" x="44" y="54">{eyebrow}</text>',
    ]


def mark(p, cx, cy, size):
    """Ishara's mark: four bars in a purple tile, breathing gently."""
    p.append(f'<circle cx="{cx}" cy="{cy}" r="{size * 0.95}" fill="url(#halo)"/>')
    p.append(f'<rect x="{cx - size / 2}" y="{cy - size / 2}" width="{size}" height="{size}" rx="{size * 0.27}" fill="url(#mark)" filter="url(#sh)"/>')
    bw, gap = size * 0.1, size * 0.07
    for i, h in enumerate([0.46, 0.7, 0.62, 0.38]):
        x = cx - (4 * bw + 3 * gap) / 2 + i * (bw + gap)
        p.append(f'<rect class="breathe" style="animation-delay:{i * 0.2:.1f}s" x="{x:.1f}" y="{cy - h * size / 2:.1f}" '
                 f'width="{bw:.1f}" height="{h * size:.1f}" rx="{bw / 2:.1f}" fill="#fff"/>')


# ---- architecture: one turn around the loop -----------------------------------------------------

ARCH_W, ARCH_H, LOOP_DUR = 1400, 700, 10


def architecture(t):
    p = frame(t, ARCH_W, ARCH_H, "One turn of an Ishara call travels a loop: the clinic's words reach the app through Deepgram and the Ishara backend; "
              "the user's words reach the clinic through Groq, the fact-checker and Sarvam", "ONE TURN OF A CALL")
    L, R, TOP, BOT = 300, 1100, 170, 530
    rad, mid = (BOT - TOP) / 2, (TOP + BOT) / 2
    loop = (f"M {R} {mid} A {rad} {rad} 0 0 0 {R - rad} {TOP} H {L + rad} A {rad} {rad} 0 0 0 {L + rad} {BOT} "
            f"H {R - rad} A {rad} {rad} 0 0 0 {R} {mid} Z")
    p.append(f'<path d="{loop}" fill="none" stroke="{t["track"]}" stroke-width="14"/>')
    p.append(f'<path d="{loop}" fill="none" stroke="{t["cardline"]}" stroke-width="1.5" stroke-dasharray="1 9" stroke-linecap="round"/>')
    quarter, straight, half = math.pi * rad / 2, R - L - 2 * rad, math.pi * rad
    total = 2 * quarter + 2 * straight + half

    def frac(x, top):
        return (quarter + (R - rad - x) if top else quarter + straight + half + (x - L - rad)) / total

    stops = [  # x, top?, icon, title, detail, colour
        (860, True, "mic", "Deepgram", "transcribes them", t["green"]),
        (620, True, "branch", "Ishara decides", "accept, answer, defer", t["green"]),
        (560, False, "spark", "Groq polishes", "your words, no new facts", t["accent"]),
        (720, False, "shield", "Fact-checker", "blocks invented facts", t["accent"]),
        (880, False, "speaker", "Sarvam speaks", "your line, over Plivo", t["accent"]),
    ]
    for x, top, name, title, detail, color in stops:
        y = TOP if top else BOT
        f = frac(x, top)
        a, b, c = max(0.001, f - 0.01), f + 0.005, min(0.999, f + 0.06)
        p.append(f'<circle class="mv" cx="{x}" cy="{y}" r="34" fill="{color}" opacity="0">{glow_anim(LOOP_DUR, a, b, c, peak=0.28)}</circle>')
        p.append(f'<circle cx="{x}" cy="{y}" r="26" fill="{t["card"]}" stroke="{color}" stroke-width="2.5" filter="url(#sh)"/>')
        p.append(ic(name, x - 12, y - 12, 24, color))
        ty = y - 52 if top else y + 52
        p.append(f'<text class="t2" x="{x}" y="{ty}" text-anchor="middle">{title}</text><text class="s" x="{x}" y="{ty + 18}" text-anchor="middle">{detail}</text>')
    # The two ends: the app and the clinic.
    for x, name, title, detail, f in [(L, "phone", "Ishara app", "2 s to step in", 0.5), (R, "handset", "Clinic", "any phone", 0.0)]:
        p.append(f'<rect x="{x - 48}" y="{mid - 48}" width="96" height="96" rx="26" fill="{t["card"]}" stroke="{t["cardline"]}" filter="url(#sh)"/>')
        p.append(f'<rect class="mv" x="{x - 48}" y="{mid - 48}" width="96" height="96" rx="26" fill="none" stroke="{t["accent"]}" stroke-width="3" opacity="0">'
                 f'{glow_anim(LOOP_DUR, 0.49, 0.505, 0.58, first=(f == 0))}</rect>')
        p.append(ic(name, x - 18, mid - 30, 36, t["accent"]))
        p.append(f'<text class="t2" x="{x}" y="{mid + 26}" text-anchor="middle">{title}</text><text class="s" x="{x}" y="{mid + 66}" text-anchor="middle">{detail}</text>')
    # The middle: the mark and the idea.
    mark(p, 700, mid - 28, 96)
    p.append(f'<text class="t1" x="700" y="{mid + 52}" text-anchor="middle">Their words reach your screen.</text>')
    p.append(f'<text class="t1" x="700" y="{mid + 78}" text-anchor="middle" style="fill:{t["accent"]}">Yours reach their phone.</text>')
    # The travelling light: green with their words, purple with yours.
    p.append(f'<circle class="mv" r="18" fill="url(#halo)"><animateMotion dur="{LOOP_DUR}s" repeatCount="indefinite" path="{loop}"/></circle>')
    p.append(f'<circle class="mv" r="8" fill="{t["green"]}"><animateMotion dur="{LOOP_DUR}s" repeatCount="indefinite" path="{loop}"/>'
             f'<animate attributeName="fill" dur="{LOOP_DUR}s" repeatCount="indefinite" calcMode="discrete" values="{t["green"]};{t["accent"]}" keyTimes="0;0.5"/></circle>')
    # The platform underneath, along the bottom edge.
    p.append(f'<text class="s" x="700" y="{ARCH_H - 40}" text-anchor="middle">Ishara backend: FastAPI on Heroku · Bolna runs the call: Deepgram, Sarvam, Plivo · '
             f'the app: SwiftUI, MediaPipe, the ASL model on device</text>')
    p.append("</svg>")
    return "\n".join(p) + "\n"


# ---- one call in six steps ----------------------------------------------------------------------

STEPS = [
    ("Type the request", ["The number, what it's about,", "and a PDF they might need"]),
    ("Ishara calls", ["It says who it is, then", "asks in its own words"]),
    ("Read every word", ["Both sides captioned,", "times pulled out for you"]),
    ("Ishara handles it", ["Each reply waits 2 s", "for you, then it is said"]),
    ("Step in any time", ["Tap, type or sign; polished", "and fact-checked, then said"]),
    ("The gist", ["What was agreed, quoted,", "with any follow-ups"]),
]
STEP_W, STEP_H, STEP_CYCLE, STEP_GAP = 1400, 340, 13.0, 1.8


def steps(t):
    n = len(STEPS)
    x0, x1, line_y = 160, 1240, 120
    xs = [x0 + i * (x1 - x0) / (n - 1) for i in range(n)]
    end = (n - 1) * STEP_GAP / STEP_CYCLE * 100
    css = (f"@keyframes prog{{0%{{transform:scaleX(0)}}{end:.1f}%{{transform:scaleX(1)}}92%{{transform:scaleX(1);opacity:1}}100%{{transform:scaleX(1);opacity:0}}}}"
           f".prog{{transform-box:fill-box;transform-origin:left;animation:prog {STEP_CYCLE}s linear infinite}}"
           f".st{{font-size:20px;font-weight:700;fill:{t['text']}}}.sd{{font-size:14.5px;fill:{t['muted']}}}.num{{font-size:17px;font-weight:700}}")
    for i in range(n):
        a = i * STEP_GAP / STEP_CYCLE * 100
        css += (f"@keyframes on{i}{{0%,{max(0, a - 0.1):.2f}%{{opacity:0}}{a + 2:.2f}%,92%{{opacity:1}}100%{{opacity:0}}}}"
                f".on{i}{{animation:on{i} {STEP_CYCLE}s cubic-bezier(.23,1,.32,1) infinite}}")
    # Still, every step is shown as reached.
    css += "@media (prefers-reduced-motion:reduce){.prog," + ",".join(f".on{i}" for i in range(n)) + "{animation:none;opacity:1;transform:none}}"
    p = frame(t, STEP_W, STEP_H, "One Ishara call in six steps: type the request, Ishara calls, read every word, Ishara handles it, step in any time, the gist",
              "ONE CALL, YOUR WAY", css)
    p.append(f'<line x1="{x0}" y1="{line_y}" x2="{x1}" y2="{line_y}" stroke="{t["track"]}" stroke-width="6" stroke-linecap="round"/>')
    p.append(f'<rect class="prog" x="{x0}" y="{line_y - 3}" width="{x1 - x0}" height="6" rx="3" fill="{t["accent"]}"/>')
    for i, (title, lines) in enumerate(STEPS):
        x = xs[i]
        p.append(f'<rect x="{x - 98}" y="{line_y + 40}" width="196" height="136" rx="18" fill="{t["card"]}" stroke="{t["cardline"]}" filter="url(#sh)"/>')
        p.append(f'<rect class="on{i}" x="{x - 98}" y="{line_y + 40}" width="196" height="136" rx="18" fill="{t["soft"]}" stroke="{t["accent"]}" stroke-width="2" opacity="0"/>')
        p.append(f'<circle cx="{x}" cy="{line_y}" r="20" fill="{t["card"]}" stroke="{t["cardline"]}" stroke-width="2"/>')
        p.append(f'<circle class="on{i}" cx="{x}" cy="{line_y}" r="20" fill="{t["accent"]}" opacity="0"/>')
        p.append(f'<text class="num" x="{x}" y="{line_y + 6}" text-anchor="middle" fill="{t["muted"]}">{i + 1}</text>')
        p.append(f'<text class="num on{i}" x="{x}" y="{line_y + 6}" text-anchor="middle" fill="#FFFFFF" opacity="0">{i + 1}</text>')
        p.append(f'<text class="st" x="{x}" y="{line_y + 80}" text-anchor="middle">{title}</text>')
        for j, line in enumerate(lines):
            p.append(f'<text class="sd" x="{x}" y="{line_y + 110 + j * 21}" text-anchor="middle">{line}</text>')
    p.append("</svg>")
    return "\n".join(p) + "\n"


# ---- the cost of one call ----------------------------------------------------------------------

COST_W, COST_H, COST_CYCLE = 1400, 620, 10.0
BASE, PER_DOLLAR = 500, 4.2


def cost(t):
    css = (f"@keyframes grow{{0%{{transform:scaleY(0.02)}}14%{{transform:scaleY(1)}}94%{{transform:scaleY(1);opacity:1}}100%{{transform:scaleY(1);opacity:0}}}}"
           f".g1{{transform-box:fill-box;transform-origin:bottom;animation:grow {COST_CYCLE}s cubic-bezier(.23,1,.32,1) infinite}}"
           f"@keyframes grow2{{0%,12%{{transform:scaleY(0.02)}}26%{{transform:scaleY(1)}}94%{{transform:scaleY(1);opacity:1}}100%{{transform:scaleY(1);opacity:0}}}}"
           f".g2{{transform-box:fill-box;transform-origin:bottom;animation:grow2 {COST_CYCLE}s cubic-bezier(.23,1,.32,1) infinite}}"
           f"@keyframes show{{0%,28%{{opacity:0}}34%,94%{{opacity:1}}100%{{opacity:0}}}}"
           f".show{{animation:show {COST_CYCLE}s cubic-bezier(.23,1,.32,1) infinite}}"
           f".big{{font-size:150px;font-weight:800;fill:{t['accent']};letter-spacing:-6px}}"
           f".val{{font-size:22px;font-weight:700;fill:{t['text']}}}.axis{{font-size:14px;fill:{t['muted']}}}"
           f".h2{{font-size:28px;font-weight:700;fill:{t['text']}}}"
           "@media (prefers-reduced-motion:reduce){.g1,.g2,.show{animation:none;opacity:1;transform:none}}")
    p = frame(t, COST_W, COST_H, "One 10-minute call: $40.70 to $80.60 through a human video relay, $0.60 through an AI voice agent; up to 99% less, every minute",
              "THE COST OF ONE CALL", css)
    p.append(f'<text class="h2" x="120" y="110">One 10-minute call</text>')
    for v in [0, 20, 40, 60, 80]:
        y = BASE - v * PER_DOLLAR
        p.append(f'<line x1="130" y1="{y}" x2="820" y2="{y}" stroke="{t["text"] if v == 0 else t["cardline"]}" stroke-width="{2 if v == 0 else 1}"/>')
        p.append(f'<text class="axis" x="118" y="{y + 5}" text-anchor="end">${v}</text>')
    low, high, ai = 40.70 * PER_DOLLAR, (80.60 - 40.70) * PER_DOLLAR, max(4, 0.60 * PER_DOLLAR)
    hx, ax, w = 260, 600, 170
    p.append(f'<rect class="g1" x="{hx}" y="{BASE - low}" width="{w}" height="{low}" rx="8" fill="{t["accent"]}"/>')
    p.append(f'<rect class="g2" x="{hx}" y="{BASE - low - high}" width="{w}" height="{high}" rx="8" fill="{t["accent"]}" fill-opacity=".35"/>')
    p.append(f'<rect class="g1" x="{ax}" y="{BASE - ai}" width="{w}" height="{ai}" rx="2" fill="{t["accent"]}"/>')
    p.append(f'<text class="val show" x="{hx + w / 2}" y="{BASE - low - high - 14}" text-anchor="middle">$40.70–$80.60</text>')
    p.append(f'<text class="val show" x="{ax + w / 2}" y="{BASE - 20}" text-anchor="middle" style="fill:{t["accent"]}">$0.60</text>')
    for x, title, sub in [(hx, "Human video relay", "$4.07–$8.06 a minute"), (ax, "AI voice agent", "from $0.06 a minute")]:
        p.append(f'<text class="t2" x="{x + w / 2}" y="{BASE + 34}" text-anchor="middle">{title}</text>')
        p.append(f'<text class="s" x="{x + w / 2}" y="{BASE + 56}" text-anchor="middle">{sub}</text>')
    p.append(f'<g class="show"><text class="big" x="900" y="300">99%</text>')
    p.append(f'<text class="h2" x="906" y="350">less, every minute</text>')
    p.append(f'<text class="s" x="906" y="380">Up to: ($8.06 − $0.06) ÷ $8.06, before telephony</text></g>')
    p.append("</svg>")
    return "\n".join(p) + "\n"


if __name__ == "__main__":
    here = Path(__file__).parent
    for name, theme in THEMES.items():
        (here / f"architecture-{name}.svg").write_text(architecture(theme))
        (here / f"steps-{name}.svg").write_text(steps(theme))
        (here / f"cost-{name}.svg").write_text(cost(theme))
    print("wrote architecture, steps and cost, light and dark")
