import json
import sys
import types
import uuid
from typing import ClassVar

import django
import pytest
from django.conf import settings
from django.http import HttpRequest
from django.test import RequestFactory
from django.test.utils import override_settings

from djsonapi import DjsonApi, Resource
from djsonapi.exceptions import NotFound
from djsonapi.response import Response

settings.configure(
    DEBUG=True,
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    ALLOWED_HOSTS=["*"],
    SECRET_KEY="test",
    ROOT_URLCONF=None,
)
django.setup()


class Article(Resource):
    _type: ClassVar = "articles"
    _attributes: ClassVar = ["title", "content"]
    _create_fields: ClassVar = ["title", "content"]
    _required_create_fields: ClassVar = ["title", "content"]

    id: uuid.UUID
    title: str
    content: str


def _make_urlconf(api):
    module = types.ModuleType("_test_urls")
    setattr(module, "urlpatterns", api.urls)
    sys.modules["_test_urls"] = module
    return "_test_urls"


class TestUrls:
    def test_get_one_url(self):
        api = DjsonApi()

        @api.get_one("articles")
        def view(request, article_id: uuid.UUID) -> Article: ...

        urls = api.urls
        assert len(urls) == 3
        assert urls[0].name == "get_one__articles"
        assert urls[0].pattern.regex.pattern is not None

    def test_get_many_url(self):
        api = DjsonApi()

        @api.get_many("articles")
        def view(request) -> list[Article]: ...

        urls = api.urls
        assert len(urls) == 3
        assert urls[0].name == "get_many__articles"
        assert urls[0].pattern.regex.pattern is not None

    def test_pk_type_inference(self):
        api = DjsonApi()

        @api.get_one("articles")
        def view(request, article_id: uuid.UUID) -> Article: ...

        urls = api.urls
        converters = urls[0].pattern.converters
        assert "article_id" in converters


class TestCreateOne:
    def test_create_one_url(self):
        api = DjsonApi()

        @api.create_one("articles")
        def view(request: HttpRequest, payload: Article) -> Article: ...

        urls = api.urls
        assert len(urls) == 3
        assert any(u.name == "create_one__articles" for u in urls)

    def test_201_response_with_location(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_one("articles")
        def get_article(request, article_id: uuid.UUID) -> Article: ...

        @api.create_one("articles")
        def view(request: HttpRequest, payload: Article) -> Article:
            return Article(id=article_id, title=payload.title, content=payload.content)

        article_id = uuid.uuid4()
        body = json.dumps({
            "data": {
                "type": "articles",
                "attributes": {"title": "Test", "content": "Hello"},
            }
        })
        request = factory.post("/articles/", body, content_type="application/vnd.api+json")

        urlconf = _make_urlconf(api)
        with override_settings(ROOT_URLCONF=urlconf):
            response = view(request)

        assert response.status_code == 201
        assert response["Content-Type"] == "application/vnd.api+json"
        assert "Location" in response

        body = json.loads(response.content)
        assert "data" in body
        assert body["data"]["type"] == "articles"
        assert "attributes" in body["data"]
        assert body["data"]["attributes"]["title"] == "Test"
        assert body["data"]["attributes"]["content"] == "Hello"

    def test_202_accepted(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.create_one("articles")
        def view(request: HttpRequest, payload: Article) -> None:
            return None

        body = json.dumps({
            "data": {
                "type": "articles",
                "attributes": {"title": "T", "content": "C"},
            }
        })
        request = factory.post("/articles/", body, content_type="application/vnd.api+json")
        response = view(request)

        assert response.status_code == 202
        body = json.loads(response.content)
        assert body["jsonapi"] == {"version": "1.0"}

    def test_400_on_validation_error(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.create_one("articles")
        def view(request: HttpRequest, payload: Article) -> Article:
            return Article(id=uuid.uuid4(), title=payload.title, content=payload.content)

        body = json.dumps({
            "data": {
                "type": "articles",
                "attributes": {"title": "T"},  # missing required "content"
            }
        })
        request = factory.post("/articles/", body, content_type="application/vnd.api+json")
        response = view(request)

        assert response.status_code == 400
        assert response["Content-Type"] == "application/vnd.api+json"
        body = json.loads(response.content)
        assert "errors" in body
        assert body["errors"][0]["source"]["pointer"] == "/data/attributes"

    def test_400_on_invalid_json(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.create_one("articles")
        def view(request: HttpRequest, payload: Article) -> Article:
            return Article(id=uuid.uuid4(), title="T", content="C")

        request = factory.post("/articles/", "not json", content_type="application/vnd.api+json")
        response = view(request)

        assert response.status_code == 400

    def test_unhandled_exception_returns_500(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.create_one("articles")
        def view(request: HttpRequest, payload: Article) -> Article:
            raise ValueError("something broke")

        body = json.dumps({
            "data": {
                "type": "articles",
                "attributes": {"title": "T", "content": "C"},
            }
        })
        request = factory.post("/articles/", body, content_type="application/vnd.api+json")
        response = view(request)

        assert response.status_code == 500
        body = json.loads(response.content)
        assert "errors" in body

    def test_sync_handler(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.create_one("articles")
        def view(request: HttpRequest, payload: Article) -> Article:
            return Article(id=uuid.uuid4(), title=payload.title, content=payload.content)

        body = json.dumps({
            "data": {
                "type": "articles",
                "attributes": {"title": "T", "content": "C"},
            }
        })
        request = factory.post("/articles/", body, content_type="application/vnd.api+json")
        response = view(request)

        assert response.status_code == 201
        body = json.loads(response.content)
        assert body["data"]["attributes"]["title"] == "T"

    def test_async_handler(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.create_one("articles")
        async def view(request: HttpRequest, payload: Article) -> Article:
            return Article(id=uuid.uuid4(), title=payload.title, content=payload.content)

        body = json.dumps({
            "data": {
                "type": "articles",
                "attributes": {"title": "T", "content": "C"},
            }
        })
        request = factory.post("/articles/", body, content_type="application/vnd.api+json")
        import asyncio

        response = asyncio.run(view(request))

        assert response.status_code == 201
        body = json.loads(response.content)
        assert body["data"]["attributes"]["title"] == "T"

    def test_client_generated_id_accepted(self):
        api = DjsonApi()
        factory = RequestFactory()

        class ArticleWithClientId(Resource):
            _type: ClassVar = "articles"
            _attributes: ClassVar = ["title", "content"]
            _create_fields: ClassVar = ["id", "title", "content"]
            _required_create_fields: ClassVar = ["title", "content"]

            id: uuid.UUID
            title: str
            content: str

        @api.create_one("articles")
        def view(request: HttpRequest, payload: ArticleWithClientId) -> ArticleWithClientId:
            return ArticleWithClientId(
                id=payload.id, title=payload.title, content=payload.content
            )

        client_id = uuid.uuid4()
        body = json.dumps({
            "data": {
                "type": "articles",
                "id": str(client_id),
                "attributes": {"title": "T", "content": "C"},
            }
        })
        request = factory.post("/articles/", body, content_type="application/vnd.api+json")
        response = view(request)

        assert response.status_code == 201
        body = json.loads(response.content)
        assert body["data"]["id"] == str(client_id)


class TestGetOne:
    def test_handler_called_with_correct_args(self):
        api = DjsonApi()
        factory = RequestFactory()

        calls = []

        @api.get_one("articles")
        def view(request, article_id: uuid.UUID) -> Article:
            calls.append((request, article_id))
            return Article(id=article_id, title="t", content="c")

        uid = uuid.uuid4()
        request = factory.get(f"/articles/{uid}")
        view(request, article_id=uid)

        assert len(calls) == 1
        assert calls[0] == (request, uid)

    def test_response_structure(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_one("articles")
        def view(request, article_id: uuid.UUID) -> Article:
            return Article(id=article_id, title="Test", content="Content")

        uid = uuid.uuid4()
        request = factory.get(f"/articles/{uid}")
        response = view(request, article_id=uid)

        assert response.status_code == 200
        assert response["Content-Type"] == "application/vnd.api+json"

        body = json.loads(response.content)
        assert "data" in body
        assert "links" in body
        assert body["jsonapi"] == {"version": "1.0"}
        assert body["data"]["type"] == "articles"
        assert body["data"]["id"] == str(uid)
        assert body["data"]["attributes"] == {"title": "Test", "content": "Content"}

    def test_self_link_when_reverse_works(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_one("articles")
        def view(request, article_id: uuid.UUID) -> Article:
            return Article(id=article_id, title="T", content="C")

        uid = uuid.uuid4()
        urlconf = _make_urlconf(api)

        with override_settings(ROOT_URLCONF=urlconf):
            request = factory.get(f"/articles/{uid}")
            response = view(request, article_id=uid)

        body = json.loads(response.content)
        assert body["data"]["links"]["self"] == f"/articles/{uid}"
        assert body["links"]["self"] == f"/articles/{uid}"

    def test_not_found_exception(self):
        api = DjsonApi()
        factory = RequestFactory()

        uid = uuid.uuid4()

        @api.get_one("articles")
        def view(request, article_id: uuid.UUID) -> Article:
            raise NotFound(f"Article {article_id} not found")

        request = factory.get("/articles/123")
        response = view(request, article_id=uid)

        assert response.status_code == 404
        assert response["Content-Type"] == "application/vnd.api+json"
        body = json.loads(response.content)
        assert "errors" in body
        assert body["errors"][0]["detail"] == f"Article {uid} not found"

    def test_unhandled_exception_returns_500(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_one("articles")
        def view(request, article_id: uuid.UUID) -> Article:
            raise ValueError("something broke")

        request = factory.get("/articles/123")
        response = view(request, article_id=uuid.uuid4())

        assert response.status_code == 500
        assert response["Content-Type"] == "application/vnd.api+json"
        body = json.loads(response.content)
        assert "errors" in body

    def test_sync_handler(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_one("articles")
        def view(request, article_id: uuid.UUID) -> Article:
            return Article(id=article_id, title="T", content="C")

        uid = uuid.uuid4()
        request = factory.get(f"/articles/{uid}")
        response = view(request, article_id=uid)

        assert response.status_code == 200
        body = json.loads(response.content)
        assert body["data"]["id"] == str(uid)

    def test_async_handler(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_one("articles")
        async def view(request, article_id: uuid.UUID) -> Article:
            return Article(id=article_id, title="T", content="C")

        uid = uuid.uuid4()
        request = factory.get(f"/articles/{uid}")
        import asyncio

        response = asyncio.run(view(request, article_id=uid))

        assert response.status_code == 200
        body = json.loads(response.content)
        assert body["data"]["id"] == str(uid)


class TestGetMany:
    def test_handler_called_with_request(self):
        api = DjsonApi()
        factory = RequestFactory()

        calls = []

        @api.get_many("articles")
        def view(request) -> list[Article]:
            calls.append(request)
            return [Article(id=uuid.uuid4(), title="t", content="c")]

        request = factory.get("/articles/")
        view(request)

        assert len(calls) == 1
        assert calls[0] is request

    def test_response_structure(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_many("articles")
        def view(request) -> list[Article]:
            return [
                Article(id=uuid.uuid4(), title="One", content="A"),
                Article(id=uuid.uuid4(), title="Two", content="B"),
            ]

        request = factory.get("/articles/")
        response = view(request)

        assert response.status_code == 200
        assert response["Content-Type"] == "application/vnd.api+json"

        body = json.loads(response.content)
        assert "data" in body
        assert "links" in body
        assert body["jsonapi"] == {"version": "1.0"}
        assert len(body["data"]) == 2
        for item in body["data"]:
            assert item["type"] == "articles"
            assert "id" in item
            assert "attributes" in item

    def test_self_link_when_reverse_works(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_many("articles")
        def view(request) -> list[Article]:
            return [Article(id=uuid.uuid4(), title="T", content="C")]

        urlconf = _make_urlconf(api)

        with override_settings(ROOT_URLCONF=urlconf):
            request = factory.get("/articles/")
            response = view(request)

        body = json.loads(response.content)
        assert body["links"]["self"] == "/articles/"

    def test_unhandled_exception_returns_500(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_many("articles")
        def view(request) -> list[Article]:
            raise ValueError("something broke")

        request = factory.get("/articles/")
        response = view(request)

        assert response.status_code == 500
        assert response["Content-Type"] == "application/vnd.api+json"
        body = json.loads(response.content)
        assert "errors" in body

    def test_sync_handler(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_many("articles")
        def view(request) -> list[Article]:
            return [
                Article(id=uuid.uuid4(), title="A", content="B"),
                Article(id=uuid.uuid4(), title="C", content="D"),
            ]

        request = factory.get("/articles/")
        response = view(request)

        assert response.status_code == 200
        body = json.loads(response.content)
        assert len(body["data"]) == 2

    def test_async_handler(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_many("articles")
        async def view(request) -> list[Article]:
            return [
                Article(id=uuid.uuid4(), title="A", content="B"),
                Article(id=uuid.uuid4(), title="C", content="D"),
            ]

        request = factory.get("/articles/")
        import asyncio

        response = asyncio.run(view(request))

        assert response.status_code == 200
        body = json.loads(response.content)
        assert len(body["data"]) == 2

    def test_relationship_links_from_other_endpoint(self):
        api = DjsonApi()
        factory = RequestFactory()

        class Author(Resource):
            _type: ClassVar = "authors"
            id: uuid.UUID
            name: str

        class Book(Resource):
            _type: ClassVar = "books"
            _attributes: ClassVar = ["title"]
            _singular_relationships: ClassVar = [("author", "authors")]

            id: uuid.UUID
            title: str
            author: uuid.UUID

        @api.get_one("authors")
        def get_author(request, author_id: uuid.UUID) -> Author:
            return Author(id=author_id, name="test")

        @api.get_many("books")
        def list_books(request) -> list[Book]:
            author_id = uuid.uuid4()
            return [
                Book(id=uuid.uuid4(), title="B1", author=author_id),
                Book(id=uuid.uuid4(), title="B2", author=author_id),
            ]

        urlconf = _make_urlconf(api)

        with override_settings(ROOT_URLCONF=urlconf):
            request = factory.get("/books/")
            response = list_books(request)

        body = json.loads(response.content)
        for item in body["data"]:
            rel = item["relationships"]["author"]
            assert "links" in rel
            assert "related" in rel["links"]
            assert rel["links"]["related"].startswith("/authors/")


class TestQueryParams:
    def test_filter_str_param(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_many("articles")
        def view(request, filter__title__contains: str = "") -> list[Article]:
            return [
                Article(id=uuid.uuid4(), title=title, content="c")
                for title in ["Hello", "World"]
            ]

        request = factory.get("/articles/?filter[title][contains]=ello")
        response = view(request)

        assert response.status_code == 200

    def test_filter_str_passed_to_handler(self):
        api = DjsonApi()
        factory = RequestFactory()
        calls = []

        @api.get_many("articles")
        def view(request, filter__title: str = "") -> list[Article]:
            calls.append(filter__title)
            return [Article(id=uuid.uuid4(), title="T", content="C")]

        request = factory.get("/articles/?filter[title]=hello")
        view(request)
        assert calls == ["hello"]

    def test_filter_str_default_when_missing(self):
        api = DjsonApi()
        factory = RequestFactory()
        calls = []

        @api.get_many("articles")
        def view(request, filter__title: str = "default_val") -> list[Article]:
            calls.append(filter__title)
            return [Article(id=uuid.uuid4(), title="T", content="C")]

        request = factory.get("/articles/")
        view(request)
        assert calls == ["default_val"]

    def test_int_param_conversion(self):
        api = DjsonApi()
        factory = RequestFactory()
        calls = []

        @api.get_many("articles")
        def view(request, page__limit: int = 10) -> list[Article]:
            calls.append(page__limit)
            return [Article(id=uuid.uuid4(), title="T", content="C")]

        request = factory.get("/articles/?page[limit]=25")
        view(request)
        assert calls == [25]

    def test_int_param_default(self):
        api = DjsonApi()
        factory = RequestFactory()
        calls = []

        @api.get_many("articles")
        def view(request, page__limit: int = 10) -> list[Article]:
            calls.append(page__limit)
            return [Article(id=uuid.uuid4(), title="T", content="C")]

        request = factory.get("/articles/")
        view(request)
        assert calls == [10]

    def test_bool_param_conversion(self):
        api = DjsonApi()
        factory = RequestFactory()
        calls = []

        @api.get_many("articles")
        def view(request, include__author: bool = False) -> list[Article]:
            calls.append(include__author)
            return [Article(id=uuid.uuid4(), title="T", content="C")]

        request = factory.get("/articles/?include=author")
        view(request)
        assert calls == [True]

    def test_list_str_param(self):
        api = DjsonApi()
        factory = RequestFactory()
        calls = []

        @api.get_many("articles")
        def view(request, sort: list[str] = []) -> list[Article]:
            calls.append(sort)
            return [Article(id=uuid.uuid4(), title="T", content="C")]

        request = factory.get("/articles/?sort=-created_at,title")
        view(request)
        assert calls == [["-created_at", "title"]]

    def test_list_str_empty_default(self):
        api = DjsonApi()
        factory = RequestFactory()
        calls = []

        @api.get_many("articles")
        def view(request, fields__articles: list[str] = []) -> list[Article]:
            calls.append(fields__articles)
            return [Article(id=uuid.uuid4(), title="T", content="C")]

        request = factory.get("/articles/")
        view(request)
        assert calls == [[]]

    def test_required_param_missing_returns_400(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_many("articles")
        def view(request, filter__q: str) -> list[Article]:
            return [Article(id=uuid.uuid4(), title="T", content="C")]

        request = factory.get("/articles/")
        response = view(request)
        assert response.status_code == 400

    def test_invalid_int_returns_400(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_many("articles")
        def view(request, page__limit: int = 10) -> list[Article]:
            return [Article(id=uuid.uuid4(), title="T", content="C")]

        request = factory.get("/articles/?page[limit]=abc")
        response = view(request)
        assert response.status_code == 400

    def test_include_from_flat_csv(self):
        api = DjsonApi()
        factory = RequestFactory()
        calls = []

        @api.get_many("articles")
        def view(request, include__author: bool = False) -> list[Article]:
            calls.append(include__author)
            return [Article(id=uuid.uuid4(), title="T", content="C")]

        request = factory.get("/articles/?include=author")
        view(request)
        assert calls == [True]

    def test_include_multiple_from_flat_csv(self):
        api = DjsonApi()
        factory = RequestFactory()
        calls = []

        @api.get_many("articles")
        def view(request, include__author: bool = False, include__comments: bool = False) -> list[Article]:
            calls.append(include__author)
            calls.append(include__comments)
            return [Article(id=uuid.uuid4(), title="T", content="C")]

        request = factory.get("/articles/?include=author,comments")
        view(request)
        assert calls == [True, True]

    def test_include_absent_uses_default(self):
        api = DjsonApi()
        factory = RequestFactory()
        calls = []

        @api.get_many("articles")
        def view(request, include__author: bool = False) -> list[Article]:
            calls.append(include__author)
            return [Article(id=uuid.uuid4(), title="T", content="C")]

        request = factory.get("/articles/")
        view(request)
        assert calls == [False]

    def test_query_params_applied_to_get_one(self):
        api = DjsonApi()
        factory = RequestFactory()
        calls = []

        @api.get_one("articles")
        def view(request, article_id: uuid.UUID, filter__q: str = "") -> Article:
            calls.append(filter__q)
            return Article(id=article_id, title="T", content="C")

        uid = uuid.uuid4()
        request = factory.get(f"/articles/{uid}?filter[q]=test")
        view(request, article_id=uid)
        assert calls == ["test"]

    def test_query_params_applied_to_create_one(self):
        api = DjsonApi()
        factory = RequestFactory()
        calls = []

        @api.create_one("articles")
        def view(request: HttpRequest, payload: Article, filter__q: str = "") -> Article:
            calls.append(filter__q)
            return Article(id=uuid.uuid4(), title="T", content="C")

        body = json.dumps({
            "data": {"type": "articles", "attributes": {"title": "T", "content": "C"}}
        })
        request = factory.post("/articles/?filter[q]=hello", body, content_type="application/vnd.api+json")
        view(request)
        assert calls == ["hello"]

    def test_openapi_spec_includes_query_params(self):
        api = DjsonApi()

        @api.get_many("articles")
        def view(request, filter__q: str = "", page__limit: int = 10, sort: list[str] = []) -> list[Article]: ...

        spec = api._build_openapi_spec()
        op = spec["paths"]["/articles/"]["get"]
        params = {p["name"]: p for p in op.get("parameters", [])}
        assert "filter[q]" in params
        assert params["filter[q]"]["in"] == "query"
        assert params["filter[q]"]["schema"]["type"] == "string"
        assert "page[limit]" in params
        assert params["page[limit]"]["schema"]["type"] == "integer"
        assert "sort" in params
        assert params["sort"]["schema"]["type"] == "array"

    def test_bare_filter_returns_error(self):
        from django.core.exceptions import ImproperlyConfigured

        api = DjsonApi()
        with pytest.raises(ImproperlyConfigured):

            @api.get_many("articles")
            def view(request, filter: str = "") -> list[Article]:
                return []

    def test_nested_sort_returns_400(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_many("articles")
        def view(request, sort__field: str = "") -> list[Article]:
            return []

        request = factory.get("/articles/?sort[field]=title")
        response = view(request)
        assert response.status_code == 400

    def test_extra_strips_prefix(self):
        api = DjsonApi()
        factory = RequestFactory()
        calls = []

        @api.get_many("articles")
        def view(request, extra__custom: str = "") -> list[Article]:
            calls.append(extra__custom)
            return [Article(id=uuid.uuid4(), title="T", content="C")]

        request = factory.get("/articles/?custom=hello")
        view(request)
        assert calls == ["hello"]

    def test_fields_filtering_attributes(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_many("articles")
        def view(request, fields__articles: list[str] = []) -> list[Article]:
            uid = uuid.uuid4()
            return [Article(id=uid, title="T", content="C")]

        request = factory.get("/articles/?fields[articles]=title")
        response = view(request)

        body = json.loads(response.content)
        item = body["data"][0]
        assert "id" in item  # id always present
        assert "title" in item["attributes"]
        assert "content" not in item["attributes"]

    def test_fields_filtering_not_applied_when_not_requested(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_many("articles")
        def view(request, fields__articles: list[str] = []) -> list[Article]:
            uid = uuid.uuid4()
            return [Article(id=uid, title="T", content="C")]

        request = factory.get("/articles/")
        response = view(request)

        body = json.loads(response.content)
        item = body["data"][0]
        assert "title" in item["attributes"]
        assert "content" in item["attributes"]

    def test_openapi_spec_include_params(self):
        api = DjsonApi()

        @api.get_many("articles")
        def view(request, include__author: bool = False, include__comments: bool = False) -> list[Article]: ...

        spec = api._build_openapi_spec()
        op = spec["paths"]["/articles/"]["get"]
        params = {p["name"]: p for p in op.get("parameters", [])}
        assert "include" in params
        assert params["include"]["schema"]["type"] == "string"
        assert "author" in params["include"]["description"]
        assert "comments" in params["include"]["description"]


class TestResponse:
    def test_plain_return_still_works(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_one("articles")
        def view(request, article_id: uuid.UUID) -> Article:
            return Article(id=article_id, title="T", content="C")

        uid = uuid.uuid4()
        request = factory.get(f"/articles/{uid}")
        response = view(request, article_id=uid)
        assert response.status_code == 200

    def test_response_included_in_body(self):
        api = DjsonApi()
        factory = RequestFactory()

        class Author(Resource):
            _type: ClassVar = "authors"
            id: int
            name: str

        @api.get_many("articles")
        def view(request) -> Response[list[Article]]:
            author = Author(id=1, name="Alice")
            return Response(
                data=[Article(id=uuid.uuid4(), title="T", content="C")],
                included=[author],
            )

        request = factory.get("/articles/")
        response = view(request)
        body = json.loads(response.content)
        assert "included" in body
        assert len(body["included"]) == 1
        assert body["included"][0]["type"] == "authors"
        assert body["included"][0]["id"] == "1"

    def test_response_no_included_when_empty(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_many("articles")
        def view(request) -> Response[list[Article]]:
            return Response(
                data=[Article(id=uuid.uuid4(), title="T", content="C")],
                included=[],
            )

        request = factory.get("/articles/")
        response = view(request)
        body = json.loads(response.content)
        assert "included" not in body

    def test_included_with_relationship_links(self):
        api = DjsonApi()
        factory = RequestFactory()

        class Author(Resource):
            _type: ClassVar = "authors"
            id: int
            name: str

        class Book(Resource):
            _type: ClassVar = "books"
            _attributes: ClassVar = ["title"]
            _singular_relationships: ClassVar = [("author", "authors")]
            id: uuid.UUID
            title: str
            author: int

        @api.get_one("authors")
        def get_author(request, author_id: int) -> Author:
            return Author(id=author_id, name="A")

        @api.get_many("books")
        def list_books(request) -> Response[list[Book]]:
            return Response(
                data=[Book(id=uuid.uuid4(), title="B", author=1)],
                included=[Author(id=1, name="A")],
            )

        urlconf = _make_urlconf(api)
        with override_settings(ROOT_URLCONF=urlconf):
            request = factory.get("/books/")
            response = list_books(request)

        body = json.loads(response.content)
        # Included author should have links to its own relationships
        included = body["included"][0]
        assert included["type"] == "authors"
        assert included["id"] == "1"
        # Primary data should have relationship links
        item = body["data"][0]
        assert item["relationships"]["author"]["links"]["related"] == "/authors/1"

    def test_response_on_get_one(self):
        api = DjsonApi()
        factory = RequestFactory()

        class Author(Resource):
            _type: ClassVar = "authors"
            id: int
            name: str

        @api.get_one("articles")
        def view(request, article_id: uuid.UUID) -> Response[Article]:
            return Response(
                data=Article(id=article_id, title="T", content="C"),
                included=[Author(id=1, name="A")],
            )

        uid = uuid.uuid4()
        request = factory.get(f"/articles/{uid}")
        response = view(request, article_id=uid)
        body = json.loads(response.content)
        assert "included" in body
        assert len(body["included"]) == 1


class TestExceptions:
    def test_not_found_renders_correctly(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_one("articles")
        def view(request, article_id: uuid.UUID) -> Article:
            raise NotFound("Custom detail")

        request = factory.get("/articles/123")
        response = view(request, article_id=uuid.uuid4())

        body = json.loads(response.content)
        error = body["errors"][0]
        assert error["status"] == "404"
        assert error["code"] == "not_found"
        assert error["title"] == "Not found"
        assert error["detail"] == "Custom detail"


class TestStartupValidation:
    def test_bare_include_param_errors(self):
        from django.core.exceptions import ImproperlyConfigured

        api = DjsonApi()
        with pytest.raises(ImproperlyConfigured):

            @api.get_many("articles")
            def view(request, include: str = "") -> list[Article]: ...

    def test_bare_include_param_on_get_one_errors(self):
        from django.core.exceptions import ImproperlyConfigured

        api = DjsonApi()
        with pytest.raises(ImproperlyConfigured):

            @api.get_one("articles")
            def view(request, article_id: int, include: str = "") -> Article: ...

    def test_bare_include_param_on_create_one_errors(self):
        from django.core.exceptions import ImproperlyConfigured

        api = DjsonApi()
        with pytest.raises(ImproperlyConfigured):

            @api.create_one("articles")
            def view(request, payload: Article, include: str = "") -> Article: ...
