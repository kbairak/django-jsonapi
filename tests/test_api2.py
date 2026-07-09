import inspect
import json
import sys
import types
from typing import ClassVar

import django
import pytest
from django.conf import settings
from django.http import HttpRequest
from django.test import RequestFactory
from django.test.utils import override_settings

from djsonapi.exceptions import BadRequest, DjsonApiExceptionMulti, NotFound
from djsonapi.resource import Resource
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
    _edit_fields: ClassVar = ["title"]
    _singular_relationships: ClassVar = [("author", "users")]
    _plural_relationships: ClassVar = [("categories", "categories")]

    id: int
    title: str = ""
    content: str = ""


class UserResource(Resource):
    _type: ClassVar = "users"
    _attributes: ClassVar = ["username", "email"]

    id: int
    username: str = ""
    email: str = ""


class CategoryResource(Resource):
    _type: ClassVar = "categories"
    _attributes: ClassVar = ["name"]

    id: int
    name: str = ""


# ── Endpoint base class tests ─────────────────────────────────────────────


class TestEndpoint:
    def test_url_name_no_template(self):
        from djsonapi.api2 import Endpoint

        ep = Endpoint("articles", lambda r: None)
        assert ep.url == "articles"

    def test_url_name_with_template(self):
        from djsonapi.api2 import Endpoint

        class MyEp(Endpoint):
            URL_NAME_TEMPLATE = "{type_name}__coll"

        ep = MyEp("articles", lambda r: None)
        assert ep.url_name == "articles__coll"

    def test_smart_parameters_skips_request(self):
        from djsonapi.api2 import Endpoint

        def handler(request, x: int, y: str):
            ...

        ep = Endpoint("articles", handler)
        assert [p.name for p in ep.smart_parameters] == ["x", "y"]

    def test_expected_extra_only_extra_prefix(self):
        from djsonapi.api2 import Endpoint

        def handler(request, extra__page: int = 1, extra__limit: int = 10, sort: str = ""):
            ...

        ep = Endpoint("articles", handler)
        assert [p.name for p in ep.expected_extra] == ["extra__page", "extra__limit"]

    def test_return_resource_type_bare_resource(self):
        from djsonapi.api2 import Endpoint

        def handler(request) -> Article:
            ...

        ep = Endpoint("articles", handler)
        assert ep.return_resource_type is Article

    def test_return_resource_type_response_wrapped(self):
        from djsonapi.api2 import Endpoint

        def handler(request) -> Response[Article]:
            ...

        ep = Endpoint("articles", handler)
        assert ep.return_resource_type is Article

    def test_return_resource_type_response_list(self):
        from djsonapi.api2 import Endpoint

        def handler(request) -> Response[list[Article]]:
            ...

        ep = Endpoint("articles", handler)
        assert ep.return_resource_type is Article

    def test_return_resource_type_none(self):
        from djsonapi.api2 import Endpoint

        def handler(request) -> int:
            return 42

        ep = Endpoint("articles", handler)
        assert ep.return_resource_type is None

    def test_view_missing_required_param_raises(self):
        from djsonapi.api2 import Endpoint

        def handler(request, required: str):
            ...

        ep = Endpoint("articles", handler)
        with pytest.raises(DjsonApiExceptionMulti) as exc:
            ep.view(RequestFactory().get("/"))
        assert any("required" in str(e) for e in exc.value.args)

    def test_view_unknown_query_param_raises(self):
        from djsonapi.api2 import Endpoint

        ep = Endpoint("articles", lambda r: None)
        with pytest.raises(DjsonApiExceptionMulti) as exc:
            ep.view(RequestFactory().get("/?nope=1"))
        assert any("nope" in str(e) for e in exc.value.args)

    def test_view_wraps_result_in_response(self):
        from djsonapi.api2 import Endpoint

        ep = Endpoint("articles", lambda r: "hello")
        req = RequestFactory().get("/")
        result = ep.view(req)
        assert isinstance(result, Response)
        assert result.data == "hello"

    def test_postprocess_204_returns_httpresponse(self):
        from djsonapi.api2 import Endpoint

        class NoContentEp(Endpoint):
            SUCCESS_STATUS: ClassVar[int] = 204

        ep = NoContentEp("articles", lambda r: None)
        req = RequestFactory().get("/")
        resp = ep._postprocess(Response(data=None), req)
        assert resp.status_code == 204

    def test_postprocess_sets_status_on_response(self):
        from djsonapi.api2 import Endpoint

        ep = Endpoint("articles", lambda r: "ok")
        req = RequestFactory().get("/")
        result = ep._postprocess(Response(data="ok"), req)
        assert result.status == 200


# ── Concrete endpoint classes ─────────────────────────────────────────────


class TestGetOneEndpoint:
    def test_url_includes_pk(self):
        from djsonapi.api2 import GetOneEndpoint

        ep = GetOneEndpoint("articles", lambda r, article_id: None)
        assert "<str:article_id>" in ep.url

    def test_url_name(self):
        from djsonapi.api2 import GetOneEndpoint

        ep = GetOneEndpoint("articles", lambda r, aid: None)
        assert ep.url_name == "articles__item"

    def test_pk_extracted_from_url_kwargs(self):
        from djsonapi.api2 import GetOneEndpoint

        def handler(request, article_id) -> Article:
            return Article(id=article_id)

        ep = GetOneEndpoint("articles", handler)
        req = RequestFactory().get("/articles/1")
        result = ep.view(req, article_id="1")
        assert isinstance(result, dict)
        assert result["data"]["id"] == "1"

    def test_view_with_include_kwargs(self):
        from djsonapi.api2 import GetOneEndpoint

        def handler(request, article_id: int, include__author: bool = False) -> Article:
            return Article(id=article_id)

        ep = GetOneEndpoint("articles", handler, include_types=[UserResource])
        req = RequestFactory().get("/articles/1?include=author")
        result = ep.view(req, article_id="1")
        assert isinstance(result, dict)
        assert result["data"]["id"] == "1"

    def test_returns_serialized_dict_from_postprocess(self):
        from djsonapi.api2 import GetOneEndpoint

        def handler(request, article_id: int) -> Article:
            return Article(id=article_id)

        ep = GetOneEndpoint("articles", handler)
        req = RequestFactory().get("/articles/1")
        result = ep._postprocess(Response(data=Article(id=1)), req)
        assert isinstance(result, dict)
        assert "data" in result


class TestGetManyEndpoint:
    def test_url_no_id(self):
        from djsonapi.api2 import GetManyEndpoint

        ep = GetManyEndpoint("articles", lambda r: [])
        assert ep.url == "articles"

    def test_url_name(self):
        from djsonapi.api2 import GetManyEndpoint

        ep = GetManyEndpoint("articles", lambda r: [])
        assert ep.url_name == "articles__collection"

    def test_sort_param_as_string(self):
        from djsonapi.api2 import GetManyEndpoint

        def handler(request, sort: str = ""):
            ...

        ep = GetManyEndpoint("articles", handler)
        req = RequestFactory().get("/?sort=title")
        kwargs, errors = ep._get_kwargs(req, {}, req.GET.dict())
        assert kwargs.get("sort") == "title"

    def test_sort_param_with_commas_as_list(self):
        from djsonapi.api2 import GetManyEndpoint

        def handler(request, sort: list[str] = None):
            ...

        ep = GetManyEndpoint("articles", handler)
        req = RequestFactory().get("/?sort=title,author")
        kwargs, errors = ep._get_kwargs(req, {}, req.GET.dict())
        assert kwargs.get("sort") == ["title", "author"]

    def test_page_param_converted_to_int(self):
        from djsonapi.api2 import GetManyEndpoint

        def handler(request, page: int = 1):
            ...

        ep = GetManyEndpoint("articles", handler)
        req = RequestFactory().get("/?page=2")
        kwargs, errors = ep._get_kwargs(req, {}, req.GET.dict())
        assert kwargs.get("page") == 2

    def test_page_invalid_conversion_error(self):
        from djsonapi.api2 import GetManyEndpoint

        def handler(request, page: int = 1):
            ...

        ep = GetManyEndpoint("articles", handler)
        req = RequestFactory().get("/?page=abc")
        kwargs, errors = ep._get_kwargs(req, {}, req.GET.dict())
        assert errors

    def test_filter_param_passed_through(self):
        from djsonapi.api2 import GetManyEndpoint

        def handler(request, filter__title: str = ""):
            ...

        ep = GetManyEndpoint("articles", handler)
        req = RequestFactory().get("/?title=hello")
        kwargs, errors = ep._get_kwargs(req, {}, req.GET.dict())
        assert kwargs.get("filter__title") == "hello"


class TestCreateOneEndpoint:
    def test_url_no_id(self):
        from djsonapi.api2 import CreateOneEndpoint

        def handler(r, p: Article) -> Article:
            return Article(id=1)
        ep = CreateOneEndpoint("articles", handler)
        assert ep.url == "articles"

    def test_parses_body_into_payload_kwarg(self):
        from djsonapi.api2 import CreateOneEndpoint

        def handler(request, payload: Article) -> Article:
            return payload

        ep = CreateOneEndpoint("articles", handler)
        body = json.dumps({"data": {"type": "articles", "attributes": {"title": "T", "content": "C"}}})
        req = RequestFactory().post("/", body, content_type="application/vnd.api+json")
        result = ep.view(req)
        assert isinstance(result, dict)
        assert result["data"]["type"] == "articles"
        assert result["data"]["attributes"]["title"] == "T"
        assert result["data"]["attributes"]["content"] == "C"

    def test_bad_json_body_returns_error(self):
        from djsonapi.api2 import CreateOneEndpoint

        def handler(request, payload: Article):
            return payload

        ep = CreateOneEndpoint("articles", handler)
        req = RequestFactory().post("/", "not json", content_type="application/vnd.api+json")
        with pytest.raises(DjsonApiExceptionMulti) as exc:
            ep.view(req)
        assert any("JSON" in str(e) for e in exc.value.args)


class TestEditOneEndpoint:
    def test_url_includes_pid(self):
        from djsonapi.api2 import EditOneEndpoint

        def handler(r, aid: int, p: Article) -> Article:
            return Article(id=aid)

        ep = EditOneEndpoint("articles", handler)
        assert "<int:aid>" in ep.url

    def test_url_name(self):
        from djsonapi.api2 import EditOneEndpoint

        def handler(r, aid: int, p: Article) -> Article:
            return Article(id=aid)

        ep = EditOneEndpoint("articles", handler)
        assert ep.url_name == "articles__item"

    def test_extracts_pk_and_payload(self):
        from djsonapi.api2 import EditOneEndpoint

        def handler(request, article_id: int, payload: Article):
            return Article(id=article_id, title=payload.title)

        ep = EditOneEndpoint("articles", handler)
        body = json.dumps({"data": {"type": "articles", "id": 1, "attributes": {"title": "Upd"}}})
        req = RequestFactory().patch("/", body, content_type="application/vnd.api+json")
        result = ep.view(req, article_id="1")
        assert isinstance(result, dict)
        assert result["data"]["id"] == "1"
        assert result["data"]["attributes"]["title"] == "Upd"


class TestDeleteOneEndpoint:
    def test_url_includes_pid(self):
        from djsonapi.api2 import DeleteOneEndpoint

        ep = DeleteOneEndpoint("articles", lambda r, aid: None)
        assert "<str:aid>" in ep.url

    def test_returns_204_via_postprocess(self):
        from djsonapi.api2 import DeleteOneEndpoint

        ep = DeleteOneEndpoint("articles", lambda r, aid: None)
        req = RequestFactory().delete("/articles/1")
        result = ep.view(req, aid="1")
        # postprocess for 204 returns HttpResponse directly
        from django.http import HttpResponse
        assert isinstance(ep._postprocess(Response(data=None), req), HttpResponse)
        assert ep._postprocess(Response(data=None), req).status_code == 204


# ── Relationship endpoint tests ────────────────────────────────────────────


class TestGetRelationshipEndpoint:
    def test_url_includes_pk_and_relationship_name(self):
        from djsonapi.api2 import GetRelationshipEndpoint

        ep = GetRelationshipEndpoint("articles", lambda r, aid: None, relationship_name="author")
        assert "<str:aid>" in ep.url
        assert "author" in ep.url

    def test_url_name(self):
        from djsonapi.api2 import GetRelationshipEndpoint

        ep = GetRelationshipEndpoint("articles", lambda r, aid: None, relationship_name="author")
        assert ep.url_name == "articles__author__related"


class TestEditRelationshipEndpoint:
    def test_url_includes_relationship_path(self):
        from djsonapi.api2 import EditRelationshipEndpoint

        ep = EditRelationshipEndpoint("articles", lambda r, aid, author_id: None, relationship_name="author")
        assert "relationship/author" in ep.url

    def test_parses_single_relationship_id(self):
        from djsonapi.api2 import EditRelationshipEndpoint

        def handler(request, article_id: int, author_id: int):
            return author_id

        ep = EditRelationshipEndpoint("articles", handler, relationship_name="author")
        body = json.dumps({"data": {"type": "users", "id": "5"}})
        req = RequestFactory().patch("/", body, content_type="application/vnd.api+json")
        kwargs, errors = ep._get_kwargs(req, {"article_id": "1"}, req.GET.dict())
        assert not errors
        assert kwargs.get("author_id") == 5

    def test_returns_204(self):
        from djsonapi.api2 import EditRelationshipEndpoint

        ep = EditRelationshipEndpoint("articles", lambda r, aid, author_id: None, relationship_name="author")
        assert ep.SUCCESS_STATUS == 204


class TestAddToRelationshipEndpoint:
    def test_parses_plural_relationship_ids(self):
        from djsonapi.api2 import AddToRelationshipEndpoint

        def handler(request, article_id: int, category_ids: list[int]):
            return category_ids

        ep = AddToRelationshipEndpoint("articles", handler, relationship_name="categories")
        body = json.dumps({"data": [{"type": "categories", "id": "1"}, {"type": "categories", "id": "2"}]})
        req = RequestFactory().post("/", body, content_type="application/vnd.api+json")
        kwargs, errors = ep._get_kwargs(req, {"article_id": "1"}, req.GET.dict())
        assert not errors
        assert kwargs.get("category_ids") == [1, 2]


# ── DjsonApi ────────────────────────────────────────────────────────────────


class TestDjsonApiRegistry:
    def test_decorator_registers_endpoint(self):
        from djsonapi.api2 import DjsonApi

        api = DjsonApi()

        @api.get_one("articles")
        def view(request, aid: int): ...

        assert len(api.registry) == 1

    def test_get_one_creates_getoneendpoint(self):
        from djsonapi.api2 import DjsonApi, GetOneEndpoint

        api = DjsonApi()

        @api.get_one("articles")
        def view(request, aid: int): ...

        assert isinstance(api.registry[0], GetOneEndpoint)

    def test_get_many(self):
        from djsonapi.api2 import DjsonApi

        api = DjsonApi()

        @api.get_many("articles")
        def view(request): ...

        assert len(api.registry) == 1

    def test_create_one(self):
        from djsonapi.api2 import DjsonApi

        api = DjsonApi()

        @api.create_one("articles")
        def view(request, p: Article): ...

        assert len(api.registry) == 1

    def test_edit_one(self):
        from djsonapi.api2 import DjsonApi

        api = DjsonApi()

        @api.edit_one("articles")
        def view(request, aid: int, p: Article): ...

        assert len(api.registry) == 1

    def test_delete_one(self):
        from djsonapi.api2 import DjsonApi

        api = DjsonApi()

        @api.delete_one("articles")
        def view(request, aid: int): ...

        assert len(api.registry) == 1

    def test_get_relationship(self):
        from djsonapi.api2 import DjsonApi

        api = DjsonApi()

        @api.get_relationship("articles", "author")
        def view(request, aid: int): ...

        assert len(api.registry) == 1

    def test_edit_relationship(self):
        from djsonapi.api2 import DjsonApi

        api = DjsonApi()

        @api.edit_relationship("articles", "author")
        def view(request, aid: int, author_id: int): ...

        assert len(api.registry) == 1

    def test_reset_relationship(self):
        from djsonapi.api2 import DjsonApi

        api = DjsonApi()

        @api.reset_relationship("articles", "categories")
        def view(request, aid: int, category_ids: list[int]): ...

        assert len(api.registry) == 1

    def test_add_to_relationship(self):
        from djsonapi.api2 import DjsonApi

        api = DjsonApi()

        @api.add_to_relationship("articles", "categories")
        def view(request, aid: int, category_ids: list[int]): ...

        assert len(api.registry) == 1

    def test_remove_from_relationship(self):
        from djsonapi.api2 import DjsonApi

        api = DjsonApi()

        @api.remove_from_relationship("articles", "categories")
        def view(request, aid: int, category_ids: list[int]): ...

        assert len(api.registry) == 1


class TestDjsonApiUrls:
    def test_urls_includes_all_registered_endpoints(self):
        from djsonapi.api2 import DjsonApi

        api = DjsonApi()

        @api.get_one("articles")
        def get_article(request, aid: int): ...

        @api.get_many("articles")
        def list_articles(request): ...

        urls = api.urls
        assert len(urls) >= 2

    def test_urls_are_django_urlpatterns(self):
        from djsonapi.api2 import DjsonApi
        from django.urls import URLPattern

        api = DjsonApi()

        @api.get_one("articles")
        def view(request, aid: int): ...

        urls = api.urls
        assert all(isinstance(u, URLPattern) for u in urls)


class TestDjsonApiCombineViews:
    def test_405_on_wrong_method(self):
        from djsonapi.api2 import DjsonApi

        api = DjsonApi()

        @api.get_one("articles")
        def view(request, aid: int):
            return Response(data="ok")

        req = RequestFactory().post("/articles/1")
        combine = api.combine_views(api.registry)
        resp = combine(req, aid="1")
        assert resp.status_code == 405

    def test_method_dispatch_to_correct_handler(self):
        from djsonapi.api2 import DjsonApi

        api = DjsonApi()

        @api.get_one("articles")
        def get_view(request, aid: int):
            return Response(data="get")

        @api.delete_one("articles")
        def delete_view(request, aid: int):
            return None

        req = RequestFactory().delete("/articles/1")
        combine = api.combine_views(api.registry)
        resp = combine(req, aid="1")
        assert resp.status_code == 204

    def test_unhandled_exception_returns_500(self):
        from djsonapi.api2 import DjsonApi

        api = DjsonApi()

        @api.get_one("articles")
        def view(request, aid: int):
            raise ValueError("boom")

        req = RequestFactory().get("/articles/1")
        combine = api.combine_views(api.registry)
        resp = combine(req, aid="1")
        assert resp.status_code == 500

    def test_dict_result_gets_serialized(self):
        from djsonapi.api2 import DjsonApi

        api = DjsonApi()

        @api.get_one("articles")
        def view(request, aid: int):
            return Response(data=Article(id=aid))

        req = RequestFactory().get("/articles/1")
        combine = api.combine_views(api.registry)
        resp = combine(req, aid="1")
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert "data" in data

    def test_response_object_gets_serialized(self):
        from djsonapi.api2 import DjsonApi

        api = DjsonApi()

        @api.get_one("articles")
        def view(request, aid: int):
            return Response(data=Article(id=aid))

        req = RequestFactory().get("/articles/1")
        combine = api.combine_views(api.registry)
        resp = combine(req, aid="1")
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data["data"]["type"] == "articles"


# ── ReturnsDataMixin ────────────────────────────────────────────────────────


class TestReturnsDataMixin:
    def test_invalid_include_types_raises_valueerror(self):
        from djsonapi.api2 import ReturnsDataMixin

        def handler(request, article_id: int, include__nonexist: bool = False):
            ...

        with pytest.raises(ValueError, match="Invalid include"):
            ReturnsDataMixin("articles", handler, sparse=False)

    def test_invalid_sparse_types_raises_valueerror(self):
        from djsonapi.api2 import ReturnsDataMixin

        def handler(request, article_id: int, fields__unknown: list[str] | None = None):
            ...

        with pytest.raises(ValueError, match="Invalid sparse"):
            ReturnsDataMixin("articles", handler, sparse=True)

    def test_expected_includes_from_params(self):
        from djsonapi.api2 import ReturnsDataMixin

        def handler(request, article_id: int, include__author: bool = False) -> Article:
            ...

        ep = ReturnsDataMixin("articles", handler, sparse=True, include_types=[UserResource])
        assert ep.expected_includes == {"author"}
        assert ep.allowed_includes == {"author", "categories"}

    def test_expected_sparse(self):
        from djsonapi.api2 import ReturnsDataMixin

        def handler(request, article_id: int, fields__articles: list[str] | None = None) -> Article:
            ...

        ep = ReturnsDataMixin("articles", handler, sparse=True, include_types=[UserResource])
        assert ep.expected_sparse == {"articles"}
        assert "articles" in ep.allowed_sparse

    def test_allowed_sparse_from_resource(self):
        from djsonapi.api2 import ReturnsDataMixin

        def handler(request) -> Article:
            ...

        ep = ReturnsDataMixin("articles", handler, sparse=True)
        allowed = ep.allowed_sparse
        assert "articles" in allowed
        assert "title" in allowed["articles"]

    def test_allowed_includes_from_resource_relationships(self):
        from djsonapi.api2 import ReturnsDataMixin

        def handler(request) -> Article:
            ...

        ep = ReturnsDataMixin("articles", handler, sparse=True)
        assert "author" in ep.allowed_includes
        assert "categories" in ep.allowed_includes

    def test_postprocess_returns_serialized_result(self):
        from djsonapi.api2 import ReturnsDataMixin

        def handler(request) -> Article:
            ...

        ep = ReturnsDataMixin("articles", handler, sparse=False)
        req = RequestFactory().get("/articles/1")
        result = ep._postprocess(Response(data=Article(id=1)), req)
        assert isinstance(result, dict)
        assert result["data"]["type"] == "articles"