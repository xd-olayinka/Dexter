# Dexter + Anthony — Build Plan

Developer handoff. This is the forward plan: what the next passes build to take the system
from "shell + scaffold that runs" to "daily driver." Pairs with `BACKEND_TASKS.md`
(the backend checklist) and `docs/setup.html` (the install steps).

## Naming

- **DEXTER** — Delegator, Executor, XD Task Terminator, Enabling Revenue. The **Orchestrator**
  (planning, oversight, routing). Warm UI.
- **ANTHONY** — Autonomous Networked Tactical Handler for Operations, Notifications & Yield.
  The **Shadow** / execution layer (spawns executors, runs the tool loop, reports). Dark UI.
- Two operatives, one app, toggle in the top bar. Internal code still uses `mode: 'orch' | 'shadow'`
  and the `.shadow-mode` CSS class — only user-facing copy says "Anthony".

## Locked decisions (2026-07)

| Decision | Choice |
|---|---|
| Voice input | **Push-to-talk** button (hold to record). Wake-word later. |
| Orch scope, next pass | Real Projects/Tasks CRUD · voice command on Home · briefing generator · file/URL attach |
| Anthony scope, next pass | Real executor work (Ollama + tools) · Selector wired to live router · Burn wired to live ledger · kill-switch/guard-config panel |
| Archive (NotebookLM alt) | **Deferred** to Phase 6 — its own project |
| Audience for docs | Developer / technical handoff |
| Hosting | Hybrid: static frontend on the web + local FastAPI backend (demo-mode fallback offline) |

---

## Phase 2 — "Make it real"

**Status (2026-09-24): done**, 2.1–2.7 below. See `docs/BACKEND_TASKS.md` for the backend
implementation notes and its "Known honest constraints" for what's still unverified (real
Whisper/Piper, in particular — only tested against the dummy voice path in this environment).

Ordered so each step is independently shippable. Frontend and backend halves noted.

### 2.1 · Push-to-talk voice — done
- **Backend**: `/ws/voice` unchanged for VAD/STT/TTS, plus a new client → `{"type":"commit"}`
  message that finalizes a turn immediately on button release. Needed because a real (non-dummy)
  VAD only fires on detected *silence* — once the client stops streaming chunks, it would never
  see that silence and would hang forever. The old dummy-VAD-only path (which fires on the very
  first chunk) masked this gap; `commit` fixes it for when torch/Whisper are actually installed.
- **Frontend**: `src/lib/voice.ts` (raw PCM16 @16kHz capture via ScriptProcessorNode, TTS playback
  buffers the full reply before playing — simpler and gap-free vs. per-chunk scheduling) +
  `src/components/MicButton.tsx` (hold-to-record, shows a disabled "voice not installed" state
  from `/api/status`'s capabilities). Wired into `Chat.tsx` and `OrchHome`'s command bar.

### 2.2 · Real executor work — done (`docs/BACKEND_TASKS.md` P1)
- Ops Feed + Live Tasks needed no frontend change, as predicted — results are just real now.

### 2.3 · Projects / Tasks on Postgres — done (P3)
- `src/screens/Orch.tsx`'s `Projects()`/`Tasks()` use live data when online, original mock
  markup/data kept as the offline fallback. Added inline create (project name, task title) and
  per-task delegate-to-Anthony, since a real CRUD screen needs a way to add records, not just view.

### 2.4 · Briefing generator — done (P4)
- `OrchHome` reads `/api/briefing/today` when online (real stats + chips), canned line offline.

### 2.5 · File / URL attach — done (P5)
- `Chat.tsx`'s attach button now branches: an image stays a local-only preview (no vision model
  wired into the Brain), a document (pdf/txt/md/csv) goes to `/api/files/upload` for real —
  extracted, embedded, and it becomes usable memory via chat's recall (P2), not just a write-only
  store. Settings → "Ingested Documents" lists/deletes and adds by URL.

### 2.6 · Selector + Burn live — done
- `Selector` shows real provider availability + an interactive "Try the Router" dry-run tester
  (the static "Last 3 Picks" couldn't be made real — nothing logs past picks with reasons — so
  it's replaced with a live tool instead of a fabricated history). `Credits` (Burn) shows real
  per-provider spend and the real guard config/custom rules, both offline-fallback to the mocks.

### 2.7 · Guard-config panel — done (P6)
- Settings → Guardrails: edit daily/per-task/high-cost/long-running caps (takes effect on the
  next spawned task, no restart) and add/remove custom rules (keyword match, spend cap, or
  always-require-approval — declarative, not arbitrary code).

---

## Later phases

**Status 2026-09-25:** Phase 4 (team + multi-user, dependency map) is done — see
`PHASE_3_4_PLAN.md`. Phase 6 Archive v1 is done (notebooks, cited Q&A, two-voice briefing). Phase 3's
Prometheus integration is live; the third-party integrations below still need OAuth apps.

- **Phase 3 · Integrations (MCP-first).** Wrap Slack / Gmail / GitHub / Calendar / Stripe as MCP
  servers. Tier 1 = servers the brain calls (service credentials, run headless); Tier 2 = the same
  servers configured inside each executor. An inbound event bus (webhooks + pollers) lands outside
  events on a queue the orchestrator reacts to. First integration TBD (Slack or Gmail recommended —
  most inbound signal).
- **Phase 4 · Team + multi-user.** Auth (Clerk/Auth0 or a signed daemon↔brain token), roles,
  shared businesses, the dependency map (business ↔ team ↔ agent ↔ tool).
- **Phase 6 · Archive.** Personal-intelligence vault on the existing pgvector memory: notebooks,
  drop PDFs/links, chat over sources with citations, two-voice audio briefings using the Dexter +
  Anthony TTS voices. Deliberately a NotebookLM alternative with no subscription.

## Services you'll add (all free to start)

Ollama · PostgreSQL + pgvector · Docker + SearXNG · ntfy (phone push) · voice libs
(torch, faster-whisper, piper). Paid, only when a task earns it: Anthropic / OpenAI keys;
Groq is a free fast tier. Full step-by-step in `docs/setup.html`.
