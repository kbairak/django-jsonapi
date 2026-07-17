import uuid
from typing import Annotated, ClassVar

from djsonapi.resource import Resource


def test_article_read_schema():
    class Article(Resource):
        _type: ClassVar = "articles"
        _attributes: ClassVar = ["title", "content"]
        _singular_relationships: ClassVar = ["author"]

        id: uuid.UUID
        title: str
        content: str
        author: uuid.UUID

    assert Article.jsonschema_read() == {
        "type": "object",
        "properties": {
            "type": {"const": "articles"},
            "id": {"type": "string", "format": "uuid"},
            "attributes": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "content": {"type": "string"}},
                "required": ["title", "content"],
                "additionalProperties": False,
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
                                    "id": {"type": "string"},
                                },
                                "required": ["type", "id"],
                                "additionalProperties": False,
                            }
                        },
                        "required": ["data"],
                        "additionalProperties": False,
                    }
                },
                "required": ["author"],
                "additionalProperties": False,
            },
        },
        "required": ["type", "id", "attributes", "relationships"],
        "additionalProperties": False,
    }


def test_sparse_article_read_schema():
    class SparseArticle(Resource):
        _type: ClassVar = "articles"
        _attributes: ClassVar = ["title"]
        _singular_relationships: ClassVar = []

        id: uuid.UUID
        title: str

    assert SparseArticle.jsonschema_read() == {
        "type": "object",
        "properties": {
            "type": {"const": "articles"},
            "id": {"type": "string", "format": "uuid"},
            "attributes": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
                "additionalProperties": False,
            },
        },
        "required": ["type", "id", "attributes"],
        "additionalProperties": False,
    }


def test_no_relationships_read_schema():
    class NoRelationshipsArticle(Resource):
        _type: ClassVar = "articles"
        _attributes: ClassVar = ["title", "content"]
        _singular_relationships: ClassVar = []

        id: uuid.UUID
        title: str
        content: str

    assert NoRelationshipsArticle.jsonschema_read() == {
        "type": "object",
        "properties": {
            "type": {"const": "articles"},
            "id": {"type": "string", "format": "uuid"},
            "attributes": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "content": {"type": "string"}},
                "required": ["title", "content"],
                "additionalProperties": False,
            },
        },
        "required": ["type", "id", "attributes"],
        "additionalProperties": False,
    }


def test_no_attributes_read_schema():
    class NoAttributesArticle(Resource):
        _type: ClassVar = "articles"
        _attributes: ClassVar = []
        _singular_relationships: ClassVar = ["author"]

        id: uuid.UUID
        author: uuid.UUID

    assert NoAttributesArticle.jsonschema_read() == {
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
                                    "id": {"type": "string"},
                                },
                                "required": ["type", "id"],
                                "additionalProperties": False,
                            }
                        },
                        "required": ["data"],
                        "additionalProperties": False,
                    }
                },
                "required": ["author"],
                "additionalProperties": False,
            },
        },
        "required": ["type", "id", "relationships"],
        "additionalProperties": False,
    }


def test_plural_relationships_in_schema():
    class Article(Resource):
        _type: ClassVar = "articles"
        _attributes: ClassVar = ["title"]
        _singular_relationships: ClassVar = ["author"]
        _plural_relationships: ClassVar = ["tags"]

        id: uuid.UUID
        title: str
        author: uuid.UUID
        tags: list[uuid.UUID]

    assert Article.jsonschema_read() == {
        "type": "object",
        "properties": {
            "type": {"const": "articles"},
            "id": {"type": "string", "format": "uuid"},
            "attributes": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
                "additionalProperties": False,
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
                                    "id": {"type": "string"},
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
                                        "id": {"type": "string"},
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
                "required": ["author", "tags"],
                "additionalProperties": False,
            },
        },
        "required": ["type", "id", "attributes", "relationships"],
        "additionalProperties": False,
    }


def test_dict_relationships():
    class DictRels(Resource):
        _type = "articles"
        _attributes: ClassVar = ["title"]
        _singular_relationships: ClassVar = {"author": "users"}

        id: uuid.UUID
        title: str
        author: uuid.UUID

    assert DictRels.jsonschema_read() == {
        "type": "object",
        "properties": {
            "type": {"const": "articles"},
            "id": {"type": "string", "format": "uuid"},
            "attributes": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
                "additionalProperties": False,
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
                                    "id": {"type": "string"},
                                },
                                "required": ["type", "id"],
                                "additionalProperties": False,
                            }
                        },
                        "required": ["data"],
                        "additionalProperties": False,
                    }
                },
                "required": ["author"],
                "additionalProperties": False,
            },
        },
        "required": ["type", "id", "attributes", "relationships"],
        "additionalProperties": False,
    }


def test_tuple_plural_relationships():
    class TuplePluralRels(Resource):
        _type = "articles"
        _attributes: ClassVar = ["title"]
        _singular_relationships: ClassVar = ["author"]
        _plural_relationships: ClassVar = [("tags", "tag_objects"), "categories"]

        id: uuid.UUID
        title: str
        author: uuid.UUID
        tags: list[uuid.UUID]
        categories: list[uuid.UUID]

    assert TuplePluralRels.jsonschema_read() == {
        "type": "object",
        "properties": {
            "type": {"const": "articles"},
            "id": {"type": "string", "format": "uuid"},
            "attributes": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
                "additionalProperties": False,
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
                                    "id": {"type": "string"},
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
                                        "type": {"const": "tag_objects"},
                                        "id": {"type": "string"},
                                    },
                                    "required": ["type", "id"],
                                    "additionalProperties": False,
                                },
                            }
                        },
                        "required": ["data"],
                        "additionalProperties": False,
                    },
                    "categories": {
                        "type": "object",
                        "properties": {
                            "data": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"const": "categories"},
                                        "id": {"type": "string"},
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
                "required": ["author", "tags", "categories"],
                "additionalProperties": False,
            },
        },
        "required": ["type", "id", "attributes", "relationships"],
        "additionalProperties": False,
    }


def test_default_and_annotated_in_schema():
    class Article(Resource):
        _type: ClassVar = "articles"
        _attributes: ClassVar = ["title", "category"]
        _singular_relationships: ClassVar = ["author"]

        id: uuid.UUID
        title: str
        author: uuid.UUID
        category: Annotated[str, {"examples": ["tech", "science"]}] = "tech"

    schema = Article.jsonschema_read()
    assert schema == {
        "type": "object",
        "properties": {
            "type": {"const": "articles"},
            "id": {"type": "string", "format": "uuid"},
            "attributes": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "category": {
                        "type": "string",
                        "examples": ["tech", "science"],
                        "default": "tech",
                    },
                },
                "required": ["title", "category"],
                "additionalProperties": False,
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
                                    "id": {"type": "string"},
                                },
                                "required": ["type", "id"],
                                "additionalProperties": False,
                            }
                        },
                        "required": ["data"],
                        "additionalProperties": False,
                    }
                },
                "required": ["author"],
                "additionalProperties": False,
            },
        },
        "required": ["type", "id", "attributes", "relationships"],
        "additionalProperties": False,
    }
