# D.E.X.T.E.R + A.N.T.H.O.N.Y

> **DEXTER** — **D**elegator · **E**xecutor · **X**D Task Terminator · **E**nabling **R**evenue
> **ANTHONY** — **A**utonomous **N**etworked **T**actical **H**andler for **O**perations, **N**otifications & **Y**ield

A personal AI operative that runs a business owner's operations through two linked protocols, each with its own named agent:

- **DEXTER · Orchestrator** — the visible layer. Talks to the Commander, plans work, routes reasoning to frontier models.
- **ANTHONY · Shadow** — the dark ops layer. Spawns executor sub-agents, scores them for efficiency, executes autonomously within guardrails, and reports back.

One app, two operatives, two faces. Toggle between them any time.

## Status

**2026-09-25 · vision gaps closed (non-integration).** See `docs/PHASE_3_4_PLAN.md` §8. Selector Core
now really picks the cheapest capable model per task across Ollama, DeepSeek, Groq, Anthropic
(Haiku 4.5 / Sonnet 5 / Opus 5, Fable 5.1 opt-in) and OpenAI, and Anthony's tool loop runs on any
of them. Spend is a persistent **credit ledger** with a monthly budget, per-provider and per-agent
caps, and burn-rate alerts. Home's stats are real (or honestly empty). In-flight tasks survive a
restart, the app installs as a **PWA**, the **Archive** has notebooks with cited Q&A plus a
two-voice audio briefing, and `docker compose up` runs the backend with Postgres. Still open:
third-party integrations (Slack/Gmail/Stripe/GitHub need OAuth apps) and an actual hosting choice.

**Milestone 3 · Phase 2 + most of Phase 3/4 complete** (see `docs/BACKEND_TASKS.md` for P1–P6,
`docs/PHASE_3_4_PLAN.md` for what's below). Anthony runs real work through the Brain instead of a
stub; chat has persistent + semantic memory; Projects/Tasks, the morning briefing, and file/URL
ingest are live; guard caps/rules are runtime-editable; push-to-talk voice is wired end to end.
Accounts + businesses exist (off by default — `DEXTER_REQUIRE_AUTH=false`), with real invites and
a multi-business switcher; persistent Agent identity has a real efficiency score; the PRD §8
success metrics are tracked against their own stated targets; and the **Prometheus MCP bridge is
wired and verified live** against a real production Prometheus workspace (`DEXTER_PROMETHEUS_MCP_URL`/
`_TOKEN`). The Dependency map (business → team → agent → tool, PRD §4) shows real, observed
relationships — never a fabricated edge. With auth on, every data and control route (including
Anthony's kill/approve/guard endpoints) needs a session, and claiming an invite needs its one-time
code. 67 backend tests passing (`server/tests/`). Everything
still degrades to Demo mode when the backend isn't running, so the Pages deploy stays alive.

See [`docs/setup.html`](docs/setup.html) for the step-by-step install checklist — Ollama, Postgres + pgvector, SearXNG, voice pipeline, ntfy phone push, optional cloud API keys.

## Stack

**Frontend** — Vite + React 19 + TypeScript, Poppins (display) + Satoshi (UI) self-hosted, design tokens as CSS variables that flip via `.shadow-mode` on the shell. Deploys to GitHub Pages on push to `main`.

**Backend** — Python FastAPI + async, Ollama (local LLM) + Postgres/pgvector (memory) + SearXNG (search) + Piper/Whisper (voice) + ntfy.sh (phone push). Selector Core routes Anthony's work across Ollama, DeepSeek, Groq, Anthropic (official `anthropic` SDK) and OpenAI; every call is costed into the credit ledger.

## Develop

```bash
# Frontend
npm install
npm run dev       # http://localhost:5173/Dexter/
npm run build

# Backend
cd server
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python run.py    # http://localhost:8000
```

**Fastest way to a working brain:** set `DEXTER_DEEPSEEK_API_KEY` in `server/.env`
(key from platform.deepseek.com) — chat and executors go live with no Ollama install.
The Brain layer auto-prefers a healthy Ollama when present, falls back to DeepSeek otherwise.

### Run the backend in Docker

```bash
docker compose up        # API on :8000 + Postgres/pgvector; keys go in server/.env
```

To host it (Fly.io, Railway, Render, a VPS), deploy `server/Dockerfile`, point
`DEXTER_DATABASE_URL` at a Postgres with pgvector, and add the frontend's origin to
`DEXTER_CORS_ORIGINS` (JSON list, e.g. `["https://xd-olayinka.github.io"]`). Then set the backend URL
in the app's Settings.

Live: https://xd-olayinka.github.io/Dexter/
