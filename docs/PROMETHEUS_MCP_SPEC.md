# Prometheus MCP Integration Spec — Dexter/Anthony ↔ Prometheus

> **Purpose:** This document tells a backend engineer exactly what to build so that
> Dexter (Orchestrator) and Anthony (Shadow executor) can read work from, and write
> results back to, the Prometheus project-management platform over MCP.
>
> **Date:** 2026-09-21  
> **Owner:** XD (xd.olayinka@gmail.com)  
> **Consumers:** Dexter backend (`server/` — Python FastAPI), Anthony executor agents  
> **Provider:** Prometheus backend (`apps/web/convex/` — Convex)

---

## 1. Integration Model

```
┌─────────────────────────────────┐          MCP (stdio / HTTP+SSE)          ┌──────────────────────────────┐
│  DEXTER (Orchestrator)          │──────────────────────────────────────────▶│  PROMETHEUS MCP SERVER        │
│  · reads projects/issues        │                                          │  · Convex HTTP actions        │
│  · plans work, generates briefs │◀─────────────────────────────────────────│  · single write path          │
│                                 │                                          │  · append-only activity       │
│  ANTHONY (Shadow Executor)      │──────────────────────────────────────────│  · per-member token auth      │
│  · picks issues from queue      │          (same MCP connection)           │  · scoped permissions         │
│  · runs tool loop, posts result │                                          └──────────────────────────────┘
│  · transitions states           │
└─────────────────────────────────┘
```

**Key principle:** Dexter and Anthony are *external AI tools* in Prometheus's model (doc 10 §3,
lane 3 "External MCP client"). They connect over MCP like any Claude Code or Cursor instance.
Prometheus is the system of record — Dexter/Anthony never bypass the single write path.

### 1.1 Connection Modes

| Mode | Transport | When |
|---|---|---|
| **Local dev** | stdio | Owner runs Prometheus MCP sidecar on the same machine as the Dexter backend |
| **Hosted** | Streamable HTTP + SSE | Prometheus deployed (Convex Cloud); Dexter backend reaches it over HTTPS |

### 1.2 Authentication

Prometheus issues **per-member MCP tokens** (Settings → Connections). For the Dexter/Anthony
integration, the Owner mints a token scoped to their own identity. All writes are attributed to
`actorType: 'agent'` with the Owner as the parent member.

Token setup:
1. Owner opens Prometheus → Settings → Connections
2. Clicks "Create MCP connection" → copies the token
3. Pastes into Dexter's `server/.env` as `DEXTER_PROMETHEUS_MCP_TOKEN`
4. Dexter backend registers the Prometheus MCP as a tool source at startup

---

## 2. Prometheus MCP Tool Catalog

These are the tools Prometheus's MCP server exposes (per doc 10 §4 + doc 07 §5.2).
The Dexter backend must be able to call each one.

### 2.1 Read Tools (Dexter uses these for planning/briefings)

| Tool | Input | Output | Dexter Use |
|---|---|---|---|
| `list_issues` | `{team_id?, project_id?, assignee_id?, state?, priority?, limit?, offset?}` | `Issue[]` (token-lean Markdown per §9.1) | Morning briefing, workload scan, sprint planning |
| `get_issue` | `{issue_id}` | Full issue Markdown (spec + context blocks + relations + artifacts + activity) | Deep context before delegating to Anthony |
| `my_queue` | `{}` | Issues assigned to the token's member: pickable + in-progress | Anthony checks what work is available |
| `list_dependencies` | `{issue_id?}` | Blocker/blocked-by graph for an issue or the member's queue | Dexter checks dependency chains before scheduling |
| `list_projects` | `{status?, limit?}` | `Project[]` summary (name, health, progress, lead, dates) | Dashboard/briefing data |
| `get_project` | `{project_id}` | Full project: overview, issues summary, stakeholders, workspace docs | Dexter loads project context for planning |
| `list_teams` | `{}` | `Team[]` (name, key, member count, active cycle) | Context for routing work |
| `get_workload` | `{team_id?, cycle_id?}` | Per-member capacity/committed/completed/pending | Dexter uses for load-balancing delegation |

### 2.2 Write Tools (Anthony uses these to execute work)

| Tool | Input | Output | Anthony Use |
|---|---|---|---|
| `pick_issue` | `{issue_id}` | Updated issue (now assigned to token's member) | Anthony claims work from the queue |
| `update_issue` | `{issue_id, patch: {description?, checklist_ticks?, artifact_link?, progress_note?}}` | Updated issue + `activity_id` | Anthony posts progress/attaches artifacts |
| `transition_issue` | `{issue_id, to_state, reason?}` | `{ok, gated?}` — may return `proposal_id` if approval-required | Anthony moves issues through workflow |
| `post_feedback` | `{issue_id, body, artifact_links?}` | Comment + `activity_id` | Anthony posts completion report |
| `comment_issue` | `{issue_id, body}` | Comment + `activity_id` | Dexter/Anthony add notes |
| `create_issue` | `{team_id, title, description?, spec?, priority?, assignee_id?, labels?, project_id?}` | New issue + `activity_id` | Dexter creates sub-tasks discovered during planning |
| `link_issues` | `{source_id, target_id, type: 'blocks'|'relates'|'duplicates'}` | Relation + `activity_id` | Dexter creates dependency links |
| `attach_artifact` | `{issue_id, kind: 'repo'|'branch'|'pr'|'commit'|'deploy', url, ref?, sha?}` | ArtifactLink + `activity_id` | Anthony attaches PRs/commits |

### 2.3 MCP Resources (read-only data Dexter can fetch by URI)

| Resource URI | Returns |
|---|---|
| `prometheus://issue/{id}.md` | Issue in canonical Markdown (§9.1) |
| `prometheus://project/{id}/brief.md` | Project brief: overview docs, work orders, blueprints |
| `prometheus://team/{key}/board.md` | Team board snapshot (columns + issue summaries) |
| `prometheus://workspace/context.md` | Workspace context (stack, DoD, AI dos/don'ts) |

---

## 3. What Dexter/Anthony Need Built (Dexter Backend Side)

These are changes to `server/` in the Dexter repo.

### 3.1 MCP Client Module — `server/mcp/prometheus.py`

A new module that wraps the Prometheus MCP connection:

```python
# Pseudo-structure — the real implementation uses @modelcontextprotocol/sdk
# or a Python MCP client library

class PrometheusMCP:
    """Client for the Prometheus MCP server."""

    def __init__(self, token: str, endpoint: str):
        self.token = token        # DEXTER_PROMETHEUS_MCP_TOKEN
        self.endpoint = endpoint  # DEXTER_PROMETHEUS_MCP_URL

    # Read tools — used by Dexter (Orchestrator)
    async def list_issues(self, **filters) -> list[dict]: ...
    async def get_issue(self, issue_id: str) -> dict: ...
    async def my_queue(self) -> list[dict]: ...
    async def list_dependencies(self, issue_id: str = None) -> list[dict]: ...
    async def list_projects(self, **filters) -> list[dict]: ...
    async def get_project(self, project_id: str) -> dict: ...
    async def list_teams(self) -> list[dict]: ...
    async def get_workload(self, team_id: str = None, cycle_id: str = None) -> dict: ...

    # Write tools — used by Anthony (Executor)
    async def pick_issue(self, issue_id: str) -> dict: ...
    async def update_issue(self, issue_id: str, patch: dict) -> dict: ...
    async def transition_issue(self, issue_id: str, to_state: str, reason: str = "") -> dict: ...
    async def post_feedback(self, issue_id: str, body: str, artifacts: list = None) -> dict: ...
    async def comment_issue(self, issue_id: str, body: str) -> dict: ...
    async def create_issue(self, team_id: str, title: str, **kwargs) -> dict: ...
    async def link_issues(self, source_id: str, target_id: str, type: str) -> dict: ...
    async def attach_artifact(self, issue_id: str, kind: str, url: str, **kwargs) -> dict: ...

    # Resources
    async def read_resource(self, uri: str) -> str: ...

    # Health
    async def health(self) -> bool: ...
```

### 3.2 Config Additions — `server/config.py`

```python
# New env vars
prometheus_mcp_token: str = ""       # DEXTER_PROMETHEUS_MCP_TOKEN
prometheus_mcp_url: str = ""         # DEXTER_PROMETHEUS_MCP_URL (empty = not connected)
prometheus_mcp_transport: str = "http"  # "stdio" | "http"
```

### 3.3 Tool Registration — `server/tools/prometheus_tools.py`

Register Prometheus as tools in the existing tool registry so Anthony's executor loop
can call them via the Brain's function-calling interface:

```python
# Each tool wraps a PrometheusMCP method
# Example — the executor sees these as callable tools:
Tool(name="prometheus_list_issues", description="List issues from Prometheus filtered by team/project/state/assignee", ...)
Tool(name="prometheus_get_issue", description="Get full issue details from Prometheus including spec, context, and dependencies", ...)
Tool(name="prometheus_pick_issue", description="Claim an issue from the Prometheus queue (assigns to you)", ...)
Tool(name="prometheus_update_issue", description="Post a progress update or attach artifacts to a Prometheus issue", ...)
Tool(name="prometheus_transition_issue", description="Move a Prometheus issue to a new workflow state", ...)
Tool(name="prometheus_post_feedback", description="Post a completion report to a Prometheus issue", ...)
Tool(name="prometheus_create_issue", description="Create a new issue in Prometheus", ...)
Tool(name="prometheus_link_issues", description="Create a dependency link between two Prometheus issues", ...)
Tool(name="prometheus_attach_artifact", description="Attach a PR/commit/branch/deploy to a Prometheus issue", ...)
```

### 3.4 Status & Settings — `server/status.py` + Frontend

Add a Prometheus connection status to `/api/status`:
```json
{
  "prometheus": {
    "connected": true,
    "url": "https://prometheus.convex.cloud/.../mcp",
    "workspace": "ZinoDev",
    "member": "Zino Adidi"
  }
}
```

Frontend: new ConnRow in Settings → Core Systems for "Prometheus · PM".

### 3.5 Dexter Orchestrator Workflows

These are the high-value workflows Dexter should run using Prometheus data:

| Workflow | Trigger | Prometheus Tools Used | Output |
|---|---|---|---|
| **Morning Briefing** | Daily / on-demand | `list_projects`, `my_queue`, `get_workload`, `list_issues(state=blocked)` | Spoken/written brief: active projects, today's queue, blockers, capacity |
| **Sprint Planning** | On-demand | `list_issues`, `list_dependencies`, `get_workload` | Suggested issue assignments, dependency warnings, capacity check |
| **Issue Deep Dive** | Before delegation | `get_issue`, `list_dependencies` | Full context package for Anthony before execution |
| **Delegation** | User command / auto | `pick_issue`, then Anthony runs the tool loop | Anthony claims + executes + reports |
| **Progress Sync** | After Anthony completes | `post_feedback`, `transition_issue`, `attach_artifact` | Issue updated in Prometheus with result |
| **Dependency Watch** | Periodic | `list_dependencies` for in-progress work | Alerts when a blocker is resolved or a new one appears |
| **Project Health** | On-demand | `get_project`, `list_issues` | Health summary with risk flags |

---

## 4. What Prometheus Needs Built (Prometheus Backend Side)

These are the requirements for the Prometheus backend engineer to make the MCP server
work for Dexter/Anthony.

### 4.1 MCP Server — `apps/web/convex/mcp/` (Priority 1)

Build the MCP HTTP surface as Convex HTTP actions. This is the §4 tool set from doc 10,
but with specific attention to what Dexter/Anthony need:

**Required tools (build first):**

1. **`list_issues`** — Query by team/project/assignee/state/priority with pagination.
   Return token-lean Markdown (§9.1 format), not full JSON. Max 50 per page.

2. **`get_issue`** — Full issue with spec sections, context blocks, relations (blocks/blocked-by),
   artifact links, and recent activity (last 20 entries). Returns §9.1 Markdown.

3. **`my_queue`** — Issues assigned to the token's member in states: Unstarted, Started, In Review.
   Ordered by priority then due date. This is the primary "what should I work on" query.

4. **`pick_issue`** — Assign an issue to the token's member. Writes activity
   `{action: 'assigned', actor_type: 'agent', before: {assignee: null}, after: {assignee: member}}`.
   Fails if already assigned to someone else (return the current assignee).

5. **`update_issue`** — Partial patch: progress notes (appended to description or as comment),
   checklist ticks (by `ac_id`), artifact links. Each field is optional. Writes activity.

6. **`transition_issue`** — State change request. Runs gate evaluation. If gates pass, transitions
   and writes activity. If a gate requires approval, creates a `proposal` and returns
   `{ok: false, gated: true, proposal_id, gates: [{key, status, reason}]}`.
   The proposal appears in Prometheus's Approvals queue for the human to resolve.

7. **`post_feedback`** — Create a comment attributed to the agent (the member's tool),
   with optional artifact links in the same mutation. This is how Anthony reports results.

8. **`comment_issue`** — Plain comment. Simpler than `post_feedback` (no artifacts).

9. **`create_issue`** — Create with at least: team_id, title. Optional: description, spec
   (context/requirements/acceptance_criteria), priority, assignee_id, labels, project_id,
   parent_id (for sub-issues). Server generates identifier. Writes activity.

10. **`link_issues`** — Create a relation. For `blocks` type, run DAG validation
    (`fn_validate_blocks_link`). Writes activity.

11. **`attach_artifact`** — Add an artifact link (branch/PR/commit/deploy) to an issue.
    Writes activity.

12. **`list_dependencies`** — For a given issue or the member's queue, return blocks/blocked-by
    with current state of each linked issue.

13. **`list_projects`** — Summary list with progress rollup.

14. **`get_project`** — Full project including workspace docs (ProjectDoc summaries from the
    Work-Order Factory), work orders assigned to the member, and recent activity.

15. **`list_teams`** — Team list with active cycle info.

16. **`get_workload`** — Per-member capacity data for a team/cycle.

**MCP resources (build second):**

- `prometheus://issue/{id}.md` — canonical Markdown
- `prometheus://project/{id}/brief.md` — project brief (all ProjectDocs concatenated)
- `prometheus://team/{key}/board.md` — board snapshot
- `prometheus://workspace/context.md` — the workspace context blob (stack, DoD, AI rules)

### 4.2 Token Auth — `apps/web/convex/mcp/auth.ts` (Priority 1)

The existing Connections system (doc 12 §2) already defines `createMcpConnection` /
`revokeMcpConnection`. Extend it:

- Token is a bearer in the `Authorization` header of MCP HTTP requests
- Server resolves token → member → workspace → role
- Every MCP write includes `actor_type: 'agent'` and the resolved `member_id` in the activity row
- Rate limit: configurable per token (default 60 req/min)
- Token carries scopes: `['read', 'write', 'transition', 'link', 'comment', 'close']`
- Scope enforcement happens at the MCP layer before calling the write-path mutation

### 4.3 Response Format Conventions

All tool responses follow the existing RPC contract from doc 07 §2.5:

**Success:** `{ok: true, data: {...}, activity_id: "act_..."}`

**Failure:** `{ok: false, code: "ALREADY_ASSIGNED" | "DAG_CYCLE" | "GATE_BLOCKED" | ..., message: "...", detail: {...}}`

**Gated:** `{ok: false, gated: true, proposal_id: "prop_...", gates: [{key, status, reason}]}`

Issue data in responses uses the §9.1 canonical Markdown format — token-lean, not full JSON.
This keeps Dexter/Anthony's context window efficient.

### 4.4 Activity Attribution

Every MCP write must produce exactly one `activity` row with:

```json
{
  "actor_type": "agent",
  "actor_id": "<member_id>",
  "actor_agent_name": "Dexter" | "Anthony",
  "tool_name": "<mcp_tool_name>",
  "entity_type": "issue" | "comment" | "relation" | ...,
  "entity_id": "<id>",
  "action": "assigned" | "state_changed" | "commented" | ...,
  "payload": { "before": {...}, "after": {...} }
}
```

The `actor_agent_name` should be passed as an optional parameter on MCP tool calls
so Prometheus can distinguish Dexter (planning) from Anthony (executing) in the audit trail.

### 4.5 Gate Integration

When Anthony calls `transition_issue` and a gate blocks the transition:

1. Prometheus creates a `proposal` (not a live mutation)
2. Returns `{gated: true, proposal_id, gates: [...]}`
3. The proposal appears in Prometheus's Approvals queue
4. Owner/Admin approves or rejects in the Prometheus UI
5. Anthony can poll `get_issue` to see when the state changed (or rely on a webhook)

For Dexter, the gate response is intelligence: if a transition is blocked, Dexter
should tell the user why and what's needed (e.g., "QA check pending" or "PR must be merged").

---

## 5. Dexter/Anthony Workflow Scripts (to Build in Dexter)

### 5.1 Morning Briefing Script

```
1. Call prometheus.list_projects(status="in_progress")
2. Call prometheus.my_queue()
3. Call prometheus.get_workload(team_id=<primary_team>)
4. Call prometheus.list_issues(state="blocked", assignee_id=<owner>)
5. Synthesize into a brief:
   - Active projects + health
   - Today's queue (sorted by priority)
   - Blocked issues + what's blocking them
   - Capacity utilization
6. Present to user as spoken brief or dashboard card
```

### 5.2 Anthony Issue Execution Script

```
1. Dexter calls prometheus.get_issue(issue_id) — loads full context
2. Dexter evaluates: is this within Anthony's capability? (code task, research, etc.)
3. Dexter calls prometheus.pick_issue(issue_id) — claims it
4. Dexter delegates to Anthony with the issue context as the task brief
5. Anthony executes using its tool loop:
   a. Read the spec/requirements/acceptance criteria
   b. Use registered tools (web search, filesystem, etc.) to complete the work
   c. Call prometheus.update_issue() with progress notes
   d. Call prometheus.attach_artifact() if there are PRs/commits
   e. Call prometheus.post_feedback() with the completion report
   f. Call prometheus.transition_issue() to move to "In Review" or "Done"
6. If transition is gated → Anthony reports back to Dexter → Dexter notifies user
7. Dexter logs the result + cost in its own spend tracker
```

### 5.3 Dependency-Aware Planning

```
1. User asks Dexter to plan work for a project
2. Dexter calls prometheus.get_project(project_id) — loads brief + work orders
3. Dexter calls prometheus.list_issues(project_id=...) — current issues
4. Dexter calls prometheus.list_dependencies(issue_id=...) for each — builds graph
5. Dexter calls prometheus.get_workload() — team capacity
6. Dexter reasons over: brief goals vs current issues vs dependencies vs capacity
7. Dexter proposes:
   - New issues to create (via prometheus.create_issue)
   - Dependency links (via prometheus.link_issues)
   - Assignment suggestions based on workload
8. User approves → Dexter executes the batch
```

---

## 6. Config & Env Vars

### Dexter side (`server/.env`)

```bash
# Prometheus MCP connection
DEXTER_PROMETHEUS_MCP_TOKEN=           # from Prometheus Settings → Connections
DEXTER_PROMETHEUS_MCP_URL=             # e.g. https://your-convex.cloud/.../mcp  (empty = not connected)
DEXTER_PROMETHEUS_MCP_TRANSPORT=http   # "stdio" for local, "http" for hosted
```

### Prometheus side (Convex env / dashboard)

```bash
# No Dexter-specific config needed — Prometheus uses its existing
# per-member token system. The token Dexter holds is just a
# standard MCP connection token minted in Settings.
```

---

## 7. Build Priority Order

### Prometheus backend engineer builds (in order):

1. **MCP HTTP action scaffold** — route MCP tool calls to Convex mutations
2. **Token auth middleware** — resolve bearer → member → workspace → role
3. **Read tools first** — `list_issues`, `get_issue`, `my_queue`, `list_projects`, `get_project`, `list_teams`, `get_workload`, `list_dependencies`
4. **Write tools** — `pick_issue`, `update_issue`, `transition_issue`, `post_feedback`, `comment_issue`
5. **Create tools** — `create_issue`, `link_issues`, `attach_artifact`
6. **MCP resources** — the `prometheus://` URI handlers
7. **Gate integration** — proposal creation on blocked transitions
8. **Rate limiting + scope enforcement**

### Dexter backend builds (in parallel):

1. **`server/mcp/prometheus.py`** — MCP client wrapper
2. **`server/tools/prometheus_tools.py`** — register as executor tools
3. **Config additions** — env vars, status endpoint
4. **Frontend** — Prometheus ConnRow in Settings
5. **Briefing workflow** — morning brief using read tools
6. **Delegation workflow** — Anthony picks + executes + reports
7. **Planning workflow** — dependency-aware issue creation

---

## 8. Testing Plan

### Integration smoke test

1. Mint a Prometheus MCP token
2. Dexter calls `list_teams` → verify team data returns
3. Dexter calls `list_issues` → verify issue list in §9.1 format
4. Dexter calls `get_issue` on a specific issue → verify full spec
5. Anthony calls `pick_issue` → verify assignment in Prometheus UI
6. Anthony calls `post_feedback` → verify comment appears in Prometheus
7. Anthony calls `transition_issue` → verify state change (or gate block)

### End-to-end delegation test

1. Create an issue in Prometheus (manually)
2. Ask Dexter: "What's in my queue?"
3. Dexter reads from Prometheus, shows the issue
4. Ask Dexter: "Delegate PRM-42 to Anthony"
5. Dexter loads the issue context, delegates to Anthony
6. Anthony picks the issue, runs tool loop, posts result
7. Verify in Prometheus: issue assigned, commented, state changed, activity trail shows agent attribution

---

## 9. Security Considerations

- **Token is the owner's identity** — any MCP write through this token is attributed to the owner.
  Anthony's work shows as the owner's agent in the audit trail.
- **Never store the token in code** — `.env` only, gitignored.
- **Scope the token minimally** — `['read', 'write', 'transition', 'comment']` is sufficient.
  Avoid granting `close` until Anthony's reliability is proven.
- **Rate limits protect Prometheus** — the MCP server enforces per-token rate limits.
  Dexter's executor loop should also self-throttle (existing budget system handles this).
- **Gate-gated transitions are the safety net** — configure critical workflow states (e.g., Done)
  to require human approval. Anthony's `transition_issue` call creates a proposal instead of
  a live mutation; the owner approves in Prometheus.

---

## 10. Open Questions for the Backend Engineer

1. **Convex Cloud → localhost bridge:** The local Ollama model in Prometheus can't be reached from
   Convex Cloud functions. Doc 10 §7 parks three options: (a) local sidecar, (b) self-host Convex,
   (c) local companion process. This doesn't block the MCP server build (MCP is pure Convex HTTP
   actions), but it affects whether the local orchestrator can be tested end-to-end.

2. **MCP SDK choice:** Prometheus's MCP server should use `@modelcontextprotocol/sdk` (Node/TS).
   Dexter's client is Python — use `mcp` (the Python MCP SDK) or raw HTTP+SSE. Confirm SDK versions
   and protocol compatibility before building.

3. **Webhook vs polling for gate resolution:** After Anthony's `transition_issue` is gated, should
   Dexter poll `get_issue` or receive a Prometheus webhook when the owner approves? Webhook is better
   but requires the webhook pipeline (doc 07 §4.2) to be built first. Polling works immediately.

4. **Work-Order Factory integration:** Should Dexter be able to read/propose work orders through
   MCP, or only issues? The factory (doc 11) is Owner/Admin-only and currently uses the local
   orchestrator. If Dexter should participate, add `list_work_orders` and `get_work_order` tools.

5. **Multi-workspace:** If the owner has multiple Prometheus workspaces, should Dexter connect to
   all of them? For now, one token = one workspace. Multi-workspace support is a later concern.
