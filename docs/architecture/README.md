# Architecture board

`ishara-board.excalidraw` is the editable team whiteboard from 23 October 2026.
Open it at [excalidraw.com](https://excalidraw.com) (menu → Open) or in the VS Code
Excalidraw extension. `ishara-board.png` is a dark-theme overview of the same board.

The board has six parts, top to bottom:

| Part | What it shows |
|---|---|
| Architecture | Signer → on-device recognition → word chips → SEND → Bolna voice → call → captions back |
| A. Decisions | The seven choices agreed on 23 October (see [PLAN.md](../../PLAN.md#2-decisions)) |
| B. Edge cases | What the app does when signing or the call goes off-script |
| C. Build plan | Day-by-day lanes from 23 to 31 October, with four go/no-go gates |
| D. Testing plan | Six test layers, from unit tests to the rehearsed demo |
| E. App screens | Home, Get ready, Active call (signing), Active call (speaking) |

The plan in [PLAN.md](../../PLAN.md) is the source of truth if the board and the
plan ever disagree. Update both together.

## Where the board lags the plan (as of 23 October)

The PNG and `.excalidraw` still carry items from the pre-Option-C draft and from before
the 23 October composer switch. Read them with the plan's wording instead until the board
is re-exported:

- **Gate 1 "FAIL → Path B"**: Path B is now the main path. The plan's G1 fallbacks are a
  built-in LLM with a "repeat exactly" prompt, then Path A.
- **"Tuned to the 2 people who recorded"**: the plan uses one signer, the person who
  presents the demo.
- **"Jev (cloud) 2nd opinion"**: not in the plan; there is no cloud recognizer in the demo.
- **"Cerebras LLM drafts it"**: read as **Groq** (`openai/gpt-oss-120b`). The composer moved
  to Groq on 23 October because Cerebras is not free; the validator and template fallback
  are unchanged.

## Build status behind the board (23 October)

The board shows the target design. The backend, iOS app shell and packages, Core ML
conversion and Mac fallback exist as open PRs with offline tests; nothing has run against
real Bolna or on an iPhone yet. See [PLAN.md §6](../../PLAN.md#6-schedule-and-todos) and
the component table in [§3](../../PLAN.md#components-and-repo-layout-new-code).
