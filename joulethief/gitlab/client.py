"""Minimal GitLab REST client for the hands-off loop (stdlib only).

Authentication: a project/group access token or a service-account token in
``GITLAB_TOKEN`` (sent as PRIVATE-TOKEN), or a flow/agent OAuth token (sent as Bearer).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, bytes]]


def urllib_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (configured GitLab host)
            return resp.status, resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()


class GitLabError(RuntimeError):
    pass


@dataclass
class GitLab:
    base_url: str
    token: str
    project: str  # numeric ID or "group/project"
    bearer: bool = False
    transport: Transport = urllib_transport

    @classmethod
    def from_env(cls) -> "GitLab":
        token = os.environ.get("JOULE_GITLAB_TOKEN") or os.environ.get("GITLAB_TOKEN") or os.environ.get("AI_FLOW_GITLAB_TOKEN", "")
        bearer = bool(os.environ.get("AI_FLOW_GITLAB_TOKEN")) and not os.environ.get("JOULE_GITLAB_TOKEN")
        return cls(
            base_url=os.environ.get("CI_API_V4_URL") or f"https://{os.environ.get('GITLAB_HOST', 'gitlab.com')}/api/v4",
            token=token,
            project=os.environ.get("CI_PROJECT_ID") or os.environ.get("JOULE_PROJECT", ""),
            bearer=bearer,
        )

    # -- plumbing -------------------------------------------------------------------------
    @property
    def _project_path(self) -> str:
        return "/projects/" + urllib.parse.quote(str(self.project), safe="")

    def _headers(self) -> dict[str, str]:
        auth = {"Authorization": f"Bearer {self.token}"} if self.bearer else {"PRIVATE-TOKEN": self.token}
        return {"Content-Type": "application/json", "User-Agent": "joulethief/0.1", **auth}

    def request(self, method: str, path: str, payload: dict | None = None, query: dict | None = None,
                headers: dict[str, str] | None = None) -> Any:
        url = self.base_url.rstrip("/") + path
        if query:
            url += "?" + urllib.parse.urlencode(query, doseq=True)
        body = json.dumps(payload).encode() if payload is not None else None
        status, raw = self.transport(method, url, {**self._headers(), **(headers or {})}, body)
        if status >= 400:
            raise GitLabError(f"{method} {path} -> {status}: {raw[:300]!r}")
        return json.loads(raw) if raw else None

    # -- planning ---------------------------------------------------------------------------
    def issues(self, labels: list[str], state: str = "opened") -> list[dict]:
        return self.request("GET", f"{self._project_path}/issues",
                            query={"labels": ",".join(labels), "state": state, "per_page": 100})

    def issue_note(self, iid: int, body: str) -> dict:
        return self.request("POST", f"{self._project_path}/issues/{iid}/notes", {"body": body})

    def set_labels(self, iid: int, add: list[str] = (), remove: list[str] = ()) -> dict:
        return self.request("PUT", f"{self._project_path}/issues/{iid}",
                            {"add_labels": ",".join(add), "remove_labels": ",".join(remove)})

    def create_issue(self, title: str, description: str, labels: list[str]) -> dict:
        return self.request("POST", f"{self._project_path}/issues",
                            {"title": title, "description": description, "labels": ",".join(labels)})

    def mr_note(self, iid: int, body: str) -> dict:
        return self.request("POST", f"{self._project_path}/merge_requests/{iid}/notes", {"body": body})

    # -- agents -----------------------------------------------------------------------------
    def start_flow(self, goal: str, *, consumer_id: int | None = None, workflow_definition: str | None = None,
                   issue_iid: int | None = None, source_branch: str | None = None) -> dict:
        """Start a GitLab Duo flow with the Flows API (``POST /ai/duo_workflows/workflows``).

        Flows cannot be triggered by bots through mentions, so the dispatcher starts them
        through the API when the grid window opens, with no user prompts (hands-off).
        """
        payload: dict[str, Any] = {"project_id": str(self.project), "goal": goal, "start_workflow": True,
                                   "allow_agent_to_request_user": False, "environment": "ambient"}
        if consumer_id is not None:
            payload["ai_catalog_item_consumer_id"] = consumer_id
        if workflow_definition:
            payload["workflow_definition"] = workflow_definition
        if issue_iid is not None:
            payload["issue_id"] = issue_iid
        if source_branch:
            payload["source_branch"] = source_branch
        return self.request("POST", "/ai/duo_workflows/workflows", payload)

    def flow_trace(self, workflow_id: int) -> str:
        url = self.base_url.rstrip("/") + f"/ai/duo_workflows/workflows/{workflow_id}/trace.jsonl"
        status, raw = self.transport("GET", url, self._headers(), None)
        if status >= 400:
            raise GitLabError(f"trace {workflow_id} -> {status}")
        return raw.decode()

    # -- verify / release / configure -------------------------------------------------------
    def run_pipeline(self, ref: str, variables: dict[str, str]) -> dict:
        return self.request("POST", f"{self._project_path}/pipeline",
                            {"ref": ref, "variables": [{"key": k, "value": v} for k, v in variables.items()]})

    def approve_deployment(self, deployment_id: int, approved: bool, comment: str) -> dict:
        return self.request("POST", f"{self._project_path}/deployments/{deployment_id}/approval",
                            {"status": "approved" if approved else "rejected", "comment": comment})

    def set_feature_flag(self, name: str, active: bool) -> dict:
        return self.request("PUT", f"{self._project_path}/feature_flags/{urllib.parse.quote(name)}", {"active": active})

    # -- govern -----------------------------------------------------------------------------
    def set_external_control(self, control_id: int, passed: bool, hmac_secret: str) -> dict:
        """Report the carbon-budget control to the GitLab compliance centre (HMAC + timestamp + nonce)."""
        status = "pass" if passed else "fail"
        path = f"/api/v4/projects/{self.project}/compliance_external_controls/{control_id}/status"
        timestamp, nonce = str(int(time.time())), secrets.token_hex(16)
        signature = external_control_signature(hmac_secret, timestamp, nonce, path, status)
        return self.request("PATCH", f"/projects/{self.project}/compliance_external_controls/{control_id}/status",
                            {"status": status},
                            headers={"X-Gitlab-Timestamp": timestamp, "X-Gitlab-Nonce": nonce,
                                     "X-Gitlab-Hmac-Sha256": signature})


def external_control_signature(secret: str, timestamp: str, nonce: str, path: str, status: str) -> str:
    message = f"{timestamp}{nonce}{path}status={status}"
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
