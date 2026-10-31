# Context-aware calls and glanceable summaries

6–7 November 2026.

Ishara is a general-purpose voice relay for people with hearing or speaking
difficulties. A clinic appointment is one fixture, alongside passport and
home-service requests. The user supplies an intention and relevant context;
conversation does not follow a fixed appointment questionnaire.

## Findings

Four recent calls were inspected privately. All used the steer path, even though
the caller intended unattended delegation. An earlier call successfully relayed
a patient identifier, then failed on a combined allergy/blood-pressure question.
The archives did not retain attachment counts, attachment contents or exact
rejected planner actions, so they cannot prove the input payload of the last two
calls. No private transcript or account response is included here.

Synthetic reproductions through the real HTTP/custom-LLM routes established:

- An any-word field filter rejected a valid allergy span when another question
  part matched the generic word “last”.
- A single source span could not express separate requested facts without also
  reading unrelated rows; an inherited lookup limit rejected longer valid spans.
- A generic name fast path could answer a doctor-name question with the caller's
  name. Single-role validation also rejected questions asking about two people.
- An unfinished goal plus a neutral acknowledgement could become a missing-fact
  handoff and end an unattended call.
- Separately, the legacy native delegated request omitted setup documents and
  some context. This is a code-path defect, not an established cause of those four
  steer calls.
- Recent titles described contacts, while the main notes surface preferred a
  provider paragraph or chronological events. Notes refresh stopped at provider
  summary availability. Archive reads rewrote files, extending retention and
  changing apparent call order.

## Repair boundaries

Autonomous call modes share caller-owned sources and a multi-span answer boundary.
The planner can select several exact facts for one question. Generic labelled
fields and prose remain available, including split label/value layouts; the ASL
model is unchanged. Question references prevent stale live consent from becoming
permission for a different question. Neutral acknowledgements do not create
missing information. Accepting an offer is separate from receiver-confirmed work,
and unanswered receiver questions prevent a successful close.

The founder clarified that omitted time, budget and routine service preferences
leave the agent free to choose. A stated routine fee does not need an extra live
approval when no limit was supplied. The agent may select a reasonable offered
option to advance the request; explicit constraints still apply. This differs
from inventing an unknown address, allergy or identifier. Selected options,
times and fees belong in the ordinary summary details.

Internal structured output records actions and evidence. It is not a spoken
answer template, a fixed number of questions, or a clinic-specific workflow.
Reasoning about relevance and unfamiliar conversation still depends on the
model; strict JSON alone does not establish semantic correctness.

The native attachment reader now prevents calling during a read or after a read
failure. Safe logs retain document counts and character counts, plus action and
rejection categories, without logging document text or model responses.

A versioned `CallNotes.presentation` supplies one task title, authoritative
outcome overview, at most three details and one next step. The summary model selects source-clause IDs from a per-call enum; it cannot
write the factual details. The renderer preserves the selected clauses, including
qualifications and negation, and excludes agent completion claims. A literal
`none` choice keeps the internal instruction selection compatible with the
provider; the public optional next-step field is unchanged. A deterministic
fallback retains actual missing questions, including secondary unresolved items. The provider paragraph cannot promote
an unclear call to success. Transcript and event details stay expandable below.
The removed automatic-summary disclaimer is not rendered.

Summary work runs once per changed finished-call input, outside the live voice
response path. Reads do not generate inference. Background summaries wait while another call is
active and retry a quota response at most once; the live voice path does not wait
for summary generation. Stale background results cannot
replace newer notes. Archive updates preserve original retention timestamps;
Recent ordering uses transcript chronology. No new provider or recognition model
is introduced.

## Verification

The final local backend run passed **1,557 tests**, with formatting and Ruff
checks passing. The web passed 7 unit and 14 browser tests plus its production
build. Native verification passed 242 unit tests and four focused UI regressions;
one optional recognition parity test was skipped. Android requires the repository
CI toolchain. Physical-device installation was not verified.

## Reproduce without telephone calls

```sh
cd backend
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
cd ..
backend/.venv/bin/python scripts/planner_replay.py --dry-run
backend/.venv/bin/python scripts/planner_replay.py --suite clinical --dry-run
backend/.venv/bin/python scripts/planner_replay.py --http --dry-run
backend/.venv/bin/python scripts/planner_replay.py --http --suite autonomy --dry-run
```

The live versions require authorized provider credits and environment credentials.
They use synthetic context and fake telephony, with a hard limit of twelve model
requests per replay. Pacing is outside the production response deadline.

```sh
backend/.venv/bin/python scripts/planner_replay.py --http --live --interval-seconds 16
```

Four synthetic live-provider summary cases passed: a confirmed appointment with
time, fee and instruction; an incomplete request with its missing identifier;
a passport choice and fee; and a qualified allergy statement whose wording
must remain intact. The planner replays are separately qualified; summary success
does not establish voice-call success.

No telephone call was placed during this repair. Physical camera performance,
telephony transcription and voice timing still require a device rehearsal.
