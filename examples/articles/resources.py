import datetime
from typing import ClassVar

from djsonapi import Resource


class ArticleResource(Resource):
    _type: ClassVar = "articles"
    _attributes: ClassVar = ["title", "content", "created_at"]
    _singular_relationships: ClassVar = [("author", "users")]
    _create_fields: ClassVar = ["title", "content", "author"]
    _required_create_fields: ClassVar = ["title", "content"]

    id: int
    title: str
    content: str
    created_at: datetime.datetime
    author: int


class UserResource(Resource):
    _type: ClassVar = "users"
    _attributes: ClassVar = ["username", "email"]

    id: int
    username: str
    email: str
