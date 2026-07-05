import datetime
import uuid
from dataclasses import MISSING as DC_MISSING
from dataclasses import dataclass
from dataclasses import fields as dc_fields
from typing import (
    Annotated,
    Any,
    ClassVar,
    Literal,
    Sequence,
    dataclass_transform,
    get_args,
    get_origin,
)

MISSING = object()

_PYTHON_TO_JSONSCHEMA = {
    str: {"type": "string"},
    int: {"type": "integer"},
    float: {"type": "number"},
    bool: {"type": "boolean"},
    uuid.UUID: {"type": "string", "format": "uuid"},
    datetime.datetime: {"type": "string", "format": "date-time"},
    datetime.date: {"type": "string", "format": "date"},
}


def _type_to_schema(tp: Any, default: Any = MISSING) -> dict:
    origin = get_origin(tp)
    args = get_args(tp)
    if origin is Annotated:
        result = _type_to_schema(args[0])
        for arg in args[1:]:
            if isinstance(arg, dict):
                result.update(arg)
    elif origin is Literal:
        arg_types = {type(a) for a in args}
        if len(args) == 1:
            result: dict = {"const": args[0]}
        else:
            result = {"enum": list(args)}
        if len(arg_types) == 1:
            _type = _PYTHON_TO_JSONSCHEMA.get(list(arg_types)[0])
            if _type:
                result["type"] = _type["type"]
    elif origin is list:
        item_schema = _type_to_schema(args[0]) if args else {}
        result = {"type": "array", "items": item_schema}
    elif origin is dict:
        result = {"type": "object"}
    elif type(None) in args:
        non_null = [a for a in args if a is not type(None)]
        if len(non_null) == 1:
            result = _type_to_schema(non_null[0])
            result["nullable"] = True
        else:
            result = {"anyOf": [_type_to_schema(a) for a in non_null], "nullable": True}
    elif tp in _PYTHON_TO_JSONSCHEMA:
        result = dict(_PYTHON_TO_JSONSCHEMA[tp])
    else:
        result = {"type": "string"}
    if default is not MISSING:
        result["default"] = default
    return result


@dataclass_transform()
class Resource:
    _type: ClassVar[str] = ""
    _attributes: ClassVar[list[str]] = []
    _singular_relationships: ClassVar[Any] = []
    _plural_relationships: ClassVar[Any] = []
    _create_fields: ClassVar[list[str]] = []
    _required_create_fields: ClassVar[list[str]] = []
    _edit_fields: ClassVar[list[str]] = []

    @staticmethod
    def _normalize_relationships(
        rels: Any,
    ) -> list[tuple[str, str]]:
        if isinstance(rels, dict):
            return list(rels.items())
        result: list[tuple[str, str]] = []
        for item in rels:
            if isinstance(item, str):
                result.append((item, item))
            elif isinstance(item, tuple) and len(item) == 2:
                result.append(item)
            else:
                raise TypeError(
                    f"Expected str or 2-tuple, got {type(item).__name__}"
                )
        return result

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        dataclass(cls)
        cls._singular_relationships = cls._normalize_relationships(
            cls._singular_relationships
        )
        cls._plural_relationships = cls._normalize_relationships(
            cls._plural_relationships
        )

    @classmethod
    def _annotations(cls) -> dict[str, type]:
        annotations: dict[str, type] = {}
        for base in reversed(cls.__mro__):
            annotations.update(getattr(base, "__annotations__", {}))
        return annotations

    @classmethod
    def _field_map(cls) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for f in dc_fields(cls):  # type: ignore[arg-type]
            default = f.default if f.default is not DC_MISSING else MISSING
            result[f.name] = {"type": f.type, "default": default}
        return result

    @classmethod
    def _field_schema(cls, name: str) -> dict:
        field_map = cls._field_map()
        info = field_map.get(name)
        if info:
            return _type_to_schema(info["type"], default=info["default"])
        return _type_to_schema(str)

    @classmethod
    def _rel_names(cls) -> set[str]:
        return {f for f, _ in cls._singular_relationships} | {
            f for f, _ in cls._plural_relationships
        }

    @staticmethod
    def _rel_schema_singular(type_name: str, id_schema: dict) -> dict:
        return {
            "type": "object",
            "properties": {
                "data": {
                    "type": "object",
                    "properties": {
                        "type": {"const": type_name},
                        "id": id_schema,
                    },
                    "required": ["type", "id"],
                    "additionalProperties": False,
                }
            },
            "required": ["data"],
            "additionalProperties": False,
        }

    @staticmethod
    def _rel_schema_plural(type_name: str, id_schema: dict) -> dict:
        return {
            "type": "object",
            "properties": {
                "data": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"const": type_name},
                            "id": id_schema,
                        },
                        "required": ["type", "id"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["data"],
            "additionalProperties": False,
        }

    @classmethod
    def _attr_schema(cls, attr_fields: list[str], required_fields: list[str]) -> dict:
        attr_props: dict[str, dict] = {}
        for field in attr_fields:
            attr_props[field] = cls._field_schema(field)
        return {
            "type": "object",
            "properties": attr_props,
            "required": required_fields,
            "additionalProperties": False,
        }

    @classmethod
    def jsonschema_read(cls) -> dict:
        properties: dict[str, dict] = {
            "type": {"const": cls._type},
        }
        required: list[str] = ["type"]

        properties["id"] = cls._field_schema("id")
        required.append("id")

        if cls._attributes:
            properties["attributes"] = cls._attr_schema(
                list(cls._attributes), list(cls._attributes)
            )
            required.append("attributes")

        if cls._singular_relationships or cls._plural_relationships:
            rel_props: dict[str, dict] = {}
            for field, type_name in cls._singular_relationships:
                rel_props[field] = cls._rel_schema_singular(
                    type_name, cls._field_schema(field)
                )
            for field, type_name in cls._plural_relationships:
                field_map = cls._field_map()
                info = field_map.get(field)
                if info:
                    args = get_args(info["type"])
                    item_tp = args[0] if args else str
                    id_schema = _type_to_schema(item_tp)
                else:
                    id_schema = _type_to_schema(str)
                rel_props[field] = cls._rel_schema_plural(type_name, id_schema)
            properties["relationships"] = {
                "type": "object",
                "properties": rel_props,
                "required": [f for f, _ in cls._singular_relationships]
                + [f for f, _ in cls._plural_relationships],
                "additionalProperties": False,
            }
            required.append("relationships")

        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    @classmethod
    def jsonschema_create(cls) -> dict:
        properties: dict[str, dict] = {
            "type": {"const": cls._type},
        }
        required: list[str] = ["type"]

        rel_names = cls._rel_names()
        create_fields = set(cls._create_fields)

        if "id" in create_fields:
            properties["id"] = cls._field_schema("id")
            if "id" in cls._required_create_fields:
                required.append("id")

        attr_fields = [f for f in cls._create_fields if f != "id" and f not in rel_names]
        if attr_fields:
            properties["attributes"] = cls._attr_schema(
                attr_fields,
                [f for f in cls._required_create_fields if f in attr_fields],
            )
            required.append("attributes")

        create_rel_fields = create_fields & rel_names
        if create_rel_fields:
            rel_props: dict[str, dict] = {}
            for field, type_name in cls._singular_relationships:
                if field in create_rel_fields:
                    rel_props[field] = cls._rel_schema_singular(
                        type_name, cls._field_schema(field)
                    )
            for field, type_name in cls._plural_relationships:
                if field in create_rel_fields:
                    field_map = cls._field_map()
                    info = field_map.get(field)
                    if info:
                        args = get_args(info["type"])
                        item_tp = args[0] if args else str
                        id_schema = _type_to_schema(item_tp)
                    else:
                        id_schema = _type_to_schema(str)
                    rel_props[field] = cls._rel_schema_plural(type_name, id_schema)
            if rel_props:
                properties["relationships"] = {
                    "type": "object",
                    "properties": rel_props,
                    "additionalProperties": False,
                }

        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    @classmethod
    def jsonschema_edit(cls) -> dict:
        properties: dict[str, dict] = {
            "type": {"const": cls._type},
            "id": cls._field_schema("id"),
        }
        required: list[str] = ["type", "id"]

        rel_names = cls._rel_names()
        edit_fields = set(cls._edit_fields)

        attr_fields = [f for f in cls._edit_fields if f not in rel_names]
        if attr_fields:
            properties["attributes"] = cls._attr_schema(attr_fields, [])
            properties["attributes"]["minProperties"] = 1

        edit_rel_fields = edit_fields & rel_names
        if edit_rel_fields:
            rel_props: dict[str, dict] = {}
            for field, type_name in cls._singular_relationships:
                if field in edit_rel_fields:
                    rel_props[field] = cls._rel_schema_singular(
                        type_name, cls._field_schema(field)
                    )
            for field, type_name in cls._plural_relationships:
                if field in edit_rel_fields:
                    field_map = cls._field_map()
                    info = field_map.get(field)
                    if info:
                        args = get_args(info["type"])
                        item_tp = args[0] if args else str
                        id_schema = _type_to_schema(item_tp)
                    else:
                        id_schema = _type_to_schema(str)
                    rel_props[field] = cls._rel_schema_plural(type_name, id_schema)
            if rel_props:
                properties["relationships"] = {
                    "type": "object",
                    "properties": rel_props,
                    "minProperties": 1,
                    "additionalProperties": False,
                }

        has_attrs = "attributes" in properties
        has_rels = "relationships" in properties
        if has_attrs and not has_rels:
            required.append("attributes")
        elif has_rels and not has_attrs:
            required.append("relationships")
        elif has_attrs and has_rels:
            pass

        result: dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }
        if has_attrs and has_rels:
            result["minProperties"] = 3

        return result

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        if isinstance(value, datetime.datetime):
            return value.isoformat()
        if isinstance(value, datetime.date):
            return value.isoformat()
        if isinstance(value, uuid.UUID):
            return str(value)
        return value

    @staticmethod
    def _convert_value(value: Any, tp: type) -> Any:
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
        return value

    @classmethod
    def _from_jsonapi_payload(cls, payload: dict) -> object:
        data = payload["data"]
        annotations = cls._annotations()
        instance = object.__new__(cls)

        for field in cls._create_fields:
            if field == "id" and "id" in data:
                instance.id = cls._convert_value(data["id"], annotations.get("id", str))
            elif field in cls._attributes:
                attr_val = data.get("attributes", {}).get(field)
                if attr_val is not None:
                    setattr(instance, field, cls._convert_value(attr_val, annotations.get(field, str)))
            elif field in cls._rel_names():
                rel_data = data.get("relationships", {}).get(field, {}).get("data")
                if rel_data is not None:
                    if isinstance(rel_data, dict):
                        setattr(instance, field, cls._convert_value(rel_data["id"], annotations.get(field, str)))
                    elif isinstance(rel_data, list):
                        tp = annotations.get(field, list)
                        args = get_args(tp)
                        item_tp = args[0] if args else str
                        setattr(instance, field, [cls._convert_value(item["id"], item_tp) for item in rel_data])

        return instance

    def serialize(self) -> dict:
        result: dict = {"type": self._type}
        id_val = getattr(self, "id", MISSING)
        if id_val is not MISSING:
            result["id"] = str(id_val)
        for field in self._attributes:
            value = getattr(self, field, MISSING)
            if value is not MISSING:
                result.setdefault("attributes", {})[field] = self._serialize_value(value)
        for field, type_name in self._singular_relationships:
            value = getattr(self, field, MISSING)
            if value is not MISSING:
                result.setdefault("relationships", {})[field] = {
                    "data": {"type": type_name, "id": str(value)}
                }
        for field, type_name in self._plural_relationships:
            value = getattr(self, field, MISSING)
            if value is not MISSING:
                assert isinstance(value, Sequence)
                result.setdefault("relationships", {})[field] = {
                    "data": [{"type": type_name, "id": str(item)} for item in value]
                }
        return result
