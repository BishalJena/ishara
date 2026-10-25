"""Write artifacts/teach.html: one card per demo word with the reference video(s) to copy.

Serves local copies only (Lifeprint YouTube clips, ISLRTC dictionary clips, your own
October webcam takes); nothing is uploaded or redistributed. Serve from artifacts/:

    cd spikes/recognition/artifacts && python3 -m http.server 8765
    open http://localhost:8765/teach.html
"""
from __future__ import annotations

from pathlib import Path

ARTIFACTS = Path(__file__).resolve().parent.parent / "recognition" / "artifacts"
LP, ISL = "asl_probe/lifeprint", "gemini_probe/raw/islrtc"

# (word, form to sign, how-to from the video, [(label, src, model result on that clip)], lifeprint page)
CARDS = [
    ("hello", "ASL wave (the ISLRTC clip shows the same sign)",
     "Open hand up near your temple or ear, palm forward, a small wave outward. One or two waves, then hands down.",
     [("ISLRTC hello (same sign as ASL)", f"{ISL}/Hello_h264.mp4", "model: hello 0.82"),
      ("your own take, 20 Oct", "sessions/20261020-085528/001.mp4", "model: hello 0.93"),
      ("your own take, 20 Oct", "sessions/20261020-090502/001.mp4", "model: hello 0.79")], "h/hello.htm"),
    ("thankyou", "ASL (the ISLRTC clip shows the same sign)",
     "Flat hand, fingertips touch the chin, then the hand moves forward and slightly down toward the listener.",
     [("ISLRTC thank you (same sign as ASL)", f"{ISL}/Thank_You_h264.mp4", "model: thankyou 0.92")], "t/thank-you.htm"),
    ("yes", "ASL fist nod (ISLRTC's hand form also works)",
     "Make a fist, bend it up and down at the wrist like a head nodding, twice.",
     [("Lifeprint yes", f"{LP}/yt_yes_0usayvOXzHo.mp4", "model: yes 0.72"),
      ("ISLRTC yes, hand form (same as ASL)", f"{ISL}/Yes_h264.mp4", "model: yes 0.92")], "y/yes.htm"),
    ("no", "ASL",
     "Index and middle finger extended together, close them onto the thumb once or twice, like a beak snapping shut.",
     [("Lifeprint no", f"{LP}/yt_no_QJXKaOSyl4o.mp4", "model: no 0.93")], "n/no.htm"),
    ("now", "ASL (we use it for 'today')",
     "Both hands in front of you, palms up, fingers slightly bent; drop both hands down together a short, sharp distance.",
     [("Lifeprint now", f"{LP}/yt_now_g2j70neQ_lI.mp4", "model: now 0.90")], "n/now.htm"),
    ("please", "ASL",
     "Flat hand on the middle of your chest, rub in a circle once or twice.",
     [("Lifeprint please", f"{LP}/yt_please_rnb9FxPO7is.mp4", "model: please 0.94")], "p/please.htm"),
    ("tomorrow", "ASL",
     "Thumb-up fist, thumb touching the cheek near the jaw, arc the hand forward and a little down. Do it once (twice means 'every day').",
     [("Lifeprint tomorrow", f"{LP}/yt_tomorrow_6gFOZMDptIk.mp4", "model: tomorrow 0.70"),
      ("Lifeprint tomorrow, 2nd video", f"{LP}/yt_tomorrow_E17VasimjWo.mp4", "model: every 0.57 (doubled?)")], "t/tomorrow.htm"),
    ("wait", "ASL",
     "Both hands palms up in front of you, one a little ahead of the other, fingers wiggling.",
     [("Lifeprint wait (the sign is at 3-6 s)", f"{LP}/yt_wait_4gAd3p_Jgq8.mp4#t=3,6.5", "model: wait 0.88 on that window"),
      ("Lifeprint wait, 2nd video", f"{LP}/yt_wait_6GXWaW1omCI.mp4", "model: flat (not recognized)")], "w/wait.htm"),
    ("morning", "ASL, candidate (0.62 once for you; Lifeprint clips not recognized)",
     "Left arm horizontal across the body; right flat hand, palm up, rises from under the left elbow like the sun coming up.",
     [("Lifeprint morning", f"{LP}/yt_morning_PKrGMspKng4.mp4", "model: flat (happy 0.15)"),
      ("Lifeprint morning, 2nd video", f"{LP}/yt_morning_iH8N44QMh7c.mp4", "model: flat (table 0.05)")], "m/morning.htm"),
    ("sick", "ASL, DROPPED (your attempts read as taste/go; Lifeprint clip flat)",
     "Bent middle finger of one hand touches the forehead; the other hand's bent middle finger touches the stomach. Pained face.",
     [("Lifeprint sick lesson", f"{LP}/yt_sick_oe9All9w7Ng.mp4", "model: flat (if 0.08)")], "s/sick.htm"),
    ("time", "ASL, DROPPED (your wrist taps read as arm/weus)",
     "Index finger taps the back of the other wrist, where a watch would be, twice.",
     [("Lifeprint time (6-frame animation)", f"{LP}/gif_time_time-1.gif", "model: not testable on a GIF"),
      ], "t/time.htm"),
]

STYLE = """body{font:16px -apple-system,Helvetica,sans-serif;margin:24px;background:#111;color:#eee}
h1{font-size:22px} .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:20px}
.card{background:#1d1d1d;border-radius:12px;padding:16px} .card h2{margin:0 0 4px;font-size:26px;text-transform:uppercase}
.form{color:#9fd;font-weight:600} .how{margin:8px 0 12px;line-height:1.4} .clip{margin:8px 0}
.clip small{display:block;color:#aaa;margin-top:2px} video,img{width:100%;border-radius:8px;background:#000}
a{color:#8cf} .note{background:#262626;padding:12px 16px;border-radius:10px;margin-bottom:20px;line-height:1.5}"""


def card(word, form, how, clips, page) -> str:
    media = []
    for label, src, result in clips:
        tag = (f'<img src="{src}" alt="{label}">' if src.endswith(".gif")
               else f'<video src="{src}" controls loop muted playsinline preload="metadata"></video>')
        media.append(f'<div class="clip">{tag}<small>{label} &middot; {result}</small></div>')
    link = f'<a href="https://www.lifeprint.com/asl101/pages-signs/{page}" target="_blank">Lifeprint page</a>'
    return (f'<div class="card"><h2>{word}</h2><div class="form">{form}</div><div class="how">{how}</div>'
            f'{"".join(media)}<div>{link}</div></div>')


def main() -> int:
    body = "".join(card(*c) for c in CARDS)
    note = ("<div class=note><b>How to practise:</b> play each video a few times and copy it. Sit as you will in the demo, "
            "face and both hands in frame, hands resting on the table between signs. The probe cuts a sign when your hands "
            "leave the rest line and come back; one sign per attempt, about 1&ndash;2 s. These clips are local copies for "
            "learning only (Lifeprint, ISLRTC, your own October takes).</div>")
    html = f"<!doctype html><meta charset=utf-8><title>Ishara: signs to learn</title><style>{STYLE}</style><h1>ASL signs for the probe, in order</h1>{note}<div class=grid>{body}</div>"
    (ARTIFACTS / "teach.html").write_text(html)
    print(ARTIFACTS / "teach.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
