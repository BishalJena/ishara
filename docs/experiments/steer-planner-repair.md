# General-purpose steer planner repair

6 November 2026.

Ishara should complete a context-authorized call unattended when the supplied
information is sufficient. It can accept a suitable operation or option without
another live approval. It must answer the receiver's current question, preserve
unanswered parts of the request and distinguish acceptance from completed work.

## Repair

Private planning uses a nested strict JSON schema. Each action has only its own
fields. Caller facts, document spans, receiver turns and goal evidence have source
IDs. Delivered live replies bind to question instances, not repeated wording.
New captions, presence changes and user input invalidate stale decisions.

An offer must match an unresolved external-action goal and the request's timing,
service and spending constraints. Retained terms include prices from preceding
captions. Historical amounts and refused prices do not authorize a charge.
Accepting an offer does not resolve the goal. Current-turn receiver confirmation
can resolve it immediately, after merging with earlier goal evidence.

Unknown essential information reaches an available caller as a follow-up. An
absent caller gets an honest closure and unresolved notes. Missing model output
cannot become an invented answer, repeated next-step question or false success.
Explicit corrections revoke relevant evidence; unrelated negative answers retain
previously collected information. Notes use the current proof state.

The phone-free HTTP replay also exposed a routing defect. “Shall I go ahead?”
matched the greeting's unscoped “go ahead” phrase and bypassed inference. Only a
standalone floor invitation now matches that greeting rule.

## Executed verification

- Backend formatting, Ruff and 1,346 tests passed after the routing regression.
- The production Groq client and GPT-OSS 120B passed 13 synthetic replay steps
  using 12 model requests. One step checks a deterministic consent guard.
- A separate live-model HTTP replay used the real FastAPI routes, call manager
  and fake telephone adapter. Four model requests verified unattended acceptance,
  an exact document answer, receiver confirmation, successful final notes, and
  honest closure with follow-up when an essential caller fact was absent.
- The provider response deadline remained 2.5 seconds. Evaluation requests were
  spaced outside that deadline to avoid creating an artificial burst.
- Independent read-only review passed 18 acceptance challenges and 136 focused
  tests. These are additional test cases, not additional provider requests.
- Five browser state tests, 14 browser integration tests and the web build passed.
- The full native run passed 279 tests and skipped 16. Its one failed summary
  test exposed missing fallibility wording and obsolete scroll order. Both were
  repaired; the focused UI regression passed after rebuilding the app.
- Shared Swift packages and shell checks passed. Recognition replay environments,
  the Android Swift SDK and JDK were unavailable in the publication checkout.
- The configured voice agent's graph, custom endpoint, webhook, transcription,
  voice, silence settings and summary option matched the expected configuration.

No real telephone call was placed. All documents and conversation fixtures sent
to the model were synthetic. Account responses and provider captures remain
outside the repository. No credentials or private endpoint values are included.

## Model selection and limits

The initial flat-schema integration failed live verification. Nested action
shapes and explicit caller/receiver roles corrected the transport contract.
GPT-OSS 120B passed the final autonomous fixture set. GPT-OSS 20B failed three
steps; another candidate produced a provider error during qualification. Neither
was promoted as an automatic fallback.

A rapid earlier run hit the provider's token-per-minute limit. Paced fixture
success does not prove unlimited call throughput. Account quotas, inference
availability and latency remain operational constraints. The repair preserves an
honest follow-up when reasoning is unavailable; it does not change billing plans.

Strict JSON guarantees a data shape, not semantic truth. Exact quotation proves
provenance, not arbitrary answer relevance. Intent alignment and broader language
interpretation still depend on the model and conservative guards. These fixtures
cannot establish flawless behavior across every service or conversation. A real
call remains necessary to rehearse recognition, telephony transcription,
interruptions and end-to-end voice timing.

Run the committed fixtures from the repository root:

```sh
backend/.venv/bin/python scripts/planner_replay.py --dry-run
# Paid inference requires task authorization and provider credentials in the environment.
backend/.venv/bin/python scripts/planner_replay.py --live --interval-seconds 15
```

API contracts were checked against the provider's
[structured-output documentation](https://console.groq.com/docs/structured-outputs),
[reasoning controls](https://console.groq.com/docs/reasoning),
[rate-limit documentation](https://console.groq.com/docs/rate-limits), and
[voice agent retrieval API](https://www.bolna.ai/docs/api-reference/agent/v2/get).
