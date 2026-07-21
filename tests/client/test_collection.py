from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from djsonapi_client_py import Collection

HOST = "http://testserver"


def mock_get(sdk, status=200, payload=None):
    resp = AsyncMock()
    resp.__aenter__.return_value = resp
    resp.__aexit__.return_value = None
    resp.status = status
    resp.json = AsyncMock(return_value=payload or {})
    return patch.object(sdk._session, "get", return_value=resp)


class TestCollectionAwait:
    async def test_await_populates_data(self, article_type, article_list_response):
        sdk = article_type._sdk
        col = Collection(sdk, f"{HOST}/articles")
        assert col._data is None
        async with sdk:
            with mock_get(sdk, payload=article_list_response):
                result = await col
                assert result is col
                assert col._data is not None
                assert len(col._data) == 2
                assert col._data[0].title == "Hello World"

    async def test_await_sets_links(self, article_type, article_list_response):
        sdk = article_type._sdk
        col = Collection(sdk, f"{HOST}/articles")
        async with sdk:
            with mock_get(sdk, payload=article_list_response):
                await col
                assert "next" in col._links
                assert "last" in col._links

    async def test_await_sets_meta(self, article_type, article_list_response):
        sdk = article_type._sdk
        col = Collection(sdk, f"{HOST}/articles")
        async with sdk:
            with mock_get(sdk, payload=article_list_response):
                await col
                assert col.meta == {"total": 10}

    async def test_await_idempotent(self, article_type, article_list_response):
        sdk = article_type._sdk
        col = Collection(sdk, f"{HOST}/articles")
        async with sdk:
            with mock_get(sdk, payload=article_list_response):
                await col
                first = col._data
                await col
                assert col._data is first

    async def test_await_passes_params(self, article_type):
        sdk = article_type._sdk
        col = Collection(sdk, f"{HOST}/articles", {"filter[title]": "hello"})
        async with sdk:
            with mock_get(sdk, payload={"data": []}):
                await col


class TestCollectionChaining:
    def test_filter(self, sdk):
        col = Collection(sdk, f"{HOST}/articles").filter(title="hello")
        assert col._params["filter[title]"] == "hello"

    def test_filter_chains(self, sdk):
        col = Collection(sdk, f"{HOST}/articles").filter(title="hello").filter(author="42")
        assert col._params == {"filter[title]": "hello", "filter[author]": "42"}

    def test_include(self, sdk):
        col = Collection(sdk, f"{HOST}/articles").include("author", "categories")
        assert col._params["include"] == "author,categories"

    def test_sort(self, sdk):
        col = Collection(sdk, f"{HOST}/articles").sort("title", "-created_at")
        assert col._params["sort"] == "title,-created_at"

    def test_fields(self, sdk):
        col = Collection(sdk, f"{HOST}/articles").fields(articles=["title", "content"])
        assert col._params["fields[articles]"] == "title,content"

    def test_page_number(self, sdk):
        col = Collection(sdk, f"{HOST}/articles").page(2)
        assert col._params["page"] == "2"

    def test_page_params(self, sdk):
        col = Collection(sdk, f"{HOST}/articles").page(size="20", number="3")
        assert col._params["page[size]"] == "20"
        assert col._params["page[number]"] == "3"

    def test_extra(self, sdk):
        col = Collection(sdk, f"{HOST}/articles").extra(custom="value")
        assert col._params["custom"] == "value"

    def test_returns_new_collection(self, sdk):
        col = Collection(sdk, f"{HOST}/articles")
        filtered = col.filter(title="hello")
        assert filtered is not col
        assert col._params == {}

    def test_extracts_url_params_on_init(self, sdk):
        col = Collection(sdk, f"{HOST}/articles?foo=bar")
        assert col._url == f"{HOST}/articles"
        assert col._params == {"foo": "bar"}


class TestCollectionGetItem:
    async def test_getitem(self, article_type, article_list_response):
        sdk = article_type._sdk
        col = Collection(sdk, f"{HOST}/articles")
        async with sdk:
            with mock_get(sdk, payload=article_list_response):
                await col
                assert col[0].title == "Hello World"

    async def test_getitem_unfetched_raises(self, sdk):
        col = Collection(sdk, f"{HOST}/articles")
        with pytest.raises(RuntimeError, match="not fetched"):
            col[0]

    async def test_len(self, article_type, article_list_response):
        sdk = article_type._sdk
        col = Collection(sdk, f"{HOST}/articles")
        async with sdk:
            with mock_get(sdk, payload=article_list_response):
                await col
                assert len(col) == 2

    async def test_len_unfetched_raises(self, sdk):
        col = Collection(sdk, f"{HOST}/articles")
        with pytest.raises(RuntimeError, match="not fetched"):
            len(col)


class TestCollectionIteration:
    async def test_aiter(self, article_type, article_list_response):
        sdk = article_type._sdk
        col = Collection(sdk, f"{HOST}/articles")
        async with sdk:
            with mock_get(sdk, payload=article_list_response):
                titles = [item.title async for item in col]
                assert titles == ["Hello World", "Second Article"]

    async def test_all_single_page(self, article_type):
        sdk = article_type._sdk
        payload = {
            "data": [
                {"type": "articles", "id": "1", "attributes": {"title": "A"}},
                {"type": "articles", "id": "2", "attributes": {"title": "B"}},
            ]
        }
        col = Collection(sdk, f"{HOST}/articles")
        async with sdk:
            with mock_get(sdk, payload=payload):
                articles = [a async for a in col.all()]
                assert len(articles) == 2


class TestCollectionPagination:
    async def test_has_next(self, article_type, article_list_response):
        sdk = article_type._sdk
        col = Collection(sdk, f"{HOST}/articles")
        async with sdk:
            with mock_get(sdk, payload=article_list_response):
                await col
                assert col.has_next()

    async def test_has_next_false_when_missing(self, article_type):
        sdk = article_type._sdk
        col = Collection(sdk, f"{HOST}/articles")
        async with sdk:
            with mock_get(sdk, payload={"data": []}):
                await col
                assert not col.has_next()

    async def test_get_next(self, article_type, article_list_response):
        sdk = article_type._sdk
        col = Collection(sdk, f"{HOST}/articles")
        async with sdk:
            with mock_get(sdk, payload=article_list_response):
                await col
                next_col = col.get_next()
                assert next_col._params == {"page": "2"}

    async def test_has_previous(self, article_type, article_list_response):
        sdk = article_type._sdk
        col = Collection(sdk, f"{HOST}/articles")
        async with sdk:
            with mock_get(sdk, payload=article_list_response):
                await col
                assert not col.has_previous()

    async def test_has_first(self, article_type, article_list_response):
        sdk = article_type._sdk
        col = Collection(sdk, f"{HOST}/articles")
        async with sdk:
            with mock_get(sdk, payload=article_list_response):
                await col
                assert col.has_first()

    async def test_has_last(self, article_type, article_list_response):
        sdk = article_type._sdk
        col = Collection(sdk, f"{HOST}/articles")
        async with sdk:
            with mock_get(sdk, payload=article_list_response):
                await col
                assert col.has_last()

    async def test_get_last(self, article_type, article_list_response):
        sdk = article_type._sdk
        col = Collection(sdk, f"{HOST}/articles")
        async with sdk:
            with mock_get(sdk, payload=article_list_response):
                await col
                last_col = col.get_last()
                assert last_col._params == {"page": "5"}

    async def test_all_pages_follows_next(self, article_type):
        sdk = article_type._sdk
        p1 = {
            "data": [{"type": "articles", "id": "1"}],
            "links": {"next": f"{HOST}/articles?page=2"},
        }
        p2 = {"data": [{"type": "articles", "id": "2"}]}

        resp1 = AsyncMock()
        resp1.__aenter__.return_value = resp1
        resp1.__aexit__.return_value = None
        resp1.status = 200
        resp1.json = AsyncMock(return_value=p1)

        resp2 = AsyncMock()
        resp2.__aenter__.return_value = resp2
        resp2.__aexit__.return_value = None
        resp2.status = 200
        resp2.json = AsyncMock(return_value=p2)

        col = Collection(sdk, f"{HOST}/articles")
        async with sdk:
            with patch.object(sdk._session, "get", side_effect=[resp1, resp2]):
                pages = [p async for p in col.all_pages()]
                assert len(pages) == 2
                assert pages[0]._data is not None
                assert pages[1]._data is not None
                assert pages[0]._data[0].id == "1"
                assert pages[1]._data[0].id == "2"

    async def test_all_follows_pagination(self, article_type):
        sdk = article_type._sdk
        p1 = {
            "data": [{"type": "articles", "id": "1", "attributes": {"title": "A"}}],
            "links": {"next": f"{HOST}/articles?page=2"},
        }
        p2 = {"data": [{"type": "articles", "id": "2", "attributes": {"title": "B"}}]}

        resp1 = AsyncMock()
        resp1.__aenter__.return_value = resp1
        resp1.__aexit__.return_value = None
        resp1.status = 200
        resp1.json = AsyncMock(return_value=p1)

        resp2 = AsyncMock()
        resp2.__aenter__.return_value = resp2
        resp2.__aexit__.return_value = None
        resp2.status = 200
        resp2.json = AsyncMock(return_value=p2)

        col = Collection(sdk, f"{HOST}/articles")
        async with sdk:
            with patch.object(sdk._session, "get", side_effect=[resp1, resp2]):
                titles = [a.title async for a in col.all()]
                assert titles == ["A", "B"]


class TestCollectionSequence:
    def test_is_sequence(self, sdk):
        from collections.abc import Sequence

        col = Collection(sdk, f"{HOST}/articles")
        assert isinstance(col, Sequence)
