from __future__ import annotations

import datetime
from typing import Any, ClassVar, Literal, Self, TypedDict, Unpack, cast, overload

from ._runtime.collection import Collection
from ._runtime.resource import Resource


class ArticleQuery(TypedDict, total=False):
    title__contains: str
    category: int | None


class ArticleGetQuery(TypedDict, total=False):
    pass


class ArticleEdit(TypedDict, total=False):
    title: str | None
    content: str | None
    author: User | int | None


class UserQuery(TypedDict, total=False):
    username: str


class UserGetQuery(TypedDict, total=False):
    pass


class CategoryQuery(TypedDict, total=False):
    article: int | None


class ArticleCollection(Collection["Article"]):
    def filter(self, **kwargs: Unpack[ArticleQuery]) -> Self:
        return super().filter(**kwargs)
    def sort(self, *fields: Literal['title', '-title', 'created_at', '-created_at']) -> Self:
        return super().sort(*fields)
    def fields(self, *, articles: list[Literal['id', 'title', 'content', 'created_at', 'author', 'categories']] | None = None) -> Self:
        kwargs = {}
        if articles is not None:
            kwargs['articles'] = articles
        return super().fields(**kwargs)


class UserCollection(Collection["User"]):
    def filter(self, **kwargs: Unpack[UserQuery]) -> Self:
        return super().filter(**kwargs)
    def fields(self, *, users: list[Literal['id', 'username', 'articles']] | None = None) -> Self:
        kwargs = {}
        if users is not None:
            kwargs['users'] = users
        return super().fields(**kwargs)


class CategoryCollection(Collection["Category"]):
    def filter(self, **kwargs: Unpack[CategoryQuery]) -> Self:
        return super().filter(**kwargs)
    def fields(self, *, categories: list[Literal['id', 'name', 'created_at', 'articles']] | None = None) -> Self:
        kwargs = {}
        if categories is not None:
            kwargs['categories'] = categories
        return super().fields(**kwargs)


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
        "author": frozenset({"edit"}),
        "categories": frozenset({"add", "remove", "reset"}),
    }
    _collection_class: ClassVar = ArticleCollection

    id: int
    title: str
    content: str
    created_at: datetime.datetime
    author: User
    categories: CategoryCollection

    @classmethod
    def list(cls) -> ArticleCollection:
        return cast(ArticleCollection, super().list())

    @overload
    @classmethod
    async def get(cls, id: int | str, *includes: Literal["author", "categories"]) -> Article: ...

    @overload
    @classmethod
    async def get(cls, id: int | str, *includes: str) -> Article: ...
    @classmethod
    async def get(cls, id: int | str | None = None, *includes: str, **query: Any) -> Article:
        return cast(Article, await super().get(id, *includes, **query))

    @overload
    @classmethod
    async def find(cls, *includes: Literal["author", "categories"], **query: Unpack[ArticleQuery]) -> Article: ...

    @overload
    @classmethod
    async def find(cls, *includes: str, **query: Unpack[ArticleQuery]) -> Article: ...
    @classmethod
    async def find(cls, *includes: str, **query: Unpack[ArticleQuery]) -> Article:
        return cast(Article, await super().find(*includes, **query))

    @classmethod
    async def create(cls, *, title: str, content: str, author: User | int | None = None, categories: list[Category | list[int] | None] | None = None) -> Article:
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
    async def edit(self, relationship: Literal["author"], resource: User | int) -> None: ...
    @overload
    async def edit(self, relationship: str, resource: Any) -> None: ...
    async def edit(self, relationship: str, resource: Any) -> None:
        return await super().edit(relationship, resource)

    @overload
    async def add(self, relationship: Literal["categories"], *resources: Category | int) -> None: ...
    @overload
    async def add(self, relationship: str, *resources: Any) -> None: ...
    async def add(self, relationship: str, *resources: Any) -> None:
        return await super().add(relationship, *resources)

    @overload
    async def remove(self, relationship: Literal["categories"], *resources: Category | int) -> None: ...
    @overload
    async def remove(self, relationship: str, *resources: Any) -> None: ...
    async def remove(self, relationship: str, *resources: Any) -> None:
        return await super().remove(relationship, *resources)

    @overload
    async def reset(self, relationship: Literal["categories"], *resources: Category | int) -> None: ...
    @overload
    async def reset(self, relationship: str, *resources: Any) -> None: ...
    async def reset(self, relationship: str, *resources: Any) -> None:
        return await super().reset(relationship, *resources)


class User(Resource):
    _type: ClassVar[str] = "users"
    _attribute_types: ClassVar[dict[str, Any]] = {
        "id": int,
        "username": str,
    }
    _relationship_types: ClassVar[dict[str, tuple[str, bool]]] = {
        "articles": ("articles", True),
    }
    _capabilities: ClassVar[frozenset[str]] = frozenset(
        {"get_many", "get_one"}
    )
    _collection_class: ClassVar = UserCollection

    id: int
    username: str
    articles: ArticleCollection

    @classmethod
    def list(cls) -> UserCollection:
        return cast(UserCollection, super().list())

    @overload
    @classmethod
    async def get(cls, id: int | str, *includes: Literal["articles"]) -> User: ...

    @overload
    @classmethod
    async def get(cls, id: int | str, *includes: str) -> User: ...
    @classmethod
    async def get(cls, id: int | str | None = None, *includes: str, **query: Any) -> User:
        return cast(User, await super().get(id, *includes, **query))

    @overload
    @classmethod
    async def find(cls, *includes: Literal["articles"], **query: Unpack[UserQuery]) -> User: ...

    @overload
    @classmethod
    async def find(cls, *includes: str, **query: Unpack[UserQuery]) -> User: ...
    @classmethod
    async def find(cls, *includes: str, **query: Unpack[UserQuery]) -> User:
        return cast(User, await super().find(*includes, **query))


class Category(Resource):
    _type: ClassVar[str] = "categories"
    _attribute_types: ClassVar[dict[str, Any]] = {
        "id": int,
        "name": str,
        "created_at": datetime.datetime | None,
    }
    _relationship_types: ClassVar[dict[str, tuple[str, bool]]] = {
        "articles": ("articles", True),
    }
    _capabilities: ClassVar[frozenset[str]] = frozenset(
        {"create", "delete", "get_many"}
    )
    _collection_class: ClassVar = CategoryCollection

    id: int
    name: str
    created_at: datetime.datetime | None
    articles: ArticleCollection

    @classmethod
    def list(cls) -> CategoryCollection:
        return cast(CategoryCollection, super().list())

    @overload
    @classmethod
    async def find(cls, *includes: Literal["articles"], **query: Unpack[CategoryQuery]) -> Category: ...

    @overload
    @classmethod
    async def find(cls, *includes: str, **query: Unpack[CategoryQuery]) -> Category: ...
    @classmethod
    async def find(cls, *includes: str, **query: Unpack[CategoryQuery]) -> Category:
        return cast(Category, await super().find(*includes, **query))

    @classmethod
    async def create(cls, *, name: str) -> Category:
        kwargs: dict[str, Any] = {"name": name}
        return cast(Category, await super().create(**kwargs))
