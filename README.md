# D.E.X.T.E.R + A.N.T.H.O.N.Y

> **DEXTER** — **D**elegator · **E**xecutor · **X**D Task Terminator · **E**nabling **R**evenue
> **ANTHONY** — **A**utonomous **N**etworked **T**actical **H**andler for **O**perations, **N**otifications & **Y**ield

A personal AI operative that runs a business owner's operations through two linked protocols, each with its own named agent:

- **DEXTER · Orchestrator** — the visible layer. Talks to the Commander, plans work, routes reasoning to frontier models.
- **ANTHONY · Shadow** — the dark ops layer. Spawns executor sub-agents, scores them for efficiency, executes autonomously within guardrails, and reports back.

One app, two operatives, two faces. Toggle between them any time.

## Status

**Milestone 1 · Live backend + UI wired.** UI shell, dual-protocol design system, and a full Python FastAPI backend with 6 layers (chat, memory, tools, voice, shadow executors, cloud escalation). Everything degrades to Demo mode when the backend isn't running, so the Pages deploy stays alive.

See [`docs/setup.html`](docs/setup.html) for the step-by-step install checklist — Ollama, Postgres + pgvector, SearXNG, voice pipeline, ntfy phone push, optional cloud API keys.

## Stack

**Frontend** — Vite + React 19 + TypeScript, Poppins (display) + Satoshi (UI) self-hosted, design tokens as CSS variables that flip via `.shadow-mode` on the shell. Deploys to GitHub Pages on push to `main`.

**Backend** — Python FastAPI + async, Ollama (local LLM) + Postgres/pgvector (memory) + SearXNG (search) + Piper/Whisper (voice) + ntfy.sh (phone push), with optional Anthropic/OpenAI/Groq escalation.

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

Live: https://xd-olayinka.github.io/Dexter/
