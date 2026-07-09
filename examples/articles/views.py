from django.http import HttpRequest

from djsonapi.api import DjsonApi
from djsonapi.exceptions import BadRequest, Conflict, NotFound
from djsonapi.response import Response

from .models import Article as ArticleModel
from .models import Category as CategoryModel
from .models import User as UserModel
from .resources import (
    Article as ArticleResource,
)
from .resources import (
    Category as CategoryResource,
)
from .resources import (
    User as UserResource,
)

# Utils


def _article_to_resource(article: ArticleModel, include_categories=False) -> ArticleResource:
    return ArticleResource(
        id=article.id,
        title=article.title,
        content=article.content,
        created_at=article.created_at,
        author=article.author_id,
        categories=[c.id for c in article.categories.all()] if include_categories else None,
    )


def _category_to_resource(category: CategoryModel) -> CategoryResource:
    return CategoryResource(
        id=category.id,
        name=category.name,
        slug=category.slug,
        description=category.description,
        created_at=category.created_at,
        articles=[a.id for a in category.articles.all()],
    )


# API


api = DjsonApi()


# ── ArticleModel ───────────────────────────────────────────────────────────


@api.get_one(
    "articles", errors=[BadRequest, NotFound], include_types=(UserResource, CategoryResource)
)
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
            included.append(_category_to_resource(category))
    return Response(
        data=_article_to_resource(article, include_categories=True),
        included=included or None,
    )


@api.get_many("articles", errors=[BadRequest], include_types=(UserResource, CategoryResource))
def list_articles(
    request: HttpRequest,
    filter__title__contains: str = "",
    filter__categories: str = "",
    sort: str = "",
    page: int = 1,
    include__author: bool = False,
    include__categories: bool = False,
) -> Response[list[ArticleResource]]:
    qs = ArticleModel.objects.all()

    if filter__title__contains:
        qs = qs.filter(title__contains=filter__title__contains)
    if filter__categories:
        category_ids = [int(c.strip()) for c in filter__categories.split(",") if c.strip()]
        if category_ids:
            qs = qs.filter(categories__in=category_ids)
    if sort:
        fields = [f.strip() for f in sort.split(",")]
        qs = qs.order_by(*fields)
    else:
        qs = qs.order_by("id")

    if include__author:
        qs = qs.select_related("author")

    page_size = 10
    offset = (page - 1) * page_size
    qs = qs[offset : offset + page_size]
    links: dict[str, dict[str, str | int]] = {"next": {"page": page + 1}}
    if page > 1:
        links["prev"] = {"page": page - 1}

    articles = list[ArticleResource]()
    users = set[UserResource]()
    categories_set = set[CategoryResource]()

    for article in qs:
        articles.append(_article_to_resource(article))
        if include__author:
            users.add(
                UserResource(
                    id=article.author.pk,
                    username=article.author.username,
                    email=article.author.email,
                )
            )
        if include__categories:
            for category in article.categories.all():
                categories_set.add(_category_to_resource(category))

    included = list[ArticleResource | UserResource | CategoryResource]()
    if include__author:
        included.extend(users)
    if include__categories:
        included.extend(categories_set)

    return Response(
        data=articles,
        included=included or None,
        links=links,
    )


@api.create_one("articles", errors=[BadRequest])
def create_article(request: HttpRequest, payload: ArticleResource) -> ArticleResource:
    article = ArticleModel.objects.create(
        title=payload.title, content=payload.content, author_id=payload.author
    )
    if payload.categories:
        article.categories.set(payload.categories)
    return _article_to_resource(article)


@api.edit_one("articles", errors=[BadRequest, NotFound, Conflict])
def edit_article(
    request: HttpRequest, article_id: int, payload: ArticleResource
) -> ArticleResource:
    try:
        article = ArticleModel.objects.get(id=article_id)
    except ArticleModel.DoesNotExist:
        raise NotFound(f"ArticleModel with id '{article_id}' not found")
    update_fields: list[str] = []
    if hasattr(payload, "title"):
        article.title = payload.title
        update_fields.append("title")
    if hasattr(payload, "content"):
        article.content = payload.content
        update_fields.append("content")
    if hasattr(payload, "author"):
        article.author_id = payload.author
        update_fields.append("author")
    if update_fields:
        article.save(update_fields=update_fields)
    if hasattr(payload, "categories") and payload.categories is not None:
        article.categories.set(payload.categories)
    return _article_to_resource(article)


@api.delete_one("articles", errors=[NotFound])
def delete_article(request: HttpRequest, article_id: int) -> None:
    try:
        article = ArticleModel.objects.get(id=article_id)
    except ArticleModel.DoesNotExist:
        raise NotFound(f"ArticleModel with id '{article_id}' not found")
    article.delete()


# ── ArticleModel Relationships ────────────────────────────────────────────


@api.get_relationship("articles", "author", errors=[BadRequest])
def get_article_author(request: HttpRequest, article_id: int) -> UserResource:
    try:
        article = ArticleModel.objects.select_related("author").get(id=article_id)
    except ArticleModel.DoesNotExist:
        raise NotFound(f"ArticleModel with id '{article_id}' not found")
    return UserResource(
        id=article.author.pk,
        username=article.author.username,
        email=article.author.email,
    )


@api.edit_relationship("articles", "author", errors=[BadRequest])
def edit_article_author(request: HttpRequest, article_id: int, author_id: int) -> None:
    try:
        article = ArticleModel.objects.get(id=article_id)
    except ArticleModel.DoesNotExist:
        raise NotFound(f"ArticleModel with id '{article_id}' not found")
    article.author_id = author_id
    article.save()


@api.get_relationship("articles", "categories", errors=[BadRequest])
def get_article_categories(
    request: HttpRequest,
    article_id: int,
    page: int = 1,
) -> Response[list[CategoryResource]]:
    try:
        article = ArticleModel.objects.prefetch_related("categories").get(id=article_id)
    except ArticleModel.DoesNotExist:
        raise NotFound(f"ArticleModel with id '{article_id}' not found")
    qs = article.categories.all()
    page_size = 10
    offset = (page - 1) * page_size
    qs = qs[offset : offset + page_size]
    links: dict[str, dict[str, str | int]] = {"next": {"page": page + 1}}
    if page > 1:
        links["prev"] = {"page": page - 1}
    return Response(
        data=[_category_to_resource(c) for c in qs],
        links=links,
    )


@api.reset_relationship("articles", "categories", errors=[BadRequest])
def reset_article_categories(
    request: HttpRequest, article_id: int, category_ids: list[int]
) -> None:
    try:
        article = ArticleModel.objects.get(id=article_id)
    except ArticleModel.DoesNotExist:
        raise NotFound(f"ArticleModel with id '{article_id}' not found")
    article.categories.set(category_ids)


@api.add_to_relationship("articles", "categories", errors=[BadRequest])
def add_to_article_categories(
    request: HttpRequest, article_id: int, category_ids: list[int]
) -> None:
    try:
        article = ArticleModel.objects.get(id=article_id)
    except ArticleModel.DoesNotExist:
        raise NotFound(f"ArticleModel with id '{article_id}' not found")
    article.categories.add(*category_ids)


@api.remove_from_relationship("articles", "categories", errors=[BadRequest])
def remove_from_article_categories(
    request: HttpRequest, article_id: int, category_ids: list[int]
) -> None:
    try:
        article = ArticleModel.objects.get(id=article_id)
    except ArticleModel.DoesNotExist:
        raise NotFound(f"ArticleModel with id '{article_id}' not found")
    article.categories.remove(*category_ids)


# ── User ──────────────────────────────────────────────────────────────


@api.get_one("users", errors=[BadRequest])
def get_user(request: HttpRequest, user_id: int) -> UserResource:
    try:
        user = UserModel.objects.get(id=user_id)
    except UserModel.DoesNotExist:
        raise NotFound(f"UserModel with id '{user_id}' not found")
    return UserResource(id=user.pk, username=user.username, email=user.email)


@api.get_many("users", errors=[BadRequest])
def list_users(request: HttpRequest, page: int = 1) -> Response[list[UserResource]]:
    qs = UserModel.objects.all()
    page_size = 10
    offset = (page - 1) * page_size
    qs = qs[offset : offset + page_size]
    links: dict[str, dict[str, str | int]] = {"next": {"page": page + 1}}
    if page > 1:
        links["prev"] = {"page": page - 1}
    users = [UserResource(id=user.pk, username=user.username, email=user.email) for user in qs]
    return Response(data=users, links=links)


@api.get_relationship("users", "articles", errors=[BadRequest])
def get_user_articles(
    request: HttpRequest, user_id: int, page: int = 1
) -> Response[list[ArticleResource]]:
    try:
        user = UserModel.objects.prefetch_related("articles").get(id=user_id)
    except UserModel.DoesNotExist:
        raise NotFound(f"UserModel with id '{user_id}' not found")
    qs = ArticleModel.objects.filter(author_id=user_id)
    page_size = 10
    offset = (page - 1) * page_size
    qs = qs[offset : offset + page_size]
    links: dict[str, dict[str, str | int]] = {"next": {"page": page + 1}}
    if page > 1:
        links["prev"] = {"page": page - 1}
    return Response(
        data=[_article_to_resource(article) for article in qs],
        links=links,
    )


# ── CategoryModel ──────────────────────────────────────────────────────────


@api.get_one("categories", errors=[BadRequest, NotFound])
def get_category(request: HttpRequest, category_id: int) -> CategoryResource:
    try:
        category = CategoryModel.objects.get(id=category_id)
    except CategoryModel.DoesNotExist:
        raise NotFound(f"CategoryModel with id '{category_id}' not found")
    return _category_to_resource(category)


@api.get_many("categories", errors=[BadRequest])
def list_categories(
    request: HttpRequest,
    filter__name__icontains: str = "",
    filter__slug: str = "",
    sort: str = "",
    page: int = 1,
    include__articles: bool = False,
) -> Response[list[CategoryResource]]:
    qs = CategoryModel.objects.all()

    if filter__name__icontains:
        qs = qs.filter(name__icontains=filter__name__icontains)
    if filter__slug:
        qs = qs.filter(slug=filter__slug)
    if sort:
        fields = [f.strip() for f in sort.split(",")]
        qs = qs.order_by(*fields)
    else:
        qs = qs.order_by("name")

    if include__articles:
        qs = qs.prefetch_related("articles")

    page_size = 10
    offset = (page - 1) * page_size
    qs = qs[offset : offset + page_size]
    links: dict[str, dict[str, str | int]] = {"next": {"page": page + 1}}
    if page > 1:
        links["prev"] = {"page": page - 1}

    categories = list[CategoryResource]()
    articles = set[ArticleResource]()

    for category in qs:
        categories.append(_category_to_resource(category))
        if include__articles:
            for article in category.articles.all():
                articles.add(_article_to_resource(article))

    return Response(
        data=categories,
        included=list(articles) if include__articles else None,
        links=links,
    )


@api.create_one("categories", errors=[BadRequest])
def create_category(request: HttpRequest, payload: CategoryResource) -> CategoryResource:
    category = CategoryModel.objects.create(
        name=payload.name,
        slug=payload.slug,
        description=payload.description or "",
    )
    return _category_to_resource(category)


@api.edit_one("categories", errors=[BadRequest, NotFound, Conflict])
def edit_category(
    request: HttpRequest, category_id: int, payload: CategoryResource
) -> CategoryResource:
    try:
        category = CategoryModel.objects.get(id=category_id)
    except CategoryModel.DoesNotExist:
        raise NotFound(f"CategoryModel with id '{category_id}' not found")
    update_fields: list[str] = []
    if hasattr(payload, "name"):
        category.name = payload.name
        update_fields.append("name")
    if hasattr(payload, "slug"):
        category.slug = payload.slug
        update_fields.append("slug")
    if hasattr(payload, "description"):
        category.description = payload.description or ""
        update_fields.append("description")
    if update_fields:
        category.save(update_fields=update_fields)
    return _category_to_resource(category)


@api.delete_one("categories")
def delete_category(request: HttpRequest, category_id: int) -> None:
    try:
        category = CategoryModel.objects.get(id=category_id)
    except CategoryModel.DoesNotExist:
        raise NotFound(f"CategoryModel with id '{category_id}' not found")
    category.delete()


@api.get_relationship("categories", "articles", errors=[BadRequest])
def get_category_articles(
    request: HttpRequest, category_id: int, page: int = 1
) -> Response[list[ArticleResource]]:
    try:
        category = CategoryModel.objects.prefetch_related("articles").get(id=category_id)
    except CategoryModel.DoesNotExist:
        raise NotFound(f"CategoryModel with id '{category_id}' not found")
    qs = category.articles.all()
    page_size = 10
    offset = (page - 1) * page_size
    qs = qs[offset : offset + page_size]
    links: dict[str, dict[str, str | int]] = {"next": {"page": page + 1}}
    if page > 1:
        links["prev"] = {"page": page - 1}
    return Response(
        data=[_article_to_resource(article) for article in qs],
        links=links,
    )


@api.reset_relationship("categories", "articles", errors=[BadRequest])
def reset_category_articles(
    request: HttpRequest, category_id: int, article_ids: list[int]
) -> None:
    try:
        category = CategoryModel.objects.get(id=category_id)
    except CategoryModel.DoesNotExist:
        raise NotFound(f"CategoryModel with id '{category_id}' not found")
    category.articles.set(article_ids)


@api.add_to_relationship("categories", "articles", errors=[BadRequest])
def add_category_articles(request: HttpRequest, category_id: int, article_ids: list[int]) -> None:
    try:
        category = CategoryModel.objects.get(id=category_id)
    except CategoryModel.DoesNotExist:
        raise NotFound(f"CategoryModel with id '{category_id}' not found")
    category.articles.add(*article_ids)


@api.remove_from_relationship("categories", "articles", errors=[BadRequest])
def remove_category_articles(
    request: HttpRequest, category_id: int, article_ids: list[int]
) -> None:
    try:
        category = CategoryModel.objects.get(id=category_id)
    except CategoryModel.DoesNotExist:
        raise NotFound(f"CategoryModel with id '{category_id}' not found")
    category.articles.remove(*article_ids)
