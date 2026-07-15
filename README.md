# D.E.X.T.E.R · Shadow Protocol

> **D**elegator · **E**xecutor · **X**D Task Terminator · **E**nabling **R**evenue

A personal AI Shadow Operative that runs a business owner's operations across two linked protocols:

- **Orchestrator** — the visible layer. Talks to the Commander, plans work, routes reasoning to frontier models.
- **Shadow** — the dark ops layer. Spawns executor sub-agents, scores them for efficiency, executes autonomously.

One app, one identity, two faces. Toggle between them any time.

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

Live: https://xd-olayinka.github.io/Dexter/
