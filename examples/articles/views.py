# pyright: reportAttributeAccessIssue=false
from django.http import HttpRequest

from djsonapi import DjsonApi, Response
from djsonapi.exceptions import Conflict, NotFound

from .models import Article, Category, User
from .resources import ArticleResource, CategoryResource, UserResource

api = DjsonApi()


def _article_to_resource(article: Article) -> ArticleResource:
    return ArticleResource(
        id=article.id,
        title=article.title,
        content=article.content,
        created_at=article.created_at,
        author=article.author_id,
        categories=list(article.categories.values_list("id", flat=True)),
    )


def _category_to_resource(category: Category) -> CategoryResource:
    return CategoryResource(
        id=category.id,
        name=category.name,
        slug=category.slug,
        description=category.description,
        created_at=category.created_at,
        articles=list(category.articles.values_list("id", flat=True)),
    )


# ── Category ──────────────────────────────────────────────────────────


@api.get_one("categories", errors=[NotFound])
def get_category(request: HttpRequest, category_id: int) -> CategoryResource:
    try:
        category = Category.objects.get(id=category_id)
    except Category.DoesNotExist:
        raise NotFound(f"Category with id '{category_id}' not found")
    return _category_to_resource(category)


@api.get_many("categories")
def list_categories(
    request: HttpRequest,
    filter__name__icontains: str = "",
    filter__slug: str = "",
    sort: str = "",
    page: int = 1,
    include__articles: bool = False,
) -> Response[list[CategoryResource]]:
    qs = Category.objects.all()

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


@api.create_one("categories")
def create_category(request: HttpRequest, payload: CategoryResource) -> CategoryResource:
    category = Category.objects.create(
        name=payload.name,
        slug=payload.slug,
        description=payload.description or "",
    )
    return _category_to_resource(category)


@api.edit_one("categories", errors=[NotFound, Conflict])
def edit_category(
    request: HttpRequest, category_id: int, payload: CategoryResource
) -> CategoryResource:
    try:
        category = Category.objects.get(id=category_id)
    except Category.DoesNotExist:
        raise NotFound(f"Category with id '{category_id}' not found")
    category.name = payload.name
    category.slug = payload.slug
    category.description = payload.description or ""
    category.save()
    return _category_to_resource(category)


@api.delete_one("categories")
def delete_category(request: HttpRequest, category_id: int) -> None:
    try:
        category = Category.objects.get(id=category_id)
    except Category.DoesNotExist:
        raise NotFound(f"Category with id '{category_id}' not found")
    category.delete()


@api.get_relationship("categories", "articles")
def get_category_articles(
    request: HttpRequest, category_id: int
) -> list[ArticleResource]:
    try:
        category = Category.objects.prefetch_related("articles").get(id=category_id)
    except Category.DoesNotExist:
        raise NotFound(f"Category with id '{category_id}' not found")
    return [_article_to_resource(article) for article in category.articles.all()]


@api.reset_relationship("categories", "articles")
def reset_category_articles(
    request: HttpRequest, category_id: int, article_ids: list[int]
) -> None:
    try:
        category = Category.objects.get(id=category_id)
    except Category.DoesNotExist:
        raise NotFound(f"Category with id '{category_id}' not found")
    category.articles.set(article_ids)


@api.add_to_relationship("categories", "articles")
def add_category_articles(
    request: HttpRequest, category_id: int, article_ids: list[int]
) -> None:
    try:
        category = Category.objects.get(id=category_id)
    except Category.DoesNotExist:
        raise NotFound(f"Category with id '{category_id}' not found")
    category.articles.add(*article_ids)


@api.remove_from_relationship("categories", "articles")
def remove_category_articles(
    request: HttpRequest, category_id: int, article_ids: list[int]
) -> None:
    try:
        category = Category.objects.get(id=category_id)
    except Category.DoesNotExist:
        raise NotFound(f"Category with id '{category_id}' not found")
    category.articles.remove(*article_ids)


# ── Article ───────────────────────────────────────────────────────────


@api.get_one("articles", errors=[NotFound])
def get_article(request: HttpRequest, article_id: int) -> ArticleResource:
    try:
        article = Article.objects.get(id=article_id)
    except Article.DoesNotExist:
        raise NotFound(f"Article with id '{article_id}' not found")
    return _article_to_resource(article)


@api.get_many("articles")
def list_articles(
    request: HttpRequest,
    filter__title__contains: str = "",
    filter__categories: str = "",
    sort: str = "",
    page: int = 1,
    include__author: bool = False,
    include__categories: bool = False,
) -> Response[list[ArticleResource]]:
    qs = Article.objects.all()

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


@api.create_one("articles")
def create_article(request: HttpRequest, payload: ArticleResource) -> ArticleResource:
    article = Article.objects.create(
        title=payload.title, content=payload.content, author_id=payload.author
    )
    if payload.categories:
        article.categories.set(payload.categories)
    return _article_to_resource(article)


@api.edit_one("articles", errors=[NotFound, Conflict])
def edit_article(
    request: HttpRequest, article_id: int, payload: ArticleResource
) -> ArticleResource:
    try:
        article = Article.objects.get(id=article_id)
    except Article.DoesNotExist:
        raise NotFound(f"Article with id '{article_id}' not found")
    article.title = payload.title
    article.content = payload.content
    article.author_id = payload.author
    article.save()
    if payload.categories is not None:
        article.categories.set(payload.categories)
    return _article_to_resource(article)


@api.delete_one("articles")
def delete_article(request: HttpRequest, article_id: int) -> None:
    try:
        article = Article.objects.get(id=article_id)
    except Article.DoesNotExist:
        raise NotFound(f"Article with id '{article_id}' not found")
    article.delete()


# ── Article Relationships ────────────────────────────────────────────


@api.get_relationship("articles", "author")
def get_article_author(request: HttpRequest, article_id: int) -> UserResource:
    try:
        article = Article.objects.select_related("author").get(id=article_id)
    except Article.DoesNotExist:
        raise NotFound(f"Article with id '{article_id}' not found")
    return UserResource(
        id=article.author.pk,
        username=article.author.username,
        email=article.author.email,
    )


@api.edit_relationship("articles", "author")
def edit_article_author(request: HttpRequest, article_id: int, author_id: int) -> None:
    try:
        article = Article.objects.get(id=article_id)
    except Article.DoesNotExist:
        raise NotFound(f"Article with id '{article_id}' not found")
    article.author_id = author_id
    article.save()


@api.get_relationship("articles", "categories")
def get_article_categories(
    request: HttpRequest, article_id: int
) -> list[CategoryResource]:
    try:
        article = Article.objects.prefetch_related("categories").get(id=article_id)
    except Article.DoesNotExist:
        raise NotFound(f"Article with id '{article_id}' not found")
    return [_category_to_resource(c) for c in article.categories.all()]


@api.reset_relationship("articles", "categories")
def reset_article_categories(
    request: HttpRequest, article_id: int, category_ids: list[int]
) -> None:
    try:
        article = Article.objects.get(id=article_id)
    except Article.DoesNotExist:
        raise NotFound(f"Article with id '{article_id}' not found")
    article.categories.set(category_ids)


@api.add_to_relationship("articles", "categories")
def add_article_categories(
    request: HttpRequest, article_id: int, category_ids: list[int]
) -> None:
    try:
        article = Article.objects.get(id=article_id)
    except Article.DoesNotExist:
        raise NotFound(f"Article with id '{article_id}' not found")
    article.categories.add(*category_ids)


@api.remove_from_relationship("articles", "categories")
def remove_article_categories(
    request: HttpRequest, article_id: int, category_ids: list[int]
) -> None:
    try:
        article = Article.objects.get(id=article_id)
    except Article.DoesNotExist:
        raise NotFound(f"Article with id '{article_id}' not found")
    article.categories.remove(*category_ids)


# ── User ──────────────────────────────────────────────────────────────


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