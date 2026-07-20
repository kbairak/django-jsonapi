import uuid
from typing import ClassVar

from djsonapi.resource import UNSET, Resource


class Article(Resource):
    _type = "articles"
    _attributes: ClassVar = ["title", "content"]
    _singular_relationships: ClassVar = ["author"]

    id: uuid.UUID
    title: str
    content: str
    author: uuid.UUID


class ArticleWithPlural(Resource):
    _type = "articles"
    _attributes: ClassVar = ["title"]
    _singular_relationships: ClassVar = ["author"]
    _plural_relationships: ClassVar = ["tags"]

    id: uuid.UUID
    title: str
    author: uuid.UUID
    tags: list[uuid.UUID]


class SparseArticle(Resource):
    _type = "articles"
    _attributes: ClassVar = ["title"]
    _singular_relationships: ClassVar = []

    id: uuid.UUID
    title: str


def _make_request():
    import django
    from django.conf import settings
    if not settings.configured:
        settings.configure(
            DEBUG=True,
            DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
            ALLOWED_HOSTS=["*"],
            SECRET_KEY="test",
            ROOT_URLCONF=None,
        )
        django.setup()
    from django.test import RequestFactory
    return RequestFactory().get("/articles")


def test_basic_serialize():
    id = uuid.uuid4()
    author = uuid.uuid4()
    article = Article(id=id, title="Hello", content="World", author=author)
    assert article.serialize() == {
        "type": "articles",
        "id": str(id),
        "attributes": {"title": "Hello", "content": "World"},
        "relationships": {
            "author": {"data": {"type": "author", "id": str(author)}}
        },
    }


def test_missing_optional_attribute():
    id = uuid.uuid4()
    author = uuid.uuid4()
    article = Article(id=id, title="Hello", content="World", author=author)
    setattr(article, "content", UNSET)
    result = article.serialize()
    assert "content" not in result["attributes"]
    assert result["attributes"]["title"] == "Hello"


def test_missing_singular_relationship():
    id = uuid.uuid4()
    author = uuid.uuid4()
    article = Article(id=id, title="Hello", content="World", author=author)
    setattr(article, "author", UNSET)
    result = article.serialize()
    assert "author" not in result.get("relationships", {})


def test_no_id():
    id = uuid.uuid4()
    author = uuid.uuid4()
    article = Article(id=id, title="Hello", content="World", author=author)
    setattr(article, "id", UNSET)
    result = article.serialize()
    assert "id" not in result


def test_plural_relationships():
    id = uuid.uuid4()
    author = uuid.uuid4()
    tag1 = uuid.uuid4()
    tag2 = uuid.uuid4()
    article = ArticleWithPlural(
        id=id, title="Hello", author=author, tags=[tag1, tag2]
    )
    result = article.serialize()
    assert result["relationships"]["tags"] == {
        "data": [
            {"type": "tags", "id": str(tag1)},
            {"type": "tags", "id": str(tag2)},
        ]
    }


def test_empty_plural_relationships():
    id = uuid.uuid4()
    author = uuid.uuid4()
    article = ArticleWithPlural(
        id=id, title="Hello", author=author, tags=[]
    )
    result = article.serialize()
    assert result["relationships"]["tags"] == {"data": []}


def test_no_attributes_no_relationships():
    id = uuid.uuid4()
    article = SparseArticle(id=id, title="Hi")
    result = article.serialize()
    assert result == {"type": "articles", "id": str(id), "attributes": {"title": "Hi"}}


def test_serialize_preserves_order():
    id = uuid.uuid4()
    author = uuid.uuid4()
    article = Article(id=id, title="A", content="B", author=author)
    keys = list(article.serialize().keys())
    assert keys == ["type", "id", "attributes", "relationships"]


def test_serialize_dict_relationships():
    class DictRels(Resource):
        _type = "articles"
        _attributes: ClassVar = ["title"]
        _singular_relationships: ClassVar = {"author": "users"}

        id: uuid.UUID
        title: str
        author: uuid.UUID

    id = uuid.uuid4()
    author = uuid.uuid4()
    obj = DictRels(id=id, title="Hello", author=author)
    assert obj.serialize() == {
        "type": "articles",
        "id": str(id),
        "attributes": {"title": "Hello"},
        "relationships": {
            "author": {"data": {"type": "users", "id": str(author)}}
        },
    }


def test_resource_meta():
    id = uuid.uuid4()
    article = Article(id=id, title="Hello", content="World", author=uuid.uuid4())
    article.meta = {"computed": "value"}
    result = article.serialize()
    assert result["meta"] == {"computed": "value"}


def test_resource_meta_none():
    id = uuid.uuid4()
    article = Article(id=id, title="Hello", content="World", author=uuid.uuid4())
    result = article.serialize()
    assert "meta" not in result


def test_response_meta():
    from djsonapi.response import Response

    id = uuid.uuid4()
    article = Article(id=id, title="Hello", content="World", author=uuid.uuid4())
    resp = Response(data=article, meta={"count": 42})
    req = _make_request()
    result = resp.serialize(req)
    assert result["meta"] == {"count": 42}


def test_response_meta_none():
    from djsonapi.response import Response

    id = uuid.uuid4()
    article = Article(id=id, title="Hello", content="World", author=uuid.uuid4())
    resp = Response(data=article)
    req = _make_request()
    result = resp.serialize(req)
    assert "meta" not in result


def test_serialize_tuple_plural_relationships():
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

    id = uuid.uuid4()
    author = uuid.uuid4()
    tag1 = uuid.uuid4()
    cat1 = uuid.uuid4()
    obj = TuplePluralRels(
        id=id, title="Hello", author=author, tags=[tag1], categories=[cat1]
    )
    result = obj.serialize()
    assert result["relationships"]["tags"] == {
        "data": [{"type": "tag_objects", "id": str(tag1)}]
    }
    assert result["relationships"]["categories"] == {
        "data": [{"type": "categories", "id": str(cat1)}]
    }
