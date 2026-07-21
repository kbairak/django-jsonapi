from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from djsonapi_client_py import Resource

HOST = "http://testserver"


def mock_get(sdk, status=200, payload=None):
    resp = AsyncMock()
    resp.__aenter__.return_value = resp
    resp.__aexit__.return_value = None
    resp.status = status
    resp.json = AsyncMock(return_value=payload or {})
    return patch.object(sdk._session, "get", return_value=resp)


def mock_post(sdk, status=201, payload=None):
    resp = AsyncMock()
    resp.__aenter__.return_value = resp
    resp.__aexit__.return_value = None
    resp.status = status
    resp.json = AsyncMock(return_value=payload or {})
    return patch.object(sdk._session, "post", return_value=resp)


def mock_patch(sdk, status=200, payload=None):
    resp = AsyncMock()
    resp.__aenter__.return_value = resp
    resp.__aexit__.return_value = None
    resp.status = status
    resp.json = AsyncMock(return_value=payload or {})
    return patch.object(sdk._session, "patch", return_value=resp)


def mock_delete(sdk, status=204, payload=None):
    resp = AsyncMock()
    resp.__aenter__.return_value = resp
    resp.__aexit__.return_value = None
    resp.status = status
    resp.json = AsyncMock(return_value=payload or {})
    return patch.object(sdk._session, "delete", return_value=resp)


class TestResourceGet:
    async def test_get_by_id(self, article_type, article_response):
        async with article_type._sdk:
            with mock_get(article_type._sdk, payload=article_response):
                article = await article_type.get("1")
                assert article.id == "1"
                assert article.title == "Hello World"

    async def test_get_without_id_filters(self, article_type):
        async with article_type._sdk:
            with mock_get(article_type._sdk, payload={"data": []}):
                with pytest.raises(TypeError):
                    await article_type.get()

    async def test_get_passes_query_params(self, article_type):
        async with article_type._sdk:
            with mock_get(article_type._sdk, payload={"data": {"type": "articles", "id": "1"}}):
                article = await article_type.get(1, "author")
                assert article.id == "1"


class TestResourceCreate:
    async def test_create(self, article_type):
        payload = {"type": "articles", "id": "1", "attributes": {"title": "New"}}
        async with article_type._sdk:
            with mock_post(article_type._sdk, payload={"data": payload}):
                article = await article_type.create(title="New")
                assert article.id == "1"
                assert article.title == "New"

    async def test_create_with_relationships(self, article_type):
        User = article_type._sdk.users
        author = User(id="42")
        async with article_type._sdk:
            with mock_post(
                article_type._sdk,
                payload={
                    "data": {
                        "type": "articles",
                        "id": "1",
                        "attributes": {"title": "New"},
                        "relationships": {"author": {"data": {"type": "users", "id": "42"}}},
                    }
                },
            ):
                article = await article_type.create(title="New", author=author)
                assert article.id == "1"

    async def test_create_returns_empty_on_no_data(self, article_type):
        async with article_type._sdk:
            with mock_post(article_type._sdk, status=202, payload={}):
                article = await article_type.create(title="New")
                assert isinstance(article, Resource)


class TestResourceSave:
    async def test_save_existing_patches(self, article_type):
        article = article_type(id="1", title="Old")
        async with article_type._sdk:
            with mock_patch(
                article_type._sdk,
                payload={
                    "data": {
                        "type": "articles",
                        "id": "1",
                        "attributes": {"title": "Updated"},
                    }
                },
            ):
                await article.save(title="Updated")
                assert article.title == "Updated"

    async def test_save_new_posts(self, article_type):
        article = article_type(title="New")
        assert article.id is None
        async with article_type._sdk:
            with mock_post(
                article_type._sdk,
                payload={"data": {"type": "articles", "id": "1", "attributes": {"title": "New"}}},
            ):
                await article.save()
                assert article.id == "1"

    async def test_save_force_create(self, article_type):
        article = article_type(id="1", title="New")
        async with article_type._sdk:
            with mock_post(
                article_type._sdk,
                payload={"data": {"type": "articles", "id": "2", "attributes": {"title": "New"}}},
            ):
                await article.save(force_create=True)
                assert article.id == "2"

    async def test_save_passes_kwargs_as_fields(self, article_type):
        article = article_type(id="1", title="Old")
        async with article_type._sdk:
            with mock_patch(
                article_type._sdk,
                payload={
                    "data": {
                        "type": "articles",
                        "id": "1",
                        "attributes": {"title": "Fixed"},
                    }
                },
            ):
                await article.save(title="Fixed")
                assert article.title == "Fixed"

    async def test_save_filters_by_fields(self, article_type):
        article = article_type(id="1", title="A", content="B")
        async with article_type._sdk:
            with mock_patch(
                article_type._sdk,
                payload={
                    "data": {
                        "type": "articles",
                        "id": "1",
                        "attributes": {"title": "A"},
                    }
                },
            ):
                await article.save("title")
                assert article.title == "A"

    async def test_save_no_content_response(self, article_type):
        article = article_type(id="1", title="Old")
        async with article_type._sdk:
            with mock_patch(article_type._sdk, status=204):
                await article.save(title="New")
                assert article.title == "New"


class TestResourceDelete:
    async def test_delete(self, article_type):
        article = article_type(id="1")
        async with article_type._sdk:
            with mock_delete(article_type._sdk, status=204):
                await article.delete()
                assert article.id is None

    async def test_delete_no_content_response(self, article_type):
        article = article_type(id="1")
        async with article_type._sdk:
            with mock_delete(article_type._sdk, status=204):
                await article.delete()
                assert article.id is None


class TestResourceRefetch:
    async def test_refetch_uses_self_link(self, article_type, article_payload):
        article = article_type(id="1", title="Stale")
        async with article_type._sdk:
            with mock_get(
                article_type._sdk,
                payload={
                    "data": {
                        **article_payload,
                        "attributes": {"title": "Refreshed", "content": "Updated"},
                    }
                },
            ):
                await article.refetch()
                assert article.title == "Refreshed"

    async def test_refetch_no_self_link_falls_back(self, article_type):
        article = article_type(id="1", title="Stale")
        async with article_type._sdk:
            with mock_get(
                article_type._sdk,
                payload={"data": {"type": "articles", "id": "1", "attributes": {"title": "Refreshed"}}},
            ):
                await article.refetch()
                assert article.title == "Refreshed"

    async def test_refetch_updates_all_fields(self, article_type):
        article = article_type(id="1", title="Old", content="Old")
        async with article_type._sdk:
            with mock_get(
                article_type._sdk,
                payload={
                    "data": {
                        "type": "articles",
                        "id": "1",
                        "attributes": {"title": "New", "content": "New"},
                    }
                },
            ):
                await article.refetch()
                assert article.title == "New"
                assert article.content == "New"


class TestResourceRelationshipMutation:
    @pytest.fixture
    def article(self, article_type):
        return article_type(id="1", categories=[])

    async def test_add(self, article_type, article):
        Category = article_type._sdk.categories
        cat = Category(id="10")
        async with article_type._sdk:
            with mock_post(article_type._sdk, status=204):
                await article.add("categories", cat)

    async def test_add_multiple(self, article_type, article):
        Category = article_type._sdk.categories
        cat1 = Category(id="10")
        cat2 = Category(id="20")
        async with article_type._sdk:
            with mock_post(article_type._sdk, status=204):
                await article.add("categories", [cat1, cat2])

    async def test_remove(self, article_type, article):
        Category = article_type._sdk.categories
        async with article_type._sdk:
            with mock_delete(article_type._sdk, status=204):
                await article.remove("categories", Category(id="10"))

    async def test_reset(self, article_type, article):
        Category = article_type._sdk.categories
        async with article_type._sdk:
            with mock_patch(article_type._sdk, status=204):
                await article.reset("categories", [Category(id="10"), Category(id="20")])


class TestResourceAttributeAccess:
    async def test_getattr_delegates_to_attributes(self, sdk):
        r = Resource(_data={"type": "x", "id": "1", "attributes": {"foo": "bar"}})
        assert r.foo == "bar"

    async def test_getattr_delegates_to_related(self, sdk):
        r = Resource(
            _data={
                "type": "x",
                "id": "1",
                "relationships": {"author": {"data": {"type": "users", "id": "42"}}},
            }
        )
        assert r.author is not None
        assert r.author.id == "42"

    async def test_getattr_raises_on_unknown(self, sdk):
        r = Resource(_data={"type": "x", "id": "1"})
        with pytest.raises(AttributeError):
            r.nonexistent

    async def test_setattr_updates_attributes(self, sdk):
        r = Resource(_data={"type": "x", "id": "1", "attributes": {"foo": "bar"}})
        r.foo = "baz"
        assert r.attributes["foo"] == "baz"
        assert r.foo == "baz"

    async def test_setattr_updates_relationships(self, sdk):
        r = Resource(
            _data={
                "type": "x",
                "id": "1",
                "relationships": {"author": {"data": {"type": "users", "id": "42"}}},
            }
        )
        r.author = {"type": "users", "id": "99"}
        assert r.relationships["author"]["data"]["id"] == "99"

    async def test_setattr_reserved_names_direct(self, sdk):
        r = Resource(_data={"type": "x", "id": "1"})
        r.id = "2"
        assert r.id == "2"

    async def test_repr(self, sdk):
        r = Resource(_data={"type": "x", "id": "1", "attributes": {"foo": "bar"}})
        assert "foo" in repr(r)
        assert "id=1" in repr(r)


class TestResourcePostInit:
    async def test_singular_relationship_resolved(self, article_type):
        r = article_type(
            _data={
                "type": "articles",
                "id": "1",
                "relationships": {"author": {"data": {"type": "users", "id": "42"}}},
            }
        )
        assert r.author is not None
        assert r.author.id == "42"

    async def test_null_singular_relationship(self, article_type):
        r = article_type(
            _data={
                "type": "articles",
                "id": "1",
                "relationships": {"author": {"data": None}},
            }
        )
        assert r.author is None

    async def test_plural_relationship_resolved(self, article_type):
        r = article_type(
            _data={
                "type": "articles",
                "id": "1",
                "relationships": {
                    "categories": {
                        "data": [{"type": "categories", "id": "10"}],
                        "links": {"related": f"{HOST}/articles/1/categories"},
                    }
                },
            }
        )
        cats = r.categories
        assert cats._data is not None
        assert cats._data[0].id == "10"

    async def test_construction_from_kwargs(self, sdk):
        r = Resource(id="1", foo="bar")
        assert r.id == "1"
        assert r.attributes["foo"] == "bar"

    async def test_construction_with_relationship_kwargs(self, user_type):
        author = user_type(id="42")
        r = Resource(id="1", author=author)
        assert r.author is not None
        assert r.author.id == "42"
