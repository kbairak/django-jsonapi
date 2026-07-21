import datetime
from typing import ClassVar, Self

from djsonapi import Resource


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

    @classmethod
    def from_model(cls, article) -> Self:
        return cls(
            id=article.id,
            title=article.title,
            content=article.content,
            author=article.author_id,
            created_at=article.created_at,
            categories=list(article.categories.values_list("id", flat=True)),
        )


class Category(Resource):
    _type: ClassVar = "categories"
    _attributes: ClassVar = ["name", "created_at"]
    _plural_relationships: ClassVar = ["articles"]
    _create_fields: ClassVar = ["name"]
    _required_create_fields: ClassVar = ["name"]
    _edit_fields: ClassVar = ["name"]

    id: int
    name: str
    created_at: datetime.datetime | None = None
    articles: list[int] | None = None


class User(Resource):
    _type: ClassVar = "users"
    _attributes: ClassVar = ["username"]
    _plural_relationships: ClassVar = ["articles"]

    id: int
    username: str
    articles: list[int] | None = None
