"""A small HTTP client whose every response is cached on disk and committed.

Why commit the cache: identifier resolution must be reproducible. External
registries change (names get synonymised, keys are merged), so a rerun next
year would silently produce a different graph. With the cache in git:

* CI and reviewers rebuild the exact same output offline;
* every mapping row can cite the cache file holding the response it was
  derived from (``cache_key``), together with the retrieval timestamp;
* refreshing is an explicit act (delete the file or run with ``refresh``)
  that shows up as a diff.

Offline mode (``ANEMONE_KG_OFFLINE=1`` or ``resolution.offline: true``) never
touches the network: a cache miss raises :class:`CacheMiss`, which callers turn
into an *unresolved* row - never into a guess.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

log = logging.getLogger(__name__)


class CacheMiss(RuntimeError):
    """Offline mode and the response is not in the cache."""


@dataclass(frozen=True)
class CachedResponse:
    url: str
    status_code: int
    body: Any  # parsed JSON, or None for empty bodies (e.g. WoRMS 204)
    retrieved_at: str
    cache_key: str  # path relative to the cache root


def canonical_url(base: str, params: dict[str, Any] | None = None) -> str:
    """Stable URL: parameters sorted, so the cache key does not depend on dict order."""
    if not params:
        return base
    items = sorted((k, v) for k, v in params.items() if v is not None)
    return f"{base}?{urlencode(items, doseq=True)}"


class CachedHttp:
    def __init__(
        self,
        cache_root: Path,
        user_agent: str,
        timeout_s: float = 30,
        min_interval_s: float = 0.5,
        offline: bool | None = None,
    ) -> None:
        self.root = cache_root
        self.timeout_s = timeout_s
        self.min_interval_s = min_interval_s
        env = os.environ.get("ANEMONE_KG_OFFLINE")
        self.offline = env == "1" if env is not None else bool(offline)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})
        self._last_call = 0.0
        self.stats = {"hit": 0, "miss": 0, "network": 0}
        self.used: set[str] = set()  # cache keys served, so callers can attribute them

    def _path(self, service: str, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        return self.root / service / f"{digest}.json"

    def get(self, service: str, base: str, params: dict[str, Any] | None = None) -> CachedResponse:
        url = canonical_url(base, params)
        path = self._path(service, url)
        key = str(path.relative_to(self.root))
        if path.exists():
            self.stats["hit"] += 1
            rec = json.loads(path.read_text(encoding="utf-8"))
            self.used.add(key)
            return CachedResponse(url, rec["status_code"], rec["body"], rec["retrieved_at"], key)
        self.stats["miss"] += 1
        if self.offline:
            raise CacheMiss(url)

        wait = self.min_interval_s - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        resp = self._get_with_retry(url)
        self._last_call = time.monotonic()
        self.stats["network"] += 1

        if resp.status_code not in (200, 204, 404):
            # Do not cache server errors or throttling: they say nothing about the name.
            resp.raise_for_status()
        # NCBI E-utilities can return raw control characters inside JSON strings.
        body = (
            json.loads(resp.text, strict=False)
            if resp.status_code == 200 and resp.content
            else None
        )
        retrieved_at = datetime.now(UTC).replace(microsecond=0).isoformat()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "url": url,
                    "status_code": resp.status_code,
                    "retrieved_at": retrieved_at,
                    "body": body,
                },
                ensure_ascii=False,
                indent=1,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        self.used.add(key)
        return CachedResponse(url, resp.status_code, body, retrieved_at, key)

    def _get_with_retry(self, url: str, attempts: int = 4) -> requests.Response:
        for i in range(attempts):
            try:
                resp = self.session.get(url, timeout=self.timeout_s)
                if resp.status_code in (429, 502, 503, 504) and i < attempts - 1:
                    time.sleep(2**i)
                    continue
                return resp
            except requests.ConnectionError:
                if i == attempts - 1:
                    raise
                time.sleep(2**i)
        raise RuntimeError("unreachable")
