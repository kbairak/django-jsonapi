import uuid
from typing import Annotated, ClassVar

from djsonapi.resource import Resource


def test_basic_edit_schema():
    class Article(Resource):
        _type: ClassVar = "articles"
        _attributes: ClassVar = ["title", "content"]
        _edit_fields: ClassVar = ["title", "content"]

        id: uuid.UUID
        title: str
        content: str

    assert Article.jsonschema_edit() == {
        "type": "object",
        "properties": {
            "type": {"const": "articles"},
            "id": {"type": "string", "format": "uuid"},
            "attributes": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": [],
                "additionalProperties": False,
                "minProperties": 1,
            },
        },
        "required": ["type", "id", "attributes"],
        "additionalProperties": False,
    }


def test_edit_empty_fields():
    class Article(Resource):
        _type: ClassVar = "articles"
        _attributes: ClassVar = ["title"]
        _edit_fields: ClassVar = []

        id: uuid.UUID
        title: str

    assert Article.jsonschema_edit() == {
        "type": "object",
        "properties": {
            "type": {"const": "articles"},
            "id": {"type": "string", "format": "uuid"},
        },
        "required": ["type", "id"],
        "additionalProperties": False,
    }


def test_edit_with_relationships():
    class Article(Resource):
        _type: ClassVar = "articles"
        _attributes: ClassVar = ["title"]
        _singular_relationships: ClassVar = ["author"]
        _edit_fields: ClassVar = ["title", "author"]

        id: uuid.UUID
        title: str
        author: uuid.UUID

    assert Article.jsonschema_edit() == {
        "type": "object",
        "properties": {
            "type": {"const": "articles"},
            "id": {"type": "string", "format": "uuid"},
            "attributes": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": [],
                "additionalProperties": False,
                "minProperties": 1,
            },
            "relationships": {
                "type": "object",
                "properties": {
                    "author": {
                        "type": "object",
                        "properties": {
                            "data": {
                                "type": "object",
                                "properties": {
                                    "type": {"const": "author"},
                                    "id": {"type": "string", "format": "uuid"},
                                },
                                "required": ["type", "id"],
                                "additionalProperties": False,
                            }
                        },
                        "required": ["data"],
                        "additionalProperties": False,
                    }
                },
                "minProperties": 1,
                "additionalProperties": False,
            },
        },
        "required": ["type", "id"],
        "minProperties": 3,
        "additionalProperties": False,
    }


def test_edit_plural_relationships():
    class Article(Resource):
        _type: ClassVar = "articles"
        _attributes: ClassVar = ["title"]
        _singular_relationships: ClassVar = ["author"]
        _plural_relationships: ClassVar = ["tags"]
        _edit_fields: ClassVar = ["title", "author", "tags"]

        id: uuid.UUID
        title: str
        author: uuid.UUID
        tags: list[uuid.UUID]

    assert Article.jsonschema_edit() == {
        "type": "object",
        "properties": {
            "type": {"const": "articles"},
            "id": {"type": "string", "format": "uuid"},
            "attributes": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": [],
                "additionalProperties": False,
                "minProperties": 1,
            },
            "relationships": {
                "type": "object",
                "properties": {
                    "author": {
                        "type": "object",
                        "properties": {
                            "data": {
                                "type": "object",
                                "properties": {
                                    "type": {"const": "author"},
                                    "id": {"type": "string", "format": "uuid"},
                                },
                                "required": ["type", "id"],
                                "additionalProperties": False,
                            }
                        },
                        "required": ["data"],
                        "additionalProperties": False,
                    },
                    "tags": {
                        "type": "object",
                        "properties": {
                            "data": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"const": "tags"},
                                        "id": {"type": "string", "format": "uuid"},
                                    },
                                    "required": ["type", "id"],
                                    "additionalProperties": False,
                                },
                            }
                        },
                        "required": ["data"],
                        "additionalProperties": False,
                    },
                },
                "minProperties": 1,
                "additionalProperties": False,
            },
        },
        "required": ["type", "id"],
        "minProperties": 3,
        "additionalProperties": False,
    }


def test_edit_dict_relationships():
    class Article(Resource):
        _type: ClassVar = "articles"
        _attributes: ClassVar = ["title"]
        _singular_relationships: ClassVar = {"author": "users"}
        _edit_fields: ClassVar = ["title", "author"]

        id: uuid.UUID
        title: str
        author: uuid.UUID

    assert Article.jsonschema_edit() == {
        "type": "object",
        "properties": {
            "type": {"const": "articles"},
            "id": {"type": "string", "format": "uuid"},
            "attributes": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": [],
                "additionalProperties": False,
                "minProperties": 1,
            },
            "relationships": {
                "type": "object",
                "properties": {
                    "author": {
                        "type": "object",
                        "properties": {
                            "data": {
                                "type": "object",
                                "properties": {
                                    "type": {"const": "users"},
                                    "id": {"type": "string", "format": "uuid"},
                                },
                                "required": ["type", "id"],
                                "additionalProperties": False,
                            }
                        },
                        "required": ["data"],
                        "additionalProperties": False,
                    }
                },
                "minProperties": 1,
                "additionalProperties": False,
            },
        },
        "required": ["type", "id"],
        "minProperties": 3,
        "additionalProperties": False,
    }


def test_edit_annotated():
    class Article(Resource):
        _type: ClassVar = "articles"
        _attributes: ClassVar = ["title", "category"]
        _edit_fields: ClassVar = ["title", "category"]

        id: uuid.UUID
        title: str
        category: Annotated[str, {"examples": ["tech", "science"]}]

    assert Article.jsonschema_edit() == {
        "type": "object",
        "properties": {
            "type": {"const": "articles"},
            "id": {"type": "string", "format": "uuid"},
            "attributes": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "category": {"type": "string", "examples": ["tech", "science"]},
                },
                "required": [],
                "additionalProperties": False,
                "minProperties": 1,
            },
        },
        "required": ["type", "id", "attributes"],
        "additionalProperties": False,
    }


def test_edit_no_attributes_no_relationships():
    class Article(Resource):
        _type: ClassVar = "articles"
        _attributes: ClassVar = []
        _singular_relationships: ClassVar = []
        _edit_fields: ClassVar = []

        id: uuid.UUID

    assert Article.jsonschema_edit() == {
        "type": "object",
        "properties": {
            "type": {"const": "articles"},
            "id": {"type": "string", "format": "uuid"},
        },
        "required": ["type", "id"],
        "additionalProperties": False,
    }


def test_edit_only_relationships():
    class Article(Resource):
        _type: ClassVar = "articles"
        _attributes: ClassVar = []
        _singular_relationships: ClassVar = ["author"]
        _edit_fields: ClassVar = ["author"]

        id: uuid.UUID
        author: uuid.UUID

    assert Article.jsonschema_edit() == {
        "type": "object",
        "properties": {
            "type": {"const": "articles"},
            "id": {"type": "string", "format": "uuid"},
            "relationships": {
                "type": "object",
                "properties": {
                    "author": {
                        "type": "object",
                        "properties": {
                            "data": {
                                "type": "object",
                                "properties": {
                                    "type": {"const": "author"},
                                    "id": {"type": "string", "format": "uuid"},
                                },
                                "required": ["type", "id"],
                                "additionalProperties": False,
                            }
                        },
                        "required": ["data"],
                        "additionalProperties": False,
                    }
                },
                "minProperties": 1,
                "additionalProperties": False,
            },
        },
        "required": ["type", "id", "relationships"],
        "additionalProperties": False,
    }
