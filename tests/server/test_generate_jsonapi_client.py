import datetime
import importlib
import sys
from typing import ClassVar
from unittest.mock import AsyncMock
from unittest.mock import patch as _patch

import django
import pytest
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

from djsonapi import DjsonApi, Resource
from djsonapi.generator import generate

HOST = "http://testserver"


class Article(Resource):
    _type: ClassVar = "articles"
    _attributes: ClassVar = ["title", "content", "created_at"]
    _singular_relationships: ClassVar = [("author", "users")]
    _plural_relationships: ClassVar = ["categories"]
    _create_fields: ClassVar = ["title", "content", "author", "categories"]
    _required_create_fields: ClassVar = ["title", "content"]
    _edit_fields: ClassVar = ["title", "content", "author"]

    id: int
    title: str
    content: str
    created_at: datetime.datetime
    author: int
    categories: list[int] | None = None


class User(Resource):
    _type: ClassVar = "users"
    _attributes: ClassVar = ["username", "email"]

    id: int
    username: str
    email: str


class Category(Resource):
    _type: ClassVar = "categories"
    _attributes: ClassVar = ["name"]

    id: int
    name: str


api = DjsonApi()


@api.get_one("articles", include_types=[User, Category])
async def get_article(
    request,
    article_id: int,
    include__author: bool = False,
    include__categories: bool = False,
) -> Article: ...


@api.get_many("articles")
async def list_articles(
    request,
    filter__title__contains: str = "",
    sort: str = "",
    page: int = 1,
    include__author: bool = False,
) -> list[Article]: ...


@api.create_one("articles")
def create_article(request, payload: Article) -> Article: ...


@api.edit_one("articles")
async def edit_article(request, article_id: int, payload: Article) -> Article: ...


@api.delete_one("articles")
async def delete_article(request, article_id: int) -> None: ...


@api.get_related("articles", "author")
async def get_article_author(request, article_id: int) -> User: ...


@api.get_related("articles", "categories")
async def get_article_categories(request, article_id: int) -> list[Category]: ...


@api.add_to_relationship("articles", "categories")
async def add_article_categories(request, article_id: int, category_ids: list[int]) -> None: ...


@api.get_many("categories")
async def list_categories(request) -> list[Category]: ...


@api.get_one("users")
async def get_user(request, user_id: int) -> User: ...


@api.get_many("users")
async def list_users(request, page: int = 1) -> list[User]: ...


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    output = tmp_path_factory.mktemp("generated") / "blog_sdk"
    generate(api, output)
    sys.path.insert(0, str(output.parent))
    try:
        yield importlib.import_module("blog_sdk")
    finally:
        sys.path.remove(str(output.parent))
        for name in [n for n in sys.modules if n == "blog_sdk" or n.startswith("blog_sdk.")]:
            del sys.modules[name]


@pytest.fixture(scope="module")
def resources(generated):
    return importlib.import_module("blog_sdk.resources")


def make_sdk(generated):
    return generated.SDK(host=HOST)


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


def article_payload() -> dict:
    return {
        "type": "articles",
        "id": "1",
        "attributes": {
            "title": "Hello",
            "content": "World",
            "created_at": "2025-01-15T10:00:00",
        },
        "relationships": {
            "author": {
                "data": {"type": "users", "id": "42"},
                "links": {"related": f"{HOST}/articles/1/author"},
            },
            "categories": {
                "data": [],
                "links": {"related": f"{HOST}/articles/1/categories"},
            },
        },
        "links": {"self": f"{HOST}/articles/1"},
    }


class TestGeneratedLayout:
    def test_files_exist(self, generated, tmp_path):
        pkg = sys.modules["blog_sdk"].__path__[0]
        from pathlib import Path

        pkg = Path(pkg)
        assert (pkg / "__init__.py").exists()
        assert (pkg / "resources.py").exists()
        assert (pkg / "sdk.py").exists()
        assert (pkg / "py.typed").exists()
        assert (pkg / "_runtime" / "resource.py").exists()
        assert (pkg / "_runtime" / "collection.py").exists()
        assert (pkg / "_runtime" / "sdk.py").exists()
        assert (pkg / "_runtime" / "exceptions.py").exists()

    def test_typed_dicts_emitted(self, resources):
        from typing import get_type_hints

        article_hints = get_type_hints(resources.ArticleQuery)
        assert article_hints["title__contains"] is str
        assert "page" not in article_hints
        assert "title" in get_type_hints(resources.ArticleEdit)
        assert get_type_hints(resources.UserQuery) == {}

    def test_module_singleton(self, generated):
        assert isinstance(generated.sdk, generated.SDK)


class TestGeneratedCapabilities:
    def test_capabilities_flags(self, resources):
        assert resources.Article._capabilities == frozenset(
            {"get_one", "get_many", "create", "edit", "delete"}
        )
        assert resources.User._capabilities == frozenset({"get_one", "get_many"})

    def test_no_wrapper_for_unsupported(self, resources):
        assert "create" not in resources.User.__dict__
        assert "save" not in resources.User.__dict__

    def test_relationship_capabilities(self, resources):
        assert resources.Article._relationship_capabilities == {
            "categories": frozenset({"add"}),
        }

    async def test_unsupported_ops_raise(self, generated):
        sdk = make_sdk(generated)
        with pytest.raises(AttributeError, match="'create' not supported"):
            await sdk.users.create(username="x")
        user = sdk.users(_data={"type": "users", "id": "1", "attributes": {}})
        with pytest.raises(AttributeError, match="'delete' not supported"):
            await user.delete()

    def test_sealed_registry(self, generated, resources):
        sdk = make_sdk(generated)
        assert issubclass(sdk.articles, resources.Article)
        with pytest.raises(AttributeError):
            sdk.bogus


class TestGeneratedBehavior:
    async def test_datetime_conversion(self, generated):
        sdk = make_sdk(generated)
        article = sdk.create(article_payload())
        assert article.id == 1
        assert article.created_at == datetime.datetime(2025, 1, 15, 10, 0, 0)

    async def test_list_query_translation(self, generated):
        sdk = make_sdk(generated)
        body = {"data": [], "links": {}, "meta": {}}
        async with sdk:
            with patch_session(sdk, "get", payload=body) as mock_get:
                col = sdk.articles.list()
                col = col.filter(title__contains="foo")
                col = col.page(2)
                col = col.include("author")
                await col
        _, kwargs = mock_get.call_args
        assert kwargs["params"] == {
            "filter[title][contains]": "foo",
            "page": "2",
            "include": "author",
        }

    async def test_collection_filter_chainable(self, generated):
        sdk = make_sdk(generated)
        collection = sdk.articles.list().page(1)
        filtered = collection.filter(title__contains="x")
        assert type(filtered).__name__.endswith("Collection")
        assert filtered._params["filter[title][contains]"] == "x"
        assert filtered._params["page"] == "1"

    async def test_create_wrapper_payload(self, generated):
        sdk = make_sdk(generated)
        response_payload = article_payload()
        async with sdk:
            with patch_session(sdk, "post", status=201, payload={"data": response_payload}) as m:
                article = await sdk.articles.create(
                    title="Hello",
                    content="World",
                    author=42,
                    categories=[10],
                )
        _, kwargs = m.call_args
        assert kwargs["json"] == {
            "data": {
                "type": "articles",
                "attributes": {"title": "Hello", "content": "World"},
                "relationships": {
                    "author": {"data": {"type": "users", "id": "42"}},
                    "categories": {"data": [{"type": "categories", "id": "10"}]},
                },
            }
        }
        assert article.created_at == datetime.datetime(2025, 1, 15, 10, 0, 0)

    async def test_fetch_overload_target(self, generated):
        sdk = make_sdk(generated)
        article = sdk.create(article_payload())
        user_payload = {
            "type": "users",
            "id": "42",
            "attributes": {"username": "jdoe", "email": "j@x.com"},
        }
        async with sdk:
            with patch_session(sdk, "get", payload={"data": user_payload}):
                user = await article.author
        assert isinstance(user, sdk.users)
        assert user.username == "jdoe"

    async def test_fetch_plural_returns_collection(self, generated):
        sdk = make_sdk(generated)
        payload = article_payload()
        payload["relationships"]["categories"] = {
            "links": {"related": f"{HOST}/articles/1/categories"},
        }
        article = sdk.create(payload)
        body = {
            "data": [{"type": "categories", "id": "10", "attributes": {"name": "c"}}],
            "links": {},
        }
        async with sdk:
            with patch_session(sdk, "get", payload=body):
                result = await article.categories
        assert len(result) == 1
        assert result[0].name == "c"

    async def test_relationship_add(self, generated):
        sdk = make_sdk(generated)
        article = sdk.create(article_payload())
        async with sdk:
            with patch_session(sdk, "post", status=204) as mock_post:
                await article.add("categories", 10)
        _, kwargs = mock_post.call_args
        assert kwargs["json"] == {"data": [{"type": "categories", "id": "10"}]}

    async def test_relationship_add_blocked(self, generated):
        sdk = make_sdk(generated)
        article = sdk.create(article_payload())
        with pytest.raises(AttributeError, match="'add' on relationship 'author'"):
            await article.add("author", 1)
