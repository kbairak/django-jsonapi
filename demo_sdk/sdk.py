from __future__ import annotations

from typing import ClassVar

from ._runtime.sdk import DjsonApiSdk
from .resources import Article, Category, User


class SDK(DjsonApiSdk):
    _resource_classes: ClassVar = {
        "articles": Article,
        "users": User,
        "categories": Category,
    }

    articles: type[Article]
    users: type[User]
    categories: type[Category]


sdk = SDK()
