# Phase 3/4 + the rest of the vision — scoping & plan

**Date:** 2026-09-24, updated 2026-09-25. **Status: §1-§4 and §6-§7 below are built and tested**
(backend test count grows with each addition — see `server/tests/`; Prometheus side:
`mcpTools.test.ts`, 8 passing). §5 ("intentionally not done") is still exactly that. §4's MCP
bridge is now **verified live** against production Prometheus, not just spec-matched. **Reads with:** `05_PRD.md` (vision, §4 data model, §7 guardrails, §8 metrics,
§9 milestones), `docs/BUILD_PLAN.md` (Phase 2, done), `docs/PROMETHEUS_MCP_SPEC.md` (the
Dexter↔Prometheus integration, written 2026-09-21 by XD).

## Where this sits

Phase 2 ("make it real") is done — see `docs/BUILD_PLAN.md`. What's below is everything else the
PRD describes that isn't built yet: the multi-business/multi-person core (PRD Milestone 1's own
"Auth" item, never built even in Phase 0-1), persistent Agent identity (PRD §4's `Agent` object
doesn't exist as a row anywhere today — executors are ephemeral in-memory objects), the
Prometheus↔Dexter MCP bridge, and the success metrics PRD §8 defines but nothing counts.

## Priority order and why

1. **Auth + Business** — foundational. Nothing else in the PRD's data model (Team Member, a
   real Agent owner, per-business scoping) means anything with a single implicit user. Blocks
   Phase 3's integrations too (Slack/Gmail/GitHub credentials are per-business).
2. **Persistent Agent identity + real task history** — `task_log` has a table already but nothing
   writes to it; task/executor history is pure in-memory and lost on restart. Swarm's "efficiency
   score, fittest survive" narrative has zero backend today. Self-contained (no cross-repo work),
   fixes an honest gap, and metrics (next) need this data to exist first.
3. **Success metrics (PRD §8)** — builds directly on #2's real history. Currently nothing is
   measured: not time-to-completion, not intervention rate, not cost trend, not weekly actives.
4. **Prometheus↔Dexter MCP bridge** — the parts required of Prometheus, per
   `docs/PROMETHEUS_MCP_SPEC.md`. Both sides: Prometheus's MCP server needs 8 more tools it
   doesn't have; Dexter needs the client + tool registration to actually call them.
5. **Deferred, scoped but not built this pass** — see "What's intentionally not done" below.

---

## 1 · Auth + Business — shipped

`server/auth.py`, `server/db/schema.sql` (`businesses`/`users`/`business_members`/`sessions`),
`src/lib/auth.tsx`, `src/screens/Auth.tsx`. `projects.py`, `files.py`, `chat.py`'s memory recall,
and `shadow/router.py`'s `/delegate` are all scoped by `business_id`. The live `ExecutorManager`/
`GateManager` singletons are still process-wide (see §2's note), so `shadow/router.py` filters
live tasks and gates by the `business_id` stamped into `task.metadata` at spawn: another business's
task is a 404 for list/get/kill/approve/reject. That's route-level isolation on one machine, not a
full multi-tenant guarantee (budget snapshot and spend ledger are still global).

**Which routes need a session (with `DEXTER_REQUIRE_AUTH=true`):** everything except `/`,
`/api/status` (drives the offline/demo detection) and `/api/auth/{register,login}`. All of
`/api/shadow/*` and `/api/escalation/*` take `current_context` at the router level (2026-09-25 —
before that, kill, gate approve/reject, guard edits and spend were reachable without a session).
Guard edits (`PATCH /guards`, rule add/remove) additionally require owner/admin.


**Design decision:** no Clerk/Auth0 (the PRD's own suggestion) — this backend's stated philosophy
is "starts cleanly with zero external services," and requiring a third-party auth vendor before
the app runs at all breaks that. Built instead: a self-contained `users`/`sessions` system —
opaque bearer session tokens (hashed at rest), same shape as Prometheus's own MCP token pattern.

**Design decision:** auth is **off by default** (`DEXTER_REQUIRE_AUTH=false`) so the app you're
using today keeps working exactly as-is. Turn it on once you actually have a team. This mirrors
Prometheus's `ALLOW_OPEN_SIGNUP` env var precedent directly. With it off, every request is
attributed to an auto-created "default" user + business (same bootstrap-on-first-use pattern
Prometheus uses for its first workspace).

**Schema:** `businesses`, `users`, `business_members` (many-to-many, role owner/admin/member),
`sessions` (token_hash, user_id, expires_at). `projects`/`tasks` gain a nullable `business_id`
(nullable so existing local rows aren't orphaned).

**Backend:** `server/auth.py` — register/login/logout/me/invite, the `current_context` FastAPI
dependency (resolves the bearer session; returns the default owner context when
`DEXTER_REQUIRE_AUTH=false`), PBKDF2-SHA256 password
hashing (stdlib `hashlib`, no new native dependency).

**Frontend:** `src/lib/auth.tsx` (AuthProvider, mirrors `backend.tsx`'s pattern), a login/register
screen gating the shell when auth is required, `api.ts` attaches `Authorization: Bearer` to every
call, `/ws/chat` and `/ws/voice` take the token as a query param (browsers can't set WS headers).
Team screen (`Team()` in `Orch.tsx`) swaps its mock for real `business_members`.

## 2 · Persistent Agent identity + real task history — shipped

**Schema:** a real `agents` table (id, name, kind orchestrated/executor, model_route, status,
efficiency_score, budget_cap, owner_user_id, business_id, spawned_from_task_id, created_at). Every
`ExecutorManager.spawn()` call creates an `agents` row, and every task completion updates it and
writes to the already-defined-but-unused `task_log` table.

**Efficiency score, defined honestly:** `(1 / max(spend, $0.001)) * outcome_weight`, where
`outcome_weight` is 1.0 for `done`, 0.3 for `killed`/`gated`-then-approved, 0 for `killed` by a
guard trip — normalized 0-1 against the business's own recent tasks so it reads like the PRD's
"scores" language, not a fabricated number. This is a real, computed metric from real spend and
real outcomes — not the same thing as the PRD's aspirational "cost × capability × latency" scoring
across *candidate* agents before a task runs (that's a routing-time decision, covered by the
existing `escalation/router.py`; this is a post-hoc fitness score, which is what "fittest survive"
in the Swarm screen actually needs).

**Frontend:** `Swarm()` reads real `agents` rows (real efficiency, real status) instead of the
`SWARM` mock; offline/no-data still falls back to the mock, same pattern as every other screen.

`server/shadow/agents_store.py` (new), wired into `executor.py`'s spawn/gate/completion paths and
`shadow/router.py`'s `GET /api/shadow/agents`. `src/screens/Shadow.tsx`'s `Swarm()` reads it.

## 3 · Success metrics (PRD §8) — shipped

New `server/metrics.py`, `GET /api/metrics/summary`, computed from `task_log` + `gates` history
(once #2 makes both real) + `conversations`:

| PRD metric | Computed as |
|---|---|
| Time from command to completed mission | median/p90 of `completed_at - created_at` for `done` tasks, trailing 7/30 days |
| % of missions completed without human intervention | `done` tasks that never passed through `gated` ÷ all terminal tasks |
| Cost per completed mission, trending down | avg `spend` per `done` task, bucketed weekly, as a sparkline-ready series |
| Weekly active Commander sessions / approvals per week | distinct `conversations` in the last 7 days / count of resolved gates in the last 7 days |

**Frontend:** a small "Vitals" card on `OrchHome`, and a fuller view is reasonable to add to
Settings or a new screen later — scoped here as the API + the Home card only, not a dedicated
analytics screen (that's a design decision worth a real pass, not a bolt-on).

`server/metrics.py` (new), `GET /api/metrics/summary`. `OrchHome`'s new "Vitals" card in
`src/screens/Orch.tsx` shows all four. Needed a `was_gated` sticky flag added to `task_log` and a
new `GateManager.list_resolved_since()` — see the file for why gate history isn't business-scoped.

## 4 · Prometheus↔Dexter MCP bridge — shipped

**One deviation from the spec's suggested paths:** the client lives at
`server/integrations/prometheus_mcp.py`, not `server/mcp/prometheus.py` — a local package named
`mcp` would shadow the real `mcp` PyPI package (the official MCP Python SDK) for anything imported
after it. Tools are registered in `server/tools/prometheus_tools.py` as planned, gated on both
`DEXTER_PROMETHEUS_MCP_URL` and `_TOKEN` being set; `/api/status`'s new `prometheus` block and a
Settings ConnRow show connection state. **Not verified against a live Prometheus deployment** — no
`DEXTER_PROMETHEUS_MCP_URL` is configured anywhere in this environment; the wire format matches
Prometheus's `mcp/router.ts` as read from source, not as round-tripped.

Exactly `docs/PROMETHEUS_MCP_SPEC.md`'s §3/§4, split by repo:

**Prometheus side** (`apps/web/convex/mcp/tools.ts`, `router.ts`) — 8 new tools:
`list_projects`, `get_project`, `list_teams`, `get_workload` (reads), `comment_issue`,
`create_issue`, `link_issues`, `attach_artifact` (writes) — all through the existing single write
path (`lib/write.ts`), all gate-aware where relevant (`create_issue`/`link_issues` don't transition
state so gates don't apply; nothing here bypasses `requestTransition`). MCP *resources*
(`prometheus://...` URIs) are scoped **out** of this pass — most MCP clients (including what
Dexter's `mcp` Python SDK usage will need) work fine on tools alone, and resources are a genuinely
separate protocol surface Prometheus's router doesn't implement at all today; adding it well is
its own piece of work, not a quick add-on to this one.

**Dexter side** (`server/integrations/prometheus_mcp.py`, `server/tools/prometheus_tools.py`,
`config.py` additions, `status.py` + Settings ConnRow): a small MCP HTTP client (JSON-RPC over
POST, matching Prometheus's actual router — not the stdio transport the spec's §1.1 also
mentions, which is out of scope here since Prometheus only serves HTTP) wired into the existing
tool registry so Anthony's executor loop can call `prometheus_list_issues`,
`prometheus_pick_issue`, etc. directly. Skipped, per the same reasoning as above:
resource-URI fetching, and the stdio local-dev transport.

**Verified live, 2026-09-25.** The user minted a real MCP token against production Prometheus
(`prestigious-badger-5`) and it's set in `server/.env`. A direct call confirmed the whole round
trip: `health()` returned true, `list_teams()` and `list_projects()` returned the user's actual
"Dexter"/"Anthony" teams and projects, and `/api/status`'s `prometheus` block correctly reported
`connected: true`. This is no longer "matches the spec as read from source" — it's confirmed
against the real deployment. Note for anyone running the test suite from here on: with `.env`
configured, `tools/prometheus_tools.py` registers real `prometheus_*` tools and `/api/status`'s
Prometheus check makes one real (read-only) network call to production Prometheus per test run —
harmless, but it does add a `list_teams` entry to that workspace's `mcpCalls` audit log each time.

## 6 · Follow-ups from the first review pass — shipped

Three honest gaps flagged in the first "vision review" after §1-§4 landed, closed the same day:

- **No invite flow.** `register()` always created a *new* business — there was no way for a second
  person to actually join yours. Added `POST /api/auth/invite` (owner/admin) and taught `register`
  to recognize and *claim* a pending invite (a placeholder `users` row with an unusable
  `password_hash`) instead of creating a second business — mirrors Prometheus's own
  `claimPendingInvite` pattern. `Team()`'s "+ Invite" button is wired.
  **Hardened 2026-09-25:** claiming now needs a one-time invite code (`users.invite_code_hash`,
  hashed like session tokens). `invite` returns it once and the Team screen shows it for the
  inviter to pass on; re-inviting a still-pending email rotates it. Before this, anyone who knew
  an invited email could register first and take over the invite.
- **`agents.model_route` was never populated.** `shadow/router.py`'s `/delegate` now captures the
  Brain's actual `provider:model` at spawn time and threads it through `record_spawn`.
- **Metrics had no target to compare against.** PRD §8's own stated v1 targets (10 min
  time-to-completion, 70% without intervention) are now in `metrics.py`'s response as
  `targets` + a computed `on_track` per metric; the Vitals card shows an On track/Behind badge.

## 7 · Dependency map + multi-business switcher — shipped

Both flagged in §5 as needing a design decision, not just code; the user asked for a v1 built
against everything already real rather than waiting on a bespoke spec.

**Dependency map** (PRD §4's `Dependency` object: "edge linking business ↔ team ↔ agent ↔ tool").
New `server/dependencies.py`, `GET /api/dependencies/map`. Design choice: a labeled hierarchy
(business → members → agents each member owns → tools each agent *actually called*), not a
force-directed graph — the real relationships here nest cleanly (one owner per agent, one task per
tool call), so a graph-physics render would be decoration, not information. Every edge is
something that happened: a new `agent_tool_calls` table (one row per real tool invocation, written
best-effort from `tools/registry.py::execute`, threaded through `tools/caller.py` and
`shadow/work.py`) means an agent that never called a tool shows an empty list, never a fabricated
"might use" guess — keeps faith with NFR-4 (Explainable) and NFR-6 (Honesty), the two easiest to
cheat on with a nicer-looking fake graph. Rendered as a card on `Team()` (no new nav tab — Team is
already the "who's here" screen; "how they connect to agents and tools" is a coherent extension of
it, not a new IA surface).

**Multi-business switcher.** `sessions` gained `current_business_id` (set at login/register,
changeable via the new `POST /api/auth/switch-business`); `GET /api/auth/businesses` lists every
business a user belongs to. Settings → Account shows a switcher only when there's more than one
(the common case — one business — never sees it). Off (`DEXTER_REQUIRE_AUTH=false`) 400s the
switch endpoint rather than pretending, since there's exactly one business in that mode.

## 8 · Closing the PRD's remaining gaps — shipped 2026-09-25

The audit of PRD vs. code found these gaps that need no third-party account. All closed:

- **Selector Core was a keyword classifier + dry-run tester**, and Anthony's executors could only run
  on Ollama/DeepSeek (Anthropic/OpenAI/Groq were reachable only from the dry run). Now
  `shadow/selector.py` picks per task: required tier (classifier, or the Commander's explicit tier) →
  every configured model filtered by availability, tier, tool support, provider caps and budget →
  ranked by estimated cost ÷ observed success rate, then latency. Models with <50% success over ≥5
  runs are retired ("fittest survive"). `ModelGateway` runs the tool loop on any provider;
  `escalation/providers.py` now has tool calling for OpenAI/Groq (shared OpenAI-compatible base) and
  Anthropic (official SDK, tool_use ↔ Ollama tool_calls, thinking blocks passed back unchanged,
  refusal handling, server-side refusal fallback on Opus 5 / Fable 5.1). Roster: Claude Haiku 4.5 /
  Sonnet 5 / Opus 5 (`DEXTER_ANTHROPIC_MODEL`), Fable 5.1 opt-in (`DEXTER_SELECTOR_ALLOW_FABLE`),
  OpenAI model configurable (`DEXTER_OPENAI_MODEL`, price via `DEXTER_OPENAI_PRICE_IN/OUT`).
  `POST /api/shadow/selector/preview` shows the pick and every candidate's reason (Selector screen).
- **Credit ledger was two in-memory trackers** (reset on restart; no monthly budget, per-provider or
  per-agent cap, or burn alert). Now `ledger.py` + `spend_ledger` table: every executor, chat,
  briefing and Archive call is costed per business. Guardrails gain `monthly_budget`,
  `provider_monthly_caps`, `agent_daily_cap`, `burn_rate_alert_per_hour` (Settings → Guardrails);
  caps are checked **before every model call** (`SelectedBrain`, `_TrackedBrain`), so a tripped cap
  stops the task mid-run with the reason in its error. Alerts (burn rate, 80%/100% monthly, provider
  cap) push via ntfy at most hourly. `GET /api/ledger/summary` drives the Burn screen (month vs
  budget, projection, per-provider bars with caps, alerts).
- **Home's headline stats were hardcoded** (1,284 tasks / $482K / 312 hrs, a fictional testimonial,
  a fake ops log, "Slack · GH · Email" channels). With the backend up, `GET /api/metrics/headline`
  feeds them: tasks terminated from `task_log`; revenue enabled = Σ `revenue_value` tagged when
  delegating (shown as "—" until something is tagged); hours reclaimed = Σ `minutes_saved` (tasks
  without one count `DEXTER_DEFAULT_MINUTES_SAVED`, and the tooltip says how many); burn from the
  ledger. The briefing headline, latest Anthony report and live ops rows replace the showcase copy;
  offline demo mode keeps it, labeled "demo data".
- **Runs weren't durable.** Executors are still in-memory, but on startup anything left
  queued/running/gated is marked `interrupted` in history and re-spawned as a new task linked by
  `resumed_from` (`DEXTER_RESUME_INTERRUPTED=false` to only mark).
- **PWA** (PRD open question 3): manifest, icon, and an app-shell service worker (never caches API
  calls — offline the app falls back to demo mode as before).
- **Archive v1** (Phase 6): `archive.py` — notebooks group ingested documents; `ask` answers only
  from the notebook's passages (BM25 retrieval, works without embeddings) with numbered citations;
  `briefing` writes a DEXTER/ANTHONY two-voice script and synthesizes it with the Orchestrator and
  Shadow Piper voices when voice is installed (script-only otherwise). Settings → Archive.
- **Hosting readiness:** `server/Dockerfile` + `docker-compose.yml` (API + pgvector Postgres). Where
  to host is still a decision, not code.
- **Prometheus bridge:** Dexter now registers 19 `prometheus_*` tools — the 16 originals plus
  `prometheus_read_resource` (MCP resources) and `prometheus_my_gate_checks` /
  `prometheus_report_gate_check`, so Anthony can vote on Prometheus `agent_check`/`consensus` gates.

## 9 · Line-by-line pass — shipped 2026-09-26

A second, line-by-line read of the PRD found surfaces that were still demo copy or had no backend.
All closed (`server/ops.py` unless noted; tests in `server/tests/test_ops.py`):

- **Run Log** (Shadow Ops) was the `RUN_LOG` mock. `GET /api/ops/runlog` merges `task_log` spawns and
  completions (with reason and cost), `agent_tool_calls`, pending gates and ledger alerts, newest first.
- **Chat quick actions** were canned strings sent as messages, and the live chat opened on a scripted
  exchange. Live chat now opens with an honest line; the pills act: Approve all gates, Delegate to
  Anthony (the draft or last ask), Latest result, Hold; on Anthony's side Approve gate, Kill executor,
  Force spawn, Raise cap (+25% daily). Demo mode keeps the scripted thread.
- **Hold** — `POST /api/ops/hold`: while on, every newly delegated task parks at a "Commander hold"
  gate (`executor.py`) until approved. Per business, in-process (resets on restart — deliberate: a
  hold should never silently outlive the session that set it).
- **Spawn templates** — `spawn_templates` table, CRUD and one-click spawn (tier, budget, minutes
  saved, priority). Shadow Ops: "Save template" and a pill per template.
- **Mission priority** — `priority` on delegate (critical/high/normal/low), shown on tasks and used
  to sort the task list.
- **Standing preferences** — the FactStore had no writer. Chat now detects "remember…", "from now
  on…", "always/never…", "I prefer…", "my X is…" (never questions), saves them per business
  (`standing` facts, business-scoped keys), injects them into every chat's context, and "forget…"
  drops them. Settings → Standing preferences lists and forgets them.
- **Per-business budget** — `/api/shadow/budget` read a process-global tracker; it now reads today's
  spend for the caller's business from the persistent ledger.
- **Team** — presence (`sessions.last_seen_at`, Online/Away + last seen), team load from Prometheus
  (`list_teams` + `get_workload`, which now returns member names), and an Agents card: throughput
  (today / 7 days) and this month's routing split by model from the ledger.
- **Archive** — its own tab. Retrieval blends BM25 with embedding similarity when an embedding model
  answers (`archive.rank_hybrid`), so a passage that answers in other words can surface.
- **URL ingest** falls back to a Playwright render for JS-heavy pages (< 400 chars of text from raw
  HTML) when Playwright is installed.

- **Chat uses tools** (`server/chat_tools.py`, 2026-09-28) — per PROMETHEUS_MCP_SPEC §2, Dexter reads
  and Anthony writes: chat runs the read-only tools (Prometheus reads, web search, browser, clock) on
  its own and shows "Checking Prometheus…" while it does; any Prometheus change is a `propose_action`
  card the Commander confirms (`POST /api/ops/actions/{id}/confirm`). File tools never reach chat.

## What's intentionally not done this pass

- **Slack/Gmail/GitHub/Stripe integrations (Phase 3 proper).** Each needs an OAuth app registered
  with that provider — a client ID/secret only the product owner can obtain (a Slack app, a Google
  Cloud OAuth client, a GitHub OAuth App, a Stripe Connect app). I can build the generic
  integration-hub scaffolding once real credentials for at least one exist; building it against
  nothing would be scaffolding for its own sake.
- **The Archive vault** (Phase 6) — v1 shipped (§8), own screen and hybrid retrieval (§9). Not
  yet: per-notebook chat history.
- **Deploying the Dexter backend anywhere but the Commander's own machine.** The frontend deploys
  to GitHub Pages; the backend is now containerized (`server/Dockerfile`, `docker-compose.yml`) but
  has not been deployed to a host. That needs a hosting decision and an account.
