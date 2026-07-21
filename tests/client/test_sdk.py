from __future__ import annotations

from djsonapi_client_py import DjsonApiSdk, Resource

HOST = "http://testserver"


class TestSdkSetup:
    def test_setup_host(self):
        sdk = DjsonApiSdk()
        sdk.setup(host=HOST)
        assert sdk.host == HOST

    def test_setup_headers(self):
        sdk = DjsonApiSdk()

        async def my_headers():
            return {"Authorization": "Bearer x"}

        sdk.setup(headers=my_headers)
        assert sdk.headers is my_headers

    def test_constructor_host(self):
        sdk = DjsonApiSdk(host=HOST)
        assert sdk.host == HOST


class TestSdkSession:
    async def test_aenter_creates_session(self, sdk):
        async with sdk as s:
            assert s._session is not None
            assert not s._session.closed

    async def test_aexit_closes_session(self, sdk):
        async with sdk as s:
            pass
        assert s._session is None


class TestSdkGetAttr:
    async def test_getattr_creates_resource_subclass(self, sdk):
        Article = sdk.Article
        assert isinstance(Article, type)
        assert issubclass(Article, Resource)
        assert Article._type == "Article"

    async def test_getattr_plural_also_works(self, sdk):
        articles = sdk.articles
        assert isinstance(articles, type)
        assert issubclass(articles, Resource)
        assert articles._type == "articles"

    async def test_getattr_caches(self, sdk):
        a1 = sdk.Article
        a2 = sdk.Article
        assert a1 is a2

    async def test_getattr_binds_sdk(self, sdk):
        Article = sdk.Article
        assert Article._sdk is sdk


class TestSdkCreate:
    async def test_create_from_payload(self, sdk, article_payload):
        resource = sdk.create(article_payload)
        assert resource._type == "articles"
        assert resource.id == "1"
        assert resource.title == "Hello World"

    async def test_create_unknown_type_falls_back(self, sdk):
        data = {"type": "widgets", "id": "99"}
        resource = sdk.create(data)
        assert resource._type == "widgets"
        assert resource.id == "99"


class TestSdkParseResponse:
    async def test_parse_single(self, sdk, article_response):
        parsed = sdk._parse_response(article_response)
        assert isinstance(parsed, Resource)
        assert parsed.id == "1"

    async def test_parse_list(self, sdk, article_list_response):
        parsed = sdk._parse_response(article_list_response)
        assert isinstance(parsed, list)
        assert len(parsed) == 2

    async def test_parse_deduplicates_included(self, sdk, article_payload, user_payload):
        article_payload["relationships"]["author"]["data"] = {"type": "users", "id": "42"}
        response = {"data": article_payload, "included": [user_payload]}
        parsed = sdk._parse_response(response)
        author = parsed._related["author"]
        assert author is not None
        assert author.id == "42"
        assert author._type == "users"
        assert author.username == "jdoe"

    async def test_parse_resolves_included_refs(self, sdk, article_payload, user_payload):
        article_payload["relationships"]["author"]["data"] = {"type": "users", "id": "42"}
        response = {"data": article_payload, "included": [user_payload]}
        parsed = sdk._parse_response(response)
        author = parsed._related["author"]
        assert author.id == "42"
        assert author.username == "jdoe"

    async def test_parse_resolves_included_collection(self, sdk):
        category_payload = {"type": "categories", "id": "10", "attributes": {"name": "Tech"}}
        article = {
            "type": "articles",
            "id": "1",
            "relationships": {"categories": {"data": [{"type": "categories", "id": "10"}]}},
        }
        response = {"data": article, "included": [category_payload]}
        parsed = sdk._parse_response(response)
        cats = parsed._related["categories"]
        assert cats._data is not None
        assert cats._data[0].name == "Tech"

    async def test_parse_sets_meta_on_single(self, sdk):
        article = {"type": "articles", "id": "1"}
        response = {"data": article, "meta": {"foo": "bar"}}
        parsed = sdk._parse_response(response)
        assert parsed.meta == {"foo": "bar"}

    async def test_parse_sets_meta_on_list(self, sdk, article_list_response):
        parsed = sdk._parse_response(article_list_response)
        for r in parsed:
            assert r.meta == {"total": 10}
