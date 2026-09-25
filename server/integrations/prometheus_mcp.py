"""MCP client for Prometheus (docs/PROMETHEUS_MCP_SPEC.md, docs/PHASE_3_4_PLAN.md §4).

Deliberately NOT named `server/mcp/...` (the spec's own suggested path) — a local
package named `mcp` would shadow the real `mcp` PyPI package (the official Model
Context Protocol Python SDK) for anything imported after it, which matters if this
backend ever adopts that SDK for a *different* MCP server. This is also not using
that SDK itself: Prometheus's router speaks plain JSON-RPC 2.0 over HTTP POST (see
its own `docs/PROMETHEUS_MCP_SPEC.md` §1.1 "Hosted" mode) with no session/SSE
handshake required by the actual server implementation, so a ~40-line httpx client is
the whole surface — pulling in the full SDK for one bespoke Convex endpoint would be
the heavier, not the simpler, choice. The stdio "local dev" transport the spec also
mentions is out of scope; Prometheus only serves HTTP.

Every call is real, but this repo has never run against a live Prometheus deployment
(no `DEXTER_PROMETHEUS_MCP_URL` configured anywhere in this environment) — the wire
format matches Prometheus's `mcp/router.ts` exactly as read from its source, not as
verified against a live round trip.
"""
from __future__ import annotations

import json
import logging

import httpx

log = logging.getLogger("dexter.integrations.prometheus")


class PrometheusMCPError(RuntimeError):
    pass


class PrometheusMCP:
    def __init__(self, url: str, token: str, timeout: float = 20.0):
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._next_id = 0

    async def _call(self, tool: str, args: dict) -> dict:
        self._next_id += 1
        body = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": "tools/call",
            "params": {"name": tool, "arguments": {k: v for k, v in args.items() if v is not None}},
        }
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(self.url, json=body, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise PrometheusMCPError(f"Prometheus MCP unreachable: {e}") from e

        # Protocol-level failure (bad auth, unknown method): {jsonrpc, id, error: {code, message}}
        if "error" in data:
            raise PrometheusMCPError(data["error"].get("message", "Prometheus MCP protocol error"))

        result = data.get("result", {})
        content = result.get("content") or []
        text = content[0]["text"] if content and content[0].get("type") == "text" else "{}"
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = {"raw": text}

        # Tool-level failure: {content:[{text: '{"error": "..."}'}], isError: true}
        if result.get("isError"):
            message = parsed.get("error") if isinstance(parsed, dict) else str(parsed)
            raise PrometheusMCPError(message or "Prometheus tool call failed")
        return parsed

    async def read_resource(self, uri: str) -> str:
        """MCP resources/read — Prometheus's token-lean Markdown views (issue, project brief,
        team board, workspace context), scoped to the token's member."""
        self._next_id += 1
        body = {"jsonrpc": "2.0", "id": self._next_id, "method": "resources/read", "params": {"uri": uri}}
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(self.url, json=body, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise PrometheusMCPError(f"Prometheus MCP unreachable: {e}") from e
        if "error" in data:
            raise PrometheusMCPError(data["error"].get("message", "Prometheus resource read failed"))
        contents = data.get("result", {}).get("contents") or []
        return "\n\n".join(c.get("text", "") for c in contents)

    async def my_gate_checks(self) -> dict:
        return await self._call("my_gate_checks", {})

    async def report_gate_check(self, proposal_id: str, gate_id: str, verdict: str, detail: str | None = None) -> dict:
        return await self._call("report_gate_check", {"proposalId": proposal_id, "gateId": gate_id, "verdict": verdict, "detail": detail})

    async def health(self, timeout: float | None = None) -> bool:
        original = self.timeout
        if timeout is not None:
            self.timeout = timeout
        try:
            await self._call("list_teams", {})
            return True
        except Exception as e:
            log.warning("Prometheus MCP health check failed: %s", e)
            return False
        finally:
            self.timeout = original

    # ---------------- reads ----------------
    async def list_issues(self, **filters) -> dict:
        return await self._call("list_issues", filters)

    async def get_issue(self, issue_id: str) -> dict:
        return await self._call("get_issue", {"issueId": issue_id})

    async def my_queue(self) -> dict:
        return await self._call("my_queue", {})

    async def list_dependencies(self, issue_id: str | None = None) -> dict:
        return await self._call("list_dependencies", {"issueId": issue_id})

    async def list_projects(self, status: str | None = None, limit: int | None = None) -> dict:
        return await self._call("list_projects", {"status": status, "limit": limit})

    async def get_project(self, project_id: str) -> dict:
        return await self._call("get_project", {"projectId": project_id})

    async def list_teams(self) -> dict:
        return await self._call("list_teams", {})

    async def get_workload(self, team_id: str | None = None, cycle_id: str | None = None) -> dict:
        return await self._call("get_workload", {"teamId": team_id, "cycleId": cycle_id})

    # ---------------- writes ----------------
    async def pick_issue(self, issue_id: str) -> dict:
        return await self._call("pick_issue", {"issueId": issue_id})

    async def update_issue(self, issue_id: str, **patch) -> dict:
        return await self._call("update_issue", {"issueId": issue_id, **patch})

    async def transition_issue(self, issue_id: str, to_state_id: str, comment: str | None = None) -> dict:
        return await self._call("transition_issue", {"issueId": issue_id, "toStateId": to_state_id, "comment": comment})

    async def post_feedback(self, issue_id: str, body: str, artifacts: list | None = None) -> dict:
        return await self._call("post_feedback", {"issueId": issue_id, "body": body, "artifacts": artifacts})

    async def comment_issue(self, issue_id: str, body: str) -> dict:
        return await self._call("comment_issue", {"issueId": issue_id, "body": body})

    async def create_issue(self, team_id: str, title: str, **kwargs) -> dict:
        return await self._call("create_issue", {"teamId": team_id, "title": title, **kwargs})

    async def link_issues(self, source_id: str, target_id: str, type: str) -> dict:
        return await self._call("link_issues", {"sourceId": source_id, "targetId": target_id, "type": type})

    async def attach_artifact(self, issue_id: str, kind: str, ref: str, **kwargs) -> dict:
        return await self._call("attach_artifact", {"issueId": issue_id, "artifact": {"kind": kind, "ref": ref, **kwargs}})
