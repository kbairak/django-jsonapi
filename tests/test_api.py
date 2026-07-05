import asyncio
from dataclasses import field
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
from djsonapi.exceptions import NotFound, TooManyRequests
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


class TestEditOne:
    def test_edit_one_url(self):
        api = DjsonApi()

        @api.edit_one("articles")
        def view(request: HttpRequest, article_id: uuid.UUID, payload: Article) -> Article: ...

        urls = api.urls
        assert any(u.name == "edit_one__articles" for u in urls)

    def test_handler_called_with_correct_args(self):
        api = DjsonApi()
        factory = RequestFactory()

        calls = []

        class EditableArticle(Resource):
            _type: ClassVar = "articles"
            _attributes: ClassVar = ["title", "content"]
            _edit_fields: ClassVar = ["id", "title", "content"]
            id: uuid.UUID
            title: str
            content: str

        @api.edit_one("articles")
        def view(request: HttpRequest, article_id: uuid.UUID, payload: EditableArticle) -> EditableArticle:
            calls.append((request, article_id, payload))
            return EditableArticle(id=article_id, title=payload.title, content=payload.content)

        uid = uuid.uuid4()
        body = json.dumps({
            "data": {
                "type": "articles",
                "id": str(uid),
                "attributes": {"title": "Updated", "content": "Changed"},
            }
        })
        request = factory.patch(f"/articles/{uid}", body, content_type="application/vnd.api+json")
        view(request, article_id=uid)

        assert len(calls) == 1
        req, pk, payload = calls[0]
        assert pk == uid
        assert payload.id == uid
        assert payload.title == "Updated"
        assert payload.content == "Changed"

    def test_200_response_structure(self):
        api = DjsonApi()
        factory = RequestFactory()

        class EditableArticle(Resource):
            _type: ClassVar = "articles"
            _attributes: ClassVar = ["title", "content"]
            _edit_fields: ClassVar = ["id", "title", "content"]
            id: uuid.UUID
            title: str
            content: str

        @api.edit_one("articles")
        def view(request: HttpRequest, article_id: uuid.UUID, payload: EditableArticle) -> EditableArticle:
            return EditableArticle(id=article_id, title=payload.title, content=payload.content)

        uid = uuid.uuid4()
        body = json.dumps({
            "data": {
                "type": "articles",
                "id": str(uid),
                "attributes": {"title": "Updated", "content": "Changed"},
            }
        })
        request = factory.patch(f"/articles/{uid}", body, content_type="application/vnd.api+json")
        response = view(request, article_id=uid)

        assert response.status_code == 200
        assert response["Content-Type"] == "application/vnd.api+json"
        resp_data = json.loads(response.content)
        assert resp_data["data"]["type"] == "articles"
        assert resp_data["data"]["id"] == str(uid)
        assert resp_data["data"]["attributes"]["title"] == "Updated"
        assert resp_data["data"]["attributes"]["content"] == "Changed"

    def test_400_on_missing_id(self):
        api = DjsonApi()
        factory = RequestFactory()

        class EditableArticle(Resource):
            _type: ClassVar = "articles"
            _attributes: ClassVar = ["title", "content"]
            _edit_fields: ClassVar = ["id", "title", "content"]
            id: uuid.UUID
            title: str
            content: str

        @api.edit_one("articles")
        def view(request: HttpRequest, article_id: uuid.UUID, payload: EditableArticle) -> EditableArticle:
            return EditableArticle(id=article_id, title=payload.title, content=payload.content)

        uid = uuid.uuid4()
        body = json.dumps({
            "data": {
                "type": "articles",
                "attributes": {"title": "Updated"},
            }
        })
        request = factory.patch(f"/articles/{uid}", body, content_type="application/vnd.api+json")
        response = view(request, article_id=uid)

        assert response.status_code == 400
        resp_data = json.loads(response.content)
        assert "errors" in resp_data

    def test_400_on_invalid_json(self):
        api = DjsonApi()
        factory = RequestFactory()

        class EditableArticle(Resource):
            _type: ClassVar = "articles"
            _attributes: ClassVar = ["title", "content"]
            _edit_fields: ClassVar = ["id", "title", "content"]
            id: uuid.UUID
            title: str
            content: str

        @api.edit_one("articles")
        def view(request: HttpRequest, article_id: uuid.UUID, payload: EditableArticle) -> EditableArticle:
            return EditableArticle(id=article_id, title="T", content="C")

        uid = uuid.uuid4()
        request = factory.patch(f"/articles/{uid}", "not json", content_type="application/vnd.api+json")
        response = view(request, article_id=uid)

        assert response.status_code == 400

    def test_500_on_unhandled_exception(self):
        api = DjsonApi()
        factory = RequestFactory()

        class EditableArticle(Resource):
            _type: ClassVar = "articles"
            _attributes: ClassVar = ["title", "content"]
            _edit_fields: ClassVar = ["id", "title", "content"]
            id: uuid.UUID
            title: str
            content: str

        @api.edit_one("articles")
        def view(request: HttpRequest, article_id: uuid.UUID, payload: EditableArticle) -> EditableArticle:
            raise ValueError("something broke")

        uid = uuid.uuid4()
        body = json.dumps({
            "data": {
                "type": "articles",
                "id": str(uid),
                "attributes": {"title": "T", "content": "C"},
            }
        })
        request = factory.patch(f"/articles/{uid}", body, content_type="application/vnd.api+json")
        response = view(request, article_id=uid)

        assert response.status_code == 500

    def test_response_with_included(self):
        api = DjsonApi()
        factory = RequestFactory()

        class Author(Resource):
            _type: ClassVar = "authors"
            id: int
            name: str

        class EditableArticle(Resource):
            _type: ClassVar = "articles"
            _attributes: ClassVar = ["title", "content"]
            _singular_relationships: ClassVar = [("author", "authors")]
            _edit_fields: ClassVar = ["id", "title", "content", "author"]
            id: uuid.UUID
            title: str
            content: str
            author: int

        @api.edit_one("articles")
        def view(request: HttpRequest, article_id: uuid.UUID, payload: EditableArticle) -> Response[EditableArticle]:
            return Response(
                data=EditableArticle(id=article_id, title=payload.title, content=payload.content, author=payload.author),
                included=[Author(id=1, name="Alice")],
            )

        uid = uuid.uuid4()
        body = json.dumps({
            "data": {
                "type": "articles",
                "id": str(uid),
                "attributes": {"title": "T", "content": "C"},
                "relationships": {"author": {"data": {"type": "authors", "id": 1}}},
            }
        })
        request = factory.patch(f"/articles/{uid}", body, content_type="application/vnd.api+json")
        response = view(request, article_id=uid)

        body = json.loads(response.content)
        assert "included" in body
        assert len(body["included"]) == 1
        assert body["included"][0]["type"] == "authors"

    def test_url_routing_with_get(self):
        api = DjsonApi()
        factory = RequestFactory()

        class EditableArticle(Resource):
            _type: ClassVar = "articles"
            _attributes: ClassVar = ["title", "content"]
            _edit_fields: ClassVar = ["id", "title", "content"]
            id: uuid.UUID
            title: str
            content: str

        @api.get_one("articles")
        def get_article(request, article_id: uuid.UUID) -> EditableArticle:
            return EditableArticle(id=article_id, title="Original", content="Original")

        @api.edit_one("articles")
        def edit_article(request, article_id: uuid.UUID, payload: EditableArticle) -> EditableArticle:
            return EditableArticle(id=article_id, title=payload.title, content=payload.content)

        urlconf = _make_urlconf(api)
        with override_settings(ROOT_URLCONF=urlconf):
            uid = uuid.uuid4()
            body = json.dumps({
                "data": {
                    "type": "articles",
                    "id": str(uid),
                    "attributes": {"title": "Updated", "content": "Changed"},
                }
            })
            request = factory.patch(f"/articles/{uid}", body, content_type="application/vnd.api+json")
            response = edit_article(request, article_id=uid)

            assert response.status_code == 200
            resp_data = json.loads(response.content)
            assert resp_data["data"]["attributes"]["title"] == "Updated"

    def test_sync_handler(self):
        api = DjsonApi()
        factory = RequestFactory()

        class EditableArticle(Resource):
            _type: ClassVar = "articles"
            _attributes: ClassVar = ["title", "content"]
            _edit_fields: ClassVar = ["id", "title", "content"]
            id: uuid.UUID
            title: str
            content: str

        @api.edit_one("articles")
        def view(request: HttpRequest, article_id: uuid.UUID, payload: EditableArticle) -> EditableArticle:
            return EditableArticle(id=article_id, title=payload.title, content=payload.content)

        uid = uuid.uuid4()
        body = json.dumps({
            "data": {
                "type": "articles",
                "id": str(uid),
                "attributes": {"title": "T", "content": "C"},
            }
        })
        request = factory.patch(f"/articles/{uid}", body, content_type="application/vnd.api+json")
        response = view(request, article_id=uid)
        assert response.status_code == 200

    def test_async_handler(self):
        api = DjsonApi()
        factory = RequestFactory()
        import asyncio

        class EditableArticle(Resource):
            _type: ClassVar = "articles"
            _attributes: ClassVar = ["title", "content"]
            _edit_fields: ClassVar = ["id", "title", "content"]
            id: uuid.UUID
            title: str
            content: str

        @api.edit_one("articles")
        async def view(request: HttpRequest, article_id: uuid.UUID, payload: EditableArticle) -> EditableArticle:
            return EditableArticle(id=article_id, title=payload.title, content=payload.content)

        uid = uuid.uuid4()
        body = json.dumps({
            "data": {
                "type": "articles",
                "id": str(uid),
                "attributes": {"title": "T", "content": "C"},
            }
        })
        request = factory.patch(f"/articles/{uid}", body, content_type="application/vnd.api+json")
        response = asyncio.run(view(request, article_id=uid))
        assert response.status_code == 200


class TestDeleteOne:
    def test_delete_one_url(self):
        api = DjsonApi()

        @api.delete_one("articles")
        def view(request: HttpRequest, article_id: uuid.UUID) -> None: ...

        urls = api.urls
        assert any(u.name == "delete_one__articles" for u in urls)

    def test_204_no_content(self):
        api = DjsonApi()
        factory = RequestFactory()

        called = False

        @api.delete_one("articles")
        def view(request: HttpRequest, article_id: uuid.UUID) -> None:
            nonlocal called
            called = True

        uid = uuid.uuid4()
        request = factory.delete(f"/articles/{uid}")
        response = view(request, article_id=uid)

        assert called
        assert response.status_code == 204

    def test_404_handled(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.delete_one("articles")
        def view(request: HttpRequest, article_id: uuid.UUID) -> None:
            raise NotFound(f"Article with id '{article_id}' not found")

        uid = uuid.uuid4()
        request = factory.delete(f"/articles/{uid}")
        response = view(request, article_id=uid)

        assert response.status_code == 404

    def test_500_on_error(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.delete_one("articles")
        def view(request: HttpRequest, article_id: uuid.UUID) -> None:
            raise ValueError("something broke")

        uid = uuid.uuid4()
        request = factory.delete(f"/articles/{uid}")
        response = view(request, article_id=uid)

        assert response.status_code == 500

    def test_url_routing_with_get_patch_delete(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_one("articles")
        def get_article(request, article_id: uuid.UUID) -> Article:
            return Article(id=article_id, title="T", content="C")

        @api.delete_one("articles")
        def delete_article(request, article_id: uuid.UUID) -> None:
            pass

        urlconf = _make_urlconf(api)
        with override_settings(ROOT_URLCONF=urlconf):
            uid = uuid.uuid4()
            request = factory.delete(f"/articles/{uid}", content_type="application/vnd.api+json")
            response = delete_article(request, article_id=uid)
            assert response.status_code == 204

    def test_async_handler(self):
        api = DjsonApi()
        factory = RequestFactory()
        import asyncio

        @api.delete_one("articles")
        async def view(request: HttpRequest, article_id: uuid.UUID) -> None:
            pass

        uid = uuid.uuid4()
        request = factory.delete(f"/articles/{uid}")
        response = asyncio.run(view(request, article_id=uid))

        assert response.status_code == 204


class TestGetRelationship:
    def test_get_relationship_url(self):
        api = DjsonApi()

        @api.get_relationship("articles", "author")
        def view(request, article_id: uuid.UUID) -> Article: ...

        urls = api.urls
        assert any(u.name == "get_relationship__articles__author" for u in urls)

    def test_singular_handler_called_with_correct_args(self):
        api = DjsonApi()
        factory = RequestFactory()

        calls = []

        class Author(Resource):
            _type: ClassVar = "authors"
            id: uuid.UUID
            name: str

        @api.get_relationship("articles", "author")
        def view(request, article_id: uuid.UUID) -> Author:
            calls.append((request, article_id))
            return Author(id=uuid.uuid4(), name="Alice")

        uid = uuid.uuid4()
        request = factory.get(f"/articles/{uid}/author")
        view(request, article_id=uid)

        assert len(calls) == 1
        assert calls[0] == (request, uid)

    def test_plural_handler_called_with_correct_args(self):
        api = DjsonApi()
        factory = RequestFactory()

        calls = []

        class Comment(Resource):
            _type: ClassVar = "comments"
            id: uuid.UUID
            body: str

        @api.get_relationship("articles", "comments")
        def view(request, article_id: uuid.UUID) -> list[Comment]:
            calls.append((request, article_id))
            return [Comment(id=uuid.uuid4(), body="Nice post!")]

        uid = uuid.uuid4()
        request = factory.get(f"/articles/{uid}/comments")
        view(request, article_id=uid)

        assert len(calls) == 1
        assert calls[0] == (request, uid)

    def test_singular_response_structure(self):
        api = DjsonApi()
        factory = RequestFactory()

        class Author(Resource):
            _type: ClassVar = "authors"
            _attributes: ClassVar = ["name"]
            id: uuid.UUID
            name: str

        @api.get_relationship("articles", "author")
        def view(request, article_id: uuid.UUID) -> Author:
            return Author(id=uuid.uuid4(), name="Alice")

        uid = uuid.uuid4()
        request = factory.get(f"/articles/{uid}/author")
        response = view(request, article_id=uid)

        assert response.status_code == 200
        assert response["Content-Type"] == "application/vnd.api+json"

        body = json.loads(response.content)
        assert "data" in body
        assert body["data"]["type"] == "authors"
        assert body["data"]["attributes"]["name"] == "Alice"

    def test_plural_response_structure(self):
        api = DjsonApi()
        factory = RequestFactory()

        class Comment(Resource):
            _type: ClassVar = "comments"
            _attributes: ClassVar = ["body"]
            id: uuid.UUID
            body: str

        @api.get_relationship("articles", "comments")
        def view(request, article_id: uuid.UUID) -> list[Comment]:
            author_id = uuid.uuid4()
            return [
                Comment(id=uuid.uuid4(), body="First!"),
                Comment(id=uuid.uuid4(), body="Second"),
            ]

        uid = uuid.uuid4()
        request = factory.get(f"/articles/{uid}/comments")
        response = view(request, article_id=uid)

        assert response.status_code == 200
        body = json.loads(response.content)
        assert isinstance(body["data"], list)
        assert len(body["data"]) == 2
        for item in body["data"]:
            assert item["type"] == "comments"
            assert "attributes" in item

    def test_self_link_when_reverse_works(self):
        api = DjsonApi()
        factory = RequestFactory()

        class Author(Resource):
            _type: ClassVar = "authors"
            id: uuid.UUID
            name: str

        @api.get_relationship("articles", "author")
        def view(request, article_id: uuid.UUID) -> Author:
            return Author(id=uuid.uuid4(), name="Alice")

        urlconf = _make_urlconf(api)
        uid = uuid.uuid4()

        with override_settings(ROOT_URLCONF=urlconf):
            request = factory.get(f"/articles/{uid}/author")
            response = view(request, article_id=uid)

        body = json.loads(response.content)
        assert body["data"]["links"]["self"] == f"/articles/{uid}/author"
        assert body["links"]["self"] == f"/articles/{uid}/author"

    def test_plural_self_link(self):
        api = DjsonApi()
        factory = RequestFactory()

        class Comment(Resource):
            _type: ClassVar = "comments"
            id: uuid.UUID
            body: str

        @api.get_relationship("articles", "comments")
        def view(request, article_id: uuid.UUID) -> list[Comment]:
            return [Comment(id=uuid.uuid4(), body="Nice")]

        urlconf = _make_urlconf(api)
        uid = uuid.uuid4()

        with override_settings(ROOT_URLCONF=urlconf):
            request = factory.get(f"/articles/{uid}/comments")
            response = view(request, article_id=uid)

        body = json.loads(response.content)
        assert body["links"]["self"] == f"/articles/{uid}/comments"

    def test_related_links_use_relationship_endpoint(self):
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

        @api.get_relationship("books", "author")
        def get_book_author(request, book_id: uuid.UUID) -> Author:
            return Author(id=uuid.uuid4(), name="Alice")

        @api.get_many("books")
        def list_books(request) -> list[Book]:
            return [
                Book(id=uuid.uuid4(), title="B1", author=uuid.uuid4()),
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
            # Should link to relationship endpoint, not get_one endpoint
            assert rel["links"]["related"].startswith("/books/")

    def test_related_links_fallback_to_get_one(self):
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
            return Author(id=author_id, name="A")

        @api.get_many("books")
        def list_books(request) -> list[Book]:
            author_id = uuid.uuid4()
            return [
                Book(id=uuid.uuid4(), title="B1", author=author_id),
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

    def test_response_with_included(self):
        api = DjsonApi()
        factory = RequestFactory()

        class Author(Resource):
            _type: ClassVar = "authors"
            id: int
            name: str

        class Editor(Resource):
            _type: ClassVar = "editors"
            id: int
            name: str

        @api.get_relationship("articles", "author")
        def view(request, article_id: int) -> Response[Author]:
            return Response(
                data=Author(id=1, name="Alice"),
                included=[Editor(id=1, name="Bob")],
            )

        request = factory.get("/articles/1/author")
        response = view(request, article_id=1)

        body = json.loads(response.content)
        assert "included" in body
        assert len(body["included"]) == 1
        assert body["included"][0]["type"] == "editors"

    def test_404_on_not_found(self):
        api = DjsonApi()
        factory = RequestFactory()
        from djsonapi.exceptions import NotFound

        @api.get_relationship("articles", "author")
        def view(request, article_id: int) -> Article:
            raise NotFound(f"Article {article_id} not found")

        request = factory.get("/articles/1/author")
        response = view(request, article_id=1)

        assert response.status_code == 404
        body = json.loads(response.content)
        assert "errors" in body

    def test_500_on_unhandled_exception(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_relationship("articles", "author")
        def view(request, article_id: int) -> Article:
            raise ValueError("something broke")

        request = factory.get("/articles/1/author")
        response = view(request, article_id=1)

        assert response.status_code == 500
        body = json.loads(response.content)
        assert "errors" in body

    def test_sync_handler(self):
        api = DjsonApi()
        factory = RequestFactory()

        class Author(Resource):
            _type: ClassVar = "authors"
            id: uuid.UUID
            name: str

        @api.get_relationship("articles", "author")
        def view(request, article_id: uuid.UUID) -> Author:
            return Author(id=uuid.uuid4(), name="Alice")

        uid = uuid.uuid4()
        request = factory.get(f"/articles/{uid}/author")
        response = view(request, article_id=uid)

        assert response.status_code == 200

    def test_async_handler(self):
        api = DjsonApi()
        factory = RequestFactory()
        import asyncio

        class Author(Resource):
            _type: ClassVar = "authors"
            id: uuid.UUID
            name: str

        @api.get_relationship("articles", "author")
        async def view(request, article_id: uuid.UUID) -> Author:
            return Author(id=uuid.uuid4(), name="Alice")

        uid = uuid.uuid4()
        request = factory.get(f"/articles/{uid}/author")
        response = asyncio.run(view(request, article_id=uid))

        assert response.status_code == 200

    def test_query_params_passed_to_handler(self):
        api = DjsonApi()
        factory = RequestFactory()
        calls = []

        class Author(Resource):
            _type: ClassVar = "authors"
            id: uuid.UUID
            name: str

        @api.get_relationship("articles", "author")
        def view(request, article_id: uuid.UUID, filter__q: str = "") -> Author:
            calls.append(filter__q)
            return Author(id=uuid.uuid4(), name="Alice")

        uid = uuid.uuid4()
        request = factory.get(f"/articles/{uid}/author?filter[q]=test")
        view(request, article_id=uid)

        assert calls == ["test"]

    def test_url_routing_with_get_one(self):
        api = DjsonApi()
        factory = RequestFactory()

        class Author(Resource):
            _type: ClassVar = "authors"
            id: uuid.UUID
            name: str

        @api.get_one("articles")
        def get_article(request, article_id: uuid.UUID) -> Article:
            return Article(id=article_id, title="T", content="C")

        @api.get_relationship("articles", "author")
        def get_article_author(request, article_id: uuid.UUID) -> Author:
            return Author(id=uuid.uuid4(), name="Alice")

        urlconf = _make_urlconf(api)
        uid = uuid.uuid4()

        with override_settings(ROOT_URLCONF=urlconf):
            request = factory.get(f"/articles/{uid}/author")
            response = get_article_author(request, article_id=uid)

        assert response.status_code == 200
        body = json.loads(response.content)
        assert body["data"]["type"] == "authors"

    def test_openapi_spec(self):
        api = DjsonApi()

        class Author(Resource):
            _type: ClassVar = "authors"
            id: uuid.UUID
            name: str

        @api.get_relationship("articles", "author")
        def view(request, article_id: uuid.UUID) -> Author:
            return Author(id=uuid.uuid4(), name="Alice")

        spec = api._build_openapi_spec()
        assert "/articles/{article_id}/author" in spec["paths"]
        op = spec["paths"]["/articles/{article_id}/author"]["get"]
        assert op["tags"] == ["articles"]
        params = {p["name"]: p for p in op.get("parameters", [])}
        assert "article_id" in params
        assert params["article_id"]["in"] == "path"

    def test_invalid_param_raises_improperly_configured(self):
        from django.core.exceptions import ImproperlyConfigured

        api = DjsonApi()
        with pytest.raises(ImproperlyConfigured):

            @api.get_relationship("articles", "author")
            def view(request, article_id: int, bad_param: str) -> Article: ...


class TestEditRelationship:
    def test_url_registered(self):
        api = DjsonApi()

        @api.edit_relationship("articles", "author")
        def view(request, article_id: int, author_id: int) -> None: ...

        urls = api.urls
        assert any(u.name == "edit_relationship__articles__author" for u in urls)

    def test_handler_called_with_correct_args(self):
        api = DjsonApi()
        factory = RequestFactory()

        calls = []

        @api.edit_relationship("articles", "author")
        def view(request, article_id: int, author_id: int) -> None:
            calls.append((request, article_id, author_id))

        request = factory.patch(
            "/articles/1/relationships/author",
            json.dumps({"data": {"id": 2, "type": "authors"}}),
            content_type="application/vnd.api+json",
        )
        view(request, article_id=1)

        assert len(calls) == 1
        assert calls[0] == (request, 1, 2)

    def test_response_is_204(self):
        api = DjsonApi()

        @api.edit_relationship("articles", "author")
        def view(request, article_id: int, author_id: int) -> None: ...

        factory = RequestFactory()
        request = factory.patch(
            "/articles/1/relationships/author",
            json.dumps({"data": {"id": 2, "type": "authors"}}),
            content_type="application/vnd.api+json",
        )
        response = view(request, article_id=1)

        assert response.status_code == 204

    def test_body_without_data_returns_400(self):
        api = DjsonApi()

        @api.edit_relationship("articles", "author")
        def view(request, article_id: int, author_id: int) -> None: ...

        factory = RequestFactory()
        request = factory.patch(
            "/articles/1/relationships/author",
            json.dumps({}),
            content_type="application/vnd.api+json",
        )
        response = view(request, article_id=1)

        assert response.status_code == 400

    def test_nullable_allows_data_null(self):
        api = DjsonApi()

        calls = []

        @api.edit_relationship("articles", "author")
        def view(request, article_id: int, author_id: int | None) -> None:
            calls.append(author_id)

        factory = RequestFactory()
        request = factory.patch(
            "/articles/1/relationships/author",
            json.dumps({"data": None}),
            content_type="application/vnd.api+json",
        )
        response = view(request, article_id=1)

        assert response.status_code == 204
        assert calls == [None]

    def test_non_nullable_rejects_data_null(self):
        api = DjsonApi()

        @api.edit_relationship("articles", "author")
        def view(request, article_id: int, author_id: int) -> None: ...

        factory = RequestFactory()
        request = factory.patch(
            "/articles/1/relationships/author",
            json.dumps({"data": None}),
            content_type="application/vnd.api+json",
        )
        response = view(request, article_id=1)

        assert response.status_code == 400

    def test_self_link_in_get_one_response(self):
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

        @api.edit_relationship("books", "author")
        def edit_book_author(request, book_id: uuid.UUID, author_id: uuid.UUID) -> None: ...

        book_id = uuid.uuid4()

        @api.get_one("books")
        def get_book(request, book_id: uuid.UUID) -> Book:
            return Book(id=book_id, title="B1", author=uuid.uuid4())

        urlconf = _make_urlconf(api)

        with override_settings(ROOT_URLCONF=urlconf):
            request = factory.get(f"/books/{book_id}")
            response = get_book(request, book_id=book_id)

        body = json.loads(response.content)
        rel = body["data"]["relationships"]["author"]
        assert "links" in rel
        assert "self" in rel["links"]
        assert rel["links"]["self"] == f"/books/{book_id}/relationships/author"

    def test_openapi_spec_includes_path(self):
        api = DjsonApi()

        @api.edit_relationship("articles", "author")
        def view(request, article_id: int, author_id: int) -> None: ...

        spec = api._build_openapi_spec()
        assert "/articles/{article_id}/relationships/author" in spec["paths"]
        op = spec["paths"]["/articles/{article_id}/relationships/author"]["patch"]
        assert op["tags"] == ["articles"]


class TestOpenAPIErrorResponses:
    def test_error_response_in_openapi_spec(self):
        api = DjsonApi()

        @api.get_one("articles", errors=[NotFound, TooManyRequests])
        def view(request, article_id: int) -> Article:
            return Article(id=uuid.uuid4(), title="T", content="C")

        spec = api._build_openapi_spec()
        op = spec["paths"]["/articles/{article_id}"]["get"]

        assert "404" in op["responses"]
        assert op["responses"]["404"]["description"] == "Not found"
        assert "$ref" in op["responses"]["404"]["content"]["application/vnd.api+json"]["schema"]

        assert "429" in op["responses"]
        assert op["responses"]["429"]["description"] == "Too many requests"

    def test_error_response_schema_contents(self):
        api = DjsonApi()

        @api.get_one("articles", errors=[NotFound])
        def view(request, article_id: int) -> Article:
            return Article(id=uuid.uuid4(), title="T", content="C")

        spec = api._build_openapi_spec()
        schema = spec["components"]["schemas"]["NotFound_error"]
        error_obj = schema["properties"]["errors"]["items"]["properties"]

        assert error_obj["status"]["const"] == "404"
        assert error_obj["code"]["const"] == "not_found"
        assert error_obj["title"]["const"] == "Not found"
        assert "detail" in error_obj

    def test_error_schema_for_400_includes_source(self):
        from djsonapi.exceptions import BadRequest

        api = DjsonApi()

        @api.get_one("articles", errors=[BadRequest])
        def view(request, article_id: int) -> Article:
            return Article(id=uuid.uuid4(), title="T", content="C")

        spec = api._build_openapi_spec()
        schema = spec["components"]["schemas"]["BadRequest_error"]
        error_obj = schema["properties"]["errors"]["items"]["properties"]

        assert "source" in error_obj
        assert "pointer" in error_obj["source"]["properties"]


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


class TestPaginationLinks:
    def test_many_response_includes_merged_links(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_many("articles")
        def view(request) -> Response[list[Article]]:
            return Response(
                data=[Article(id=uuid.uuid4(), title="T", content="C")],
                links={"prev": {"page": 1}, "next": {"page": 3}},
            )

        urlconf = _make_urlconf(api)
        with override_settings(ROOT_URLCONF=urlconf):
            request = factory.get("/articles/?page=2")
            response = view(request)
        body = json.loads(response.content)

        assert body["links"]["self"] == "/articles/"
        assert body["links"]["prev"] == "/articles/?page=1"
        assert body["links"]["next"] == "/articles/?page=3"

    def test_many_response_merges_with_existing_query_params(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_many("articles")
        def view(request) -> Response[list[Article]]:
            return Response(
                data=[Article(id=uuid.uuid4(), title="T", content="C")],
                links={"prev": {"page": 1, "sort": "-title"}},
            )

        urlconf = _make_urlconf(api)
        with override_settings(ROOT_URLCONF=urlconf):
            request = factory.get("/articles/?page=2&sort=title")
            response = view(request)
        body = json.loads(response.content)

        assert "prev" in body["links"]
        assert "page=1" in body["links"]["prev"]
        assert "sort=-title" in body["links"]["prev"]

    def test_one_response_includes_links(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_one("articles")
        def view(request, article_id: uuid.UUID) -> Response[Article]:
            return Response(
                data=Article(id=article_id, title="T", content="C"),
                links={"prev": {"page": 1}},
            )

        uid = uuid.uuid4()
        urlconf = _make_urlconf(api)
        with override_settings(ROOT_URLCONF=urlconf):
            request = factory.get(f"/articles/{uid}?page=2")
            response = view(request, article_id=uid)
        body = json.loads(response.content)

        assert body["links"]["self"] == f"/articles/{uid}"
        assert body["links"]["prev"] == f"/articles/{uid}?page=1"

    def test_no_extra_links_when_response_has_none(self):
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

        assert body["links"] == {"self": "/articles/"}

    def test_empty_link_defs_keeps_self_link(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_many("articles")
        def view(request) -> Response[list[Article]]:
            return Response(
                data=[Article(id=uuid.uuid4(), title="T", content="C")],
                links={},
            )

        urlconf = _make_urlconf(api)
        with override_settings(ROOT_URLCONF=urlconf):
            request = factory.get("/articles/")
            response = view(request)
        body = json.loads(response.content)

        assert body["links"] == {"self": "/articles/"}

    def test_async_get_many_pagination_links(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_many("articles")
        async def view(request) -> Response[list[Article]]:
            return Response(
                data=[Article(id=uuid.uuid4(), title="T", content="C")],
                links={"next": {"page": 2}},
            )

        urlconf = _make_urlconf(api)
        with override_settings(ROOT_URLCONF=urlconf):
            request = factory.get("/articles/?page=1")
            response = asyncio.run(view(request))
        body = json.loads(response.content)

        assert body["links"]["self"] == "/articles/"
        assert body["links"]["next"] == "/articles/?page=2"

    def test_async_get_one_pagination_links(self):
        api = DjsonApi()
        factory = RequestFactory()

        @api.get_one("articles")
        async def view(request, article_id: uuid.UUID) -> Response[Article]:
            return Response(
                data=Article(id=article_id, title="T", content="C"),
                links={"prev": {"page": 1}},
            )

        uid = uuid.uuid4()
        urlconf = _make_urlconf(api)
        with override_settings(ROOT_URLCONF=urlconf):
            request = factory.get(f"/articles/{uid}?page=2")
            response = asyncio.run(view(request, article_id=uid))
        body = json.loads(response.content)

        assert body["links"]["self"] == f"/articles/{uid}"
        assert body["links"]["prev"] == f"/articles/{uid}?page=1"


class TestPluralRelationshipLinks:
    def test_related_link_for_plural_relationship(self):
        api = DjsonApi()
        factory = RequestFactory()

        class Chapter(Resource):
            _type: ClassVar = "chapters"
            id: uuid.UUID
            title: str

        class Book(Resource):
            _type: ClassVar = "books"
            _attributes: ClassVar = ["title"]
            _singular_relationships: ClassVar = [("author", "users")]
            _plural_relationships: ClassVar = [("chapters", "chapters")]
            id: uuid.UUID
            title: str
            author: uuid.UUID
            chapters: list[uuid.UUID] = field(default_factory=list)

        @api.get_one("books")
        def get_book(request, book_id: uuid.UUID) -> Book:
            return Book(id=book_id, title="B", author=uuid.uuid4(), chapters=[])

        @api.get_relationship("books", "chapters")
        def get_book_chapters(request, book_id: uuid.UUID) -> list[Chapter]:
            return []

        urlconf = _make_urlconf(api)
        with override_settings(ROOT_URLCONF=urlconf):
            uid = uuid.uuid4()
            request = factory.get(f"/books/{uid}")
            response = get_book(request, book_id=uid)

        body = json.loads(response.content)
        rel = body["data"]["relationships"]["chapters"]
        assert "links" in rel
        assert "related" in rel["links"]
        assert rel["links"]["related"] == f"/books/{uid}/chapters"

    def test_self_link_for_plural_relationship(self):
        api = DjsonApi()
        factory = RequestFactory()

        class Chapter(Resource):
            _type: ClassVar = "chapters"
            id: uuid.UUID
            title: str

        class Book(Resource):
            _type: ClassVar = "books"
            _attributes: ClassVar = ["title"]
            _plural_relationships: ClassVar = [("chapters", "chapters")]
            id: uuid.UUID
            title: str
            chapters: list[uuid.UUID] = field(default_factory=list)

        @api.get_one("books")
        def get_book(request, book_id: uuid.UUID) -> Book:
            return Book(id=book_id, title="B", chapters=[])

        @api.reset_relationship("books", "chapters")
        def reset_book_chapters(request, book_id: uuid.UUID, chapter_ids: list[int]) -> None:
            pass

        urlconf = _make_urlconf(api)
        with override_settings(ROOT_URLCONF=urlconf):
            uid = uuid.uuid4()
            request = factory.get(f"/books/{uid}")
            response = get_book(request, book_id=uid)

        body = json.loads(response.content)
        rel = body["data"]["relationships"]["chapters"]
        assert "links" in rel
        assert "self" in rel["links"]
        assert rel["links"]["self"] == f"/books/{uid}/relationships/chapters"

    def test_both_links_for_plural(self):
        api = DjsonApi()
        factory = RequestFactory()

        class Chapter(Resource):
            _type: ClassVar = "chapters"
            id: uuid.UUID
            title: str

        class Book(Resource):
            _type: ClassVar = "books"
            _attributes: ClassVar = ["title"]
            _plural_relationships: ClassVar = [("chapters", "chapters")]
            id: uuid.UUID
            title: str
            chapters: list[uuid.UUID] = field(default_factory=list)

        @api.get_one("books")
        def get_book(request, book_id: uuid.UUID) -> Book:
            return Book(id=book_id, title="B", chapters=[])

        @api.get_relationship("books", "chapters")
        def get_book_chapters(request, book_id: uuid.UUID) -> list[Chapter]:
            return []

        @api.reset_relationship("books", "chapters")
        def reset_book_chapters(request, book_id: uuid.UUID, chapter_ids: list[int]) -> None:
            pass

        urlconf = _make_urlconf(api)
        with override_settings(ROOT_URLCONF=urlconf):
            uid = uuid.uuid4()
            request = factory.get(f"/books/{uid}")
            response = get_book(request, book_id=uid)

        body = json.loads(response.content)
        rel = body["data"]["relationships"]["chapters"]
        assert "links" in rel
        assert rel["links"]["related"] == f"/books/{uid}/chapters"
        assert rel["links"]["self"] == f"/books/{uid}/relationships/chapters"

    def test_plural_links_in_list_response(self):
        api = DjsonApi()
        factory = RequestFactory()

        class Chapter(Resource):
            _type: ClassVar = "chapters"
            id: int
            title: str

        class Book(Resource):
            _type: ClassVar = "books"
            _attributes: ClassVar = ["title"]
            _plural_relationships: ClassVar = [("chapters", "chapters")]
            id: uuid.UUID
            title: str
            chapters: list[int] = field(default_factory=list)

        @api.get_many("books")
        def list_books(request) -> list[Book]:
            return [Book(id=uuid.uuid4(), title="B1"), Book(id=uuid.uuid4(), title="B2")]

        @api.get_relationship("books", "chapters")
        def get_book_chapters(request, book_id: uuid.UUID) -> list[Chapter]:
            return []

        urlconf = _make_urlconf(api)
        with override_settings(ROOT_URLCONF=urlconf):
            request = factory.get("/books/")
            response = list_books(request)

        body = json.loads(response.content)
        for item in body["data"]:
            rel = item["relationships"]["chapters"]
            assert "links" in rel
            assert "related" in rel["links"]
            assert rel["links"]["related"].startswith("/books/")


class TestPluralRelationshipMgmt:
    def test_reset_relationship_sends_list_of_ints(self):
        api = DjsonApi()
        factory = RequestFactory()
        calls = []

        @api.reset_relationship("books", "chapters")
        def reset_book_chapters(request, book_id: uuid.UUID, chapter_ids: list[int]) -> None:
            calls.append(chapter_ids)

        uid = uuid.uuid4()
        request = factory.patch(
            "/",
            data=json.dumps({"data": [{"id": 1, "type": "chapters"}, {"id": 2, "type": "chapters"}]}),
            content_type="application/vnd.api+json",
        )
        response = reset_book_chapters(request, book_id=uid)

        assert response.status_code == 204
        assert calls == [[1, 2]]

    def test_add_to_relationship_sends_list_of_ints(self):
        api = DjsonApi()
        factory = RequestFactory()
        calls = []

        @api.add_to_relationship("books", "chapters")
        def add_book_chapters(request, book_id: uuid.UUID, chapter_ids: list[int]) -> None:
            calls.append(chapter_ids)

        uid = uuid.uuid4()
        request = factory.post(
            "/",
            data=json.dumps({"data": [{"id": 3, "type": "chapters"}]}),
            content_type="application/vnd.api+json",
        )
        response = add_book_chapters(request, book_id=uid)

        assert response.status_code == 204
        assert calls == [[3]]

    def test_remove_from_relationship_sends_list_of_ints(self):
        api = DjsonApi()
        factory = RequestFactory()
        calls = []

        @api.remove_from_relationship("books", "chapters")
        def remove_book_chapters(request, book_id: uuid.UUID, chapter_ids: list[int]) -> None:
            calls.append(chapter_ids)

        uid = uuid.uuid4()
        request = factory.delete(
            "/",
            data=json.dumps({"data": [{"id": 1, "type": "chapters"}]}),
            content_type="application/vnd.api+json",
        )
        response = remove_book_chapters(request, book_id=uid)

        assert response.status_code == 204
        assert calls == [[1]]

    def test_openapi_spec_includes_plural_links(self):
        api = DjsonApi()

        class Chapter(Resource):
            _type: ClassVar = "chapters"
            id: int
            title: str

        class Book(Resource):
            _type: ClassVar = "books"
            _attributes: ClassVar = ["title"]
            _plural_relationships: ClassVar = [("chapters", "chapters")]
            id: int
            title: str
            chapters: list[int] = field(default_factory=list)

        @api.get_one("books")
        def get_book(request, book_id: int) -> Book:
            return Book(id=1, title="B")

        @api.get_many("books")
        def list_books(request) -> list[Book]:
            return []

        @api.create_one("books")
        def create_book(request, payload: Book) -> Book:
            return Book(id=1, title="B")

        @api.edit_one("books")
        def edit_book(request, book_id: int, payload: Book) -> Book:
            return Book(id=1, title="B")

        @api.get_relationship("books", "chapters")
        def get_book_chapters(request, book_id: int) -> list[Chapter]:
            return []

        @api.reset_relationship("books", "chapters")
        def reset_book_chapters(request, book_id: int, chapter_ids: list[int]) -> None:
            pass

        spec = api._build_openapi_spec()
        book_schema = spec["components"]["schemas"]["books_resource"]
        categories_rel = book_schema["properties"]["relationships"]["properties"]["chapters"]

        assert "links" in categories_rel["properties"]
        links = categories_rel["properties"]["links"]["properties"]
        assert "related" in links
        assert "self" in links

    def test_openapi_spec_plural_links_only_related(self):
        """Only related link when no management endpoint."""
        api = DjsonApi()

        class Chapter(Resource):
            _type: ClassVar = "chapters"
            id: int
            title: str

        class Book(Resource):
            _type: ClassVar = "books"
            _attributes: ClassVar = ["title"]
            _plural_relationships: ClassVar = [("chapters", "chapters")]
            id: int
            title: str
            chapters: list[int] = field(default_factory=list)

        @api.get_one("books")
        def get_book(request, book_id: int) -> Book:
            return Book(id=1, title="B")

        @api.get_relationship("books", "chapters")
        def get_book_chapters(request, book_id: int) -> list[Chapter]:
            return []

        spec = api._build_openapi_spec()
        book_schema = spec["components"]["schemas"]["books_resource"]
        chapters_rel = book_schema["properties"]["relationships"]["properties"]["chapters"]
        links = chapters_rel["properties"]["links"]["properties"]
        assert "related" in links
        assert "self" not in links
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
