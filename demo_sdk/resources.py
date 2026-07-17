from __future__ import annotations

import datetime
from typing import Any, ClassVar, Literal, Self, TypedDict, Unpack, cast, overload

from ._runtime.collection import Collection
from ._runtime.resource import Resource


class ArticleQuery(TypedDict, total=False):
    filter__title__contains: str
    filter__categories: str
    sort: str
    page: int
    include__author: bool
    include__categories: bool


class ArticleGetQuery(TypedDict, total=False):
    include__author: bool
    include__categories: bool


class ArticleEdit(TypedDict, total=False):
    title: str | None
    content: str | None
    author: int | None


class UserQuery(TypedDict, total=False):
    page: int


class UserGetQuery(TypedDict, total=False):
    pass


class CategoryQuery(TypedDict, total=False):
    filter__name__icontains: str
    filter__slug: str
    sort: str
    page: int
    include__articles: bool


class CategoryGetQuery(TypedDict, total=False):
    pass


class CategoryEdit(TypedDict, total=False):
    name: str | None
    slug: str | None
    description: str | None


class ArticleCollection(Collection["Article"]):
    def filter(self, **kwargs: Unpack[ArticleQuery]) -> Self:
        return super().filter(**kwargs)


class UserCollection(Collection["User"]):
    def filter(self, **kwargs: Unpack[UserQuery]) -> Self:
        return super().filter(**kwargs)


class CategoryCollection(Collection["Category"]):
    def filter(self, **kwargs: Unpack[CategoryQuery]) -> Self:
        return super().filter(**kwargs)


class Article(Resource):
    _type: ClassVar[str] = "articles"
    _attribute_types: ClassVar[dict[str, Any]] = {
        "id": int,
        "title": str,
        "content": str,
        "created_at": datetime.datetime,
    }
    _relationship_types: ClassVar[dict[str, tuple[str, bool]]] = {
        "author": ("users", False),
        "categories": ("categories", True),
    }
    _capabilities: ClassVar[frozenset[str]] = frozenset(
        {"create", "delete", "edit", "get_many", "get_one"}
    )
    _relationship_capabilities: ClassVar[dict[str, frozenset[str]]] = {
        "author": frozenset({"fetch", "reset"}),
        "categories": frozenset({"add", "fetch", "remove", "reset"}),
    }
    _collection_class: ClassVar = ArticleCollection

    id: int
    title: str
    content: str
    created_at: datetime.datetime

    @classmethod
    def list(cls, **query: Unpack[ArticleQuery]) -> ArticleCollection:
        return cast(ArticleCollection, super().list(**query))

    @classmethod
    async def get(
        cls, id: int | str | None = None, **query: Unpack[ArticleGetQuery]
    ) -> Article:
        return cast(Article, await super().get(id, **query))

    @classmethod
    async def create(
        cls,
        *,
        title: str,
        content: str,
        author: int | None = None,
        categories: list[int] | None = None
    ) -> Article:
        kwargs: dict[str, Any] = {"title": title, "content": content}
        if author is not None:
            kwargs["author"] = author
        if categories is not None:
            kwargs["categories"] = categories
        return cast(Article, await super().create(**kwargs))

    async def save(
        self, *fields: str, force_create: bool = False, **kwargs: Unpack[ArticleEdit]
    ) -> None:
        await super().save(*fields, force_create=force_create, **kwargs)

    @overload
    async def fetch(self, relationship: Literal["author"]) -> User: ...
    @overload
    async def fetch(self, relationship: Literal["categories"]) -> CategoryCollection: ...
    @overload
    async def fetch(self, relationship: str) -> Resource | Collection: ...
    async def fetch(self, relationship: str) -> Any:
        return await super().fetch(relationship)


class User(Resource):
    _type: ClassVar[str] = "users"
    _attribute_types: ClassVar[dict[str, Any]] = {
        "id": int,
        "username": str,
        "email": str,
    }
    _relationship_types: ClassVar[dict[str, tuple[str, bool]]] = {
        "articles": ("articles", True),
    }
    _capabilities: ClassVar[frozenset[str]] = frozenset(
        {"get_many", "get_one"}
    )
    _relationship_capabilities: ClassVar[dict[str, frozenset[str]]] = {
        "articles": frozenset({"fetch"}),
    }
    _collection_class: ClassVar = UserCollection

    id: int
    username: str
    email: str

    @classmethod
    def list(cls, **query: Unpack[UserQuery]) -> UserCollection:
        return cast(UserCollection, super().list(**query))

    @classmethod
    async def get(
        cls, id: int | str | None = None, **query: Unpack[UserGetQuery]
    ) -> User:
        return cast(User, await super().get(id, **query))

    @overload
    async def fetch(self, relationship: Literal["articles"]) -> ArticleCollection: ...
    @overload
    async def fetch(self, relationship: str) -> Resource | Collection: ...
    async def fetch(self, relationship: str) -> Any:
        return await super().fetch(relationship)


class Category(Resource):
    _type: ClassVar[str] = "categories"
    _attribute_types: ClassVar[dict[str, Any]] = {
        "id": int,
        "name": str,
        "slug": str,
        "description": str,
        "created_at": datetime.datetime | None,
    }
    _relationship_types: ClassVar[dict[str, tuple[str, bool]]] = {
        "articles": ("articles", True),
    }
    _capabilities: ClassVar[frozenset[str]] = frozenset(
        {"create", "delete", "edit", "get_many", "get_one"}
    )
    _relationship_capabilities: ClassVar[dict[str, frozenset[str]]] = {
        "articles": frozenset({"add", "fetch", "remove", "reset"}),
    }
    _collection_class: ClassVar = CategoryCollection

    id: int
    name: str
    slug: str
    description: str
    created_at: datetime.datetime | None

    @classmethod
    def list(cls, **query: Unpack[CategoryQuery]) -> CategoryCollection:
        return cast(CategoryCollection, super().list(**query))

    @classmethod
    async def get(
        cls, id: int | str | None = None, **query: Unpack[CategoryGetQuery]
    ) -> Category:
        return cast(Category, await super().get(id, **query))

    @classmethod
    async def create(cls, *, name: str, slug: str, description: str | None = None) -> Category:
        kwargs: dict[str, Any] = {"name": name, "slug": slug}
        if description is not None:
            kwargs["description"] = description
        return cast(Category, await super().create(**kwargs))

    async def save(
        self, *fields: str, force_create: bool = False, **kwargs: Unpack[CategoryEdit]
    ) -> None:
        await super().save(*fields, force_create=force_create, **kwargs)

    @overload
    async def fetch(self, relationship: Literal["articles"]) -> ArticleCollection: ...
    @overload
    async def fetch(self, relationship: str) -> Resource | Collection: ...
    async def fetch(self, relationship: str) -> Any:
        return await super().fetch(relationship)
