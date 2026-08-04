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

## Phase 2 — "Make it real" (the next pass)

Ordered so each step is independently shippable. Frontend and backend halves noted.

### 2.1 · Push-to-talk voice
- **Backend** (built): `/ws/voice` handles audio → VAD → Whisper → text, and text → Piper → audio,
  with two voice profiles (Dexter warm / Anthony cold). Needs `torch`, `faster-whisper`, `piper-tts` installed.
- **Frontend** (to build): a mic button component (`src/components/MicButton.tsx` + `src/lib/voice.ts`).
  Hold to record → stream PCM to `/ws/voice` → drop the transcription into the chat/command input →
  play the TTS reply. Integrate into `Chat.tsx` and the Home command bar. Graceful "voice not installed"
  state when the pipeline reports dummy components via `/api/status`.

### 2.2 · Real executor work
- See `BACKEND_TASKS.md` P1. Wire `shadow/executor.py` to `tools/caller.run_with_tools`.
- **Frontend**: the Ops Feed + Live Tasks already poll `/api/shadow/tasks` — no change needed;
  results just become real. Guard trips already surface as gates + toasts.

### 2.3 · Projects / Tasks on Postgres
- **Backend**: P3 — tables + `/api/projects`, `/api/tasks`.
- **Frontend**: `src/screens/Orch.tsx` — swap the `PROJECTS` / `TASKS_TODAY` mock imports for live
  fetches; keep the exact card/row markup. Team stays mock until real integrations.

### 2.4 · Briefing generator
- **Backend**: P4 — `/api/briefing/today`.
- **Frontend**: `OrchHome` briefing headline reads from it when online; keeps the canned line offline.

### 2.5 · File / URL attach
- **Backend**: P5 — ingest → embed → memory.
- **Frontend**: `Chat.tsx` already has the attach button (local-only today) — point it at `/api/files/*`.

### 2.6 · Selector + Burn live
- **Frontend only**: `src/screens/Shadow.tsx` — `Selector` reads `/api/escalation/providers` + `/route`
  dry-runs; `Credits` (Burn) reads `/api/escalation/spend`. Backend already serves both.

### 2.7 · Guard-config panel
- **Backend**: P6 — guards CRUD.
- **Frontend**: a section in the Settings overlay to raise/lower caps and add rules.

---

## Later phases

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
