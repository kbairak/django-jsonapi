import datetime
from typing import ClassVar

from djsonapi import Resource


class ArticleResource(Resource):
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


class CategoryResource(Resource):
    _type: ClassVar = "categories"
    _attributes: ClassVar = ["name", "slug", "description", "created_at"]
    _plural_relationships: ClassVar = ["articles"]
    _create_fields: ClassVar = ["name", "slug", "description"]
    _required_create_fields: ClassVar = ["name", "slug"]
    _edit_fields: ClassVar = ["name", "slug", "description"]

    id: int
    name: str
    slug: str
    created_at: datetime.datetime | None = None
    description: str = ""
    articles: list[int] | None = None


class UserResource(Resource):
    _type: ClassVar = "users"
    _attributes: ClassVar = ["username", "email"]
    _plural_relationships: ClassVar = ["articles"]

    id: int
    username: str
    email: str
    articles: list[int] | None = None
