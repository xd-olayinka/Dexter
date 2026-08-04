# Dexter + Anthony — Backend Task List

Developer handoff. The backend lives in `server/` (Python 3.12 + FastAPI, all async).
Everything is built to **start cleanly with zero external services** — each missing
dependency returns a stub/graceful error instead of crashing. Install services as you
go (see `docs/setup.html`), and the corresponding subsystem lights up.

Run it: `cd server && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt && copy .env.example .env && .venv\Scripts\python run.py` → http://localhost:8000 (`/docs` for Swagger).

---

## Layer map (what exists today · ~2,810 lines)

| Layer | Files | Status | Depends on |
|---|---|---|---|
| **0 · Core / Chat** | `main.py`, `chat.py`, `ollama_client.py`, `run.py`, `config.py`, `models.py`, `status.py` | ✅ Built | Ollama (optional) |
| **1 · Memory** | `db/{schema.sql,connection.py}`, `memory/{store,semantic,facts}.py` | ✅ Built · ⚠ not wired into chat yet | Postgres + pgvector |
| **2 · Tools** | `tools/{registry,caller,search,filesystem,browser,datetime_tool}.py` | ✅ Built | SearXNG (search), Playwright (browse) |
| **3 · Voice** | `voice/{vad,stt,tts,pipeline,ws_handler}.py` | ✅ Built · dummy fallbacks | torch, faster-whisper, piper-tts |
| **4 · Shadow (Anthony)** | `shadow/{executor,budget,guards,gates,router}.py` | ✅ Built · executors simulate work | ntfy (push, optional) |
| **5 · Escalation** | `escalation/{classifier,providers,router,tracker,api}.py` | ✅ Built | Anthropic/OpenAI/Groq keys (optional) |

---

## Endpoints (live today)

```
GET  /                              health
GET  /api/status                    every subsystem's up/down + config (drives Settings dots)
POST /api/chat/send                 one-shot chat
GET  /api/chat/history/{sid}        session history (in-memory)
WS   /ws/chat                       streaming chat (token frames)
WS   /ws/voice                      voice turn: audio in → transcription → TTS out

POST /api/shadow/delegate           spawn a task (Anthony)
GET  /api/shadow/tasks              list tasks
GET  /api/shadow/tasks/{id}         one task
POST /api/shadow/tasks/{id}/kill    kill a task
GET  /api/shadow/gates              pending approval gates
POST /api/shadow/gates/test         fire a test gate (+ ntfy push)
POST /api/shadow/gates/{id}/approve
POST /api/shadow/gates/{id}/reject
GET  /api/shadow/budget             daily budget snapshot

GET  /api/escalation/providers      cloud provider availability
GET  /api/escalation/spend          today's spend breakdown
GET  /api/escalation/spend/history  recent ledger entries
POST /api/escalation/route          dry-run: which model would this route to
```

---

## Pending work — in priority order

### P1 · Make executors do real work  `shadow/executor.py`
Right now `_default_work_fn` sleeps 1s and returns `"Simulated completion of: <title>"`.
- Replace with the agentic loop: `run_with_tools(ollama_client, messages, registry)` from `tools/caller.py`.
- Feed the task title/description as the objective; let the model call tools.
- Record real token spend per step into `BudgetTracker` (drives the guard trips).
- Keep the gate/kill/pause machinery — it already works.

### P2 · Wire memory into chat  `chat.py` + `memory/`
- On each turn: `ConversationStore.save_message()`, then `SemanticMemory.recall()` to prepend
  relevant history, and `FactStore` for standing preferences.
- Replace the in-memory `sessions` dict with `ConversationStore`.
- Needs Postgres running + `init_db()` (already called on startup, no-ops if DB down).

### P3 · Projects / Tasks persistence  (new: `projects.py`, tables in `db/schema.sql`)
- Add `projects` + `tasks` tables (mirror the frontend mock shape in `src/data.ts`).
- CRUD endpoints `/api/projects`, `/api/tasks` — the frontend Orch screens swap mock → live.

### P4 · Briefing generator  (new: `briefing.py`)
- `GET /api/briefing/today` → Ollama summarizes today's tasks + gates + spend (+ calendar later)
  into the "Good morning, Commander" copy. Optional daily cron.

### P5 · File / URL ingest  (new: `files.py`)
- `POST /api/files/upload` (PDF/text) and `POST /api/files/url` → parse → embed → `SemanticMemory`.
- First hook of the Archive (Phase 6).

### P6 · Guards CRUD  `shadow/guards.py` + endpoint
- `GET/POST /api/shadow/guards` to raise/lower caps and add rules from the Settings UI
  instead of editing `.env`.

---

## Known honest constraints
- **Headless Ollama in the cloud** likely needs API-key billing, not the Max/Pro subscription —
  the local daemon (logged-in session) is what runs on the seats you already pay for.
- **Per-task metering** is reliable for CLI/SDK tools; weak/unavailable for GUI subs (Cursor, ChatGPT).
- The static frontend (Vercel/Pages) has **no backend** — it runs in demo mode until you point
  Settings → Backend URL at a running server (locally, or via a Cloudflare Tunnel).
