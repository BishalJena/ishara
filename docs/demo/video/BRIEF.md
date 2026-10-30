# Ishara launch film: production brief

The prompt this film is built from. It's self-contained: an agent (Devin CLI) or an editor can
produce the film from this file, [SCRIPT.md](SCRIPT.md) and the repo.

---

## The ask

Make a 2 min 45 s launch film for **Ishara**, an iPhone app that lets Deaf people make ordinary
phone calls on their own: an AI voice agent calls for them, they read every word as captions,
and they step in by typing, tapping a suggested reply, or signing.

It should feel like a high-end product launch (Apple keynote film, YC demo-day launch video),
with the gravity of what it's about: independence and privacy for people who are shut out of
the phone. **Restrained, not flashy.** Every motion explains something. Nothing bounces for fun.

Follow [SCRIPT.md](SCRIPT.md) beat for beat. Timings may move by a second or two; the order and
the words may not change without reason.

## Non-negotiables

1. **The product is shown with the real app.** Every app screen is the actual SwiftUI app,
   recorded from the iOS simulator. Don't redraw, fake or mock up app UI in the motion graphics.
   Motion graphics live *around* the phone: callouts, push-ins, diagrams.
2. **Every number on screen carries its source** in small type underneath (SCRIPT.md, Sources).
   Don't sum populations. Label the revenue scenario as an assumption.
3. **Honest claims only.** Nothing beyond what the app does (SCRIPT.md, "Rules this film keeps").
   ASL today, not ISL. No "first", "only", "revolutionary".
4. **Fictional people and data.** Aarav Sharma, Rohan, City Care Clinic, Dr. Kavita Rao, the
   health history PDF: all synthetic. No real phone numbers except the fictional one in the script.
5. **Accessible film.** Burned-in captions for every spoken line and VO; captions never cover
   the app's own captions. Contrast ≥ 4.5:1. No flashing above 3 Hz.

## Look

- **Palette** (the app's own): ink `#0B0B0F`, paper `#FAFAF7`, Ishara purple `#8B3DFF`
  (the agent), user blue `#0A84FF`, call green `#1EA84B`, fact yellow `#F6D77A` on `#FFF6D6`,
  muted grey `#8A8A93`. Black (`#000`) only for the barrier section.
- **Type:** SF Pro Display (system font) for headlines, SF Pro Text for body, SF Mono for
  numbers in sources. Headlines 88–120 px, tracking −2%; body 34–40 px; sources 20 px, grey.
- **Device:** iPhone 17 frame (natural titanium edge, 55 px corner radius on the screen,
  Dynamic Island), soft contact shadow, upright, never tilted more than 6°.
- **Space:** a lot of empty paper. One idea per frame. The phone sits on the centre line or at
  the left third with callouts on the right.

## Motion language

- **Settled springs** (no overshoot): ~0.5 s for UI, ~0.8 s for big type. Ease-out on entry,
  ease-in on exit, never linear except tickers.
- **Type reveals by line:** each line rises 24 px and un-blurs (8 → 0 px) over 0.5 s; lines
  stagger 0.12 s. Out: fade 0.3 s.
- **Numbers count up** over 1.2 s with ease-out, landing exactly on the sourced value.
- **Callouts:** a 2 px leader line draws from the screen element to a label (0.4 s), then the
  label text reveals. Max two callouts on screen.
- **Push-ins** on the phone (scale 1.0 → 1.35, 1.2 s) only when a detail must be read: the
  proposal bar, the one-tap replies, the sign panel, the gist.
- **Transitions:** cuts on beats, or a match move (the waveform becomes the call screen's
  caption; the phone ring becomes the app's ringing state). No wipes, no spins, no glitches.

## Sound

- **Phone audio for the demo:** an Indian ring-back tone (400 Hz, 25 Hz modulated, 0.4 s on,
  0.2 s off, 0.4 s on, 2 s off) ×2; Rohan's lines band-limited like a phone line (300–3400 Hz);
  Ishara's lines clean (the product's Sarvam voice, Indian English). Each line starts on the
  frame its caption appears in the app recording.
- **Score:** a quiet, warm pad that swells under section 4 (Ishara) and resolves at the close.
  It drops out completely for "Now imagine you can't hear the other side."
- **VO** (optional; SCRIPT.md lines): calm, close-mic'd. The film must work with VO muted.

## Pipeline (what's in the repo)

| Step | How |
|---|---|
| 1. Film call | `FakeCallDriver` plays the film's call when the app is launched with `-IsharaDriver fake -IsharaFlow steer -IsharaFilm 1` (the steer call screen, the real `TurnStore` rules, timed receptionist lines) |
| 2. Record the app | `FilmRecordingUITests` drives the app exactly as in SCRIPT.md §5 while `xcrun simctl io <sim> recordVideo` records the screen; it writes `film-timeline.json` (when each line and tap happened) to sync audio and callouts |
| 3. Voices | `cd video && python3 scripts/make_audio.py` (macOS voices; `--voices sarvam` for the product's own voice): one file per spoken line, the ring-back and a placeholder score in `public/audio/`, timed from the timeline; phone-band filter on Rohan |
| 4. Compose | Remotion project in `video/` (`ln -f raw/app.mp4 public/app.mp4`): one composition `IsharaFilm`, one component per section, the app recording in an iPhone frame via `<OffthreadVideo>`; `src/demo/plan.ts` holds the cut and maps every voice and callout through it |
| 5. Sign insert | `python3 scripts/track_sign_card.py` tracks the camera card; the founder's THANK YOU clip goes in `public/sign.mp4` and `SIGN_CLIP = true` in `src/sections/Demo.tsx` |
| 6. Render | `npm run render` → `out/ishara-film.mp4` (H.264, 1080p30, AAC) |

## Deliverables

- `out/ishara-film.mp4`: 1920×1080, 30 fps, about 2:45.
- `out/ishara-film-vertical.mp4`: 1080×1920 cut of sections 4–5 for social (optional).
- Stills of each section for the submission page.

## Done when

- Someone who has never seen Ishara can say, after one viewing, what it does, who it's for, and
  why it matters, and can read every app caption in the demo.
- Every number on screen matches SCRIPT.md's sources.
- The demo's lines, timings and taps are those of the real app; nothing in the phone is drawn.
