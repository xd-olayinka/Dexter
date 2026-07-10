# D.E.X.T.E.R. Mini PRD
**Delegator, Executor, XD Task Terminator, Enabling Revenue**
Version 0.1 · July 2026 · Owner: Commander

---

## 1. Vision

Dexter is a personal AI Shadow Operative that runs a business owner's operations across two linked protocols:

- **Orchestrator Protocol (Dexter):** the visible, imaginative layer. Talks to the Commander, understands intent, plans work, and routes reasoning to frontier models (Claude Opus, Claude Fable, GPT 5.5). Tracks teams, businesses, agents, and spend.
- **Shadow Protocol:** the dark ops layer. Spawns and manages executor sub-agents, scores them for efficiency, selects the cheapest capable agent per task, executes autonomously within guardrails, and reports back.

One app, one identity, two faces. The user toggles between them at any time.

## 2. Problem

Founders and small teams juggle many tools (Slack, email, CRM, GitHub, finance apps) and increasingly many AI agents on top of them. Nothing ties together: (a) the humans and their roles, (b) the agents doing work, (c) the businesses those agents serve, and (d) the money the agents burn across multiple AI providers. Dexter is that connective tissue plus an execution engine.

## 3. Users

- **Primary:** solo founder or small business operator (the Commander) running 1 to 3 businesses.
- **Secondary:** their team members (2 to 15 people) who own or review agent output.
- **Tertiary (later):** agencies operating Dexter on behalf of clients.

## 4. Core Objects (Data Model)

| Object | Key fields | Notes |
|---|---|---|
| Business | name, status, integrations, health | e.g. Ledger&Co, Northwind Studio |
| Team Member | name, role, status, owned agents | humans, with presence and permissions |
| Agent | name, type (orchestrated / executor), model route, status, efficiency score, budget cap, owner | Shadow-created executors carry spawn metadata |
| Mission | title, priority, business, assigned agents, state (draft, running, gated, done, killed) | the unit of delegated work |
| Dependency | edge linking business ↔ team ↔ agent ↔ tool | powers the dependency map |
| Credit Ledger | provider, tokens/units, cost, period, alerts | Anthropic, OpenAI, search, voice, infra |
| Approval Gate | mission, action, requester agent, decision | human-in-the-loop checkpoint |
| Chat Thread | protocol context, messages, attachments (images, files) | Dexter's voice differs per protocol |

## 5. Key Features (MVP)

### 5.1 Dual Protocol Shell
- Persistent Orch / Shadow toggle in the top bar. Same five tabs, reskinned content and tone.
- Orchestrator: light warm minimal UI, planning and oversight language.
- Shadow: dark gold/red ops UI, execution and telemetry language.

### 5.2 Home (Briefing)
- Personalized greeting with priorities and revenue ops (Orchestrator) or overnight run summary (Shadow).
- Operative hero card with Dexter identity.
- Four headline stats: tasks terminated, revenue enabled, hours reclaimed, model spend.

### 5.3 Agents / Swarm
- Orchestrator view: agents with live status, model routing split (Opus / Fable / GPT 5.5), throughput.
- Shadow view: executor swarm, spawn timestamps, efficiency scores, kill events, and the Selector Core that picks the cheapest capable agent per task.
- Spawn button (Orchestrator suggests, Shadow force-spawns).

### 5.4 Team & Dependencies / Ops Log
- Orchestrator: team members, roles, presence, and which agents each person owns or reviews.
- Business dependency cards: business ↔ team ↔ agents ↔ tools, with health status.
- Shadow: chronological ops log with guard trips and terminations, every action explained.

### 5.5 Credits & Usage
- Unified spend ledger across providers with per-provider bars, monthly budget, and burn-rate alerts.
- Budget guards: hard caps per agent and per provider. Shadow auto-terminates executors that trip a cap and logs why.

### 5.6 Chat (Both Protocols)
- Conversational command center: ask, approve, delegate, hold.
- Quick-action pills (approve all, view draft, delegate to Shadow, hold).
- Image and file upload into the active mission thread.
- Dexter identity switches voice per protocol (advisor vs. operator).

## 6. Backend Architecture (Proposed)

```
Client (PWA / React Native)
        │  WebSocket + REST
        ▼
API Gateway (FastAPI or Node/Nest)
        │
        ├─ Auth (Clerk/Auth0, org + role based)
        ├─ Orchestrator Service
        │    · intent parsing, planning
        │    · model router → Anthropic API (Opus, Fable),
        │      OpenAI API (GPT 5.5), fallback chain
        ├─ Shadow Service (agent runtime)
        │    · spawner: creates executor sub-agents from templates
        │    · selector: scores efficiency (cost × capability × latency)
        │    · guardrails: budget caps, approval gates, kill switch
        │    · queue: Redis / Temporal for durable runs
        ├─ Integration Hub (MCP-first)
        │    · Slack, Gmail, GitHub, Stripe, QuickBooks,
        │      Figma, CRM, Calendar via MCP servers
        ├─ Ledger Service
        │    · usage metering per provider, cost normalization,
        │      alerts and projections
        └─ Data Layer
             · Postgres (objects), Redis (state/queues),
               S3 (attachments), pgvector (memory/RAG)
```

**Why MCP-first for integrations:** every external tool is wrapped as an MCP server, so agents (regardless of the model behind them) get one uniform tool interface, and new tools plug in without touching agent code.

## 7. Guardrails & Trust

- Every executor action is logged to the Ops Log with cost and reason.
- Irreversible or spend-heavy actions require an Approval Gate (surfaced in Chat and Home).
- Per-agent and per-provider budget caps with auto-terminate.
- Role-based permissions: team members see only their businesses and agents.

## 8. Success Metrics

- Time from command to completed mission (target: under 10 minutes for standard ops).
- % of missions completed without human intervention (target: 70% by v1).
- Cost per completed mission trending down via Selector efficiency.
- Weekly active Commander sessions and approvals per week.

## 9. Milestones

| Phase | Scope | Target |
|---|---|---|
| 0 · Prototype | This UI shell, mocked data, protocol toggle | Done |
| 1 · Skeleton | Auth, data model, chat with real Orchestrator routing (Opus/Fable/GPT 5.5) | 3 weeks |
| 2 · Shadow v1 | Executor spawning, Selector v1, budget guards, ops log | +4 weeks |
| 3 · Integrations | MCP hub: Slack, Gmail, Stripe, GitHub; credit ledger live | +4 weeks |
| 4 · Team | Multi-user roles, approval gates, dependency map | +3 weeks |

## 10. Open Questions

1. Which single integration proves the most value first (Slack, Gmail, or Stripe)?
2. Should Shadow executors run on cheaper models by default (Haiku-class) with escalation, or let the Selector choose freely?
3. Mobile-first PWA or native app for v1?
4. What is the monthly AI budget ceiling Dexter should enforce out of the box?
