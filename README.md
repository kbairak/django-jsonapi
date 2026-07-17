# djsonapi — JSON:API for Django, without the headache

[JSON:API](https://jsonapi.org/) is a specification for building APIs that don't
make you want to throw your laptop out the window. `djsonapi` brings it to
Django with:

- **Server** — Declarative resources, decorator-based endpoints, JSON Schema
  validation, OpenAPI + Redoc docs, auto-generated relationship URLs
- **Client** — Generic async client (`djsonapi_client.DjsonApiSdk`) and a
  **typed SDK generator** that produces a sealed, IDE-friendly Python package
  mirroring your exact API

```python
pip install djsonapi
```

Needs Django ≥4.2, Python ≥3.13, and works with async views natively (sync
handlers get wrapped with `sync_to_async`).

---

# Server

## Quickstart

Define a resource, register some endpoints, plug the URLs into your project:

```python
# articles/resources.py
from djsonapi import DjsonApi, Resource, Response
from typing import ClassVar

api = DjsonApi()


class ArticleResource(Resource):
    _type: ClassVar = "articles"
    _attributes: ClassVar = ["title", "content", "created_at"]
    _singular_relationships: ClassVar = [("author", "users")]
    _create_fields: ClassVar = ["title", "content", "author"]
    _required_create_fields: ClassVar = ["title"]

    id: int
    title: str
    content: str
    created_at: datetime
    author: int


class UserResource(Resource):
    _type: ClassVar = "users"
    _attributes: ClassVar = ["username", "email"]
    id: int
    username: str
    email: str
```

```python
# articles/views.py
from articles.resources import api, ArticleResource, UserResource


@api.get_one("articles")
def get_article(request, article_id: int) -> ArticleResource:
    article = Article.objects.get(id=article_id)
    return ArticleResource(
        id=article.id,
        title=article.title,
        content=article.content,
        created_at=article.created_at,
        author=article.author_id,
    )


@api.get_many("articles")
def list_articles(request) -> list[ArticleResource]:
    return [
        ArticleResource(id=a.id, title=a.title, ...)
        for a in Article.objects.all()
    ]


@api.create_one("articles")
def create_article(request, payload: ArticleResource) -> ArticleResource:
    article = Article.objects.create(**payload.as_create_payload())
    return ArticleResource(id=article.id, title=article.title, ...)


@api.edit_one("articles")
def edit_article(request, article_id: int, payload: ArticleResource) -> ArticleResource:
    article = Article.objects.get(id=article_id)
    for key, value in payload.as_edit_payload().items():
        setattr(article, key, value)
    article.save()
    return ArticleResource(id=article.id, title=article.title, ...)


@api.delete_one("articles")
def delete_article(request, article_id: int) -> None:
    Article.objects.get(id=article_id).delete()
```

Wire it up:

```python
# blog/urls.py
from articles.resources import api

urlpatterns = [
    path("api/", api.urls),
]
```

Done. You now have:

| Method   | URL                  | What it does           |
| -------- | -------------------- | ---------------------- |
| `GET`    | `/api/articles`      | List articles          |
| `POST`   | `/api/articles`      | Create article         |
| `GET`    | `/api/articles/{id}` | Get one article        |
| `PATCH`  | `/api/articles/{id}` | Edit article           |
| `DELETE` | `/api/articles/{id}` | Delete article         |
| `GET`    | `/api/openapi.json`  | OpenAPI 3.0.3 spec     |
| `GET`    | `/api/docs/`         | Redoc interactive docs |

## What's happening on the wire?

### GET /api/articles

```
GET /api/articles HTTP/1.1
Accept: application/vnd.api+json
```

```json
{
  "data": [
    {
      "type": "articles",
      "id": "1",
      "attributes": {
        "title": "Why JSON:API is great",
        "content": "Let me count the ways...",
        "created_at": "2026-07-17T10:00:00Z"
      },
      "relationships": {
        "author": {
          "data": { "type": "users", "id": "42" },
          "links": {
            "self": "/api/articles/1/relationship/author",
            "related": "/api/articles/1/author"
          }
        }
      },
      "links": {
        "self": "/api/articles/1"
      }
    }
  ],
  "meta": {
    "count": 1
  }
}
```

### GET /api/articles/1

```
GET /api/articles/1 HTTP/1.1
Accept: application/vnd.api+json
```

Response is the same shape as above, but `data` is a single object (not a list).

### POST /api/articles

```
POST /api/articles HTTP/1.1
Content-Type: application/vnd.api+json
Accept: application/vnd.api+json

{
  "data": {
    "type": "articles",
    "attributes": {
      "title": "New post!"
    },
    "relationships": {
      "author": {
        "data": { "type": "users", "id": "42" }
      }
    }
  }
}
```

Response: `201 Created` with the full resource in `data`, plus `self` link.

### PATCH /api/articles/1

```
PATCH /api/articles/1 HTTP/1.1
Content-Type: application/vnd.api+json
Accept: application/vnd.api+json

{
  "data": {
    "type": "articles",
    "id": "1",
    "attributes": {
      "title": "Updated title"
    }
  }
}
```

Response: `200 OK` with the updated resource.

### DELETE /api/articles/1

```
DELETE /api/articles/1 HTTP/1.1
Accept: application/vnd.api+json
```

Response: `204 No Content`, no body.

## What did the library do for you?

- Validated `Content-Type: application/vnd.api+json` on every write request
- Validated `Accept` header allows `application/vnd.api+json`
- Validated the request body against an auto-generated **JSON Schema** before
  your handler ever saw it (wrong types? missing required fields? extra keys? →
  `400 Bad Request` with a descriptive error document)
- Serialized your resource into proper JSON:API shape (type, id, attributes,
  relationships, links)
- Added `self` links and relationship links automatically
- Returned proper JSON:API error documents for 404, 400, 405, etc.

## Relationships

The library auto-derives relationship endpoints. If you register a
`get_related_resource`, it generates the `/relationship/` URLs for you.

```python
@api.get_related_resource("articles", "author")
def get_article_author(request, article_id: int) -> UserResource:
    article = Article.objects.get(id=article_id)
    user = article.author
    return UserResource(id=user.id, username=user.username, email=user.email)
```

This gives you:

| Method | URL                                   | What it does               |
| ------ | ------------------------------------- | -------------------------- |
| `GET`  | `/api/articles/1/author`              | Get the full author object |
| `GET`  | `/api/articles/1/relationship/author` | Get just `{type, id}`      |

### Link auto-discovery

Relationship `links` in responses are populated automatically based on which
endpoints you registered. Registering `get_article_author` above is enough to
make `GET /api/articles/1` include:

```json
{
  "data": {
    "type": "articles",
    "id": "1",
    "relationships": {
      "author": {
        "data": { "type": "users", "id": "42" },
        "links": {
          "self": "/api/articles/1/relationship/author",
          "related": "/api/articles/1/author"
        }
      }
    },
    "links": { "self": "/api/articles/1" }
  }
}
```

The library walks every registered URL pattern. If a reverse match exists for
`{type}__{relationship_name}__related`, the `related` link appears. Same for
`{type}__{relationship_name}__relationship` for the `self` link. No manual
link-building needed.

You can also register mutating relationship endpoints:

```python
@api.edit_relationship("articles", "author")
def edit_article_author(request, article_id: int, author_id: int) -> None:
    article = Article.objects.get(id=article_id)
    article.author_id = author_id
    article.save()
```

```python
@api.add_to_relationship("articles", "categories")
def add_to_article_categories(request, article_id: int, category_ids: list[int]) -> None:
    article = Article.objects.get(id=article_id)
    article.categories.add(*category_ids)
```

```python
@api.remove_from_relationship("articles", "categories")
def remove_from_article_categories(request, article_id: int, category_ids: list[int]) -> None:
    article = Article.objects.get(id=article_id)
    article.categories.remove(*category_ids)
```

```python
@api.reset_relationship("articles", "categories")
def reset_article_categories(request, article_id: int, category_ids: list[int]) -> None:
    article = Article.objects.get(id=article_id)
    article.categories.set(category_ids)
```

### What's happening on the wire for relationships?

**GET /articles/1/relationship/author** (check who the author is):

```
GET /api/articles/1/relationship/author HTTP/1.1
Accept: application/vnd.api+json
```

```json
{
  "data": {
    "type": "users",
    "id": "42"
  }
}
```

**PATCH /articles/1/relationship/author** (change the author):

```
PATCH /api/articles/1/relationship/author HTTP/1.1
Content-Type: application/vnd.api+json
Accept: application/vnd.api+json

{
  "data": {
    "type": "users",
    "id": "7"
  }
}
```

Response: `204 No Content`.

**POST /articles/1/relationship/categories** (add categories):

```json
{
  "data": [
    { "type": "categories", "id": "3" },
    { "type": "categories", "id": "5" }
  ]
}
```

Response: `204 No Content`.

**DELETE /articles/1/relationship/categories** (remove categories):

Body same shape as POST. Response: `204 No Content`.

**PATCH /articles/1/relationship/categories** (replace all categories):

Body same as POST. All previous categories replaced. Response: `204 No Content`.

## Filtering, Pagination, Sorting

Your handler parameters tell the library what to parse from the query string.
Parameter names use `__` as a separator that maps to JSON:API bracket syntax.

```python
@api.get_many("articles")
def list_articles(
    request,
    filter__title__contains: str = "",
    filter__author: int | None = None,
    sort: str = "",
    page: int = 1,
    include__author: bool = False,
) -> list[ArticleResource]:
    qs = Article.objects.all()
    if filter__title__contains:
        qs = qs.filter(title__contains=filter__title__contains)
    if filter__author:
        qs = qs.filter(author_id=filter__author)
    if sort:
        qs = qs.order_by(sort)
    # ... paginate with page param
    return [ArticleResource(...) for a in qs]
```

The query string
`?filter[title][contains]=json&filter[author]=42&sort=-created_at&page=2&include=author`
maps to:

| URL param                 | Handler parameter                  |
| ------------------------- | ---------------------------------- |
| `filter[title][contains]` | `filter__title__contains = "json"` |
| `filter[author]`          | `filter__author = 42`              |
| `sort=-created_at`        | `sort = "-created_at"`             |
| `page=2`                  | `page = 2`                         |
| `include=author`          | `include__author = True`           |

The library handles type conversion (string → int, etc.), validates integers for
`page`, and rejects unknown params with a `400`.

### Sparse fields

If `sparse=True` (default), clients can request only specific fields:

```
GET /api/articles?fields[articles]=title,created_at&fields[users]=username
```

Response will omit `content` from articles and `email` from included users.

## Includes

```python
@api.get_one("articles", include_types=[UserResource])
def get_article(
    request, article_id: int, include__author: bool = False
) -> Response[ArticleResource]:
    article = Article.objects.get(id=article_id)
    included = []
    if include__author:
        included.append(
            UserResource(id=article.author.id, username=article.author.username, ...)
        )
    return Response(
        data=ArticleResource(id=article.id, title=article.title, ...),
        included=included,
    )
```

The `include__author` parameter just tells your handler what the client
requested. You must populate `Response.included` yourself. Then the response
includes a top-level `included` array:

```json
{
  "data": { "type": "articles", "id": "1", "attributes": {...}, "relationships": {...} },
  "included": [
    { "type": "users", "id": "42", "attributes": { "username": "kbairak", "email": "..." } }
  ]
}
```

## Error handling

The library returns JSON:API-compliant error documents:

```json
{
  "errors": [
    {
      "status": "400",
      "title": "Bad Request",
      "detail": "Payload must have a 'data' key"
    }
  ]
}
```

## OpenAPI + Redoc

Your API is automatically documented:

- `GET /api/openapi.json` — OpenAPI 3.0.3 spec
- `GET /api/docs/` — Redoc interactive docs

The spec includes all paths, request/response schemas (auto-generated from your
Resource classes), parameter descriptions, and tags.

---

# Client

Two flavours: a **generic async client** for one-off scripts, and a **typed
generated SDK** for production use.

## Generic client (`djsonapi_client`)

```python
from djsonapi_client import DjsonApiSdk

sdk = DjsonApiSdk(host="http://localhost:8000/api/")
async with sdk:
    article = await sdk.articles.get(1)
    print(article.title)
    await article.save(title="New title")
    await article.delete()
```

### What's happening on the wire?

**`sdk.articles.get(1)`**:

```
GET /api/articles/1 HTTP/1.1
Accept: application/vnd.api+json
```

→ Parses the JSON:API response, creates a `Resource` with attributes accessible
as `article.title`, `article.author` (relationship stubs).

**`article.save(title="New title")`**:

```
PATCH /api/articles/1 HTTP/1.1
Content-Type: application/vnd.api+json
Accept: application/vnd.api+json

{
  "data": {
    "type": "articles",
    "id": "1",
    "attributes": {
      "title": "New title"
    }
  }
}
```

→ Re-parses the response, updates local state.

**`article.delete()`**: `DELETE /api/articles/1` → `204` → sets
`article.id = None`.

### Collections

```python
async with sdk:
    # Returns a lazy Collection — no HTTP request yet
    articles = sdk.articles.list(
        filter__title__contains="json",
        page=2,
        sort="-created_at",
    )

    # Triggers: GET /api/articles?filter[title][contains]=json&page=2&sort=-created_at
    for article in await articles:
        print(article.title)
```

Collections are immutable and chainable:

```python
# Chaining creates new Collection instances without fetching
base = sdk.articles.list()
filtered = base.filter(title__contains="json")
sorted = filtered.sort("-created_at")
paged = sorted.page(2)

# Still no HTTP request until iteration
async for a in paged:
    ...
```

### Pagination iteration

```python
async with sdk:
    col = sdk.articles.list(page=1)

    if col.has_next:
        next_page = await col.get_next()  # GET with page=2

    # Or iterate ALL pages
    async for page in col.all_pages():
        for article in page:
            print(article.title)

    # Or iterate ALL items across all pages
    async for article in col.all():
        print(article.title)
```

### Relationships on the client

```python
async with sdk:
    article = await sdk.articles.get(1, include__author=True)
    # article.author is already populated from `included`

    author = await article.fetch("author")
    # GET /api/articles/1/author → returns full User resource

    categories = await article.fetch("categories")
    # GET /api/articles/1/categories → returns Collection

    await article.add("categories", 3, 5)
    # POST /api/articles/1/relationship/categories
    # Body: {"data": [{"type": "categories", "id": "3"}, {"type": "categories", "id": "5"}]}

    await article.remove("categories", 3)
    # DELETE /api/articles/1/relationship/categories
    # Body: {"data": [{"type": "categories", "id": "3"}]}

    await article.reset("categories", 5, 7)
    # PATCH /api/articles/1/relationship/categories
    # Body: {"data": [{"type": "categories", "id": "5"}, {"type": "categories", "id": "7"}]}
```

### Error handling

HTTP errors raise typed exceptions:

```python
from djsonapi_client.exceptions import NotFound, Unauthorized

try:
    article = await sdk.articles.get(999)
except NotFound:
    print("Article not found")
```

| Status | Exception             |
| ------ | --------------------- |
| 400    | `BadRequest`          |
| 401    | `Unauthorized`        |
| 403    | `Forbidden`           |
| 404    | `NotFound`            |
| 405    | `MethodNotAllowed`    |
| 409    | `Conflict`            |
| 422    | `UnprocessableEntity` |
| 429    | `TooManyRequests`     |
| 500    | `InternalServerError` |

Unknown status codes get a dynamic `Http{N}` class.

## Typed generated SDK

The real magic. Once your server is running, generate a client package that
knows every type, every operation, every query parameter:

```bash
./manage.py generate_jsonapi_client articles.views::api --output ~/articles_sdk
```

(`djsonapi` must be in `INSTALLED_APPS`. `articles.views::api` is the import
path to your `DjsonApi` instance.)

The result is a **self-contained Python package** — only dependency is
`aiohttp`. It copies `djsonapi_client` as its `_runtime/` sub-package.

### Using the generated SDK

```python
from articles_sdk import sdk

async with sdk:
    # IDE completion for everything. Every method, every filter, every field.

    # Parameter names use __ → bracket translation (same as server)
    article = await sdk.articles.get(1, include__author=True)
    article.title          # str
    article.created_at     # datetime — auto-converted from ISO string

    # Typed filters
    col = sdk.articles.list(filter__title__contains="json")
    async for a in col:
        print(a.title)

    # Typed relationships
    author = await article.fetch("author")     # → User (typed!)
    categories = await article.fetch("categories")  # → CategoryCollection

    # Only supported operations are available
    await article.save(title="New title")       # Works if PATCH is registered
    await article.delete()                       # Works if DELETE is registered
    # sdk.articles.get(...) missing? → AttributeError at import time, not 404 at runtime
```

### Capability gating

The generated SDK reflects exactly what your server supports:

- No `delete()` if you didn't register `@api.delete_one`
- No `create()` if you didn't register `@api.create_one`
- No `add()`/`remove()`/`reset()` on relationships that don't have those
  endpoints
- `sdk.unknown_type` → `AttributeError` (instead of making up URLs and
  getting 404)

This is enforced at the **class level** — capabilities are `frozenset` members
on resource classes, set during SDK generation.

### Per-relationship capabilities

```python
# If you registered:
#   @api.add_to_relationship("articles", "categories") ...
#   @api.remove_from_relationship("articles", "categories") ...
# But NOT reset_relationship:

article.add("categories", 5)       # ✓ Works
article.remove("categories", 5)    # ✓ Works
article.reset("categories", [5])   # ✗ AttributeError
```

### Type conversions

The SDK reads your resource's type annotations and generates conversion code:

| Python type | JSON:API format          | Client access                         |
| ----------- | ------------------------ | ------------------------------------- |
| `int`       | `"42"`                   | `resource.id → 42`                    |
| `datetime`  | `"2026-07-17T10:00:00Z"` | `resource.created_at → datetime(...)` |
| `date`      | `"2026-07-17"`           | `resource.published_on → date(...)`   |
| `UUID`      | `"abc-123"`              | `resource.uuid → UUID(...)`           |
| `str`       | `"hello"`                | `resource.title → "hello"`            |

Conversions are applied on response hydration and reversed on request
serialization.

---

# Installation

```bash
pip install djsonapi
```

Add to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...
    "djsonapi",
]
```

---

# Full example

Check out the `examples/` directory for a complete blog application with
articles, users, categories, and all relationship operations. The `demo_sdk/`
directory contains a pre-generated typed client for it.

```bash
cd examples
python manage.py migrate
python manage.py runserver
# Hit http://localhost:8000/api/docs/ for Redoc
```

---

# Requirements

- Python ≥3.13
- Django ≥4.2
- aiohttp ≥3.14.1 (for the client)
- jsonschema ≥4.20 (for request validation)

---

# Wait, there's more

- **JSON Schema validation** — Every request body is validated before your
  handler sees it. Schemas are generated from type annotations and
  `_create_fields`/`_edit_fields`/`_required_create_fields`.
- **Dataclass integration** — `Resource` uses `@dataclass_transform`, so
  subclasses become dataclasses automatically. No `@dataclass` decorator needed.
- **Async-first, sync-welcome** — Handlers can be `async def` or `def`. Sync
  defs are wrapped with `sync_to_async`.
- **Self-contained SDK** — The generated client copies the runtime verbatim.
  Your SDK has zero dependency on `djsonapi` itself. Just `aiohttp`.
