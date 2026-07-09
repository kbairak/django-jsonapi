from django.http import HttpRequest

from djsonapi.api2 import DjsonApi
from djsonapi.exceptions import NotFound
from djsonapi.response import Response

from .models import Article as ArticleModel
from .resources import Article as ArticleResource
from .resources import Category as CategoryResource
from .resources import User as UserResource

api2 = DjsonApi()


@api2.get_one("articles", errors=[NotFound])
def get_article(
    request: HttpRequest,
    article_id: int,
    include__author: bool = False,
    include__categories: bool = False,
) -> Response[ArticleResource]:
    try:
        qs = ArticleModel.objects.all()
        if include__author:
            qs = qs.select_related("author")
        if include__categories:
            qs = qs.prefetch_related("categories")
        article = qs.get(id=article_id)
    except ArticleModel.DoesNotExist:
        raise NotFound(f"ArticleModel with id '{article_id}' not found")
    included = list[ArticleResource | UserResource | CategoryResource]()
    if include__author:
        included.append(
            UserResource(
                id=article.author.pk,
                username=article.author.username,
                email=article.author.email,
            )
        )
    if include__categories:
        for category in article.categories.all():
            included.append(
                CategoryResource(
                    id=category.id,
                    name=category.name,
                    slug=category.slug,
                    created_at=category.created_at,
                    description=category.description,
                )
            )
    return Response(
        data=ArticleResource(
            id=article.id,
            title=article.title,
            content=article.content,
            created_at=article.created_at,
            author=article.author_id,
            categories=[c.id for c in article.categories.all()] if include__categories else None,
        ),
        included=included or None,
    )
