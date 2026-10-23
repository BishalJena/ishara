# Ishara workflow: what the user does and what the app does

Updated 23 October 2026 for the demo build. Decisions and tasks live in
[PLAN.md](../PLAN.md); the visual version is the
[architecture board](architecture/README.md) (parts B and E). This is the agreed
demo flow, not a validated product: no Deaf participant has reviewed it.

## The user's journey (four screens)

```
 [1 Home] ──CALL──▶ [2 Get ready] ──start──▶ [3 Active call: signing] ──SEND──▶ [4 Active call: speaking]
                                                      ▲                                   │
                                                      └──────────── next turn ────────────┘
```

| Screen | What the user sees and does | What happens underneath |
|---|---|---|
| **1 Home** | Picks who to call (e.g. City Clinic) and the purpose (doctor's appointment). Saved details: name, preferred time. Voice: Indian English | Purpose and saved details feed the composer. Path A instead: the user dials in the Phone app, then opens Ishara |
| **2 Get ready** | Props the phone about an arm away. Checklist: face, both hands, light. Rests their hands on the table for 2 s | The 2 s rest calibrates the start/stop detector. "Start call" asks the backend to have Bolna dial (Path B) |
| **3 Active call: signing** | Reads the receptionist's caption, signs, checks the chips, checks the draft, taps **SEND**. Quick replies: Yes, No, Wait, Repeat | Each finished sign becomes a chip; every chip change recomposes the draft (Cerebras + validator, template fallback) |
| **4 Active call: speaking** | Sees "Speaking now…" with the exact sentence; SEND becomes **STOP**; then "✓ Delivered" | The backend sends a Bolna event; Bolna speaks with the Sarvam voice; chips and draft are wiped so old text can't replay |

Camera pill: **green** = watching (hands at rest), **yellow** = sign in progress,
**red** = can't see you. Chips: **green** = recognised (✕ removes one), **red [?]**
= unsure and never spoken.

Quick replies insert a full polite sentence into the draft. For example, "Repeat" →
*"Sorry, could you please repeat that?"* SEND is still required.

## One turn, step by step

```
receptionist speaks ─▶ caption on screen (Path B: Bolna's Deepgram transcript via our backend)
user reads ─────────▶ hands at rest: nothing happens, however long the pause
user signs "no" ────▶ hands drop ~0.4 s ─▶ SignCLIP match ─▶ chip [no]  ─▶ draft updates
user signs "morning"▶ hands drop ~0.4 s ─▶ SignCLIP match ─▶ chip [morning] ─▶ draft updates
user taps SEND ─────▶ backend ─▶ Bolna event ─▶ custom LLM returns the exact text ─▶ voice in the call
```

Two kinds of "end":

- **End of one sign:** automatic. The hands return to rest for about 0.4 s.
- **End of the message:** the user taps **SEND**. The app never guesses.

## Edge cases

| Situation | What the app does |
|---|---|
| Long pause or reading captions | Hands at rest, so nothing happens. Bolna says "One moment please, I'm signing my reply" after a long silence |
| Scratching nose, adjusting the phone | Too short or no match, so it's ignored or shown as [?] |
| Sign not recognised | [?] chip with "try again". Nothing spoken |
| Wrong word recognised | User taps ✕ on the chip before SEND |
| Out of frame | Red pill: "move back / hands not visible" |
| Receptionist asks something with no sign | Quick replies or saved profile phrases |
| Receptionist talks while the user signs | New caption appears; the draft is kept and the user decides |
| SEND tapped twice | The approval is single use, so nothing is spoken twice |
| Stop mid-sentence | Not yet spoken: cancelled. Already speaking: Path A can cut the audio; Path B has no documented interrupt (tested on day 1). Words already heard can't be unsaid, so the user sends a correction |
| Network drops or the call ends | "Nothing will be sent"; pending drafts are wiped; the next call starts clean |
| Receptionist says "booked" | Shown as their words only. Ishara never claims a booking itself |

## What the app knows and doesn't know

| Known | Not known |
|---|---|
| Its own camera frames, chips, drafts, approvals and playback state | Whether the receptionist understood |
| Path B: the receptionist's words (Bolna transcript via the custom-LLM requests) | Path A: anything the receptionist says (iOS Live Captions are user-visible only) |
| The call purpose and saved details the user entered | Whether a booking actually happened |

## Honest limits

About 12 personalised signs, one sign at a time with hands down between signs. Path B
calls come from a Bolna number; Path A keeps the user's number but has no app-readable
captions. The composer can reword but not add facts. See
[PLAN.md §9](../PLAN.md#9-honest-limits-say-these-in-the-pitch).

History: [20 October workflow](archive/2026-10-20-workflow.md),
[18 October workflow](archive/2026-10-18-workflow.md).
