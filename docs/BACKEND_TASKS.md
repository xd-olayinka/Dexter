# Dexter + Anthony — Backend Task List

Developer handoff. The backend lives in `server/` (Python 3.12 + FastAPI, all async).
Everything is built to **start cleanly with zero external services** — each missing
dependency returns a stub/graceful error instead of crashing. Install services as you
go (see `docs/setup.html`), and the corresponding subsystem lights up.

Run it: `cd server && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt && copy .env.example .env && .venv\Scripts\python run.py` → http://localhost:8000 (`/docs` for Swagger).

**Status (2026-09-24): P1–P6 below are all built and tested** (`server/tests/test_smoke.py`,
18 passing — run with `.venv\Scripts\python -m pytest tests/ -q`). This file is kept as the
reference for what each layer does; the "Pending work" section is now a "What P1–P6 built"
record instead.

---

## Layer map (what exists today · ~4,300 lines)

| Layer | Files | Status | Depends on |
|---|---|---|---|
| **0 · Core / Chat** | `main.py`, `chat.py`, `ollama_client.py`, `brain.py`, `run.py`, `config.py`, `models.py`, `status.py` | ✅ Built | Ollama and/or DeepSeek (`DEXTER_DEEPSEEK_API_KEY`) |
| **1 · Memory** | `db/{schema.sql,connection.py}`, `memory/{store,semantic,facts,embeddings}.py` | ✅ Built · wired into chat (P2) | Postgres + pgvector |
| **2 · Tools** | `tools/{registry,caller,search,filesystem,browser,datetime_tool}.py` | ✅ Built | SearXNG (search), Playwright (browse) |
| **3 · Voice** | `voice/{vad,stt,tts,pipeline,ws_handler}.py` | ✅ Built · dummy fallbacks · push-to-talk `commit` message added | torch, faster-whisper, piper-tts |
| **4 · Shadow (Anthony)** | `shadow/{executor,budget,guards,guard_config,gates,router}.py` | ✅ Built · executors run real work via the Brain (P1) · guards runtime-configurable (P6) | ntfy (push, optional) |
| **5 · Escalation** | `escalation/{classifier,providers,router,tracker,api}.py` | ✅ Built | Anthropic/OpenAI/Groq/DeepSeek keys (optional) |
| **6 · Projects/Tasks** | `projects.py`, tables in `db/schema.sql` | ✅ Built (P3) | Postgres |
| **7 · Briefing** | `briefing.py` | ✅ Built (P4) | none required — falls back to a stats-only sentence without a Brain |
| **8 · File/URL ingest** | `files.py`, `documents` table | ✅ Built (P5) | Postgres for persistence; pypdf for PDF text |

---

## Endpoints (live today)

```
GET  /                              health
GET  /api/status                    every subsystem's up/down + config (drives Settings dots)
POST /api/chat/send                 one-shot chat (persists + recalls memory when DB is up)
GET  /api/chat/history/{sid}        session history (in-memory)
WS   /ws/chat                       streaming chat (token frames)
WS   /ws/voice                      voice turn: audio in → transcription → TTS out
                                     client → {"type":"commit"} finalizes a push-to-talk turn
                                     immediately, without waiting on VAD-inferred silence

POST /api/shadow/delegate           spawn a task (Anthony) — now runs the real agentic loop
GET  /api/shadow/tasks              list tasks
GET  /api/shadow/tasks/{id}         one task
POST /api/shadow/tasks/{id}/kill    kill a task
GET  /api/shadow/gates              pending approval gates
POST /api/shadow/gates/test         fire a test gate (+ ntfy push)
POST /api/shadow/gates/{id}/approve
POST /api/shadow/gates/{id}/reject
GET  /api/shadow/budget             daily budget snapshot
GET  /api/shadow/guards             current guard config + custom rules
PATCH /api/shadow/guards            edit caps at runtime — no restart
POST /api/shadow/guards/rules       add a custom rule (keyword match + spend cap / always-approve)
DELETE /api/shadow/guards/rules/{id}

GET  /api/escalation/providers      cloud provider availability
GET  /api/escalation/spend          today's spend breakdown
GET  /api/escalation/spend/history  recent ledger entries
POST /api/escalation/route          dry-run: which model would this route to

GET/POST/PATCH/DELETE /api/projects[/{id}]   projects CRUD
GET/POST/PATCH/DELETE /api/tasks[/{id}]      tasks CRUD (?when=today|upcoming, ?project_id=)

GET  /api/briefing/today            model-written morning briefing from real tasks/gates/spend

POST /api/files/upload              multipart upload (pdf/txt/md/csv) → extracted + embedded
POST /api/files/url                 fetch a URL (plain httpx + HTML strip) → embedded
GET  /api/files                     list ingested documents
DELETE /api/files/{id}
```

---

## What P1–P6 built

### P1 · Real executor work — `shadow/executor.py`, `shadow/work.py`
`shadow/router.py`'s `/delegate` now passes `make_llm_work_fn(brain)` whenever the Brain
(Ollama or DeepSeek) is ready; falls back to the old 1s simulated stub only when neither is
configured. Real per-step spend flows into `BudgetTracker`, which drives the guard trips.

### P2 · Memory wired into chat — `chat.py`, `memory/embeddings.py`
Deliberate reading of "replace the in-memory sessions dict": the in-memory dict stays the
source of truth for building live context (chat must keep working if Postgres drops mid-session
— this backend's whole design promises graceful degradation), and `ConversationStore` +
`SemanticMemory` are a best-effort persistence/recall layer on top, wrapped so a DB failure
never breaks a turn. Recall pulls from **both** past conversations and ingested documents (P5),
each only injected above a similarity floor. `FactStore` is instantiated and available on
`app.state.fact_store` but has no trigger yet (no "remember this" tool) — left for a future pass.

### P3 · Projects / Tasks persistence — `projects.py`
Real CRUD behind `/api/projects` and `/api/tasks`, mirroring `src/data.ts`'s mock shape.
`src/screens/Orch.tsx`'s `Projects()`/`Tasks()` use it when online, with the original mock
markup kept as the offline/demo fallback (Build Plan 2.3).

### P4 · Briefing generator — `briefing.py`
Gathers real stats (today's tasks, pending gates, spend), then asks the Brain for one sentence
built **only** from those facts — never invents a project or number. Falls back to a plain
stats sentence with no Brain configured. 5-minute cache (`?refresh=true` bypasses it).

### P5 · File / URL ingest — `files.py`, `documents` table
Upload (pdf/txt/md/csv, 15MB cap) or a URL (plain httpx GET + HTML strip — not
`tools/browser.py`'s Playwright path, so it works without that install). Embedded when an
embedding provider is available, stored either way. Feeds back into chat via P2's recall.
Settings → "Ingested Documents" lists/deletes and adds by URL.

### P6 · Guards CRUD — `shadow/guard_config.py`, `shadow/router.py`
`GuardConfigStore` is an in-memory singleton (source of truth, read fresh on every
`ExecutorManager.spawn`) with Postgres as a best-effort persistence layer. A change via
Settings → Guardrails takes effect for the *next* spawned task immediately, no restart.
Custom rules: `{name, keyword (empty = all tasks), max_spend, require_approval, enabled}`
— declarative, not arbitrary code, so a user can't accidentally (or maliciously) inject logic.

---

## Known honest constraints
- **Headless Ollama in the cloud** likely needs API-key billing, not the Max/Pro subscription —
  the local daemon (logged-in session) is what runs on the seats you already pay for.
- **Per-task metering** is reliable for CLI/SDK tools; weak/unavailable for GUI subs (Cursor, ChatGPT).
- The static frontend (Vercel/Pages) has **no backend** — it runs in demo mode until you point
  Settings → Backend URL at a running server (locally, or via a Cloudflare Tunnel).
- **URL ingest doesn't render JavaScript** — a plain HTML fetch, so JS-heavy pages ingest poorly.
- **`FactStore`** has no write trigger yet (see P2) — the table and class exist, nothing calls them.
- **Voice hasn't been tested against real Whisper/Piper** in this environment (neither is
  installed here) — the `commit` protocol addition was verified against the dummy VAD/STT path
  only; the reasoning for why it's needed (a real VAD would never see post-release silence once
  the client stops streaming) is architectural, not empirically confirmed against real Silero/Whisper.
