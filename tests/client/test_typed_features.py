from __future__ import annotations

import datetime
from unittest.mock import AsyncMock
from unittest.mock import patch as _patch

import pytest

from djsonapi_client import Collection, DjsonApiSdk, Resource

HOST = "http://testserver"


def mock_aiohttp_response(status: int = 200, payload: dict | None = None):
    resp = AsyncMock()
    resp.__aenter__.return_value = resp
    resp.__aexit__.return_value = None
    resp.status = status
    resp.json = AsyncMock(return_value=payload or {})
    return resp


def patch_session(sdk, method: str, status: int = 200, payload: dict | None = None):
    resp = mock_aiohttp_response(status, payload)
    return _patch.object(sdk._session, method, return_value=resp)


class TypedArticle(Resource):
    _type = "articles"
    _attribute_types = {
        "id": int,
        "title": str,
        "created_at": datetime.datetime,
    }
    _relationship_types = {
        "author": ("users", False),
        "categories": ("categories", True),
    }
    _capabilities = frozenset({"get_one", "get_many", "create"})
    _relationship_capabilities = {
        "author": frozenset({"fetch"}),
        "categories": frozenset({"fetch", "add"}),
    }


class TypedUser(Resource):
    _type = "users"
    _attribute_types = {"id": int, "username": str}
    _capabilities = frozenset({"get_one", "get_many"})


class TypedCategory(Resource):
    _type = "categories"
    _attribute_types = {"id": int, "name": str}
    _capabilities = frozenset({"get_one", "get_many"})


class TypedSdk(DjsonApiSdk):
    _resource_classes = {
        "articles": TypedArticle,
        "users": TypedUser,
        "categories": TypedCategory,
    }


@pytest.fixture
def sdk():
    return TypedSdk(host=HOST)


@pytest.fixture
def article_payload() -> dict:
    return {
        "type": "articles",
        "id": "1",
        "attributes": {
            "title": "Hello World",
            "created_at": "2025-01-15T10:00:00",
        },
        "relationships": {
            "author": {
                "data": {"type": "users", "id": "42"},
                "links": {"related": f"{HOST}/articles/1/author"},
            },
            "categories": {
                "data": [{"type": "categories", "id": "10"}],
                "links": {"related": f"{HOST}/articles/1/categories"},
            },
        },
        "links": {"self": f"{HOST}/articles/1"},
    }


class TestSealedRegistry:
    def test_known_type_bound(self, sdk):
        cls = sdk.articles
        assert issubclass(cls, TypedArticle)
        assert cls._sdk is sdk

    def test_unknown_type_raises(self, sdk):
        with pytest.raises(AttributeError):
            sdk.bogus

    def test_lazy_sdk_still_open(self):
        lazy = DjsonApiSdk(host=HOST)
        assert lazy.whatever._type == "whatever"


class TestTypeConversion:
    def test_hydrate_converts(self, sdk, article_payload):
        article = sdk.create(article_payload)
        assert article.id == 1
        assert isinstance(article.id, int)
        assert article.created_at == datetime.datetime(2025, 1, 15, 10, 0, 0)
        assert isinstance(article.created_at, datetime.datetime)

    def test_payload_serializes(self, sdk):
        article = sdk.articles(
            title="T",
            created_at=datetime.datetime(2025, 1, 15, 10, 0, 0),
        )
        payload = article._payload()
        assert payload["attributes"]["created_at"] == "2025-01-15T10:00:00"

    def test_relationship_ids_coerced(self, sdk):
        article = sdk.articles(title="T", author=42, categories=[10, 20])
        payload = article._payload()
        assert "author" not in payload.get("attributes", {})
        assert payload["relationships"]["author"] == {
            "data": {"type": "users", "id": "42"}
        }
        assert payload["relationships"]["categories"] == {
            "data": [
                {"type": "categories", "id": "10"},
                {"type": "categories", "id": "20"},
            ]
        }

    def test_relationship_setattr_coerced(self, sdk, article_payload):
        article = sdk.create(article_payload)
        article.author = 7
        assert article.relationships["author"] == {"data": {"type": "users", "id": "7"}}
        assert article._related["author"].id == 7

    def test_relationship_none_singular(self, sdk):
        article = sdk.articles(title="T", author=None)
        assert article.relationships["author"] == {"data": None}


class TestCapabilities:
    async def test_blocked_create(self, sdk):
        with pytest.raises(AttributeError, match="'create' not supported"):
            await sdk.users.create(username="x")

    async def test_blocked_delete(self, sdk, article_payload):
        article = sdk.create(article_payload)
        with pytest.raises(AttributeError, match="'delete' not supported"):
            await article.delete()

    async def test_blocked_edit_via_save(self, sdk, article_payload):
        article = sdk.create(article_payload)
        with pytest.raises(AttributeError, match="'edit' not supported"):
            await article.save(title="new")

    async def test_blocked_relationship_op(self, sdk, article_payload):
        article = sdk.create(article_payload)
        with pytest.raises(AttributeError, match="'reset' on relationship 'author'"):
            await article.reset("author", 1)
        with pytest.raises(AttributeError, match="'remove' on relationship 'categories'"):
            await article.remove("categories", 1)

    async def test_allowed_op_passes(self, sdk, article_payload):
        article = sdk.create(article_payload)
        async with sdk:
            with patch_session(sdk, "post", status=204):
                await article.add("categories", 10)


class TestFetch:
    async def test_fetch_singular(self, sdk, article_payload):
        article = sdk.create(article_payload)
        user_payload = {
            "type": "users",
            "id": "42",
            "attributes": {"username": "jdoe"},
        }
        async with sdk:
            with patch_session(sdk, "get", payload={"data": user_payload}) as mock_get:
                user = await article.author
        assert isinstance(user, Resource)
        assert user._type == "users"
        assert user.username == "jdoe"
        assert article._related["author"] is user
        mock_get.assert_called_once_with(f"{HOST}/articles/1/author")

    async def test_fetch_plural(self, sdk, article_payload):
        payload = {
            **article_payload,
            "relationships": {
                **article_payload["relationships"],
                "categories": {
                    "links": {"related": f"{HOST}/articles/1/categories"},
                },
            },
        }
        article = sdk.create(payload)
        category_payload = {"type": "categories", "id": "10", "attributes": {"name": "c"}}
        body = {"data": [category_payload], "links": {}, "meta": {}}
        async with sdk:
            with patch_session(sdk, "get", payload=body):
                result = await article.categories
        assert isinstance(result, Collection)
        assert len(result) == 1
        assert result[0].name == "c"
        assert article._related["categories"] is result

    async def test_fetch_blocked(self, sdk, article_payload):
        article = sdk.create(article_payload)
        with pytest.raises(AttributeError, match="'edit' on relationship 'bogus'"):
            await article.edit("bogus", None)


class TestQueryTranslation:
    async def test_list_translates_params(self, sdk):
        body = {"data": [], "links": {}, "meta": {}}
        async with sdk:
            with patch_session(sdk, "get", payload=body) as mock_get:
                col = sdk.articles.list()
                col = col.filter(filter__title__contains="foo")
                col = col.page(2)
                col = col.sort("-created_at")
                col = col.include("author")
                col = col.fields(articles=["title"])
                col = col.extra(token="abc", something_custom="y")
                await col
        _, kwargs = mock_get.call_args
        assert kwargs["params"] == {
            "filter[title][contains]": "foo",
            "page": "2",
            "sort": "-created_at",
            "include": "author",
            "fields[articles]": "title",
            "token": "abc",
            "something_custom": "y",
        }

    async def test_get_translates_include(self, sdk, article_payload):
        async with sdk:
            with patch_session(sdk, "get", payload={"data": article_payload}) as mock_get:
                await sdk.articles.get(1, "author")
        _, kwargs = mock_get.call_args
        assert kwargs["params"] == {"include": "author"}

    async def test_find_uses_list(self, sdk, article_payload):
        async with sdk:
            with patch_session(sdk, "get", payload={"data": [article_payload]}):
                article = await sdk.articles.find(title="Hello World")
        assert article.title == "Hello World"
