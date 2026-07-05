from django.http import HttpRequest

from djsonapi import DjsonApi
from djsonapi.exceptions import NotFound

from .models import Article, User
from .resources import ArticleResource, UserResource

api = DjsonApi()


@api.get_one("articles")
def get_article(request: HttpRequest, article_id: int) -> ArticleResource:
    try:
        article = Article.objects.get(id=article_id)
    except Article.DoesNotExist:
        raise NotFound(f"Article with id '{article_id}' not found")
    return ArticleResource(
        id=article.id,
        title=article.title,
        content=article.content,
        created_at=article.created_at,
        author=article.author_id,
    )


@api.get_many("articles")
def list_articles(request: HttpRequest) -> list[ArticleResource]:
    articles = Article.objects.all()
    return [
        ArticleResource(
            id=article.id,
            title=article.title,
            content=article.content,
            created_at=article.created_at,
            author=article.author_id,
        )
        for article in articles
    ]


@api.get_one("users")
def get_user(request: HttpRequest, user_id: int) -> UserResource:
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        raise NotFound(f"User with id '{user_id}' not found")
    return UserResource(
        id=user.id,
        username=user.username,
        email=user.email,
    )


@api.get_many("users")
def list_users(request: HttpRequest) -> list[UserResource]:
    users = User.objects.all()
    return [
        UserResource(id=user.id, username=user.username, email=user.email)
        for user in users
    ]
