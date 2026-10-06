"""Eco-mode through GitLab Feature Flags (Unleash-compatible API), without extra dependencies.

When the grid is dirty, an agent turns ``eco-mode`` on through the GitLab API; the app
then shapes its own demand: longer cache lifetimes, slower dashboard refresh, profiler off.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request


class FeatureFlags:
    def __init__(self, ttl_s: float = 300.0):
        self.url = os.environ.get("JOULE_UNLEASH_URL", "")  # https://gitlab.com/api/v4/feature_flags/unleash/<id>
        self.instance_id = os.environ.get("JOULE_UNLEASH_INSTANCE_ID", "")
        self.app_name = os.environ.get("JOULE_ENVIRONMENT", "production")
        self.ttl_s = ttl_s
        self._cache: dict[str, bool] = {}
        self._fetched = 0.0
        self.overrides = {k.removeprefix("JOULE_FLAG_").lower().replace("_", "-"): v == "1"
                          for k, v in os.environ.items() if k.startswith("JOULE_FLAG_")}

    def _refresh(self) -> None:
        if not self.url or time.time() - self._fetched < self.ttl_s:
            return
        req = urllib.request.Request(self.url.rstrip("/") + "/client/features", headers={
            "UNLEASH-INSTANCEID": self.instance_id, "UNLEASH-APPNAME": self.app_name})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 (configured GitLab host)
                data = json.loads(resp.read())
            self._cache = {f["name"]: bool(f.get("enabled")) for f in data.get("features", [])}
        except Exception:  # noqa: BLE001 — flags must never take the app down
            pass
        self._fetched = time.time()

    def enabled(self, name: str, default: bool = False) -> bool:
        if name in self.overrides:
            return self.overrides[name]
        self._refresh()
        return self._cache.get(name, default)
