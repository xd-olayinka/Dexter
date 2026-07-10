# D.E.X.T.E.R · Shadow Protocol

> **D**elegator · **E**xecutor · **X**D Task Terminator · **E**nabling **R**evenue

A personal AI Shadow Operative that runs a business owner's operations across two linked protocols:

- **Orchestrator** — the visible layer. Talks to the Commander, plans work, routes reasoning to frontier models.
- **Shadow** — the dark ops layer. Spawns executor sub-agents, scores them for efficiency, executes autonomously.

One app, one identity, two faces. Toggle between them any time.

## Status

**Milestone 0 · Prototype** — this UI shell with mocked data. See `DEXTER_MINI_PRD.md` for the full roadmap.

## Stack

- Vite + React 19 + TypeScript
- Poppins (display) + Satoshi (UI), self-hosted
- Design tokens as CSS variables, semantic tokens flip via `.shadow-mode` on the shell
- Deploys to GitHub Pages on push to `main`

## Develop

```bash
npm install
npm run dev       # http://localhost:5173/Dexter/
npm run build
```

Live: https://xd-olayinka.github.io/Dexter/
