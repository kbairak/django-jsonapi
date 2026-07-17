import uuid
from datetime import date, datetime
from typing import Annotated, Literal, Optional

from djsonapi.resource import _type_to_schema


def test_str():
    assert _type_to_schema(str) == {"type": "string"}


def test_int():
    assert _type_to_schema(int) == {"type": "integer"}


def test_float():
    assert _type_to_schema(float) == {"type": "number"}


def test_bool():
    assert _type_to_schema(bool) == {"type": "boolean"}


def test_uuid():
    assert _type_to_schema(uuid.UUID) == {"type": "string", "format": "uuid"}


def test_datetime():
    assert _type_to_schema(datetime) == {"type": "string", "format": "date-time"}


def test_date():
    assert _type_to_schema(date) == {"type": "string", "format": "date"}


def test_list_of_str():
    assert _type_to_schema(list[str]) == {"type": "array", "items": {"type": "string"}}


def test_list_of_uuid():
    assert _type_to_schema(list[uuid.UUID]) == {
        "type": "array",
        "items": {"type": "string", "format": "uuid"},
    }


def test_nested_list():
    assert _type_to_schema(list[list[str]]) == {
        "type": "array",
        "items": {"type": "array", "items": {"type": "string"}},
    }


def test_dict():
    assert _type_to_schema(dict[str, int]) == {"type": "object"}


def test_literal_str():
    assert _type_to_schema(Literal["draft", "published"]) == {
        "type": "string",
        "enum": ["draft", "published"],
    }


def test_literal_int():
    assert _type_to_schema(Literal[1, 2, 3]) == {"type": "integer", "enum": [1, 2, 3]}


def test_literal_single():
    assert _type_to_schema(Literal["pending"]) == {"type": "string", "const": "pending"}


def test_optional_str():
    assert _type_to_schema(Optional[str]) == {"type": "string", "nullable": True}


def test_optional_int():
    assert _type_to_schema(Optional[int]) == {"type": "integer", "nullable": True}


def test_optional_literal():
    assert _type_to_schema(Optional[Literal["a", "b"]]) == {
        "type": "string",
        "enum": ["a", "b"],
        "nullable": True,
    }


def test_str_or_none():
    assert _type_to_schema(str | None) == {"type": "string", "nullable": True}


def test_str_or_int_or_none():
    schema = _type_to_schema(str | int | None)
    assert schema == {"anyOf": [{"type": "string"}, {"type": "integer"}], "nullable": True}


def test_unknown_type():
    assert _type_to_schema(bytearray) == {"type": "string"}


def test_annotated_metadata():
    assert _type_to_schema(Annotated[str, {"examples": ["a", "b"]}]) == {
        "type": "string",
        "examples": ["a", "b"],
    }


def test_annotated_metadata_overwrites():
    assert _type_to_schema(Annotated[str, {"type": "integer"}]) == {"type": "integer"}


def test_default_param():
    assert _type_to_schema(str, default="default_category") == {
        "type": "string",
        "default": "default_category",
    }


def test_default_with_annotated():
    assert _type_to_schema(
        Annotated[str, {"examples": ["a"]}], default="x"
    ) == {
        "type": "string",
        "examples": ["a"],
        "default": "x",
    }
