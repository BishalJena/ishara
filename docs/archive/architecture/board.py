"""Writes the architecture board: ishara-board.excalidraw (editable) and ishara-board.svg, from
one description below, so the two never drift. Render the PNG from the SVG:

    python3 docs/archive/architecture/board.py
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new \
      --force-device-scale-factor=2 --window-size=1840,2260 --default-background-color=ffffffff \
      --screenshot=docs/archive/architecture/ishara-board.png docs/archive/architecture/ishara-board.svg

Without Chrome, macOS Quick Look works too: it renders a square thumbnail, so pad the SVG to a
2260 x 2260 viewBox (`viewBox="-210 0 2260 2260"`, white background), run
`qlmanage -t -s 4520 -o /tmp <padded.svg>`, then `sips -c 4520 3680` the result (centre crop).

Edit the content here, not in Excalidraw, or the next run overwrites the edits.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
WIDTH, HEIGHT = 1840, 2260
INK = "#1e1e1e"
MUTED = "#495057"
FILL = {
    "phone": "#a5d8ff", "backend": "#ffec99", "bolna": "#d0bfff", "person": "#e9ecef",
    "you": "#b2f2bb", "stop": "#ffc9c9", "out": "#96f2d7", "mac": "#dee2e6", "none": "transparent",
}
CHAR = 0.53  # Helvetica: average glyph width / font size, for the overflow check


@dataclass
class Shape:
    id: str
    kind: str  # rectangle | ellipse | diamond
    x: float
    y: float
    w: float
    h: float
    text: str
    fill: str
    size: int = 16
    align: str = "center"
    dashed: bool = False
    stroke: str = INK


@dataclass
class Text:
    id: str
    x: float
    y: float
    text: str
    size: int = 16
    bold: bool = False
    color: str = INK
    anchor: str = "start"


@dataclass
class Arrow:
    id: str
    points: list[tuple[float, float]]
    dashed: bool = False
    label: str | None = None
    label_at: tuple[float, float] | None = None


@dataclass
class Board:
    shapes: list[Shape] = field(default_factory=list)
    texts: list[Text] = field(default_factory=list)
    arrows: list[Arrow] = field(default_factory=list)

    def box(self, id, x, y, w, h, text, fill="phone", kind="rectangle", **kw) -> Shape:
        shape = Shape(id, kind, x, y, w, h, text, FILL[fill], **kw)
        self.shapes.append(shape)
        return shape

    def text(self, id, x, y, text, **kw) -> None:
        self.texts.append(Text(id, x, y, text, **kw))

    def arrow(self, id, *points, **kw) -> None:
        self.arrows.append(Arrow(id, list(points), **kw))

    def link(self, id, a: Shape, b: Shape, side: str = "x", **kw) -> None:
        """Straight arrow between two shapes' facing edges (side x: left/right, y: top/bottom)."""
        if side == "x":
            start = (a.x + a.w, a.y + a.h / 2) if b.x > a.x else (a.x, a.y + a.h / 2)
            end = (b.x, b.y + b.h / 2) if b.x > a.x else (b.x + b.w, b.y + b.h / 2)
        else:
            start = (a.x + a.w / 2, a.y + a.h) if b.y > a.y else (a.x + a.w / 2, a.y)
            end = (b.x + b.w / 2, b.y) if b.y > a.y else (b.x + b.w / 2, b.y + b.h)
        self.arrow(id, start, end, **kw)

    def check(self) -> list[str]:
        problems = []
        for s in self.shapes:
            room = s.w * (0.62 if s.kind == "diamond" else 0.8 if s.kind == "ellipse" else 0.92)
            for line in s.text.split("\n"):
                if len(line) * CHAR * s.size > room:
                    problems.append(f"{s.id}: '{line}' is too wide for {s.w:.0f}")
            if len(s.text.split("\n")) * s.size * 1.25 > s.h * (0.7 if s.kind != "rectangle" else 0.95):
                problems.append(f"{s.id}: too many lines for {s.h:.0f}")
        return problems


def build() -> Board:
    b = Board()
    b.text("title", 40, 30, "Ishara: sign what you need, approve it, and the call is made for you", size=34, bold=True)
    b.text("subtitle", 40, 78, "Architecture as of 28 October 2026 (decisions D1, D8, D9 in PLAN.md). "
           "Blue runs on the iPhone, yellow on our backend, purple at Bolna, green is the user's own action.",
           size=16, color=MUTED)

    # ---- 1. Live call ----
    b.text("s1", 40, 130, "1. Live call: you sign each reply; it is spoken only after you tap SEND", size=22, bold=True)
    w, h, y, gap = 180, 110, 175, 42
    xs = [40 + i * (w + gap) for i in range(8)]
    you = b.box("l-you", xs[0], y, w, h, "You\n(Deaf or\nnonspeaking signer)", "person", kind="ellipse", size=14)
    cam = b.box("l-cam", xs[1], y, w, h, "Front camera +\nMediaPipe Holistic\nlandmarks")
    model = b.box("l-model", xs[2], y, w, h, "ASL Signs model\n250 signs, used\nas is (LiteRT)")
    rule = b.box("l-rule", xs[3], y, w, h, "Open-set rule (3)\nchip · did you\nmean? · [?]")
    draft = b.box("l-draft", xs[4], y, w, h, "Draft sentence\nGroq + validator,\ntemplate fallback", "backend")
    send = b.box("l-send", xs[5], y, w, h, "You check the\ndraft and\ntap SEND", "you")
    voice = b.box("l-voice", xs[6], y, w, h, "Bolna speaks the\nexact text\n(Sarvam voice)", "bolna")
    rec = b.box("l-rec", xs[7], y, w, h, "Receptionist\n(any phone)", "person", kind="ellipse")
    for i, (a, c) in enumerate(zip([you, cam, model, rule, draft, send, voice], [cam, model, rule, draft, send, voice, rec])):
        b.link(f"l-a{i}", a, c)
    asr = b.box("l-asr", xs[6], y + 170, w, 80, "Deepgram transcript\n(Bolna)", "bolna")
    cap = b.box("l-cap", xs[3], y + 170, w * 2 + gap, 80, "Captions in the app: what they said,\nand what was spoken for you", "out")
    b.arrow("l-r1", (rec.x + rec.w / 2, rec.y + rec.h), (rec.x + rec.w / 2, asr.y + 40), (asr.x + asr.w, asr.y + 40))
    b.link("l-r2", asr, cap)
    b.arrow("l-r3", (cap.x, cap.y + 40), (you.x + you.w / 2, cap.y + 40), (you.x + you.w / 2, you.y + you.h))
    b.text("l-note", xs[0], y + 262, "Bonus (Path A): your own Phone call with Apple's Add Audio in Calls "
           "plays the approved sentence; no captions in the app.", size=14, color=MUTED)

    # ---- 2. Call for me ----
    b.text("s2", 40, 490, "2. Call for me: you approve a brief once; the agent makes the call and brings back notes",
           size=22, bold=True)
    y2 = 535
    you2 = b.box("d-you", xs[0], y2, w, h, "You", "person", kind="ellipse")
    ask = b.box("d-req", xs[1], y2, w, h, "Sign or tap what\nyou need, e.g.\nTOMORROW + name", "you", size=15)
    brief = b.box("d-brief", xs[2], y2, w, h, "Brief built from\nexactly that\n(nothing added)", "backend")
    ok = b.box("d-ok", xs[3], y2, w, h, "You approve it\nonce: stay to\nanswer, or not", "you")
    calls = b.box("d-call", xs[4], y2, w, h, "Bolna agent calls,\nsays who it calls\nfor, then the brief", "bolna", size=15)
    brain = b.box("d-brain", xs[5], y2, w, h, "Agent follows only\nthe brief; every\nline is checked", "backend", size=15)
    rec2 = b.box("d-rec", xs[7], y2, w, h, "Receptionist", "person", kind="ellipse")
    for i, (a, c) in enumerate(zip([you2, ask, brief, ok, calls], [ask, brief, ok, calls, brain])):
        b.link(f"d-a{i}", a, c)
    b.arrow("d-talk", (brain.x + brain.w, brain.y + 40), (rec2.x, rec2.y + 40))
    b.arrow("d-hear", (rec2.x, rec2.y + 72), (brain.x + brain.w, brain.y + 72))
    b.text("d-talk-l", brain.x + brain.w + 14, brain.y + 18, "speaks and listens", size=14, color=MUTED)
    decide = b.box("d-dec", xs[5], y2 + 165, w, 120, "A decision\nthat is yours", "none", kind="diamond")
    b.link("d-a5", brain, decide, side="y")
    att = b.box("d-att", xs[3] - 20, y2 + 330, w * 2 + gap + 40, 90,
                "Stayed: \"one moment\"; the app asks YES / NO /\nWAIT, or a time word for \"when?\"; sign or\ntap (no answer in 10 s: it will call back)", "you", size=15)
    un = b.box("d-un", xs[6], y2 + 330, w + 40, 90, "Left it (unattended):\n\"I'll check and call\nback\", then hangs up", "stop", size=15)
    b.arrow("d-a6", (decide.x, decide.y + 60), (att.x + att.w / 2, decide.y + 60), (att.x + att.w / 2, att.y))
    b.arrow("d-a7", (decide.x + decide.w, decide.y + 60), (un.x + un.w / 2, decide.y + 60), (un.x + un.w / 2, un.y))
    b.text("d-stay", att.x + att.w / 2 + 10, decide.y + 70, "you stayed", size=14, color=MUTED)
    b.text("d-left", un.x + un.w / 2 + 10, decide.y + 70, "you left it", size=14, color=MUTED)
    notes = b.box("d-notes", xs[0], y2 + 330, w * 2 + gap - 20, 90,
                  "Notes after the call: outcome,\nwhat they offered, open questions,\nthe full transcript", "out", size=15)
    b.link("d-a8", att, notes)
    b.arrow("d-a9", (un.x + un.w / 2, un.y + un.h), (un.x + un.w / 2, un.y + un.h + 34),
            (notes.x + notes.w / 2, un.y + un.h + 34), (notes.x + notes.w / 2, notes.y + notes.h))

    # ---- 3. Recognition rule ----
    y3 = 1075
    b.text("s3", 40, y3, "3. How a sign becomes a chip (on the phone, nothing uploaded)", size=22, bold=True)
    y3b = y3 + 50
    ends = b.box("r-end", 40, y3b, 200, 100, "The sign ends:\nhands back at\nrest for ~0.4 s")
    soft = b.box("r-soft", 290, y3b, 220, 100, "All 250 signs scored;\nnever narrowed to\nour words first")
    inv = b.box("r-inv", 560, y3b - 10, 210, 120, "Top sign one\nof our words?", "none", kind="diamond", size=15)
    conf = b.box("r-conf", 830, y3b - 10, 220, 120, "p ≥ cut-off\n(0.45–0.65), 0.3\nahead of next?", "none", kind="diamond", size=15)
    chip = b.box("r-chip", 1110, y3b, 200, 100, "Chip\n(can still be\nremoved with ✕)", "you")
    maybe = b.box("r-maybe", 830, y3b + 170, 220, 90, "p ≥ 0.35: \"Did you mean\nTOMORROW?\" counts\nonly if tapped", "phone", size=15)
    unsure = b.box("r-unsure", 560, y3b + 170, 210, 90, "[?] nothing is\nspoken; sign again", "stop")
    b.link("r-a1", ends, soft)
    b.link("r-a2", soft, inv)
    b.link("r-a3", inv, conf)
    b.link("r-a4", conf, chip)
    b.link("r-a5", inv, unsure, side="y")
    b.link("r-a6", conf, maybe, side="y")
    b.arrow("r-a7", (maybe.x, maybe.y + 45), (unsure.x + unsure.w, unsure.y + 45))
    b.text("r-l1", 780, y3b + 22, "yes", size=14, color=MUTED)
    b.text("r-l2", 1058, y3b + 22, "yes", size=14, color=MUTED)
    b.text("r-l3", 672, y3b + 125, "no", size=14, color=MUTED)
    b.text("r-l4", 948, y3b + 125, "no", size=14, color=MUTED)
    b.text("r-l5", 778, y3b + 186, "below", size=14, color=MUTED)
    b.box("r-side", 1370, y3b, 430, 260,
          "Also on the phone\n\n• A hand left the picture during or as the\n   sign ends: [?] with a framing hint\n"
          "• A signed answer the agent's question\n   offers (YES, TOMORROW, ...) answers it\n"
          "• 8 chip words: hello, thank you, yes,\n   no, now, please, tomorrow, wait\n   (morning: iPhone test pending)",
          "none", size=15, align="left", dashed=True)

    # ---- 4. Where each piece runs ----
    y4 = 1470
    b.text("s4", 40, y4, "4. Where each piece runs", size=22, bold=True)
    cols = [
        ("w-phone", "phone", "iPhone app (SwiftUI)",
         "• Camera, MediaPipe Holistic\n• ASL Signs model via LiteRT\n• Sign detector and the rule (3)\n"
         "• Screens: Home, Get ready, Call,\n   Brief, Notes\n• Holds no API keys"),
        ("w-backend", "backend", "Backend (FastAPI, Heroku)",
         "• Calls, turns, single-use SEND\n• Draft: Groq + validator + templates\n• Briefs and the agent's brain\n   (Groq + rules, every line checked)\n"
         "• Bolna's custom-LLM endpoint\n• Status webhook, call notes"),
        ("w-bolna", "bolna", "Bolna (voice agent)",
         "• Places the call (Plivo number)\n• Deepgram transcription\n• Sarvam voice\n• Speak step says only the\n   approved text\n• Call summary after the call"),
        ("w-mac", "mac", "Mac (fallback and tools)",
         "• Webcam recognizer into the\n   same backend call\n• Sign Lab: local backend with a\n   scripted receptionist\n"
         "• Probe, parity and summary tools\n   for recognition"),
    ]
    cw, ch = 420, 250
    for i, (cid, fill, title, body) in enumerate(cols):
        x = 40 + i * (cw + 20)
        b.box(cid, x, y4 + 45, cw, ch, f"{title}\n\n{body}", fill, size=16, align="left")

    # ---- 5. Rules and status ----
    y5 = 1830
    b.text("s5", 40, y5, "5. Rules that never bend, and where the build is", size=22, bold=True)
    b.box("rules", 40, y5 + 45, 880, 330,
          "Safety rules\n\n• Nothing is spoken unless you tapped SEND (live call) or\n   approved the brief (call for me).\n"
          "• Unsure recognition stays silent: [?] or \"did you mean\", never a guess.\n"
          "• The agent never agrees to anything outside the brief: it asks\n   you, or says it will call back.\n"
          "• The draft may reword your signs but never adds a day, time,\n   number or name.\n"
          "• Calls go only to allowlisted, consenting numbers, from\n   Ishara's calling number (Bolna's), and say they are for a Deaf caller.",
          "stop", size=16, align="left")
    b.box("status", 940, y5 + 45, 860, 330,
          "Status, 28 October\n\n• Built and tested in the iOS simulator: both call modes, and the\n   ASL model running inside the app.\n"
          "• Public ASL clips, app and Mac: 0 wrong chips with the shipped\n   settings; same decision on 17 of 18 parity clips.\n"
          "• Real Bolna calls passed: Live and all three Call-for-me flows,\n   from the simulator app with sign videos as the camera.\n"
          "• Not yet: the iPhone (camera, speed, phone clips, final cut-offs).\n"
          "• No Deaf user has tested it. ISL is the goal; it is blocked by data.",
          "mac", size=16, align="left")
    return b


# ---- writers ----

def _seed(key: str) -> int:
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)


def _base(id: str, kind: str, x: float, y: float, w: float, h: float, **extra) -> dict:
    return {"id": id, "type": kind, "x": x, "y": y, "width": w, "height": h, "angle": 0,
            "strokeColor": INK, "backgroundColor": "transparent", "fillStyle": "solid", "strokeWidth": 2,
            "strokeStyle": "solid", "roughness": 1, "opacity": 100, "groupIds": [], "frameId": None,
            "roundness": None, "seed": _seed(id), "version": 1, "versionNonce": _seed(id + "n"),
            "isDeleted": False, "boundElements": [], "updated": 1793088000000, "link": None,
            "locked": False, **extra}


def _text_el(id, x, y, w, h, text, size, color=INK, align="left", container=None, valign="top") -> dict:
    return _base(id, "text", x, y, w, h, strokeColor=color, text=text, originalText=text, fontSize=size,
                 fontFamily=2, textAlign=align, verticalAlign=valign, containerId=container,
                 autoResize=True, lineHeight=1.25)


def excalidraw(board: Board) -> dict:
    elements = []
    for s in board.shapes:
        el = _base(s.id, s.kind, s.x, s.y, s.w, s.h, backgroundColor=s.fill, strokeColor=s.stroke,
                   strokeStyle="dashed" if s.dashed else "solid",
                   roundness={"type": 3} if s.kind == "rectangle" else {"type": 2},
                   boundElements=[{"id": f"{s.id}-t", "type": "text"}])
        lines = s.text.split("\n")
        th = len(lines) * s.size * 1.25
        tw = max(len(line) for line in lines) * s.size * CHAR
        tx = s.x + 12 if s.align == "left" else s.x + (s.w - tw) / 2
        elements += [el, _text_el(f"{s.id}-t", tx, s.y + (s.h - th) / 2, tw, th, s.text, s.size,
                                  align=s.align, container=s.id, valign="middle")]
    for t in board.texts:
        lines = t.text.split("\n")
        elements.append(_text_el(t.id, t.x, t.y, max(len(x) for x in lines) * t.size * CHAR,
                                 len(lines) * t.size * 1.25, t.text, t.size, t.color))
    for a in board.arrows:
        (x0, y0), pts = a.points[0], a.points
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        elements.append(_base(a.id, "arrow", x0, y0, max(xs) - min(xs), max(ys) - min(ys),
                              strokeStyle="dashed" if a.dashed else "solid", roundness={"type": 2},
                              points=[[px - x0, py - y0] for px, py in pts], lastCommittedPoint=None,
                              startBinding=None, endBinding=None, startArrowhead=None, endArrowhead="arrow"))
    return {"type": "excalidraw", "version": 2, "source": "docs/archive/architecture/board.py",
            "elements": elements, "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None}, "files": {}}


def _svg_lines(x, y, text, size, anchor, weight="normal", color=INK) -> str:
    out = [f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" font-weight="{weight}" fill="{color}">']
    for i, line in enumerate(text.split("\n")):
        out.append(f'<tspan x="{x}" dy="{0 if i == 0 else size * 1.25}">{escape(line) or " "}</tspan>')
    return "".join(out) + "</text>"


def svg(board: Board) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" '
             'font-family="Helvetica, Arial, sans-serif">',
             '<defs><marker id="head" markerWidth="12" markerHeight="10" refX="11" refY="5" orient="auto">'
             f'<path d="M0,0 L12,5 L0,10 z" fill="{INK}"/></marker></defs>',
             f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#ffffff"/>']
    for s in board.shapes:
        dash = ' stroke-dasharray="8 6"' if s.dashed else ""
        style = f'fill="{s.fill if s.fill != "transparent" else "none"}" stroke="{s.stroke}" stroke-width="2"{dash}'
        if s.kind == "rectangle":
            parts.append(f'<rect x="{s.x}" y="{s.y}" width="{s.w}" height="{s.h}" rx="14" {style}/>')
        elif s.kind == "ellipse":
            parts.append(f'<ellipse cx="{s.x + s.w / 2}" cy="{s.y + s.h / 2}" rx="{s.w / 2}" ry="{s.h / 2}" {style}/>')
        else:
            cx, cy = s.x + s.w / 2, s.y + s.h / 2
            parts.append(f'<polygon points="{cx},{s.y} {s.x + s.w},{cy} {cx},{s.y + s.h} {s.x},{cy}" {style}/>')
        lines = s.text.split("\n")
        top = s.y + (s.h - len(lines) * s.size * 1.25) / 2 + s.size * 0.95
        if s.align == "left":
            first, rest = lines[0], "\n".join(lines[1:])
            parts.append(_svg_lines(s.x + 16, top, first, s.size + 2, "start", "bold"))
            parts.append(_svg_lines(s.x + 16, top + s.size * 1.25, rest, s.size, "start"))
        else:
            parts.append(_svg_lines(s.x + s.w / 2, top, s.text, s.size, "middle"))
    for a in board.arrows:
        dash = ' stroke-dasharray="8 6"' if a.dashed else ""
        pts = " ".join(f"{x},{y}" for x, y in a.points)
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{INK}" stroke-width="2"{dash} marker-end="url(#head)"/>')
    for t in board.texts:
        parts.append(_svg_lines(t.x, t.y + t.size, t.text, t.size, t.anchor, "bold" if t.bold else "normal", t.color))
    return "\n".join(parts + ["</svg>"])


def main() -> int:
    board = build()
    problems = board.check()
    for p in problems:
        print("warning:", p)
    (HERE / "ishara-board.excalidraw").write_text(json.dumps(excalidraw(board), indent=1) + "\n")
    (HERE / "ishara-board.svg").write_text(svg(board) + "\n")
    print(f"wrote ishara-board.excalidraw and ishara-board.svg ({len(problems)} warnings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
