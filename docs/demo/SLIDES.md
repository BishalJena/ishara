# Slide outline

Six sections, one to three slides each. Pairs with the [demo script](SCRIPT.md); the
[submission text](SUBMISSION.md) uses the same claims. Wording marked **(exact)** is the
pitch line from the [handoff](../handoffs/2026-10-26-ready-made-asl-recognizer.md#rules-for-this-track)
and must be said as written.

## 1. Problem

- Many everyday services are booked by phone, like a clinic's appointment line.
- A Deaf person who signs has no easy way to make that voice call on their own. Human
  sign-language relay services exist in India ([ledger W04](../CLAIM-LEDGER.md)), but they
  need an interpreter on the line.
- Visual: a clinic's "call to book" line next to a signer with no way in.
- This is the team's framing; we have no user research or Deaf participant input behind it yet.

## 2. What it does

- **Live mode:** you sign each reply, Ishara drafts a sentence, and **nothing is spoken until
  you tap SEND**. You read the receptionist's words as captions.
- **Call for me:** you sign what you need (e.g. TOMORROW · MORNING), approve a short brief
  **once**, and the call agent makes the call. When a decision is yours (a time is offered),
  it says "One moment, please." and asks you: sign or tap **yes / no / wait**. No answer in
  10 s, or you're not watching: it says it will call back, never decides for you.
- Afterwards: call notes with the outcome, what was offered, what you answered, and the
  transcript.
- **Calls come from a Bolna number, not your own number.** Before every call the app says
  "Calls are placed from Ishara's calling number, not your own number."; say out loud that
  this number is Bolna's.
- Visuals: [Home](img/01-home.png), [brief](img/04-brief.png), [AskCard](img/05-ask-card.png),
  [notes](img/07-notes.png).

## 3. How it works

```
iPhone (SwiftUI)                         Backend (FastAPI, Heroku)            Bolna (voice agent)
camera → MediaPipe Holistic landmarks    chips → draft: Groq + validator,     Plivo phone line
→ ASL Signs model (LiteRT, on device)    template fallback                    Deepgram hears
→ word chips → SEND / yes·no·wait  ◀WS▶  call + turn state, single-use   ◀─▶ Sarvam voice speaks
captions · notes                         approvals; Bolna's custom LLM        our backend decides
                                         Call for me: brief, rule brain,      what it says
                                         check_line on every agent line
```

- Recognition: **(exact)** *"a published, signer-independent ASL model trained on public data
  from 21 Deaf signers"*: the Kaggle ASL Signs 1st-place model, used as is (no training, no
  fine-tuning). Full 250-way softmax; a chip only at p ≥ 0.6 with margin ≥ 0.3 for a
  vocabulary word; "Did you mean …?" between 0.35 and 0.6 (counts only when tapped);
  otherwise `?`.
- Rehearsed words: hello, thankyou, yes, no, now, please, tomorrow (candidates: morning, wait).
- Voice: Bolna places the call from its default number; our backend is Bolna's custom LLM,
  so apart from its fixed welcome (the disclosure) and goodbye, Bolna says what the backend
  returns; approved text goes in through Bolna's event injection. *By design; not yet run on
  a real call.*
- Partners: Bolna (agent, call, events, call summary), Sarvam Bulbul v4 Flash (voice),
  Deepgram nova-3 (speech-to-text), Plivo (phone line), Groq `openai/gpt-oss-120b` (draft
  wording).

## 4. Safety

- **(exact)** *"nothing is spoken on a call without the user's approval"*: SEND in live mode;
  one approval of the brief plus each yes/no in Call for me.
- Approvals are single use and tied to a turn; unsure signs (`?`), stale drafts, a dropped
  connection and an ended call stay silent. A reply that wasn't confirmed shows "Not
  delivered — tap SEND again"; nothing is resent on its own.
- The LLM may reword but not add facts: a validator rejects missing meanings and any invented
  day, time, number or name; templates are the fallback. Every Call-for-me agent line passes
  `check_line` (no invented numbers, times, names or bookings).
- Calls only to allowlisted, consenting numbers; synthetic details in the demo.
- The call opens with a disclosure: "Hello, I'm calling for a Deaf caller who is using
  Ishara, a sign-language app. Their replies may take a few seconds."
- Visuals: [`?` chip](img/11-live-unsure.png), [wrong chip removed before SEND](img/13-live-wrong-chip.png),
  [STOP](img/14-live-speaking-stop.png), [not delivered](img/15-live-not-delivered.png).

## 5. Honest limits

Say all of these.

- **(exact)** *"the presenter is hearing and learned the signs from Lifeprint"*.
- **(exact)** *"ISL is the goal and is blocked by data, which is the problem we want to solve"*.
  Public ISL data has about 16 clips per word and none for yes/no/sorry, so the demo is pure
  ASL; ISL signs are not mixed in.
- **(exact)** *"no Deaf-user validation yet"*. No Deaf participant has tested the design.
- A small rehearsed vocabulary, one sign at a time with hands down between signs. Not
  continuous signing, not general translation.
- **Calls come from a Bolna number, not the user's own number.**
- What is measured so far is small: 6 of 11 Lifeprint clips and four of the presenter's signs
  on the first try, on a Mac; 0 wrong auto-accepts at p ≥ 0.6 on the clips we have. The
  thresholds are provisional until the phone-clip check.
- **Pending on 28 Oct (update before the deck is final):** first real Bolna call, iPhone run
  (speed, live camera), D9 on Heroku. If any of these are still pending on demo day, say so on
  this slide.

## 6. What's next

- ISL: collect consented, signer-diverse ISL data with Deaf partners, then the same open-set
  design.
- Test with Deaf users before anything else is built.
- Own-number calls (Path A: Apple's Add Audio in Calls), Hindi, more words.
