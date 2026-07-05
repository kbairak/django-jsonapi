from django.http import HttpRequest

from djsonapi import DjsonApi, Response
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
def list_articles(
    request: HttpRequest, filter__title__contains: str = "", include__author=False
) -> Response[list[ArticleResource]]:
    qs = Article.objects.all()
    if filter__title__contains:
        qs = qs.filter(title__contains=filter__title__contains)
    if include__author:
        qs = qs.select_related("author")
    articles = list[ArticleResource]()
    users = set[UserResource]()
    for article in qs:
        articles.append(
            ArticleResource(
                id=article.id,
                title=article.title,
                content=article.content,
                created_at=article.created_at,
                author=article.author_id,
            )
        )
        if include__author:
            users.add(
                UserResource(
                    id=article.author.pk,
                    username=article.author.username,
                    email=article.author.email,
                )
            )
    return Response(
        data=articles,
        included=list(users) if include__author else None,
    )


@api.create_one("articles")
def create_article(request: HttpRequest, payload: ArticleResource) -> ArticleResource:
    article = Article.objects.create(
        title=payload.title, content=payload.content, author_id=payload.author
    )
    return ArticleResource(
        id=article.id,
        title=article.title,
        content=article.content,
        created_at=article.created_at,
        author=article.author_id,
    )


@api.edit_one("articles")
def edit_article(request: HttpRequest, article_id: int, payload: ArticleResource) -> ArticleResource:
    try:
        article = Article.objects.get(id=article_id)
    except Article.DoesNotExist:
        raise NotFound(f"Article with id '{article_id}' not found")
    article.title = payload.title
    article.content = payload.content
    article.author_id = payload.author
    article.save()
    return ArticleResource(
        id=article.id,
        title=article.title,
        content=article.content,
        created_at=article.created_at,
        author=article.author_id,
    )


@api.delete_one("articles")
def delete_article(request: HttpRequest, article_id: int) -> None:
    try:
        article = Article.objects.get(id=article_id)
    except Article.DoesNotExist:
        raise NotFound(f"Article with id '{article_id}' not found")
    article.delete()


@api.get_one("users")
def get_user(request: HttpRequest, user_id: int) -> UserResource:
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        raise NotFound(f"User with id '{user_id}' not found")
    return UserResource(id=user.pk, username=user.username, email=user.email)


@api.get_many("users")
def list_users(request: HttpRequest) -> list[UserResource]:
    users = User.objects.all()
    return [UserResource(id=user.pk, username=user.username, email=user.email) for user in users]
