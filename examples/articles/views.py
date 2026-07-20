from typing import Literal

from django.db import IntegrityError
from django.http import HttpRequest

from djsonapi.api import DjsonApi
from djsonapi.exceptions import Conflict, NotFound

from .models import Article as ArticleModel
from .models import Category as CategoryModel
from .models import User as UserModel
from .resources import Article as ArticleResource
from .resources import Category as CategoryResource
from .resources import User as UserResource

api = DjsonApi()


# Articles


@api.get_many("articles")
def get_articles(
    request: HttpRequest,
    filter__title__contains: str = "",
    filter__category: int | None = None,
    sort: Literal["title", "-title", "created_at", "-created_at"] = "-created_at",
) -> list[ArticleResource]:
    qs = ArticleModel.objects.all()

    if sort == "title":
        qs = qs.order_by("title")
    elif sort == "-title":
        qs = qs.order_by("-title")
    elif sort == "created_at":
        qs = qs.order_by("created_at")
    else:
        qs = qs.order_by("-created_at")

    if filter__title__contains:
        qs = qs.filter(title__contains=filter__title__contains)
    if filter__category is not None:
        qs = qs.filter(categories__id=filter__category)

    return [ArticleResource.from_model(article) for article in qs]


@api.get_one("articles", errors=(NotFound,))
def get_article(request: HttpRequest, article_id: int) -> ArticleResource:
    try:
        article = ArticleModel.objects.get(id=article_id)
    except ArticleModel.DoesNotExist:
        raise NotFound(f"Article with id '{article_id}' not found")
    return ArticleResource.from_model(article)


@api.create_one("articles", errors=(Conflict,))
def create_article(request: HttpRequest, payload: ArticleResource) -> ArticleResource:
    try:
        article = ArticleModel.objects.create(
            title=payload.title, content=payload.content, author_id=payload.author
        )
    except IntegrityError:
        raise Conflict()
    return ArticleResource.from_model(article)


@api.edit_one("articles", errors=(NotFound, Conflict))
def edit_article(
    request: HttpRequest, article_id: int, payload: ArticleResource
) -> ArticleResource:
    try:
        article = ArticleModel.objects.get(pk=article_id)
    except ArticleModel.DoesNotExist:
        raise NotFound(f"Article with id '{article_id}' not found")
    if payload.title is not ArticleResource.UNSET and article.title != payload.title:
        article.title = payload.title
    if payload.content is not ArticleResource.UNSET and article.content != payload.content:
        article.content = payload.content
    if payload.author is not ArticleResource.UNSET and article.author_id != payload.author:
        article.author_id = payload.author
    try:
        article.save()
    except IntegrityError:
        raise Conflict()
    return ArticleResource.from_model(article)


@api.delete_one("articles", errors=(NotFound,))
def delete_article(request: HttpRequest, article_id: int) -> None:
    (count, _) = ArticleModel.objects.filter(pk=article_id).delete()
    if count == 0:
        raise NotFound()


@api.get_related("articles", "author")
def get_article_author(request: HttpRequest, article_id: int) -> UserResource:
    try:
        article = ArticleModel.objects.get(id=article_id)
    except ArticleModel.DoesNotExist:
        raise NotFound(f"Article with id '{article_id}' not found")
    return get_user(request, article.author_id)


@api.edit_relationship("articles", "author", errors=(NotFound,))
def edit_article_author(request: HttpRequest, article_id: int, new_author_id: int) -> None:
    try:
        article = ArticleModel.objects.get(id=article_id)
    except ArticleModel.DoesNotExist:
        raise NotFound(f"Article with id '{article_id}' not found")
    try:
        new_author = UserModel.objects.get(id=new_author_id)
    except UserModel.DoesNotExist:
        raise NotFound(f"User with id '{new_author_id}' not found")

    article.author = new_author
    article.save()


def _mutate_article_categories(
    op: Literal["reset", "add", "remove"], article_id: int, category_ids: list[int]
) -> None:
    try:
        article = ArticleModel.objects.get(id=article_id)
    except ArticleModel.DoesNotExist:
        raise NotFound(f"Article with id '{article_id}' not found")

    categories = CategoryModel.objects.filter(id__in=category_ids)
    if missing_category_ids := set(category_ids) - {category.id for category in categories}:
        raise NotFound(f"Categories with ids '{missing_category_ids}' not found")
    if op == "reset":
        article.categories.set(categories)
    elif op == "add":
        article.categories.add(*categories)
    elif op == "remove":
        article.categories.remove(*categories)


@api.reset_relationship("articles", "categories", errors=(NotFound,))
def reset_article_categories(
    request: HttpRequest, article_id: int, category_ids: list[int]
) -> None:
    _mutate_article_categories("reset", article_id, category_ids)


@api.add_to_relationship("articles", "categories", errors=(NotFound,))
def add_article_categories(request: HttpRequest, article_id: int, category_ids: list[int]) -> None:
    _mutate_article_categories("add", article_id, category_ids)


@api.remove_from_relationship("articles", "categories", errors=(NotFound,))
def remove_article_categories(
    request: HttpRequest, article_id: int, category_ids: list[int]
) -> None:
    _mutate_article_categories("remove", article_id, category_ids)


@api.get_related("articles", "categories")
def get_article_categories(request: HttpRequest, article_id: int) -> list[CategoryResource]:
    try:
        ArticleModel.objects.get(id=article_id)
    except ArticleModel.DoesNotExist:
        raise NotFound(f"Article with id '{article_id}' not found")
    return get_categories(request, filter__article=article_id)


# Users


@api.get_many("users")
def get_users(request: HttpRequest, filter__username: str = "") -> list[UserResource]:
    qs = UserModel.objects.all()
    if filter__username:
        qs = qs.filter(username=filter__username)
    return [UserResource(id=user.pk, username=user.username) for user in qs]


@api.get_one("users", errors=(NotFound,))
def get_user(request: HttpRequest, user_id: int) -> UserResource:
    try:
        user = UserModel.objects.get(id=user_id)
    except UserModel.DoesNotExist:
        raise NotFound(f"User with id '{user_id}' not found")
    return UserResource(id=user.pk, username=user.username)


# Categories


@api.get_many("categories")
def get_categories(
    request: HttpRequest, filter__article: int | None = None
) -> list[CategoryResource]:
    qs = CategoryModel.objects.all()
    if filter__article is not None:
        qs = qs.filter(articles__id=filter__article)
    return [
        CategoryResource(id=category.id, name=category.name, created_at=category.created_at)
        for category in qs
    ]


@api.create_one("categories", errors=(Conflict,))
def create_category(request: HttpRequest, payload: CategoryResource) -> CategoryResource:
    try:
        category = CategoryModel.objects.create(name=payload.name)
    except IntegrityError:
        raise Conflict()
    return CategoryResource(id=category.id, name=category.name, created_at=category.created_at)


@api.delete_one("categories", errors=(NotFound,))
def delete_category(request: HttpRequest, category_id: int) -> None:
    count, _ = CategoryModel.objects.filter(pk=category_id).delete()
    if count == 0:
        raise NotFound()
