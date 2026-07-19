from __future__ import annotations

import datetime
import logging
import types
import uuid
from typing import Annotated, Any, ClassVar, Literal, Union, get_args, get_origin

from .collection import Collection, translate_query

logger = logging.getLogger(__name__)

ALL_CAPABILITIES = frozenset({"get_one", "get_many", "create", "edit", "delete"})

_NONE_TYPE = type(None)


def _convert_value(value: Any, tp: Any) -> Any:
    """Best-effort JSON -> Python conversion driven by a type annotation."""
    if value is None or tp is None or tp is Any:
        return value
    origin = get_origin(tp)
    if origin is Annotated:
        return _convert_value(value, get_args(tp)[0])
    if origin is Literal:
        return value
    if origin is list:
        args = get_args(tp)
        item_tp = args[0] if args else Any
        return [_convert_value(item, item_tp) for item in value]
    if origin in (Union, types.UnionType):
        non_none = [a for a in get_args(tp) if a is not _NONE_TYPE]
        if len(non_none) == 1:
            return _convert_value(value, non_none[0])
        return value
    try:
        if tp is int:
            return int(value)
        if tp is float:
            return float(value)
        if tp is str:
            return str(value)
        if tp is bool:
            return bool(value)
        if tp is uuid.UUID:
            return uuid.UUID(value)
        if tp is datetime.datetime:
            return datetime.datetime.fromisoformat(value)
        if tp is datetime.date:
            return datetime.date.fromisoformat(value)
        if tp is datetime.time:
            return datetime.time.fromisoformat(value)
    except (TypeError, ValueError):
        return value
    return value


def _serialize_value(value: Any) -> Any:
    """Python -> JSON conversion for payload building."""
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    return value


class Resource:
    id: str | None
    attributes: dict[str, Any]
    relationships: dict[str, Any]
    links: dict[str, str]
    meta: dict[str, Any]
    _related: dict[str, Any]

    _type: ClassVar[str] = ""
    _sdk: ClassVar[Any] = None
    _attribute_types: ClassVar[dict[str, Any]] = {}
    _relationship_types: ClassVar[dict[str, tuple[str, bool]]] = {}
    _capabilities: ClassVar[frozenset[str]] = ALL_CAPABILITIES
    _relationship_capabilities: ClassVar[dict[str, frozenset[str]] | None] = None
    _collection_class: ClassVar[type[Collection[Any]]] = Collection

    @classmethod
    def _check_capability(cls, operation: str) -> None:
        if operation not in cls._capabilities:
            msg = f"{cls.__name__}: '{operation}' not supported by this server"
            raise AttributeError(msg)

    @classmethod
    def _check_relationship_capability(cls, relationship: str, operation: str) -> None:
        caps = cls._relationship_capabilities
        if caps is None:
            return
        if operation not in caps.get(relationship, frozenset()):
            msg = (
                f"{cls.__name__}: '{operation}' on relationship "
                f"'{relationship}' not supported by this server"
            )
            raise AttributeError(msg)

    @classmethod
    def _convert(cls, name: str, value: Any) -> Any:
        tp = cls._attribute_types.get(name)
        if tp is None:
            return value
        return _convert_value(value, tp)

    def __init__(self, **kwargs: Any) -> None:
        self.id = None
        self.attributes = {}
        self.relationships = {}
        self.links = {}
        self.meta = {}
        self._related = {}
        self._fetched = False

        if "_data" in kwargs:
            data = kwargs.pop("_data")
            self.id = self._convert("id", data.get("id"))
            self.attributes = {
                key: self._convert(key, value)
                for key, value in data.get("attributes", {}).items()
            }
            self.relationships = data.get("relationships", {})
            self.links = data.get("links", {})
            self.__post_init__()
            self._fetched = bool(data.get("attributes")) or bool(data.get("relationships"))
            return

        if "id" in kwargs:
            self.id = kwargs.pop("id")

        for key, value in kwargs.items():
            if key in self._relationship_types:
                self.relationships[key] = self._coerce_relationship(key, value)
                self._related[key] = self._coerce_related(key, value)
            elif Resource._is_relationship(value):
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
            "_fetched",
            "_type",
            "_sdk",
        ):
            object.__setattr__(self, name, value)
            return

        if name in self.attributes:
            self.attributes[name] = value
            return

        if name in self._relationship_types:
            self.relationships[name] = self._coerce_relationship(name, value)
            self._related[name] = self._coerce_related(name, value)
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
                        r = self._sdk.create(relationship["data"])
                    else:
                        r = Resource(_data=relationship["data"])
                    r.links.setdefault("self", relationship.get("links", {}).get("related"))
                    self._related[name] = r
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
                        data = None
                else:
                    if "data" in relationship:
                        data = [Resource(_data=item) for item in relationship["data"]]
                    else:
                        data = None
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

    def _coerce_relationship(self, name: str, value: Any) -> dict[str, Any]:
        """Build a relationship object from a typed (id-based) value."""
        target, plural = self._relationship_types[name]
        if value is None:
            return {"data": [] if plural else None}
        if plural:
            assert isinstance(value, (list, tuple))
            return {"data": [self._typed_ri(target, item) for item in value]}
        return {"data": self._typed_ri(target, value)}

    @staticmethod
    def _typed_ri(target: str, value: Any) -> dict[str, Any]:
        if isinstance(value, Resource):
            return {"type": value._type, "id": str(value.id)}
        if isinstance(value, dict):
            if "type" in value and "id" in value:
                return value
            if "data" in value:
                return value["data"]
        return {"type": target, "id": str(value)}

    def _coerce_related(self, name: str, value: Any) -> Any:
        """Build the local _related entry for a typed (id-based) value."""
        target, plural = self._relationship_types[name]

        def stub(item: Any) -> Resource:
            ri = self._typed_ri(target, item)
            if self._sdk is not None:
                cls = getattr(self._sdk, ri["type"])
                return cls(_data={"type": ri["type"], "id": ri["id"]})
            return Resource(_data=ri)

        if plural:
            items = [] if value is None else [stub(item) for item in value]
            return Collection(self._sdk, "", _data=items)
        if value is None:
            return None
        return stub(value)

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
            return {"type": value._type, "id": str(value.id)}
        if isinstance(value, dict) and "data" in value:
            return value["data"]
        return value

    @staticmethod
    def _str_relationship_ids(relationship: Any) -> Any:
        if not isinstance(relationship, dict):
            return relationship
        data = relationship.get("data")
        if isinstance(data, dict) and "id" in data:
            return {**relationship, "data": {**data, "id": str(data["id"])}}
        if isinstance(data, list):
            return {
                **relationship,
                "data": [
                    {**ri, "id": str(ri["id"])} if isinstance(ri, dict) and "id" in ri else ri
                    for ri in data
                ],
            }
        return relationship

    @staticmethod
    def _is_singular(relationship: dict) -> bool:
        return "data" in relationship and not isinstance(relationship["data"], list)

    @classmethod
    async def get(cls, __id: Any = None, /, *includes: str, **query: Any) -> Resource:
        if __id is None:
            raise TypeError("get() requires an id")
        cls._check_capability("get_one")
        assert cls._sdk._session is not None
        url = f"{cls._type}/{__id}"
        params = translate_query(query)
        if includes:
            params["include"] = ",".join(includes)
        logger.debug("GET %s params=%s", url, params or {})
        async with cls._sdk._session.get(url, params=params) as response:
            body = await response.json()
            logger.debug("Response %s: %s", response.status, body)
            cls._sdk._raise_for_status(response.status, body)
            return cls._sdk._parse_response(body)

    @classmethod
    async def find(cls, *includes: str, **query: Any) -> Resource:
        if not query:
            raise TypeError("find() requires filter arguments")
        col = cls.list()
        if includes:
            col = col.include(*includes)
        col = col.filter(**query)
        await col
        assert col._data is not None
        if len(col._data) != 1:
            raise ValueError(f"Expected 1 result, got {len(col._data)}")
        return col._data[0]

    def __await__(self):
        return self._ensure_fetched().__await__()

    async def _ensure_fetched(self) -> Resource:
        if self._fetched:
            return self
        await self._refetch_impl()
        return self

    async def _refetch_impl(self) -> None:
        url = self.links.get("self") or f"{self._type}/{self.id}"
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
            self._fetched = True

    async def refetch(self) -> None:
        self._check_capability("get_one")
        await self._refetch_impl()

    async def delete(self) -> None:
        self._check_capability("delete")
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
        cls._check_capability("create")
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
        attrs = {k: _serialize_value(v) for k, v in attrs.items()}
        rels = {k: Resource._str_relationship_ids(v) for k, v in rels.items()}
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
        if self.id is not None and not force_create:
            self._check_capability("edit")
        else:
            self._check_capability("create")

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
        cls._check_capability("get_many")
        return cls._collection_class(cls._sdk, f"{cls._type}")

    def _mutation_ris(self, relationship: str, resources: tuple) -> list[dict]:
        if len(resources) == 1 and isinstance(resources[0], (list, tuple)):
            resources = tuple(resources[0])
        if relationship in self._relationship_types:
            target = self._relationship_types[relationship][0]
            return [Resource._typed_ri(target, r) for r in resources]
        return [Resource._as_ri(r) for r in resources]

    async def add(self, relationship: str, *resources):
        self._check_relationship_capability(relationship, "add")
        await self._mutate_relationship("POST", relationship, self._mutation_ris(relationship, resources))

    async def remove(self, relationship: str, *resources):
        self._check_relationship_capability(relationship, "remove")
        await self._mutate_relationship("DELETE", relationship, self._mutation_ris(relationship, resources))

    async def reset(self, relationship: str, *resources):
        self._check_relationship_capability(relationship, "reset")
        await self._mutate_relationship("PATCH", relationship, self._mutation_ris(relationship, resources))

    async def edit(self, relationship: str, resource: Any) -> None:
        self._check_relationship_capability(relationship, "edit")
        ri = self._mutation_ris(relationship, (resource,))[0]
        assert self._sdk._session is not None
        assert self.id is not None
        url = f"{self._type}/{self.id}/relationship/{relationship}"
        payload = {"data": ri}
        logger.debug("PATCH %s body=%s", url, payload)
        async with self._sdk._session.patch(url, json=payload) as response:
            body = await response.json(content_type=None) if response.status != 204 else {}
            logger.debug("Response %s", response.status)
            self._sdk._raise_for_status(response.status, body)
        rel = self.relationships.setdefault(relationship, {})
        rel["data"] = ri
        self._invalidate_related(relationship)

    def _invalidate_related(self, name: str) -> None:
        if name not in self._related:
            return
        rel = self.relationships[name]
        if Resource._is_singular(rel):
            ri = rel.get("data")
            if ri is not None and self._sdk is not None:
                r = self._sdk.create(ri)
                r.links.setdefault("self", rel.get("links", {}).get("related"))
                self._related[name] = r
            else:
                self._related[name] = None
        else:
            url = rel.get("links", {}).get("related", "")
            self._related[name] = Collection(self._sdk, url, _data=None)

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

        self._invalidate_related(relationship)
