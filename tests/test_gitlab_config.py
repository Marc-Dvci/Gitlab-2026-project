"""Static checks for the GitLab configuration: flows follow the flow registry v1 rules for custom flows."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
FLOWS = sorted((ROOT / ".gitlab" / "duo" / "flows").glob("*.yaml"))
# Tools documented for the GitLab Duo Agent Platform (doc/user/duo_agent_platform/agents/tools.md).
KNOWN_TOOLS = {
    "get_issue", "update_issue", "create_issue", "create_issue_note", "gitlab_issue_search", "list_issues",
    "get_merge_request", "list_merge_request_diffs", "create_merge_request", "create_merge_request_note",
    "gitlab_api_get", "get_pipeline_failing_jobs", "get_job_logs", "read_file", "list_dir", "find_files", "grep",
    "edit_file", "create_file_with_contents", "run_command",
}


def test_flows_exist():
    assert len(FLOWS) >= 5


@pytest.mark.parametrize("path", FLOWS, ids=lambda p: p.name)
def test_custom_flow_schema(path):
    flow = yaml.safe_load(path.read_text())
    assert flow["version"] == "v1"
    assert flow["environment"] == "ambient"  # the only value custom flows accept
    assert not {"name", "description", "product_group"} & set(flow), "rejected top-level fields"
    assert flow.get("coding_environment", "full") in ("full", "none")
    names = {c["name"] for c in flow["components"]}
    prompt_ids = {p["prompt_id"] for p in flow["prompts"]}
    for comp in flow["components"]:
        assert ":" not in comp["name"] and "." not in comp["name"]
        assert comp["prompt_id"] in prompt_ids
        assert "response_schema_id" not in comp
        tools = [t if isinstance(t, str) else next(iter(t)) for t in comp.get("toolset", [])]
        assert set(tools) <= KNOWN_TOOLS, set(tools) - KNOWN_TOOLS
        limit = comp.get("identical_tool_call_limit", 0)
        assert limit == 0 or limit >= 3
    for prompt in flow["prompts"]:
        assert "model" not in prompt
        assert "stop" not in prompt.get("params", {})
    for router in flow["routers"]:
        assert router["from"] in names
        assert router.get("to", "end") in names | {"end"}
    assert flow["flow"]["entry_point"] in names


def test_ci_jobs_use_declared_stages():
    ci = yaml.safe_load((ROOT / ".gitlab-ci.yml").read_text())
    stages = ci["stages"]
    for name, job in ci.items():
        if isinstance(job, dict) and not name.startswith(".") and name not in ("workflow", "variables", "default", "include"):
            assert job.get("stage", "test") in stages, name


def test_mcp_config_lists_server_tools():
    import json

    cfg = json.loads((ROOT / ".gitlab" / "duo" / "mcp.json").read_text())
    tools = set(cfg["mcpServers"]["joule-thief"]["approvedTools"])
    from joulethief.mcp_server import server
    import asyncio

    assert tools == {t.name for t in asyncio.run(server.list_tools())}
