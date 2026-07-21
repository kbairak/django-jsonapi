from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, ClassVar

import aiohttp

from .collection import Collection
from .exceptions import _exc_class_for
from .resource import Resource

logger = logging.getLogger(__name__)


async def noop() -> dict[str, str]:
    return {}


@dataclass
class DjsonApiSdk:
    host: str = ""
    headers: Callable[[], Awaitable[dict[str, str]]] = field(default_factory=lambda: noop)
    _registry: dict[str, type[Resource]] = field(default_factory=dict, init=False)
    _session: aiohttp.ClientSession | None = field(default=None, init=False)

    _resource_classes: ClassVar[dict[str, type[Resource]] | None] = None

    def setup(
        self, host: str = "", headers: Callable[[], Awaitable[dict[str, str]]] | None = None
    ) -> None:
        if host:
            self.host = host
        if headers is not None:
            self.headers = headers

    def __getattr__(self, attr: str) -> type[Resource]:
        if attr not in self._registry:
            if self._resource_classes is not None:
                if attr not in self._resource_classes:
                    msg = f"{type(self).__name__} has no resource type '{attr}'"
                    raise AttributeError(msg)
                base = self._resource_classes[attr]
                cls = type(attr, (base,), {"_type": base._type, "_sdk": self})
            else:
                cls = type(attr, (Resource,), {"_type": attr, "_sdk": self})
            self._registry[attr] = cls
        return self._registry[attr]

    async def __aenter__(self):
        assert self.headers is not None
        media_headers = {
            "Content-Type": "application/vnd.api+json",
            "Accept": "application/vnd.api+json",
        }
        self._session = aiohttp.ClientSession(
            self.host, headers={**media_headers, **await self.headers()}
        )
        return self

    async def __aexit__(self, _exc_type, _exc_val, _exc_tb):
        assert self._session is not None
        await self._session.close()
        self._session = None

    def create(self, data: dict):
        _type = data["type"]
        cls = getattr(self, _type)
        return cls(_data=data)

    def _parse_response(self, response: dict) -> Resource | list[Resource]:
        resources: dict[tuple[str, str], Resource] = {}
        data = response["data"]

        if isinstance(data, list):
            for item in data:
                r = self.create(item)
                resources[(r._type, item["id"])] = r
        else:
            r = self.create(data)
            resources[(r._type, data["id"])] = r

        for item in response.get("included", []):
            key = (item["type"], item["id"])
            if key not in resources:
                r = self.create(item)
                resources[key] = r

        for resource in resources.values():
            for rel_name, related in resource._related.items():
                if isinstance(related, Resource) and related.id is not None:
                    key = (related._type, related.id)
                    if key in resources:
                        resource._related[rel_name] = resources[key]
                elif isinstance(related, Collection) and related._data is not None:
                    for i, item in enumerate(related._data):
                        if item.id is not None:
                            key = (item._type, item.id)
                            if key in resources:
                                related._data[i] = resources[key]

        meta = response.get("meta", {})
        if isinstance(data, list):
            result = [resources[(item["type"], item["id"])] for item in data]
            for r in result:
                r.meta = meta
            return result
        result = resources[(data["type"], data["id"])]
        result.meta = meta
        return result

    def _query_params(self, **query: Any) -> dict[str, str]:
        return {
            k: ",".join(str(v) for v in value) if isinstance(value, (list, tuple)) else str(value)
            for k, value in query.items()
        }

    def _raise_for_status(self, status: int, body: dict) -> None:
        if status < 400:
            return
        errors = body.get("errors")
        if errors and isinstance(errors, list):
            excs = [
                _exc_class_for(int(e.get("status", status)))(
                    int(e.get("status", status)),
                    e.get("title", ""),
                    e.get("detail", ""),
                )
                for e in errors
            ]
        else:
            cls = _exc_class_for(status)
            excs = [cls(status, body.get("title", ""), body.get("detail", ""))]
        raise ExceptionGroup("JSON:API error(s)", excs)
