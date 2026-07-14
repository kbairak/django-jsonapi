from __future__ import annotations

__all__ = [
    "BadRequest",
    "Collection",
    "Conflict",
    "DjsonApiClientError",
    "DjsonApiSdk",
    "Forbidden",
    "InternalServerError",
    "MethodNotAllowed",
    "NotFound",
    "Resource",
    "TooManyRequests",
    "Unauthorized",
    "UnprocessableEntity",
]

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, ClassVar, cast
from urllib.parse import parse_qs, urlparse

import aiohttp

logger = logging.getLogger(__name__)


class DjsonApiClientError(Exception):
    def __init__(self, status: int, title: str = "", detail: str = ""):
        self.status = status
        self.title = title
        self.detail = detail
        super().__init__(f"[{status}] {title}: {detail}")


class BadRequest(DjsonApiClientError): ...


class Unauthorized(DjsonApiClientError): ...


class Forbidden(DjsonApiClientError): ...


class NotFound(DjsonApiClientError): ...


class MethodNotAllowed(DjsonApiClientError): ...


class Conflict(DjsonApiClientError): ...


class UnprocessableEntity(DjsonApiClientError): ...


class TooManyRequests(DjsonApiClientError): ...


class InternalServerError(DjsonApiClientError): ...


_STANDARD_EXC_NAMES: dict[int, type[DjsonApiClientError]] = {
    400: BadRequest,
    401: Unauthorized,
    403: Forbidden,
    404: NotFound,
    405: MethodNotAllowed,
    409: Conflict,
    422: UnprocessableEntity,
    429: TooManyRequests,
    500: InternalServerError,
}

_EXC_CLASS_CACHE: dict[int, type[DjsonApiClientError]] = {}


def _exc_class_for(status: int) -> type[DjsonApiClientError]:
    cls = _STANDARD_EXC_NAMES.get(status)
    if cls is not None:
        return cls
    if status not in _EXC_CLASS_CACHE:
        _EXC_CLASS_CACHE[status] = type(
            f"Http{status}", (DjsonApiClientError,), {"__module__": __name__}
        )
    return _EXC_CLASS_CACHE[status]


async def noop() -> dict[str, str]:
    return {}


@dataclass
class DjsonApiSdk:
    host: str = ""
    headers: Callable[[], Awaitable[dict[str, str]]] = field(
        default_factory=lambda: noop, init=False
    )
    _registry: dict[str, type[Resource]] = field(default_factory=dict, init=False)
    _session: aiohttp.ClientSession | None = field(default=None, init=False)

    def setup(
        self, host: str = "", headers: Callable[[], Awaitable[dict[str, str]]] | None = None
    ) -> None:
        if host:
            self.host = host
        if headers is not None:
            self.headers = headers

    def __getattr__(self, attr: str) -> type[Resource]:
        if attr not in self._registry:
            self._registry[attr] = type(attr, (Resource,), {"_type": attr, "_sdk": self})
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

    @staticmethod
    def _query_params(**query: Any) -> dict[str, str]:
        return {
            k: ",".join(str(v) for v in value) if isinstance(value, (list, tuple)) else str(value)
            for k, value in query.items()
        }

    @staticmethod
    def _raise_for_status(status: int, body: dict) -> None:
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
            if len(excs) == 1:
                raise excs[0]
            raise ExceptionGroup("JSON:API error(s)", excs)
        cls = _exc_class_for(status)
        raise cls(status, body.get("title", ""), body.get("detail", ""))


class Resource:
    id: str | None
    attributes: dict[str, Any]
    relationships: dict[str, Any]
    links: dict[str, str]
    meta: dict[str, Any]
    _related: dict[str, Resource | Collection | None]

    _type: ClassVar[str] = ""
    _sdk: ClassVar[DjsonApiSdk]

    def __init__(self, **kwargs: Any) -> None:
        self.id = None
        self.attributes = {}
        self.relationships = {}
        self.links = {}
        self.meta = {}
        self._related = {}

        if "_data" in kwargs:
            data = kwargs.pop("_data")
            self.id = data.get("id")
            self.attributes = data.get("attributes", {})
            self.relationships = data.get("relationships", {})
            self.links = data.get("links", {})
            self.__post_init__()
            return

        if "id" in kwargs:
            self.id = kwargs.pop("id")

        for key, value in kwargs.items():
            if Resource._is_relationship(value):
                self.relationships[key] = Resource._to_relationship(value)
                self._related[key] = self._to_related_value(value)
            else:
                self.attributes[key] = value

    def __setattr__(self, name: str, value: Any) -> None:
        if name in (
            "id",
            "attributes",
            "relationships",
            "links",
            "meta",
            "_related",
            "_type",
            "_sdk",
        ):
            object.__setattr__(self, name, value)
            return

        if name in self.attributes:
            self.attributes[name] = value
            return

        if name in self.relationships:
            self.relationships[name] = Resource._to_relationship(value)
            self._related[name] = self._to_related_value(value)
            return

        if Resource._is_relationship(value):
            self.relationships[name] = Resource._to_relationship(value)
            self._related[name] = self._to_related_value(value)
        else:
            self.attributes[name] = value

    def __getattr__(self, attr: str) -> Any:
        if attr in self.attributes:
            return self.attributes[attr]
        if attr in self._related:
            return self._related[attr]
        msg = f"{self.__class__.__name__} has no attribute {attr}"
        raise AttributeError(msg)

    def __repr__(self) -> str:
        cls = self.__class__.__name__
        parts = []
        if self.id is not None:
            parts.append(f"id={self.id!r}")
        if self.attributes:
            attrs = ", ".join(f"{k}={v!r}" for k, v in self.attributes.items())
            parts.append(f"attributes={{{attrs}}}")
        if self.relationships:
            parts.append(f"relationships={{{', '.join(self.relationships)}}}")
        return f"{cls}({', '.join(parts)})"

    def __post_init__(self) -> None:
        for name, relationship in self.relationships.items():
            if Resource._is_singular(relationship):
                if relationship["data"] is not None:
                    self._related[name] = self._sdk.create(relationship["data"])
                else:
                    self._related[name] = None
            else:
                try:
                    url = relationship["links"]["related"]
                except KeyError:
                    url = ""
                try:
                    data = [self._sdk.create(item) for item in relationship["data"]]
                except KeyError:
                    data = []
                self._related[name] = Collection(self._sdk, url, _data=data)

    def _to_related_value(self, value: Any) -> Any:
        if isinstance(value, Resource):
            return value
        if isinstance(value, (list, tuple)):
            items: list[Resource] = []
            for v in value:
                if isinstance(v, Resource):
                    items.append(v)
                elif isinstance(v, dict) and "type" in v and "id" in v:
                    cls = getattr(self._sdk, v["type"])
                    items.append(cls(id=v["id"]))
                elif isinstance(v, dict) and "data" in v:
                    d = v["data"]
                    if isinstance(d, list):
                        for item in d:
                            items.append(self._sdk.create(item))
                    elif d is not None:
                        items.append(self._sdk.create(d))
            return Collection(self._sdk, "", _data=items)
        if isinstance(value, dict):
            if "type" in value and "id" in value:
                cls = getattr(self._sdk, value["type"])
                return cls(id=value["id"])
            if "data" in value:
                data = value["data"]
                if data is None:
                    return None
                if isinstance(data, (list, tuple)):
                    return Collection(
                        self._sdk, "", _data=[self._sdk.create(item) for item in data]
                    )
                return self._sdk.create(data)
        return value

    @staticmethod
    def _is_relationship(value: Any) -> bool:
        if isinstance(value, Resource):
            return True
        if isinstance(value, (list, tuple)):
            if not value:
                return True
            if all(isinstance(v, Resource) for v in value):
                return True
            if all(isinstance(v, dict) and "type" in v and "id" in v for v in value):
                return True
            if all(isinstance(v, dict) and "data" in v for v in value):
                return True
            return False
        if isinstance(value, dict):
            if "type" in value and "id" in value:
                return True
            if "data" in value:
                return True
            return False
        return False

    @staticmethod
    def _to_relationship(value: Any) -> dict[str, Any]:
        if isinstance(value, Resource):
            return {"data": {"type": value._type, "id": value.id}}
        if isinstance(value, (list, tuple)):
            return {"data": [Resource._as_ri(v) for v in value]}
        if isinstance(value, dict):
            if "type" in value and "id" in value:
                return {"data": value}
            if "data" in value:
                return value
        return {"data": value}

    @staticmethod
    def _as_ri(value: Any) -> dict[str, Any]:
        if isinstance(value, Resource):
            return {"type": value._type, "id": value.id}
        if isinstance(value, dict) and "data" in value:
            return value["data"]
        return value

    @staticmethod
    def _is_singular(relationship: dict) -> bool:
        return "data" in relationship and not isinstance(relationship["data"], list)

    @classmethod
    async def get(cls, __id: str | None = None, /, **query: Any) -> Resource:
        assert cls._sdk._session is not None
        if __id is not None:
            url = f"{cls._type}/{__id}"
            params = DjsonApiSdk._query_params(**query)
            logger.debug("GET %s params=%s", url, params or {})
            async with cls._sdk._session.get(url, params=params) as response:
                body = await response.json()
                logger.debug("Response %s: %s", response.status, body)
                DjsonApiSdk._raise_for_status(response.status, body)
                return cast(Resource, cls._sdk._parse_response(body))
        col = cls.list().filter(**query)
        await col.fetch()
        assert col._data is not None
        (result,) = col._data  # raises ValueError if 0 or >1
        return result

    async def refetch(self) -> None:
        try:
            url = self.links["self"]
        except KeyError:
            url = f"{self._type}/{self.id}"
        assert self._sdk._session is not None
        logger.debug("GET %s", url)
        async with self._sdk._session.get(url) as response:
            body = await response.json()
            logger.debug("Response %s: %s", response.status, body)
            DjsonApiSdk._raise_for_status(response.status, body)
            parsed = cast(Resource, self._sdk._parse_response(body))
            self.id = parsed.id
            self.attributes = parsed.attributes
            self.relationships = parsed.relationships
            self.links = parsed.links
            self.meta = parsed.meta
            self._related = parsed._related

    async def delete(self) -> None:
        assert self._sdk._session is not None
        assert self.id is not None
        logger.debug("DELETE /%s/%s", self._type, self.id)
        async with self._sdk._session.delete(f"{self._type}/{self.id}") as response:
            logger.debug("Response %s", response.status)
            try:
                body = await response.json(content_type=None)
            except ValueError:
                body = {}
            DjsonApiSdk._raise_for_status(response.status, body)
        self.id = None

    @classmethod
    async def create(cls, **kwargs: Any) -> Resource:
        resource = cls(**kwargs)
        payload = resource._payload()
        assert cls._sdk._session is not None
        logger.debug("POST /%s body=%s", cls._type, {"data": payload})
        async with cls._sdk._session.post(cls._type, json={"data": payload}) as response:
            body = await response.json()
            logger.debug("Response %s: %s", response.status, body)
            DjsonApiSdk._raise_for_status(response.status, body)
            data = body.get("data")
            if data is None:
                return cls()
            return cast(Resource, cls._sdk._parse_response(body))

    def _payload(self, fields: tuple[str, ...] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"type": self._type}
        if self.id is not None:
            payload["id"] = self.id
        if fields:
            attrs = {k: v for k, v in self.attributes.items() if k in fields}
            rels = {k: v for k, v in self.relationships.items() if k in fields}
        else:
            attrs = dict(self.attributes)
            rels = dict(self.relationships)
        if attrs:
            payload["attributes"] = attrs
        if rels:
            payload["relationships"] = rels
        return payload

    async def save(
        self,
        *fields: str,
        force_create: bool = False,
        **kwargs: Any,
    ) -> None:
        if kwargs:
            for key, value in kwargs.items():
                setattr(self, key, value)
            fields = tuple(kwargs.keys())

        assert self._sdk._session is not None
        payload = self._payload(fields=fields)

        if self.id is not None and not force_create:
            meth = self._sdk._session.patch(f"{self._type}/{self.id}", json={"data": payload})
            logger.debug("PATCH /%s/%s body=%s", self._type, self.id, {"data": payload})
        else:
            meth = self._sdk._session.post(self._type, json={"data": payload})
            logger.debug("POST /%s body=%s", self._type, {"data": payload})

        async with meth as response:
            body = await response.json()
            logger.debug("Response %s: %s", response.status, body)
            DjsonApiSdk._raise_for_status(response.status, body)
            data = body.get("data")
            if data is None:
                return
            parsed = cast(Resource, self._sdk._parse_response(body))
            self.id = parsed.id
            self.attributes = parsed.attributes
            self.relationships = parsed.relationships
            self.links = parsed.links
            self.meta = parsed.meta
            self._related = parsed._related

    @classmethod
    def list(cls) -> Collection:
        return Collection(cls._sdk, f"{cls._type}")

    async def add(self, relationship: str, *resources):
        if len(resources) == 1 and isinstance(resources[0], (list, tuple)):
            resources = resources[0]
        data = [Resource._as_ri(r) for r in resources]
        await self._mutate_relationship("POST", relationship, data)

    async def remove(self, relationship: str, *resources):
        if len(resources) == 1 and isinstance(resources[0], (list, tuple)):
            resources = resources[0]
        data = [Resource._as_ri(r) for r in resources]
        await self._mutate_relationship("DELETE", relationship, data)

    async def reset(self, relationship: str, *resources):
        if len(resources) == 1 and isinstance(resources[0], (list, tuple)):
            resources = resources[0]
        data = [Resource._as_ri(r) for r in resources]
        await self._mutate_relationship("PATCH", relationship, data)

    async def _mutate_relationship(self, method: str, relationship: str, data: list[dict]) -> None:
        assert self._sdk._session is not None
        assert self.id is not None
        url = f"{self._type}/{self.id}/relationship/{relationship}"
        payload = {"data": data}
        logger.debug("%s %s body=%s", method, url, payload)
        async with getattr(self._sdk._session, method.lower())(url, json=payload) as response:
            body = await response.json(content_type=None) if response.status != 204 else {}
            logger.debug("Response %s", response.status)
            DjsonApiSdk._raise_for_status(response.status, body)

        rel = self.relationships.setdefault(relationship, {})
        if method == "PATCH":
            rel["data"] = list(data)
        else:
            if not isinstance(rel.get("data"), list):
                rel["data"] = []
            existing = rel["data"]
            if method == "POST":
                existing_ids = {ri.get("id") for ri in existing if isinstance(ri, dict)}
                for ri in data:
                    if ri["id"] not in existing_ids:
                        existing.append(ri)
                        existing_ids.add(ri["id"])
            else:
                remove_ids = {ri["id"] for ri in data}
                rel["data"] = [
                    ri
                    for ri in existing
                    if isinstance(ri, dict) and ri.get("id") not in remove_ids
                ]

        if relationship in self._related:
            related = self._related[relationship]
            if isinstance(related, Collection):
                existing_resources = list(related._data or [])
                if method == "PATCH":
                    related._data = [self._sdk.create(ri) for ri in data]
                elif method == "POST":
                    for ri in data:
                        if not any(e.id == ri["id"] for e in existing_resources):
                            existing_resources.append(self._sdk.create(ri))
                else:
                    remove_ids = {ri["id"] for ri in data}
                    related._data = [e for e in existing_resources if e.id not in remove_ids]


@dataclass
class Collection(Sequence):
    _sdk: DjsonApiSdk = field(repr=False)
    _url: str = field(repr=False)
    _params: dict[str, str] = field(default_factory=dict, repr=False)
    _data: list[Resource] | None = None
    _links: dict[str, str] = field(default_factory=dict, repr=False)
    meta: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        parsed = urlparse(self._url)
        if parsed.query:
            self._url = parsed._replace(query="").geturl()
            url_params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            self._params = {**url_params, **self._params}

    async def fetch(self, force=False):
        if self._data is not None and not force:
            return
        assert self._sdk._session is not None
        logger.debug("GET %s params=%s", self._url, self._params)
        async with self._sdk._session.get(self._url, params=self._params) as response:
            body = await response.json()
            logger.debug("Response %s: %s", response.status, body)
            DjsonApiSdk._raise_for_status(response.status, body)
            self._data = cast(list[Resource], self._sdk._parse_response(body))
            self._links = body.get("links", {})
            self.meta = body.get("meta", {})

    def __getitem__(self, index: int) -> Resource:
        if self._data is None:
            raise RuntimeError("Data not fetched yet. Call 'await collection.fetch()' first.")
        return self._data[index]

    def __len__(self) -> int:
        if self._data is None:
            raise RuntimeError("Data not fetched yet. Call 'await collection.fetch()' first.")
        return len(self._data)

    def filter(self, **kwargs: str) -> Collection:
        return self.__class__(self._sdk, self._url, {**self._params, **kwargs})

    def include(self, *names: str) -> Collection:
        return self.__class__(
            self._sdk,
            self._url,
            {**self._params, "include": ",".join(names)},
        )

    def fields(self, **fields: list[str]) -> Collection:
        new_params = {f"fields[{resource}]": ",".join(attrs) for resource, attrs in fields.items()}
        return self.__class__(self._sdk, self._url, {**self._params, **new_params})

    def sort(self, *fields: str) -> Collection:
        return self.__class__(self._sdk, self._url, {**self._params, "sort": ",".join(fields)})

    def page(self, _page: int | str | None = None, **params: str):
        if _page is not None:
            new_params = {"page": str(_page)}
        else:
            new_params = {f"page[{key}]": value for key, value in params.items()}
        return self.__class__(self._sdk, self._url, {**self._params, **new_params})

    def extra(self, **params: str):
        return self.__class__(self._sdk, self._url, {**self._params, **params})

    def has_next(self) -> bool:
        return "next" in self._links

    def get_next(self) -> Collection:
        return self.__class__(self._sdk, self._links["next"], self._params)

    def has_previous(self) -> bool:
        return "previous" in self._links

    def get_previous(self) -> Collection:
        return self.__class__(self._sdk, self._links["previous"], self._params)

    def has_first(self) -> bool:
        return "first" in self._links

    def get_first(self) -> Collection:
        return self.__class__(self._sdk, self._links["first"], self._params)

    def has_last(self) -> bool:
        return "last" in self._links

    def get_last(self) -> Collection:
        return self.__class__(self._sdk, self._links["last"], self._params)

    async def all_pages(self) -> AsyncIterator[Collection]:
        current_page = self
        while True:
            yield current_page
            if current_page.has_next():
                current_page = current_page.get_next()
            else:
                break

    async def all(self) -> AsyncIterator[Resource]:
        async for page in self.all_pages():
            async for item in page:
                yield item

    async def __aiter__(self) -> AsyncIterator[Resource]:
        await self.fetch()
        assert self._data is not None
        for item in self._data:
            yield item
