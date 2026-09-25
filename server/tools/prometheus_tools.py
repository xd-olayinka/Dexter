"""Registers Prometheus as tools in the executor's tool registry (docs/PHASE_3_4_PLAN.md
§4, docs/PROMETHEUS_MCP_SPEC.md §3.3) — so Anthony's tool loop (`tools/caller.py`) can
call `prometheus_list_issues`, `prometheus_pick_issue`, etc. directly, the same way it
already calls `web_search` or `read_file`.

Only registered when both `DEXTER_PROMETHEUS_MCP_URL` and `DEXTER_PROMETHEUS_MCP_TOKEN`
are set — an unconfigured Dexter simply doesn't offer these tools to the model, same
"don't advertise what isn't there" pattern as everything else in this backend.
"""
import json
import logging

from config import settings
from integrations import PrometheusMCP
from tools.registry import Tool, registry

log = logging.getLogger("dexter.tools.prometheus")

_client: PrometheusMCP | None = None
if settings.prometheus_mcp_url and settings.prometheus_mcp_token:
    _client = PrometheusMCP(settings.prometheus_mcp_url, settings.prometheus_mcp_token)


def get_client() -> PrometheusMCP | None:
    """Public accessor for status.py's connection indicator — the module-level
    singleton stays private so nothing else can bypass `_client_or_raise`'s error."""
    return _client


def _client_or_raise() -> PrometheusMCP:
    if _client is None:
        raise RuntimeError("Prometheus not connected — set DEXTER_PROMETHEUS_MCP_URL / _TOKEN in server/.env")
    return _client


async def _wrap(coro) -> str:
    """Every tool handler must return a string (it becomes the model's tool-result
    content) — never raises, so a Prometheus outage surfaces to the model as readable
    text ("couldn't reach it") instead of crashing the executor's tool loop."""
    try:
        return json.dumps(await coro)
    except Exception as e:
        log.warning("Prometheus tool call failed: %s", e)
        return f"Prometheus error: {e}"


async def prometheus_list_issues(team_id: str = None, project_id: str = None, assignee_id: str = None,
                                  state_id: str = None, cycle_id: str = None, limit: float = None) -> str:
    return await _wrap(_client_or_raise().list_issues(
        teamId=team_id, projectId=project_id, assigneeId=assignee_id, stateId=state_id, cycleId=cycle_id,
        limit=int(limit) if limit is not None else None,
    ))


async def prometheus_get_issue(issue_id: str) -> str:
    return await _wrap(_client_or_raise().get_issue(issue_id))


async def prometheus_my_queue() -> str:
    return await _wrap(_client_or_raise().my_queue())


async def prometheus_list_dependencies(issue_id: str = None) -> str:
    return await _wrap(_client_or_raise().list_dependencies(issue_id))


async def prometheus_list_projects(status: str = None) -> str:
    return await _wrap(_client_or_raise().list_projects(status=status))


async def prometheus_get_project(project_id: str) -> str:
    return await _wrap(_client_or_raise().get_project(project_id))


async def prometheus_list_teams() -> str:
    return await _wrap(_client_or_raise().list_teams())


async def prometheus_get_workload(team_id: str = None, cycle_id: str = None) -> str:
    return await _wrap(_client_or_raise().get_workload(team_id=team_id, cycle_id=cycle_id))


async def prometheus_pick_issue(issue_id: str) -> str:
    return await _wrap(_client_or_raise().pick_issue(issue_id))


async def prometheus_update_issue(issue_id: str, note: str = None) -> str:
    return await _wrap(_client_or_raise().update_issue(issue_id, note=note))


async def prometheus_transition_issue(issue_id: str, to_state_id: str, comment: str = None) -> str:
    return await _wrap(_client_or_raise().transition_issue(issue_id, to_state_id, comment=comment))


async def prometheus_post_feedback(issue_id: str, body: str) -> str:
    return await _wrap(_client_or_raise().post_feedback(issue_id, body))


async def prometheus_create_issue(team_id: str, title: str, description: str = None) -> str:
    return await _wrap(_client_or_raise().create_issue(team_id, title, description=description))


async def prometheus_link_issues(source_id: str, target_id: str, type: str) -> str:
    return await _wrap(_client_or_raise().link_issues(source_id, target_id, type))


async def prometheus_attach_artifact(issue_id: str, kind: str, ref: str, url: str = None) -> str:
    return await _wrap(_client_or_raise().attach_artifact(issue_id, kind, ref, url=url))


if _client is not None:
    log.info("Prometheus connected — registering prometheus_* tools")
    registry.register(Tool(
        name="prometheus_list_issues",
        description="List issues from Prometheus filtered by team/project/state/assignee/cycle",
        parameters={
            "team_id": {"type": "string", "default": None}, "project_id": {"type": "string", "default": None},
            "assignee_id": {"type": "string", "default": None}, "state_id": {"type": "string", "default": None},
            "cycle_id": {"type": "string", "default": None}, "limit": {"type": "number", "default": None},
        },
        handler=prometheus_list_issues,
    ))
    registry.register(Tool(
        name="prometheus_get_issue",
        description="Get full issue details from Prometheus including spec, context, and dependencies",
        parameters={"issue_id": {"type": "string"}},
        handler=prometheus_get_issue,
    ))
    registry.register(Tool(
        name="prometheus_my_queue",
        description="The connected Prometheus member's pickable and in-progress work",
        parameters={},
        handler=prometheus_my_queue,
    ))
    registry.register(Tool(
        name="prometheus_list_dependencies",
        description="Blockers/blocked-by for a Prometheus issue, or across the member's queue",
        parameters={"issue_id": {"type": "string", "default": None}},
        handler=prometheus_list_dependencies,
    ))
    registry.register(Tool(
        name="prometheus_list_projects",
        description="List Prometheus projects in the connected member's scope",
        parameters={"status": {"type": "string", "default": None}},
        handler=prometheus_list_projects,
    ))
    registry.register(Tool(
        name="prometheus_get_project",
        description="Full Prometheus project: overview, issue counts, stakeholders, brief docs, work orders",
        parameters={"project_id": {"type": "string"}},
        handler=prometheus_get_project,
    ))
    registry.register(Tool(
        name="prometheus_list_teams",
        description="List Prometheus teams with member count and active cycle",
        parameters={},
        handler=prometheus_list_teams,
    ))
    registry.register(Tool(
        name="prometheus_get_workload",
        description="Per-member capacity/committed/completed points for a Prometheus team's cycle",
        parameters={"team_id": {"type": "string", "default": None}, "cycle_id": {"type": "string", "default": None}},
        handler=prometheus_get_workload,
    ))
    registry.register(Tool(
        name="prometheus_pick_issue",
        description="Claim a Prometheus issue from the queue (assigns it to the connected member)",
        parameters={"issue_id": {"type": "string"}},
        handler=prometheus_pick_issue,
    ))
    registry.register(Tool(
        name="prometheus_update_issue",
        description="Post a progress note on a Prometheus issue",
        parameters={"issue_id": {"type": "string"}, "note": {"type": "string", "default": None}},
        handler=prometheus_update_issue,
    ))
    registry.register(Tool(
        name="prometheus_transition_issue",
        description="Move a Prometheus issue to a new workflow state — gated states queue for approval instead of applying",
        parameters={"issue_id": {"type": "string"}, "to_state_id": {"type": "string"}, "comment": {"type": "string", "default": None}},
        handler=prometheus_transition_issue,
    ))
    registry.register(Tool(
        name="prometheus_post_feedback",
        description="Post a completion report to a Prometheus issue",
        parameters={"issue_id": {"type": "string"}, "body": {"type": "string"}},
        handler=prometheus_post_feedback,
    ))
    registry.register(Tool(
        name="prometheus_create_issue",
        description="Create a new issue in Prometheus, attributed to this connection",
        parameters={"team_id": {"type": "string"}, "title": {"type": "string"}, "description": {"type": "string", "default": None}},
        handler=prometheus_create_issue,
    ))
    registry.register(Tool(
        name="prometheus_link_issues",
        description="Create a dependency link between two Prometheus issues (blocks/relates/duplicates)",
        parameters={"source_id": {"type": "string"}, "target_id": {"type": "string"}, "type": {"type": "string"}},
        handler=prometheus_link_issues,
    ))
    registry.register(Tool(
        name="prometheus_attach_artifact",
        description="Attach a PR/commit/branch/deploy link to a Prometheus issue",
        parameters={"issue_id": {"type": "string"}, "kind": {"type": "string"}, "ref": {"type": "string"}, "url": {"type": "string", "default": None}},
        handler=prometheus_attach_artifact,
    ))
