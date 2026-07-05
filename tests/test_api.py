import json
import sys
import types
import uuid
from typing import ClassVar

import django
from django.conf import settings
from django.http import HttpRequest
from django.test import RequestFactory
from django.test.utils import override_settings

from djsonapi import DjsonApi, Resource
from djsonapi.exceptions import NotFound

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
    module.urlpatterns = api.urls  # type: ignore[attr-defined]
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
