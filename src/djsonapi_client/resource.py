from __future__ import annotations

import logging
from typing import Any, ClassVar

from .collection import Collection

logger = logging.getLogger(__name__)


class Resource:
    id: str | None
    attributes: dict[str, Any]
    relationships: dict[str, Any]
    links: dict[str, str]
    meta: dict[str, Any]
    _related: dict[str, Any]

    _type: ClassVar[str] = ""
    _sdk: ClassVar[Any] = None

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
            parts.append(f"id={self.id}")
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
                    if self._sdk is not None:
                        self._related[name] = self._sdk.create(relationship["data"])
                    else:
                        self._related[name] = Resource(_data=relationship["data"])
                else:
                    self._related[name] = None
            else:
                try:
                    url = relationship["links"]["related"]
                except KeyError:
                    url = ""
                if self._sdk is not None:
                    try:
                        data = [self._sdk.create(item) for item in relationship["data"]]
                    except KeyError:
                        data = []
                else:
                    data = [Resource(_data=item) for item in relationship.get("data", [])]
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
                    if self._sdk is not None:
                        cls = getattr(self._sdk, v["type"])
                        items.append(cls(id=v["id"]))
                    else:
                        items.append(Resource(_data=v))
                elif isinstance(v, dict) and "data" in v:
                    d = v["data"]
                    if isinstance(d, list):
                        for item in d:
                            if self._sdk is not None:
                                items.append(self._sdk.create(item))
                            else:
                                items.append(Resource(_data=item))
                    elif d is not None:
                        if self._sdk is not None:
                            items.append(self._sdk.create(d))
                        else:
                            items.append(Resource(_data=d))
            return Collection(self._sdk, "", _data=items)
        if isinstance(value, dict):
            if "type" in value and "id" in value:
                if self._sdk is not None:
                    cls = getattr(self._sdk, value["type"])
                    return cls(id=value["id"])
                return Resource(_data=value)
            if "data" in value:
                data = value["data"]
                if data is None:
                    return None
                if isinstance(data, (list, tuple)):
                    if self._sdk is not None:
                        return Collection(
                            self._sdk, "", _data=[self._sdk.create(item) for item in data]
                        )
                    return Collection(
                        self._sdk, "", _data=[Resource(_data=item) for item in data]
                    )
                if self._sdk is not None:
                    return self._sdk.create(data)
                return Resource(_data=data)
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
            params = cls._sdk._query_params(**query)
            logger.debug("GET %s params=%s", url, params or {})
            async with cls._sdk._session.get(url, params=params) as response:
                body = await response.json()
                logger.debug("Response %s: %s", response.status, body)
                cls._sdk._raise_for_status(response.status, body)
                return cls._sdk._parse_response(body)
        col = cls.list().filter(**query)
        await col.fetch()
        assert col._data is not None
        (result,) = col._data
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
            self._sdk._raise_for_status(response.status, body)
            parsed = self._sdk._parse_response(body)
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
            self._sdk._raise_for_status(response.status, body)
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
            cls._sdk._raise_for_status(response.status, body)
            data = body.get("data")
            if data is None:
                return cls()
            return cls._sdk._parse_response(body)

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
            self._sdk._raise_for_status(response.status, body)
            data = body.get("data")
            if data is None:
                return
            parsed = self._sdk._parse_response(body)
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
            self._sdk._raise_for_status(response.status, body)

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
